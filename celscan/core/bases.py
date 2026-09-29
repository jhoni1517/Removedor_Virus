"""Bases externas (indicadores de ameaça, lista UAD, certificados oficiais).

Cada base tem uma cópia local em ~/.celscan/bases/. A atualização roda em segundo plano
enquanto o aparelho é lido; no modo offline (CELSCAN_OFFLINE=1 ou --offline) nada é
baixado e só as cópias locais (ou as que vêm com o programa) são usadas.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from celscan import config
from celscan.core.log import LOGGER

PASTA = config.DIR / "bases"


@dataclass(frozen=True)
class Base:
    nome: str
    descricao: str
    arquivo: str  # nome do arquivo em ~/.celscan/bases
    validade_s: int
    baixar: Callable[[], str] | None  # devolve o conteúdo a gravar; None = base só local
    embutido: Path | None = None  # cópia que vem com o programa (fallback)

    @property
    def caminho(self) -> Path:
        return PASTA / self.arquivo


_REGISTRO: dict[str, Base] = {}
_travas: dict[str, threading.Lock] = {}


def registrar(base: Base) -> Base:
    _REGISTRO[base.nome] = base
    _travas.setdefault(base.nome, threading.Lock())
    return base


def todas() -> list[Base]:
    _carregar_registro()
    return list(_REGISTRO.values())


def _carregar_registro() -> None:
    # As bases se registram ao importar seus módulos (evita import circular).
    from celscan.acoes import otimizacao  # noqa: F401
    from celscan.analise import certificados, iocs  # noqa: F401


def obter_base(nome: str) -> Base:
    _carregar_registro()
    return _REGISTRO[nome]


def idade_s(base: Base) -> float | None:
    return time.time() - base.caminho.stat().st_mtime if base.caminho.exists() else None


def vencida(base: Base) -> bool:
    idade = idade_s(base)
    return base.baixar is not None and (idade is None or idade > base.validade_s)


def atualizar(nome: str, forcar: bool = False) -> tuple[bool, str]:
    """Baixa a base se estiver vencida (ou se forcar). Nunca levanta exceção."""
    base = obter_base(nome)
    if base.baixar is None:
        return True, "base local (não precisa baixar)"
    if config.OFFLINE:
        return False, "modo offline: usando a cópia local"
    with _travas[nome]:
        if not forcar and not vencida(base):
            return True, "já está atualizada"
        inicio = time.perf_counter()
        try:
            conteudo = base.baixar()
        except Exception as e:  # rede, formato, etc.
            LOGGER.warning("base %s: falha ao atualizar (%s)", nome, e)
            return False, f"não foi possível atualizar ({e})"
        PASTA.mkdir(parents=True, exist_ok=True)
        temporario = base.caminho.with_suffix(".tmp")
        temporario.write_text(conteudo, encoding="utf-8")
        temporario.replace(base.caminho)  # troca atômica: nunca fica meio arquivo
        LOGGER.info("base %s atualizada em %.1fs (%d bytes)", nome, time.perf_counter() - inicio, len(conteudo))
        return True, "atualizada"


def ler(nome: str) -> str | None:
    """Conteúdo da cópia local; se não houver, o arquivo que vem com o programa."""
    base = obter_base(nome)
    for caminho in (base.caminho, base.embutido):
        if caminho and caminho.exists():
            return caminho.read_text(encoding="utf-8")
    return None


def atualizar_em_segundo_plano(nomes: list[str] | None = None) -> threading.Thread:
    """Atualiza as bases vencidas numa thread; use .join(timeout) antes de ler."""
    alvos = nomes or [b.nome for b in todas()]

    def rodar() -> None:
        for nome in alvos:
            atualizar(nome)

    t = threading.Thread(target=rodar, name="celscan-bases", daemon=True)
    t.start()
    return t


def situacao() -> list[dict[str, object]]:
    res = []
    for b in todas():
        idade = idade_s(b)
        res.append({"nome": b.nome, "descricao": b.descricao, "local": b.caminho.exists(),
                    "embutida": bool(b.embutido and b.embutido.exists()),
                    "idade_h": None if idade is None else idade / 3600, "vencida": vencida(b)})
    return res
