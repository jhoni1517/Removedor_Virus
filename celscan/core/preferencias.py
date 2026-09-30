"""Preferências do usuário em ~/.celscan/config.json (chave do VirusTotal, modo offline, tema)."""

from __future__ import annotations

import json
import os
from typing import Any

from celscan import config

ARQUIVO = config.DIR / "config.json"


def ler() -> dict[str, Any]:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar(**valores: Any) -> dict[str, Any]:
    atual = ler()
    atual.update({k: v for k, v in valores.items() if v is not None})
    ARQUIVO.write_text(json.dumps(atual, indent=2, ensure_ascii=False), encoding="utf-8")
    if "offline" in valores and valores["offline"] is not None:
        config.OFFLINE = bool(valores["offline"])
    return atual


def chave_virustotal() -> str | None:
    """A variável VT_API_KEY tem prioridade sobre a chave salva."""
    return os.getenv("VT_API_KEY") or ler().get("chave_virustotal") or None


def aplicar() -> None:
    """Liga o modo offline se estiver salvo nas preferências."""
    if ler().get("offline"):
        config.OFFLINE = True
