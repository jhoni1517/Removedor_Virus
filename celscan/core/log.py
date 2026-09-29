"""Log em arquivo (~/.celscan/logs) com todos os comandos adb e seus tempos."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from celscan.config import DIR

LOGGER = logging.getLogger("celscan")
_arquivo: Path | None = None


def configurar(pasta: Path | None = None) -> Path:
    """Liga o log em arquivo (idempotente). Devolve o caminho do arquivo."""
    global _arquivo
    if _arquivo is None:
        pasta = pasta or DIR / "logs"
        pasta.mkdir(parents=True, exist_ok=True)
        _arquivo = pasta / "celscan.log"
        handler = RotatingFileHandler(_arquivo, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)
        LOGGER.propagate = False
    return _arquivo


def comando(args: Sequence[object], codigo: int | None, segundos: float, bytes_saida: int) -> None:
    texto = " ".join(str(a) for a in args).replace("\n", " ")
    if len(texto) > 300:
        texto = texto[:300] + "…"
    LOGGER.info("adb %s | código=%s | %.2fs | %d bytes", texto, codigo, segundos, bytes_saida)


@contextmanager
def etapa(nome: str) -> Iterator[None]:
    """Mede e registra a duração de uma etapa (ex.: 'coleta', 'hashes')."""
    inicio = time.perf_counter()
    LOGGER.info("etapa %s: início", nome)
    try:
        yield
    finally:
        LOGGER.info("etapa %s: %.1fs", nome, time.perf_counter() - inicio)
