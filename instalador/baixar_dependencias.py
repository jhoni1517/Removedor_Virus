"""Baixa o que vai embutido no instalador: ADB oficial (platform-tools) e scrcpy.

Uso: python instalador/baixar_dependencias.py   (cria ./platform-tools e ./scrcpy)
"""

from __future__ import annotations

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
SISTEMA = {"win32": "windows", "darwin": "darwin"}.get(sys.platform, "linux")
PLATFORM_TOOLS = f"https://dl.google.com/android/repository/platform-tools-latest-{SISTEMA}.zip"
SCRCPY_VERSAO = "4.1"
SCRCPY = f"https://github.com/Genymobile/scrcpy/releases/download/v{SCRCPY_VERSAO}/scrcpy-win64-v{SCRCPY_VERSAO}.zip"
# Do scrcpy só vai o necessário: o adb (e suas DLLs) vem do platform-tools oficial.
SCRCPY_FORA = {"adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "open_a_terminal_here.bat", "scrcpy-noconsole.vbs"}

# Só baixamos destes hosts oficiais (evita redirecionamento para um atacante).
HOSTS_OK = {"dl.google.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
# SHA-256 fixados (integridade). O platform-tools é "latest" e muda sempre, então não dá para fixar:
# nesse caso apenas conferimos que é um zip válido e mostramos o hash obtido.
HASHES = {
    SCRCPY: "5b12172b3264b2889f4583ee64752ce832e29bc8b1089dca81093459697165db",
}


class DownloadInseguro(Exception):
    pass


def _ler_url(url: str) -> bytes:
    if urlparse(url).scheme != "https":
        raise DownloadInseguro(f"Recuso baixar sem HTTPS: {url}")
    with urllib.request.urlopen(url, timeout=300) as r:  # noqa: S310 (host conferido abaixo)
        destino = urlparse(r.geturl()).hostname or ""
        if not any(destino == h or destino.endswith("." + h) for h in HOSTS_OK):
            raise DownloadInseguro(f"Download veio de host inesperado: {destino}")
        return r.read()


def baixar(url: str) -> zipfile.ZipFile:
    print("Baixando", url)
    dados = _ler_url(url)
    obtido = hashlib.sha256(dados).hexdigest()
    esperado = HASHES.get(url)
    if esperado and obtido != esperado:
        raise DownloadInseguro(f"SHA-256 não confere para {url}\n  esperado: {esperado}\n  obtido:   {obtido}")
    if esperado:
        print("  SHA-256 confere.")
    else:
        print(f"  SHA-256 (não fixado, 'latest'): {obtido}")
    zf = zipfile.ZipFile(io.BytesIO(dados))  # valida que é um zip íntegro
    if zf.testzip() is not None:
        raise DownloadInseguro(f"Zip corrompido: {url}")
    return zf


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
