"""Comunicação com o celular via ADB (Android Debug Bridge)."""

from __future__ import annotations

import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_PLATFORM_TOOLS = RAIZ_PROJETO / "platform-tools"
NOME_ADB = "adb.exe" if os.name == "nt" else "adb"

URL_PLATFORM_TOOLS = {
    "win32": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
    "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
}


class ErroADB(Exception):
    """Falha ao executar um comando ADB."""


@dataclass
class Dispositivo:
    serial: str
    estado: str
    modelo: str = ""

    @property
    def pronto(self) -> bool:
        return self.estado == "device"


def localizar_adb() -> str | None:
    """Procura o adb em ADB_PATH, na pasta platform-tools do projeto e no PATH."""
    env = os.environ.get("ADB_PATH")
    if env and Path(env).is_file():
        return env
    local = PASTA_PLATFORM_TOOLS / NOME_ADB
    if local.is_file():
        return str(local)
    return shutil.which("adb")


def baixar_adb() -> str:
    """Baixa o platform-tools oficial do Google para a pasta do projeto."""
    url = URL_PLATFORM_TOOLS.get(sys.platform, URL_PLATFORM_TOOLS["linux"])
    with urllib.request.urlopen(url, timeout=180) as resposta:
        dados = resposta.read()
    with zipfile.ZipFile(io.BytesIO(dados)) as arquivo_zip:
        arquivo_zip.extractall(RAIZ_PROJETO)
    adb = PASTA_PLATFORM_TOOLS / NOME_ADB
    if os.name != "nt":
        adb.chmod(0o755)
    return str(adb)


def nome_seguro(texto: str) -> str:
    """Troca caracteres inválidos em nomes de arquivo do Windows (ex.: ':' do ADB Wi-Fi)."""
    return re.sub(r'[<>:"/\\|?*]', "_", texto) or "celular"


def parse_dispositivos(saida: str) -> list[Dispositivo]:
    dispositivos = []
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) < 2 or linha.startswith(("List of devices", "*")):
            continue
        modelo = re.search(r"model:(\S+)", linha)
        dispositivos.append(
            Dispositivo(partes[0], partes[1], modelo.group(1).replace("_", " ") if modelo else "")
        )
    return dispositivos


class ADB:
    def __init__(self, caminho: str | None = None, serial: str | None = None):
        self.caminho = caminho or localizar_adb()
        if not self.caminho:
            raise ErroADB("ADB não encontrado. Use a opção de baixar o ADB ou defina ADB_PATH.")
        self.serial = serial

    def _base(self) -> list[str]:
        comando = [self.caminho]
        if self.serial:
            comando += ["-s", self.serial]
        return comando

    def executar(self, *args: str, timeout: int = 60, checar: bool = True) -> str:
        try:
            processo = subprocess.run(
                self._base() + list(args),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as erro:
            raise ErroADB(f"Tempo esgotado: adb {' '.join(args)}") from erro
        except OSError as erro:
            raise ErroADB(f"Não foi possível executar o adb: {erro}") from erro
        if checar and processo.returncode != 0:
            raise ErroADB((processo.stderr or processo.stdout).strip() or f"adb retornou {processo.returncode}")
        return processo.stdout

    def shell(self, *args: str, timeout: int = 60) -> str:
        """Executa um comando no shell do celular (argumentos são escapados)."""
        comando = " ".join(shlex.quote(a) for a in args)
        return self.executar("shell", comando, timeout=timeout, checar=False)

    def dispositivos(self) -> list[Dispositivo]:
        return parse_dispositivos(self.executar("devices", "-l"))

    def propriedade(self, nome: str) -> str:
        return self.shell("getprop", nome).strip()

    def info_dispositivo(self) -> dict[str, str]:
        return {
            "serial": self.serial or "",
            "fabricante": self.propriedade("ro.product.manufacturer"),
            "modelo": self.propriedade("ro.product.model"),
            "android": self.propriedade("ro.build.version.release"),
            "sdk": self.propriedade("ro.build.version.sdk"),
        }
