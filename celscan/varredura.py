"""Orquestra uma varredura Android: coleta (core) -> enriquecimento -> análise (analise)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from celscan.acoes import remocao
from celscan.analise import pontuacao
from celscan.config import LOJAS, permitidos
from celscan.core import coleta
from celscan.core.adb import Aparelho
from celscan.core.coleta import DadosAparelho


class Varredura:
    def __init__(self, aparelho: Aparelho, vt=None, iocs=None, sistema: bool = False):
        self.ap, self.vt, self.iocs, self.sistema = aparelho, vt, iocs, sistema
        self.permitidos = permitidos()
        self.dados: DadosAparelho | None = None

    @property
    def apps(self) -> dict[str, coleta.AppBruto]:
        assert self.dados is not None, "chame coletar() antes"
        return self.dados.apps

    @property
    def avisos(self) -> list[str]:
        return self.dados.avisos if self.dados else []

    def coletar(self) -> DadosAparelho:
        self.dados = coleta.coletar(self.ap, self.sistema)
        return self.dados

    def info(self) -> dict[str, str]:
        assert self.dados is not None
        return self.dados.info()

    def calcular_hashes(self) -> Iterator[str]:
        assert self.dados is not None
        return coleta.calcular_hashes(self.ap, self.dados, self.sistema)

    def candidatos(self, minimo: int = 20, todos: bool = False) -> list[str]:
        res = {r["pacote"]: r["score"] for r in self.pontuar()[1]}
        return [p for p, a in self.apps.items() if not a.sistema
                and (todos or res[p] >= minimo or (a.instalador or "") not in LOJAS)]

    def ler_certificado(self, pkg: str) -> None:
        coleta.ler_certificado(self.ap, self.apps[pkg])

    def consultar_vt(self, pkg: str) -> None:
        app = self.apps[pkg]
        if self.vt and app.sha256:
            try:
                app.vt = self.vt.consultar(app.sha256)
            except Exception as e:
                app.vt = {"erro": str(e)}

    def pontuar(self, agora: datetime | None = None):
        assert self.dados is not None
        return pontuacao.pontuar(self.dados, self.iocs, self.permitidos, agora)

    def remover(self, r: dict) -> tuple[bool, str]:
        return remocao.remover(self.ap, r)


AndroidScanner = Varredura  # nome antigo (v2)
