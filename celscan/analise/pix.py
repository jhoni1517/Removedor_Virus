"""Proteção Pix e bancos: apps que imitam bancos/marcas e o padrão de trojan bancário.

Trojans bancários brasileiros (ex.: PixRevolution, 2026) pedem ACESSIBILIDADE para ler e tocar na
tela e usam SOBREPOSIÇÃO ou CAPTURA DE TELA para esconder a troca da chave Pix. O risco é maior
quando o mesmo aparelho tem app de banco instalado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from celscan.config import DADOS


@dataclass(frozen=True)
class AppConhecido:
    pacote: str
    nome: str
    termos: tuple[str, ...]


@dataclass
class Bancos:
    oficiais: dict[str, AppConhecido] = field(default_factory=dict)
    iscas: list[AppConhecido] = field(default_factory=list)


@lru_cache(maxsize=1)
def carregar() -> Bancos:
    dados = yaml.safe_load((DADOS / "bancos.yaml").read_text(encoding="utf-8")) or {}
    oficiais = {a["pacote"]: AppConhecido(a["pacote"], a["nome"], tuple(a.get("termos") or ()))
                for a in dados.get("apps") or []}
    iscas = [AppConhecido("", i["nome"], tuple(i.get("termos") or ())) for i in dados.get("iscas") or []]
    return Bancos(oficiais, iscas)


def _distancia(a: str, b: str) -> int:
    """Distância de edição (Levenshtein), para achar com.whatsaap x com.whatsapp."""
    if abs(len(a) - len(b)) > 2:
        return 3
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def imitacao(pacote: str, bancos: Bancos | None = None) -> str | None:
    """Nome do app/marca que este pacote imita, ou None. O próprio app oficial nunca é imitação."""
    b = bancos or carregar()
    if pacote in b.oficiais:
        return None
    compacto = re.sub(r"[^a-z0-9]", "", pacote.lower())
    for oficial in b.oficiais.values():
        if len(pacote) >= 8 and _distancia(pacote.lower(), oficial.pacote.lower()) <= 2:
            return oficial.nome
    for conhecido in [*b.oficiais.values(), *b.iscas]:
        if any(t in compacto for t in conhecido.termos):
            return conhecido.nome
    return None


def bancarios_instalados(pacotes: set[str] | list[str], bancos: Bancos | None = None) -> list[str]:
    b = bancos or carregar()
    return sorted(b.oficiais[p].nome for p in pacotes if p in b.oficiais and b.oficiais[p].nome != "WhatsApp")


def padrao_trojan(pacote: str, acess: set[str], appops: set[str]) -> bool:
    """Acessibilidade + (sobreposição ou captura de tela): o conjunto usado para roubar Pix."""
    return pacote in acess and bool(appops & {"SYSTEM_ALERT_WINDOW", "PROJECT_MEDIA"})
