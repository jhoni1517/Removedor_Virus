"""Instaladores .apk esquecidos no armazenamento (Download, WhatsApp...).

Um .apk de golpe guardado na pasta Download é reinstalado com um toque (pelo dono ou por outro app):
listamos, conferimos o hash com as ameaças conhecidas e apagamos com cópia na quarentena (dá para desfazer).
"""

from __future__ import annotations

import re
import shlex
import tempfile
from pathlib import Path
from typing import Any

from celscan.acoes import quarentena
from celscan.core import parsers
from celscan.core.adb import Aparelho

LISTAR = ("find /sdcard -maxdepth 5 -type f -iname '*.apk' -size -100M 2>/dev/null | head -50 | while read f; do "
          "printf '%s\\t%s\\t%s\\n' \"$(stat -c %s \"$f\" 2>/dev/null)\" "
          "\"$(sha256sum \"$f\" 2>/dev/null | cut -d' ' -f1)\" \"$f\"; done")
_SEGURO = re.compile(r"^/(sdcard|storage/emulated/0)/[^\n\r\0]+\.apk$", re.I)


def listar(ap: Aparelho, iocs: Any = None) -> list[dict[str, Any]]:
    res = parsers.apks_guardados(ap.sh(LISTAR, timeout=300))
    for f in res:
        f["nome"] = f["caminho"].rsplit("/", 1)[-1]
        f["ameaca"] = iocs.checar("", None, f["sha256"]) if (iocs and f.get("sha256")) else None
    return res


def apagar(ap: Aparelho, caminhos: list[str]) -> dict[str, Any]:
    """Apaga só caminhos que a listagem atual encontrou (nada de caminho arbitrário vindo da tela)."""
    pedidos = list(dict.fromkeys(caminhos))
    for c in pedidos:
        if not _SEGURO.match(c) or "/../" in c or "/./" in c:
            raise ValueError(f"caminho não permitido: {c}")
    existentes = {f["caminho"]: f for f in listar(ap)}
    faltam = [c for c in pedidos if c not in existentes]
    if faltam:
        raise ValueError(f"arquivo não encontrado no celular: {', '.join(faltam)}")
    pasta = quarentena._nova_pasta("apks_guardados")
    locais, caminhos_zip, hashes = [], {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        for i, c in enumerate(pedidos):
            nome = f"{i:02d}_{Path(c).name}"
            local = Path(tmp) / nome
            ap.adb("pull", c, str(local), timeout=600)
            if not local.exists() or local.stat().st_size != existentes[c].get("tamanho"):
                quarentena.descartar(pasta)
                raise OSError(f"não consegui copiar {c} inteiro; nada foi apagado")
            locais.append((str(local), nome))
            caminhos_zip[nome] = c
            hashes[nome] = quarentena._sha256(local)
        nomes = quarentena._guardar_apks(pasta, locais)
    quarentena._gravar(pasta, {
        "id": pasta.name, "pacote": "apks_guardados", "nome": "Instaladores .apk apagados", "serial": ap.serial,
        "data": quarentena.datetime.now().isoformat(timespec="seconds"), "acao": "arquivos_apagados",
        "arquivos": nomes, "protegido": True, "hashes": hashes, "copia_completa": True, "caminhos": caminhos_zip,
        "motivos": [f"Apagado: {c}" for c in pedidos], "ajustes": [],
    })
    apagados = []
    for c in pedidos:
        ap.sh(f"rm -f {shlex.quote(c)}")
        apagados.append(c)
    return {"quarentena_id": pasta.name, "apagados": apagados}
