"""Baixa o que vai embutido no instalador: ADB oficial (platform-tools) e scrcpy.

Uso: python instalador/baixar_dependencias.py   (cria ./platform-tools e ./scrcpy)
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SISTEMA = {"win32": "windows", "darwin": "darwin"}.get(sys.platform, "linux")
PLATFORM_TOOLS = f"https://dl.google.com/android/repository/platform-tools-latest-{SISTEMA}.zip"
SCRCPY_VERSAO = "4.1"
SCRCPY = f"https://github.com/Genymobile/scrcpy/releases/download/v{SCRCPY_VERSAO}/scrcpy-win64-v{SCRCPY_VERSAO}.zip"
# Do scrcpy só vai o necessário: o adb (e suas DLLs) vem do platform-tools oficial.
SCRCPY_FORA = {"adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "open_a_terminal_here.bat", "scrcpy-noconsole.vbs"}


def baixar(url: str) -> zipfile.ZipFile:
    print("Baixando", url)
    with urllib.request.urlopen(url, timeout=300) as r:
        return zipfile.ZipFile(io.BytesIO(r.read()))


def main() -> None:
    baixar(PLATFORM_TOOLS).extractall(RAIZ)
    if SISTEMA == "windows":
        destino = RAIZ / "scrcpy"
        destino.mkdir(exist_ok=True)
        z = baixar(SCRCPY)
        for info in z.infolist():
            nome = Path(info.filename).name
            if nome and not info.is_dir() and nome not in SCRCPY_FORA:
                (destino / nome).write_bytes(z.read(info))
    print("Pronto.")


if __name__ == "__main__":
    main()
