"""Carrega as regras de pontuação de dados/regras.yaml (+ ~/.celscan/regras.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from celscan.config import DADOS, DIR

ARQUIVO = DADOS / "regras.yaml"
ARQUIVO_USUARIO = DIR / "regras.yaml"
GRUPOS_APP = ("apps", "permissoes", "appops")


class RegrasInvalidas(Exception):
    pass


@dataclass(frozen=True)
class Regra:
    chave: str
    titulo: str
    significa: str
    fazer: str
    peso: int = 0
    nivel: str = ""

    def achado(self, detalhe: object = None) -> dict[str, Any]:
        """Um achado pronto para mostrar: título curto + o que significa + o que fazer."""
        titulo = self.titulo.replace("{detalhe}", str(detalhe)) if detalhe is not None else self.titulo
        return {"chave": self.chave, "peso": self.peso, "nivel": self.nivel, "titulo": titulo,
                "significa": self.significa, "fazer": self.fazer}


@dataclass
class Regras:
    apps: dict[str, Regra]
    permissoes: dict[str, Regra]
    appops: dict[str, Regra]
    aparelho: dict[str, Regra]
    limites: dict[str, int]
    parametros: dict[str, int]
    nota: dict[str, Any]


def _mesclar(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        base[k] = _mesclar(base.get(k, {}), v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def _regras(grupo: str, dados: dict) -> dict[str, Regra]:
    res = {}
    for chave, r in (dados.get(grupo) or {}).items():
        faltando = [c for c in ("titulo", "significa", "fazer") if not r.get(c)]
        if grupo in GRUPOS_APP and "peso" not in r:
            faltando.append("peso")
        if grupo == "aparelho" and r.get("nivel") not in ("ALTO", "MÉDIO", "BAIXO"):
            faltando.append("nivel (ALTO/MÉDIO/BAIXO)")
        if faltando:
            raise RegrasInvalidas(f"regras.yaml: '{grupo}.{chave}' sem {', '.join(faltando)}")
        res[chave] = Regra(chave=chave, titulo=r["titulo"], significa=r["significa"], fazer=r["fazer"],
                           peso=int(r.get("peso", 0)), nivel=r.get("nivel", ""))
    return res


def carregar(caminho: Path | None = None, usuario: Path | None = ARQUIVO_USUARIO) -> Regras:
    dados = yaml.safe_load(Path(caminho or ARQUIVO).read_text(encoding="utf-8")) or {}
    if usuario and Path(usuario).exists():
        dados = _mesclar(dados, yaml.safe_load(Path(usuario).read_text(encoding="utf-8")) or {})
    return Regras(
        apps=_regras("apps", dados), permissoes=_regras("permissoes", dados), appops=_regras("appops", dados),
        aparelho=_regras("aparelho", dados), limites=dict(dados.get("limites") or {}),
        parametros=dict(dados.get("parametros") or {}), nota=dict(dados.get("nota") or {}),
    )
