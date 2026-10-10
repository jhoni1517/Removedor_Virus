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
import uuid
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
    z = zipfile.ZipFile(io.BytesIO(r.content))
    if z.testzip() is not None:  # download cortado/corrompido: não instala um adb quebrado
        raise AdbErro("O download do Platform Tools veio corrompido. Tente de novo.")
    z.extractall(DIR)
    adb = DIR / "platform-tools" / EXE
    if os.name != "nt":
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
    try:
        versao = subprocess.run([str(adb), "version"], capture_output=True, text=True, timeout=30,
                                creationflags=SEM_JANELA).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AdbErro(f"O adb baixado não abriu: {e}") from e
    if "Android Debug Bridge" not in versao:
        raise AdbErro("O adb baixado não respondeu como esperado.")
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
    except FileNotFoundError as e:  # adb apagado/movido depois de localizado (antivírus, atualização)
        global _ADB
        _ADB = None
        raise AdbAusente("ADB não encontrado (o arquivo sumiu). Use o botão para baixar de novo.") from e
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
               espera_reinicio: float = 2.0, pausa: threading.Event | None = None) -> None:
    """Chama `callback(lista)` a cada mudança de aparelhos (adb track-devices). Bloqueia até `parar`.

    O track-devices manda quadros "<4 dígitos hex de tamanho><lista>". Se o processo cair
    (adb reiniciado, cabo, etc.), recomeça depois de `espera_reinicio` segundos. Enquanto `pausa`
    estiver ligada, não fala com o adb (ex.: modo mouse OTG do scrcpy precisa da porta USB livre).
    """
    pausa = pausa or threading.Event()
    while not parar.is_set():
        if pausa.is_set():
            parar.wait(0.5)
            continue
        try:
            p = subprocess.Popen([*_cmd(), "track-devices"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 creationflags=SEM_JANELA)
        except (OSError, AdbErro) as e:
            log.LOGGER.warning("track-devices indisponível: %s", e)
            parar.wait(espera_reinicio * 5)
            continue
        assert p.stdout is not None
        def vigiar(proc: subprocess.Popen = p) -> None:
            while not (parar.is_set() or pausa.is_set()) and proc.poll() is None:
                parar.wait(0.3)
            proc.kill()

        vigia = threading.Thread(target=vigiar, daemon=True)
        vigia.start()
        try:
            while not (parar.is_set() or pausa.is_set()):
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
        from celscan.core import adb_direto

        try:
            return adb_direto.shell(self.serial, comando, timeout, erro)
        except adb_direto.Timeout as e:
            raise AdbErro(f"'adb shell {comando[:40]}' excedeu {timeout}s") from e
        except adb_direto.Indisponivel:
            pass  # sem conexão direta: usa um processo adb (modo antigo)
        return self.adb("shell", comando, timeout=timeout, erro=erro)

    def bytes(self, comando: str, timeout: int = 60) -> bytes:
        """Saída binária sem conversão de quebra de linha (exec-out)."""
        from celscan.core import adb_direto

        try:
            return adb_direto.binario(self.serial, comando, timeout)
        except adb_direto.Timeout as e:
            raise AdbErro(f"leitura binária excedeu {timeout}s") from e
        except adb_direto.Indisponivel:
            pass
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
        # nome único: duas operações no mesmo aparelho (ex.: diagnóstico + varredura) não sobrescrevem
        # nem apagam o script uma da outra
        remoto = f"/data/local/tmp/celscan_{uuid.uuid4().hex[:10]}.sh"
        try:
            from celscan.core import adb_direto

            try:
                adb_direto.enviar(self.serial, local, remoto)
            except adb_direto.Indisponivel:
                r = run(["-s", self.serial, "push", local, remoto], timeout=60)
                if r.returncode != 0:
                    raise AdbErro(f"falha ao enviar script: {r.stderr.strip()}") from None
            try:
                saida = self.sh(f"sh {remoto}", timeout=timeout)
            finally:
                try:
                    self.sh(f"rm -f {remoto}", timeout=30)
                except AdbErro:
                    pass  # aparelho sumiu: o script fica em /data/local/tmp (o Android limpa ao reiniciar)
        finally:
            os.unlink(local)
        return secoes(saida)

    def linhas(self, comando: str, silencio: float = 180) -> Iterator[str]:
        """Executa e entrega a saída linha a linha (para barra de progresso).

        `silencio`: se o aparelho ficar esse tempo sem mandar nada (travou, cabo com mau contato), encerra
        com AdbErro em vez de deixar a varredura parada para sempre."""
        from celscan.core import adb_direto

        try:
            yield from adb_direto.linhas(self.serial, comando, silencio)
            return
        except adb_direto.Timeout as e:
            raise AdbErro(f"o aparelho parou de responder por {int(silencio)} s") from e
        except adb_direto.Indisponivel:
            pass
        inicio, n = time.perf_counter(), 0
        p = subprocess.Popen([*_cmd(), "-s", self.serial, "shell", comando],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
        assert p.stdout is not None
        ultimo = [time.monotonic()]
        parado = threading.Event()

        def vigiar() -> None:
            while p.poll() is None:
                if time.monotonic() - ultimo[0] > silencio:
                    parado.set()
                    p.kill()
                    return
                time.sleep(1)

        threading.Thread(target=vigiar, daemon=True).start()
        try:
            for linha in p.stdout:
                ultimo[0] = time.monotonic()
                n += len(linha)
                yield linha.rstrip("\r\n")
        finally:
            p.stdout.close()
            if p.poll() is None:
                p.kill()  # quem consumia parou no meio (cancelado): não deixa o processo pendurado
            p.wait()
            log.comando(["shell", comando], p.returncode, time.perf_counter() - inicio, n)
        if parado.is_set():
            raise AdbErro(f"o aparelho parou de responder por {int(silencio)} s")
