"""Pastas usadas pelo programa (funciona instalado em Arquivos de Programas)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent


def pasta_recursos() -> Path:
    """Arquivos que vão junto com o programa (ADB embutido no instalador)."""
    return Path(getattr(sys, "_MEIPASS", RAIZ_PROJETO))


def pasta_dados() -> Path:
    """Pasta gravável do usuário: %LOCALAPPDATA%\\RemovedorVirus no Windows."""
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
    pasta = Path(base) / "RemovedorVirus" if base else Path.home() / ".removedor_virus"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def pasta_quarentena() -> Path:
    return pasta_dados() / "quarentena"


def pasta_relatorios() -> Path:
    return pasta_dados() / "relatorios"


def _arquivo_config() -> Path:
    return pasta_dados() / "config.json"


def ler_config() -> dict:
    try:
        return json.loads(_arquivo_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_config(**valores) -> None:
    config = ler_config() | valores
    _arquivo_config().write_text(json.dumps(config, indent=2), encoding="utf-8")
