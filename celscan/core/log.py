"""Log em arquivo (~/.celscan/logs) com todos os comandos adb e seus tempos."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from celscan.config import DIR

LOGGER = logging.getLogger("celscan")
_arquivo: Path | None = None


class SemDadosPessoais(logging.Filter):
    """Mascara no log o que não deve sair do computador quando a pessoa manda o celscan.log para suporte:
    código de pareamento Wi-Fi, IMEI, telefone, e-mail e token da interface."""

    REGRAS = (
        (re.compile(r"(\bpair\s+\S+\s+)\d{6}\b"), r"\1******"),
        (re.compile(r"\b(\d{2})\d{11}(\d{2})\b"), r"\1***********\2"),  # IMEI (15 dígitos)
        (re.compile(r"\(?\b\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}\b"), "(**) *****-****"),  # telefone BR
        (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "***@***"),
        (re.compile(r"([?&]t=)[\w-]{16,}"), r"\1***"),
    )

    def filter(self, registro: logging.LogRecord) -> bool:
        try:
            msg = registro.getMessage()
        except Exception:  # noqa: BLE001
            return True
        novo = msg
        for rx, troca in self.REGRAS:
            novo = rx.sub(troca, novo)
        if novo != msg:
            registro.msg, registro.args = novo, None
        return True


def configurar(pasta: Path | None = None) -> Path:
    """Liga o log em arquivo (idempotente). Devolve o caminho do arquivo."""
    global _arquivo
    if _arquivo is None:
        pasta = pasta or DIR / "logs"
        pasta.mkdir(parents=True, exist_ok=True)
        _arquivo = pasta / "celscan.log"
        handler = RotatingFileHandler(_arquivo, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        handler.addFilter(SemDadosPessoais())
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
