"""CelScan Agente: app auxiliar Android instalado só durante a análise.

Resolve o que o adb sozinho faz mal: nome e ícone reais de TODOS os apps de uma vez e o tempo de
uso de cada app (para achar "apps esquecidos"). Fluxo:

    with Agente(ap) as ag:        # instala, libera estatísticas de uso (appops), confere a versão
        ag.apps()                 # {pacote: {nome, icone, sistema, instalado, atualizado}}
        ag.uso(dias=90)           # {pacote: {ultimo_uso, frente_min}}
                                  # ao sair: desinstala (a menos que manter=True)

Só leitura, sem internet, sem ícone, e só o shell do adb consegue consultar (ver agente/).
"""

from __future__ import annotations

import base64
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from celscan import config
from celscan.core.adb import AdbErro, Aparelho
from celscan.core.log import LOGGER

PACOTE = "com.celscan.agente"
URI = "content://com.celscan.agente.dados"
VERSAO = "1"


class AgenteIndisponivel(AdbErro):
    pass


def apk() -> Path | None:
    """O APK vem no instalador (celscan/dados/agente) ou do build local (agente/build)."""
    cands = [os.getenv("CELSCAN_AGENTE_APK"), config.DADOS / "agente" / "celscan-agente.apk",
             config.recursos() / "celscan" / "dados" / "agente" / "celscan-agente.apk",
             config.PACOTE.parent / "agente" / "build" / "celscan-agente.apk"]
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None


def disponivel() -> bool:
    return apk() is not None


def parse_linhas(saida: str) -> list[dict[str, str]]:
    """Saída do `content query`: 'Row: 0 col=valor, col2=valor' -> [{col: valor}].

    Os valores do Agente nunca têm vírgula+espaço (textos vêm em Base64), então a divisão é segura.
    """
    linhas = []
    for linha in saida.splitlines():
        m = re.match(r"^Row:\s*\d+\s+(.*)$", linha.strip())
        if not m:
            continue
        d = {}
        for parte in m.group(1).split(", "):
            k, sep, v = parte.partition("=")
            if sep:
                d[k.strip()] = "" if v == "NULL" else v
        linhas.append(d)
    return linhas


def _texto(b64: str) -> str:
    try:
        return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def _data(ms: str) -> str | None:
    try:
        v = int(ms)
        return datetime.fromtimestamp(v / 1000).isoformat(timespec="seconds") if v > 0 else None
    except (ValueError, OSError):
        return None


class Agente:
    def __init__(self, ap: Aparelho, manter: bool = False):
        self.ap, self.manter = ap, manter
        self.instalado = False

    def __enter__(self) -> Agente:
        caminho = apk()
        if not caminho:
            raise AgenteIndisponivel("O CelScan Agente não veio nesta instalação.")
        out = self.ap.adb("install", "-r", str(caminho), timeout=120, erro=True)
        if "Success" not in out:
            raise AgenteIndisponivel(f"Não consegui instalar o Agente: {out[-200:]}")
        self.instalado = True
        self.ap.sh(f"appops set {PACOTE} GET_USAGE_STATS allow")
        v = parse_linhas(self.ap.sh(f"content query --uri {URI}/versao"))
        if not v or v[0].get("versao") != VERSAO:
            self.__exit__(None, None, None)
            raise AgenteIndisponivel("O Agente não respondeu (versão inesperada).")
        LOGGER.info("Agente instalado em %s", self.ap.serial)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.instalado and not self.manter:
            try:
                self.ap.adb("uninstall", PACOTE, timeout=60)
                LOGGER.info("Agente removido de %s", self.ap.serial)
            except AdbErro:
                LOGGER.warning("Não consegui remover o Agente de %s", self.ap.serial)
            self.instalado = False

    def apps(self, icones: bool = True) -> dict[str, dict[str, Any]]:
        saida = self.ap.sh(f"content query --uri '{URI}/apps?icones={1 if icones else 0}'", timeout=180)
        res = {}
        for d in parse_linhas(saida):
            pkg = d.get("pacote")
            if not pkg or pkg == PACOTE:
                continue
            icone = d.get("icone") or ""
            if icone:
                icone = "data:image/png;base64," + icone.replace("-", "+").replace("_", "/")
            res[pkg] = {"nome": _texto(d.get("nome", "")) or pkg, "icone": icone or None,
                        "sistema": d.get("sistema") == "1", "instalado": _data(d.get("instalado", "")),
                        "atualizado": _data(d.get("atualizado", ""))}
        return res

    def uso(self, dias: int = 90) -> dict[str, dict[str, Any]]:
        saida = self.ap.sh(f"content query --uri '{URI}/uso?dias={dias}'", timeout=120)
        res = {}
        for d in parse_linhas(saida):
            if d.get("pacote"):
                res[d["pacote"]] = {"ultimo_uso": _data(d.get("ultimo_uso", "")),
                                    "frente_min": round(int(d.get("frente_ms") or 0) / 60000)}
        return res


def apps_esquecidos(ap: Aparelho, dias: int = 90) -> dict[str, Any]:
    """Apps instalados pelo usuário que não foram abertos nos últimos `dias`."""
    with Agente(ap) as ag:
        apps, uso = ag.apps(icones=True), ag.uso(dias)
    agora = datetime.now()
    lista = []
    for pkg, a in apps.items():
        if a["sistema"]:
            continue
        u = uso.get(pkg, {})
        ultimo = u.get("ultimo_uso")
        if ultimo and (agora - datetime.fromisoformat(ultimo)).days < dias:
            continue
        lista.append({"pacote": pkg, "nome": a["nome"], "icone": a["icone"], "instalado": a["instalado"],
                      "ultimo_uso": ultimo})
    lista.sort(key=lambda x: (x["ultimo_uso"] or "", x["nome"].lower()))
    return {"dias": dias, "apps": lista, "total_usuario": sum(1 for a in apps.values() if not a["sistema"])}
