"""Camada de acesso ao ADB: localização, download, execução e coleta em lote."""

from __future__ import annotations

import io
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable, Iterator

from celscan.config import DIR, recursos
from celscan.core import log
from celscan.core.parsers import secoes

URL_PT = "https://dl.google.com/android/repository/platform-tools-latest-{}.zip"
SO = {"Windows": "windows", "Darwin": "darwin", "Linux": "linux"}
EXE = "adb.exe" if os.name == "nt" else "adb"
# No Windows, não abre uma janela preta de console a cada comando.
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ADB: str | None = None

__all__ = ["AdbAusente", "AdbErro", "Aparelho", "acompanhar", "binario", "conectar", "dispositivos",
           "instalar_platform_tools", "localizar", "parear", "parse_lista", "run", "secoes"]


class AdbErro(Exception):
    pass


class AdbAusente(AdbErro):
    pass


def localizar() -> str | None:
    cands = [os.getenv("CELSCAN_ADB"), shutil.which("adb"),
             recursos() / "platform-tools" / EXE, DIR / "platform-tools" / EXE]
    for c in cands:
        if c and os.path.isfile(c):
            return str(c)
    return None


def instalar_platform_tools() -> str:
    """Baixa o Android Platform Tools oficial para ~/.celscan."""
    import requests

    url = URL_PT.format(SO.get(platform.system(), "linux"))
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    zipfile.ZipFile(io.BytesIO(r.content)).extractall(DIR)
    adb = DIR / "platform-tools" / EXE
    if os.name != "nt":
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
    global _ADB
    _ADB = str(adb)
    return _ADB


def binario() -> str:
    global _ADB
    if not _ADB:
        _ADB = localizar()
    if not _ADB:
        raise AdbAusente("ADB não encontrado.")
    return _ADB


def _cmd() -> list[str]:
    """Início da linha de comando. Um .py (ADB simulado dos testes) roda pelo Python atual."""
    b = binario()
    return [sys.executable, b] if b.endswith(".py") else [b]


def run(args: list[str], timeout: int = 120, entrada: str | None = None) -> subprocess.CompletedProcess[str]:
    inicio = time.perf_counter()
    try:
        r = subprocess.run([*_cmd(), *args], capture_output=True, encoding="utf-8", errors="replace",
                           timeout=timeout, input=entrada, creationflags=SEM_JANELA)
    except subprocess.TimeoutExpired as e:
        log.comando(args, None, time.perf_counter() - inicio, 0)
        raise AdbErro(f"'adb {' '.join(map(str, args[:4]))}' excedeu {timeout}s") from e
    log.comando(args, r.returncode, time.perf_counter() - inicio, len(r.stdout or ""))
    return r


def dispositivos() -> list[tuple[str, str]]:
    run(["start-server"], timeout=30)
    return parse_lista(run(["devices"]).stdout)


ESTADOS = r"device|unauthorized|offline|recovery|sideload|bootloader|authorizing|connecting|no permissions.*"


def parse_lista(texto: str) -> list[tuple[str, str]]:
    """Linhas 'serial<TAB>estado' (saída de `adb devices` ou de um quadro do track-devices)."""
    res = []
    for linha in texto.splitlines():
        m = re.match(rf"^(\S+)\s+({ESTADOS})$", linha.strip())
        if m:
            res.append((m.group(1), m.group(2)))
    return res


def acompanhar(callback: Callable[[list[tuple[str, str]]], None], parar: threading.Event,
               espera_reinicio: float = 2.0) -> None:
    """Chama `callback(lista)` a cada mudança de aparelhos (adb track-devices). Bloqueia até `parar`.

    O track-devices manda quadros "<4 dígitos hex de tamanho><lista>". Se o processo cair
    (adb reiniciado, cabo, etc.), recomeça depois de `espera_reinicio` segundos.
    """
    while not parar.is_set():
        try:
            p = subprocess.Popen([*_cmd(), "track-devices"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 creationflags=SEM_JANELA)
        except (OSError, AdbErro) as e:
            log.LOGGER.warning("track-devices indisponível: %s", e)
            parar.wait(espera_reinicio * 5)
            continue
        assert p.stdout is not None
        vigia = threading.Thread(target=lambda proc=p: (parar.wait(), proc.kill()), daemon=True)
        vigia.start()
        try:
            while not parar.is_set():
                cabecalho = p.stdout.read(4)
                if len(cabecalho) < 4:
                    break
                try:
                    tamanho = int(cabecalho, 16)
                except ValueError:
                    break
                callback(parse_lista(p.stdout.read(tamanho).decode("utf-8", "replace")))
        finally:
            p.kill()
            p.wait()
        parar.wait(espera_reinicio)


def parear(endereco: str, codigo: str) -> str:
    return (run(["pair", endereco, codigo], timeout=60).stdout or "").strip()


def conectar(endereco: str) -> str:
    return (run(["connect", endereco], timeout=30).stdout or "").strip()


class Aparelho:
    def __init__(self, serial: str):
        self.serial = serial

    def adb(self, *args: str, timeout: int = 120, erro: bool = False) -> str:
        r = run(["-s", self.serial, *args], timeout=timeout)
        return ((r.stdout or "") + ((r.stderr or "") if erro else "")).strip()

    def sh(self, comando: str, timeout: int = 120, erro: bool = False) -> str:
        return self.adb("shell", comando, timeout=timeout, erro=erro)

    def bytes(self, comando: str, timeout: int = 60) -> bytes:
        """Saída binária sem conversão de quebra de linha (exec-out)."""
        inicio = time.perf_counter()
        try:
            r = subprocess.run([*_cmd(), "-s", self.serial, "exec-out", comando],
                               capture_output=True, timeout=timeout, creationflags=SEM_JANELA)
        except subprocess.TimeoutExpired as e:
            log.comando(["exec-out", comando], None, time.perf_counter() - inicio, 0)
            raise AdbErro(f"leitura binária excedeu {timeout}s") from e
        log.comando(["exec-out", comando], r.returncode, time.perf_counter() - inicio, len(r.stdout))
        return r.stdout

    def script(self, texto: str, timeout: int = 600) -> dict[str, str]:
        """Envia um script shell, executa numa única chamada e devolve as seções."""
        primeira = next((linha for linha in texto.splitlines() if linha.startswith("sec ")), "?")
        log.LOGGER.info("script no aparelho (%d linhas, começa com: %s)", texto.count("\n"), primeira)
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         encoding="utf-8", newline="\n") as f:
            f.write(texto)
            local = f.name
        remoto = "/data/local/tmp/celscan.sh"
        try:
            r = run(["-s", self.serial, "push", local, remoto], timeout=60)
            if r.returncode != 0:
                raise AdbErro(f"falha ao enviar script: {r.stderr.strip()}")
            saida = self.sh(f"sh {remoto}", timeout=timeout)
            self.sh(f"rm -f {remoto}")
        finally:
            os.unlink(local)
        return secoes(saida)

    def linhas(self, comando: str) -> Iterator[str]:
        """Executa e entrega a saída linha a linha (para barra de progresso)."""
        inicio, n = time.perf_counter(), 0
        p = subprocess.Popen([*_cmd(), "-s", self.serial, "shell", comando],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
        assert p.stdout is not None
        try:
            for linha in p.stdout:
                n += len(linha)
                yield linha.rstrip("\r\n")
        finally:
            p.stdout.close()
            p.wait()
            log.comando(["shell", comando], p.returncode, time.perf_counter() - inicio, n)
