"""Coleta de dados brutos do Android numa única chamada ao aparelho (sem análise)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

from celscan.analise import apksig
from celscan.config import PASTAS_SISTEMA
from celscan.core import parsers
from celscan.core.adb import AdbErro, Aparelho

APPOPS_COLETADOS = ("SYSTEM_ALERT_WINDOW", "REQUEST_INSTALL_PACKAGES")

SCRIPT = r"""
sec(){ echo "@@SEC $1"; }
sec props; getprop
sec pkgs; pm list packages -f -i {F}
sec desativados; pm list packages -d
sec acess; settings get secure enabled_accessibility_services
sec notif; settings get secure enabled_notification_listeners
sec sms; settings get secure sms_default_application
sec proxy; settings get global http_proxy
sec owners; dpm list-owners 2>&1
sec admins; dumpsys device_policy 2>&1
sec launcher; cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER 2>&1
sec idle; dumpsys deviceidle whitelist 2>&1
sec su; for f in /system/bin/su /system/xbin/su /sbin/su /su/bin/su /debug_ramdisk/su; do [ -e "$f" ] && echo "$f"; done
sec pkgdump; dumpsys package packages 2>&1
sec appops
for p in $(pm list packages {F} | sed 's/^package://'); do
  echo "@@PKG $p"
  for op in OPS; do
    cmd appops get $p $op 2>/dev/null || appops get $p $op 2>/dev/null
  done
done
sec fim
""".replace("OPS", " ".join(APPOPS_COLETADOS))

HASHES = ("pm list packages -f {F} | sed 's/^package://; s/=[^=]*$//' | while read f; do "
          "printf '@@H\\t%s\\t%s\\t%s\\n' \"$(stat -c %s \"$f\" 2>/dev/null)\" "
          "\"$(sha256sum \"$f\" 2>/dev/null | cut -d' ' -f1)\" \"$f\"; done")


@dataclass
class AppBruto:
    pacote: str
    apk: str
    instalador: str | None
    sistema: bool
    perms: set[str] = field(default_factory=set)  # permissões concedidas
    versao: str | None = None
    instalado: datetime | None = None
    appops: set[str] = field(default_factory=set)  # operações liberadas
    sha256: str | None = None
    tamanho: int | None = None
    cert: dict | None = None
    vt: dict | None = None


@dataclass
class DadosAparelho:
    serial: str
    props: dict[str, str]
    apps: dict[str, AppBruto]
    desativados: set[str] = field(default_factory=set)
    acess: set[str] = field(default_factory=set)
    notif: set[str] = field(default_factory=set)
    admins: dict[str, list[str]] = field(default_factory=dict)  # pacote -> componentes
    owners: set[str] = field(default_factory=set)
    sms: str = ""
    proxy: str = ""
    su: list[str] = field(default_factory=list)
    sempre_ativo: set[str] = field(default_factory=set)
    icones: set[str] | None = None
    avisos: list[str] = field(default_factory=list)

    def info(self) -> dict[str, str]:
        g = self.props.get
        return {
            "fabricante": g("ro.product.manufacturer", "?"), "modelo": g("ro.product.model", "?"),
            "android": g("ro.build.version.release", "?"), "sdk": g("ro.build.version.sdk", "?"),
            "patch_seguranca": g("ro.build.version.security_patch", "?"), "serial": self.serial,
        }


def filtro(sistema: bool) -> str:
    return "-e" if sistema else "-3"


def montar(serial: str, s: dict[str, str]) -> DadosAparelho:
    """Transforma as seções brutas do script em DadosAparelho."""
    if "fim" not in s:
        raise AdbErro("Coleta interrompida — resultado incompleto. Reconecte o cabo e tente de novo.")
    dump = parsers.pkgdump(s.get("pkgdump", ""))
    ops = parsers.appops(s.get("appops", ""), set(APPOPS_COLETADOS))
    apps: dict[str, AppBruto] = {}
    for pkg, (caminho, inst) in parsers.pacotes(s.get("pkgs", "")).items():
        d = dump.get(pkg, {})
        apps[pkg] = AppBruto(
            pacote=pkg, apk=caminho, instalador=inst, sistema=caminho.startswith(PASTAS_SISTEMA),
            perms=d.get("perms", set()), versao=d.get("versao"), instalado=d.get("instalado"),
            appops=ops.get(pkg, set()),
        )
    if not apps:
        raise AdbErro("Nenhum app listado — o 'pm list packages' falhou.")
    dados = DadosAparelho(
        serial=serial,
        props=parsers.props(s.get("props", "")),
        apps=apps,
        desativados=parsers.desativados(s.get("desativados", "")),
        acess=parsers.componentes(s.get("acess")),
        notif=parsers.componentes(s.get("notif")),
        admins=parsers.admins(s.get("admins", "")),
        owners=parsers.owners(s.get("owners", "")),
        sms=(s.get("sms") or "").strip(),
        proxy=(s.get("proxy") or "").strip(),
        su=parsers.linhas_nao_vazias(s.get("su", "")),
        sempre_ativo=parsers.sempre_ativo(s.get("idle", "")),
        icones=parsers.launcher(s.get("launcher", "")),
    )
    if dados.icones is None:
        dados.avisos.append("Não foi possível listar ícones (Android antigo): critério ignorado.")
    if not s.get("admins"):
        dados.avisos.append("Lista de administradores vazia/indisponível.")
    return dados


def coletar(ap: Aparelho, sistema: bool = False) -> DadosAparelho:
    return montar(ap.serial, ap.script(SCRIPT.replace("{F}", filtro(sistema)), timeout=900))


def calcular_hashes(ap: Aparelho, dados: DadosAparelho, sistema: bool = False) -> Iterator[str]:
    """Gerador: devolve cada pacote conforme o hash sai do aparelho."""
    por_caminho = {a.apk: a for a in dados.apps.values()}
    for linha in ap.linhas(HASHES.replace("{F}", filtro(sistema))):
        partes = linha.split("\t")
        if len(partes) != 4 or partes[0] != "@@H":
            continue
        app = por_caminho.get(partes[3])
        if not app:
            continue
        app.tamanho = int(partes[1]) if partes[1].isdigit() else None
        app.sha256 = partes[2] if re.fullmatch(r"[0-9a-f]{64}", partes[2]) else None
        yield app.pacote


def ler_certificado(ap: Aparelho, app: AppBruto) -> None:
    if app.tamanho:
        try:
            app.cert = apksig.ler_remoto(ap, app.apk, app.tamanho)
        except Exception:
            app.cert = None
