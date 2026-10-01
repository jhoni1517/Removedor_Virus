"""Conexão direta com o servidor do adb (via adbutils), sem abrir um processo `adb` por comando.

Cada comando vira uma conexão TCP com o servidor local (127.0.0.1:5037), o mesmo que o `adb.exe`
usa por baixo. Isso evita o custo de criar processo a cada chamada (pesado no Windows) e permite
várias leituras ao mesmo tempo, inclusive em vários aparelhos.

É um caminho rápido OPCIONAL: se o adbutils faltar, o servidor não responder, ou estivermos no ADB
simulado dos testes, devolve None e o CelScan usa o modo antigo (processo por comando). Desligue com
CELSCAN_ADB_DIRETO=0.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from typing import Any

from celscan.core import log

_trava = threading.Lock()
_cliente: Any = None
_desligado_ate = 0.0  # após falha de conexão com o servidor, espera um pouco antes de tentar de novo


class Timeout(Exception):
    pass


class Indisponivel(Exception):
    """O caminho direto falhou; quem chamou deve usar o modo por processo."""


def _ligado() -> bool:
    if os.getenv("CELSCAN_ADB_DIRETO", "1") == "0":
        return False
    b = os.getenv("CELSCAN_ADB", "")
    return not b.endswith(".py") or os.getenv("CELSCAN_ADB_DIRETO") == "1"


def cliente() -> Any:
    """AdbClient conectado ao servidor local, ou None (sem quebrar)."""
    global _cliente, _desligado_ate
    if not _ligado() or time.monotonic() < _desligado_ate:
        return None
    with _trava:
        if _cliente is not None:
            return _cliente
        porta = int(os.getenv("ANDROID_ADB_SERVER_PORT", "5037"))
        # Só usa o servidor que o próprio CelScan (ou o sistema) já ligou. Nunca deixa o adbutils ligar
        # o adb embutido dele: é outra versão e derrubaria o servidor do CelScan e do scrcpy.
        try:
            import socket

            with socket.create_connection(("127.0.0.1", porta), timeout=2):
                pass
        except OSError:
            _desligado_ate = time.monotonic() + 15
            return None
        try:
            from celscan.core import adb as _adb

            nosso = _adb.binario()
            if not nosso.endswith(".py"):
                os.environ["ADBUTILS_ADB_PATH"] = nosso
        except Exception:  # noqa: BLE001
            pass
        try:
            import adbutils

            c = adbutils.AdbClient(host="127.0.0.1", port=porta, socket_timeout=10)
            c.server_version()  # confirma que o servidor responde
            _cliente = c
            log.LOGGER.info("adb direto: conectado ao servidor na porta %d", porta)
            return c
        except Exception as e:  # noqa: BLE001 — sem adbutils/servidor: usa o modo por processo
            log.LOGGER.info("adb direto indisponível (%s); usando processo por comando", e)
            _desligado_ate = time.monotonic() + 15
            return None


def esquecer(religar: bool = False) -> None:
    """Descarta o cliente (ex.: servidor do adb reiniciado). religar=True tenta de novo já."""
    global _cliente, _desligado_ate
    with _trava:
        _cliente = None
        if religar:
            _desligado_ate = 0.0


def _conexao(serial: str, comando: str, timeout: float | None) -> Any:
    c = cliente()
    if c is None:
        raise Indisponivel("sem cliente")
    try:
        d = c.device(serial)
        con = d.open_transport()
        if timeout:
            con.conn.settimeout(timeout)
        con.send_command(comando)
        con.check_okay()
        return con
    except Exception as e:  # noqa: BLE001
        esquecer()
        raise Indisponivel(str(e)) from e


def _ler_tudo(con: Any) -> bytes:
    from adbutils.errors import AdbTimeout

    try:
        return con.read_until_close(encoding=None)
    except (TimeoutError, AdbTimeout) as e:
        raise Timeout(str(e)) from e
    finally:
        con.close()


def shell(serial: str, comando: str, timeout: float = 120, erro: bool = False) -> str:
    """Como `adb shell`. Sem `erro`, descarta o stderr (igual ao modo por processo)."""
    cmd = comando if erro else f"( {comando} ) 2>/dev/null"
    inicio = time.perf_counter()
    dados = _ler_tudo(_conexao(serial, "shell:" + cmd, timeout))
    log.comando(["shell*", comando], 0, time.perf_counter() - inicio, len(dados))
    return dados.decode("utf-8", "replace").replace("\r\n", "\n").strip()


def binario(serial: str, comando: str, timeout: float = 60) -> bytes:
    """Como `adb exec-out`: bytes crus, sem conversão de quebra de linha."""
    inicio = time.perf_counter()
    dados = _ler_tudo(_conexao(serial, "exec:" + comando, timeout))
    log.comando(["exec*", comando], 0, time.perf_counter() - inicio, len(dados))
    return dados


def linhas(serial: str, comando: str) -> Iterator[str]:
    """Saída linha a linha (para barra de progresso)."""
    con = _conexao(serial, f"shell:( {comando} ) 2>/dev/null", None)
    resto = b""
    try:
        while True:
            bloco = con.recv(4096)
            if not bloco:
                break
            resto += bloco
            *prontas, resto = resto.split(b"\n")
            for linha in prontas:
                yield linha.decode("utf-8", "replace").rstrip("\r")
        if resto:
            yield resto.decode("utf-8", "replace").rstrip("\r")
    finally:
        con.close()


def enviar(serial: str, local: str, remoto: str) -> None:
    """Como `adb push`."""
    c = cliente()
    if c is None:
        raise Indisponivel("sem cliente")
    try:
        c.device(serial).sync.push(local, remoto)
    except Exception as e:  # noqa: BLE001
        esquecer()
        raise Indisponivel(str(e)) from e
