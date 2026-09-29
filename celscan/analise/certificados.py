"""Certificados oficiais de apps (bancos, carteiras, gov.br...) para detectar cópias falsificadas."""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from celscan.config import DADOS
from celscan.core import bases

BASE = bases.registrar(bases.Base(
    nome="certificados", descricao="Certificados oficiais de bancos e apps populares (Brasil)",
    arquivo="certificados_oficiais.yaml", validade_s=7 * 86400,
    baixar=None,  # ainda sem fonte on-line confiável: só a lista conferida que vem com o programa
    embutido=DADOS / "certificados_oficiais.yaml",
))


@dataclass(frozen=True)
class AppOficial:
    pacote: str
    nome: str
    sha256: frozenset[str]


def carregar() -> dict[str, AppOficial]:
    texto = bases.ler("certificados") or ""
    dados = yaml.safe_load(texto) or {}
    res = {}
    for item in dados.get("apps") or []:
        certs = frozenset(str(c).replace(":", "").upper() for c in item.get("sha256") or [])
        if item.get("pacote") and certs:
            res[item["pacote"]] = AppOficial(item["pacote"], item.get("nome", item["pacote"]), certs)
    return res


def conferir(pacote: str, cert: dict | None, oficiais: dict[str, AppOficial]) -> str | None:
    """'falso' se o pacote é de um app oficial mas o certificado é outro; 'ok' se bate; None se não se aplica."""
    oficial = oficiais.get(pacote)
    if not oficial or not cert or not cert.get("sha256"):
        return None
    return "ok" if cert["sha256"].upper() in oficial.sha256 else "falso"
