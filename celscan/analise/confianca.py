""""É falso alarme": apps que o técnico marcou como confiáveis.

A marcação fica presa à ASSINATURA do app (certificado do desenvolvedor). Se um vírus se instalar com o
mesmo nome de pacote, mas outra assinatura, a marcação não vale e o alarme volta. Prova de ameaça (lista
pública, antivírus, código de trojan) também nunca é silenciada.
"""

from __future__ import annotations

import json
import time
from typing import Any

from celscan.config import DIR

ARQ = "confiaveis.json"


def _arq():
    return DIR / ARQ


def ler() -> dict[str, dict[str, Any]]:
    try:
        d = json.loads(_arq().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def marcar(pacote: str, cert_sha256: str | None, nome: str | None = None) -> dict[str, Any]:
    d = ler()
    d[pacote] = {"cert": (cert_sha256 or "").upper() or None, "nome": nome, "quando": int(time.time())}
    _arq().parent.mkdir(parents=True, exist_ok=True)
    _arq().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d[pacote]


def desmarcar(pacote: str) -> bool:
    d = ler()
    if d.pop(pacote, None) is None:
        return False
    _arq().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def confiavel(pacote: str, cert: dict | None, marcados: dict[str, dict[str, Any]] | None = None) -> bool:
    """Marcado como falso alarme E com a mesma assinatura de quando foi marcado."""
    m = (marcados if marcados is not None else ler()).get(pacote)
    if not m:
        return False
    guardado = m.get("cert")
    atual = (cert or {}).get("sha256")
    return not guardado or not atual or guardado == atual.upper()
