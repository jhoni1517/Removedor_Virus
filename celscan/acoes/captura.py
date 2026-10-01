"""Print (captura) da tela do celular conectado, salvo como PNG no computador.

Para o técnico documentar um defeito, mostrar ao cliente ou mandar para alguém. Usa o
`screencap` do próprio Android pelo USB — nada é instalado no celular.

Limite honesto: apps que bloqueiam print (bancos, alguns vídeos protegidos) e a tela com senha
bloqueada podem sair pretos. Isso é proteção do próprio Android, não defeito do CelScan.
"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from celscan.core.adb import Aparelho

PNG = b"\x89PNG\r\n\x1a\n"


class CapturaErro(Exception):
    pass


def capturar(ap: Aparelho, pasta: Path) -> dict[str, Any]:
    """Tira o print e grava em <pasta>/print_AAAAMMDD_HHMMSS.png. Devolve caminho e prévia em base64."""
    png = ap.bytes("screencap -p", timeout=30)
    if not png.startswith(PNG):
        raise CapturaErro("O celular não devolveu uma imagem. Desbloqueie a tela e tente de novo.")
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now()
    arquivo = pasta / f"print_{agora:%Y%m%d_%H%M%S}.png"
    n = 1
    while arquivo.exists():  # dois prints no mesmo segundo não se sobrescrevem
        arquivo = pasta / f"print_{agora:%Y%m%d_%H%M%S}_{n}.png"
        n += 1
    arquivo.write_bytes(png)
    return {"caminho": str(arquivo), "pasta": str(pasta), "bytes": len(png),
            "png_b64": base64.b64encode(png).decode("ascii")}
