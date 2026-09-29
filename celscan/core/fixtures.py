"""Grava a saída real de cada comando adb para virar fixture de teste (dados pessoais anonimizados)."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from celscan.acoes import otimizacao
from celscan.core import coleta
from celscan.core.adb import Aparelho

# nome do arquivo -> comando. Os marcados com (F3) servem para as funcionalidades da Fase 3.
COMANDOS = {
    "props": "getprop",
    "pkgs": "pm list packages -f -i -3",
    "pkgs_sistema": "pm list packages -f -i -s",
    "desativados": "pm list packages -d",
    "acess": "settings get secure enabled_accessibility_services",
    "notif": "settings get secure enabled_notification_listeners",
    "sms": "settings get secure sms_default_application",
    "proxy": "settings get global http_proxy",
    "private_dns": "settings get global private_dns_mode; settings get global private_dns_specifier",
    "owners": "dpm list-owners 2>&1",
    "admins": "dumpsys device_policy 2>&1",
    "launcher": "cmd package query-activities --brief -a android.intent.action.MAIN "
                "-c android.intent.category.LAUNCHER 2>&1",
    "idle": "dumpsys deviceidle whitelist 2>&1",
    "pkgdump": "dumpsys package packages 2>&1",
    "bateria": "dumpsys battery 2>&1",
    "df": "df -k /data 2>&1",
    "meminfo": "head -3 /proc/meminfo",
    "uptime": "cat /proc/uptime",
    "usuarios": "pm list users 2>&1",                          # (F3) multiusuário / perfil de trabalho
    "usagestats": "dumpsys usagestats 2>&1 | head -600",       # (F3) apps esquecidos
    "netstats": "dumpsys netstats detail 2>&1 | head -600",    # (F3) consumo em segundo plano
    "batterystats": "dumpsys batterystats --charged 2>&1 | head -600",  # (F3)
    "connectivity": "dumpsys connectivity 2>&1 | head -400",   # (F3) VPN, DNS privado, proxy
    "sensores": "dumpsys sensorservice 2>&1 | head -300",      # (F3) checklist de hardware
}
# Comando por app (usa o primeiro app instalado pelo usuário).
POR_APP = {
    "appops_app": "cmd appops get {pkg} 2>&1",  # (F3) painel de sensores: últimos acessos
    "am_start_w": "am start -W -n $(cmd package resolve-activity --brief {pkg} | tail -1) 2>&1",  # (F3)
}

_PROPS_PRIVADAS = re.compile(r"serial|imei|meid|cpuid|btaddr|bt\.addr|wifimac|mac_?addr|iccid|imsi|phone_?number",
                             re.I)


def anonimizar(texto: str, serial: str) -> str:
    """Tira serial, IMEI, e-mails, MACs, SSIDs e IPs; o resto do formato fica igual."""
    if serial:
        texto = texto.replace(serial, "SERIAL0000")
    texto = re.sub(r"^(\[[^\]]*(?:" + _PROPS_PRIVADAS.pattern + r")[^\]]*\]: \[).*(\])$",
                   r"\1ANONIMIZADO\2", texto, flags=re.M | re.I)
    texto = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "email@anonimo.invalid", texto)
    texto = re.sub(r"\b\d{15}\b", "000000000000000", texto)  # IMEI
    texto = re.sub(r"\b([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", "02:00:00:00:00:00", texto)
    texto = re.sub(r'(SSID:?\s*)"[^"]*"', r'\1"REDE"', texto)
    texto = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?=[:/\s,\]]|$)", "192.0.2.1", texto, flags=re.M)  # IPs
    return texto


def gravar(ap: Aparelho, raiz: Path, progresso: Callable[[str], None] = print) -> Path:
    props = coleta.parsers.props(ap.sh("getprop"))
    partes = [re.sub(r"[^\w]+", "", props.get(k, "x")).lower() or "x"
              for k in ("ro.product.manufacturer", "ro.product.model")]
    nome = "_".join(partes) + f"_android{props.get('ro.build.version.release', 'x')}"
    pasta = raiz / nome
    pasta.mkdir(parents=True, exist_ok=True)

    def salvar(arquivo: str, conteudo: str) -> None:
        (pasta / arquivo).write_text(anonimizar(conteudo, ap.serial), encoding="utf-8")

    for arq, cmd in COMANDOS.items():
        progresso(f"{arq}: {cmd[:60]}")
        salvar(f"{arq}.txt", ap.sh(cmd, timeout=300, erro=True))
    pkgs = list(coleta.parsers.pacotes(ap.sh("pm list packages -f -3")))
    if pkgs:
        for arq, cmd in POR_APP.items():
            progresso(f"{arq}: {pkgs[0]}")
            salvar(f"{arq}.txt", ap.sh(cmd.format(pkg=pkgs[0]), timeout=120, erro=True))
    # Saídas completas dos scripts, para o fake_adb.py reproduzir este aparelho (CELSCAN_FIXTURE=<pasta>).
    progresso("coleta.txt (script completo da varredura)")
    bruto = ap.script(coleta.SCRIPT.replace("{F}", "-3"), timeout=900)
    salvar("coleta.txt", "\n".join(f"@@SEC {k}\n{v}" for k, v in bruto.items()))
    progresso("diag.txt (script completo da otimização)")
    diag = otimizacao.DIAG.replace("PASTAS", " ".join(f'"{p}"' for p in otimizacao.PASTAS))
    bruto = ap.script(diag.replace("ANIM", " ".join(otimizacao.ANIM)), timeout=300)
    salvar("diag.txt", "\n".join(f"@@SEC {k}\n{v}" for k, v in bruto.items()))
    (pasta / "LEIAME.md").write_text(
        f"Saídas reais de {props.get('ro.product.manufacturer')} {props.get('ro.product.model')}, "
        f"Android {props.get('ro.build.version.release')} (SDK {props.get('ro.build.version.sdk')}), "
        f"patch {props.get('ro.build.version.security_patch')}.\n"
        "Gravadas com `python celscan.py fixtures`. Serial, IMEI, e-mails, MACs, SSIDs e IPs anonimizados.\n"
        "A lista de apps NÃO é anonimizada: revise antes de publicar.\n", encoding="utf-8")
    return pasta
