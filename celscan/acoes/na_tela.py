"""Qual app está na tela agora: pega no flagra o app que abriu um pop-up de anúncio.

Uso: quando a propaganda aparecer, o técnico clica em "Quem está na tela?" sem fechar o anúncio.
"""

from __future__ import annotations

import re
from typing import Any

from celscan.analise.rotulos import sdk_de
from celscan.core.adb import Aparelho

FOCO = re.compile(r"([\w.]+)/([\w.$]+)")
CONSULTAS = (
    "dumpsys activity activities 2>/dev/null | grep -E 'mResumedActivity|topResumedActivity|ResumedActivity:'",
    "dumpsys window 2>/dev/null | grep -E 'mCurrentFocus|mFocusedApp'",
)


def ler(ap: Aparelho) -> dict[str, Any] | None:
    """{'pacote', 'classe', 'anuncio'} da tela em primeiro plano, ou None se não deu para saber."""
    for cmd in CONSULTAS:
        m = FOCO.search(ap.sh(cmd) or "")
        if m:
            pkg, classe = m.group(1), m.group(2)
            if classe.startswith("."):
                classe = pkg + classe
            return {"pacote": pkg, "classe": classe, "anuncio": sdk_de(classe)}
    return None
