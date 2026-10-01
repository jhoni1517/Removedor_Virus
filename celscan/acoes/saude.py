"""Saúde do aparelho: desgaste da bateria, ciclos restantes estimados e indícios de peça trocada.

Só com o que dá para ler por USB, sem root — e com honestidade sobre os limites:

- Bateria: a capacidade real de hoje (`charge_full`) contra a de fábrica (`charge_full_design`) dá a
  saúde em %. Com os ciclos já usados dá para ESTIMAR quantos faltam até a bateria chegar a 80%.
- Peças originais ou trocadas: por USB NÃO dá para afirmar isso com certeza. O que dá são *indícios*
  (ex.: a bateria não informa a capacidade de fábrica, comum em baterias paralelas; ou informa uma
  saúde fisicamente impossível). Tudo aqui é rotulado como "indício", nunca como prova. Tela, câmera
  e outras peças não têm como ser verificadas por USB — e o resultado diz isso em vez de inventar.
"""

from __future__ import annotations

from typing import Any

# Referência conservadora: um ciclo = uma carga completa somada. Células de Li-ion costumam manter
# ~80% da capacidade por 500 ciclos (muitas chegam a 800+). Usamos 500 como "vida típica de projeto".
CICLOS_REFERENCIA = 500
SAUDE_FIM_DE_VIDA = 80  # abaixo disso a troca costuma valer a pena


def veredito_bateria(saude_pct: int | None) -> str | None:
    if saude_pct is None:
        return None
    if saude_pct >= 90:
        return "Ótima"
    if saude_pct >= 80:
        return "Boa"
    if saude_pct >= 70:
        return "Desgastada — considere trocar"
    return "Muito desgastada — troca recomendada"


def ciclos_restantes(saude_pct: int | None, ciclos: int | None) -> dict[str, Any] | None:
    """Estimativa de quantos ciclos faltam até a bateria chegar a 80% de saúde.

    Quando temos saúde E ciclos, calculamos o desgaste real por ciclo (mais honesto que um número fixo).
    Sem isso, caímos na referência de projeto. Sempre marcado como estimativa.
    """
    if ciclos is None:
        return None
    if saude_pct is not None and ciclos > 0 and saude_pct < 100:
        desgaste_por_ciclo = (100 - saude_pct) / ciclos
        if desgaste_por_ciclo > 0:
            faltam = max(0, round((saude_pct - SAUDE_FIM_DE_VIDA) / desgaste_por_ciclo))
            return {"restantes": faltam, "base": "medido", "ate_pct": SAUDE_FIM_DE_VIDA,
                    "obs": "Estimado pelo desgaste real por ciclo deste aparelho."}
    faltam = max(0, CICLOS_REFERENCIA - ciclos)
    return {"restantes": faltam, "base": "referencia", "ate_pct": SAUDE_FIM_DE_VIDA,
            "obs": f"Estimado pela vida típica de {CICLOS_REFERENCIA} ciclos (a bateria não informou a saúde)."}


def indicios_pecas(bateria: dict[str, Any]) -> list[dict[str, str]]:
    """Indícios (não provas) de peça trocada, a partir do que a bateria informa. Honesto sobre o resto."""
    indicios: list[dict[str, str]] = []
    saude_pct = bateria.get("saude_pct")
    tem_projeto = bateria.get("capacidade_projeto_mah") is not None

    if isinstance(saude_pct, (int, float)) and saude_pct > 105:
        indicios.append({
            "peca": "Bateria",
            "nivel": "alto",
            "texto": f"A bateria informa saúde de {round(saude_pct)}%, fisicamente impossível. "
                     "É típico de bateria paralela que reporta dados falsos — indício forte de troca.",
        })
    elif not tem_projeto:
        indicios.append({
            "peca": "Bateria",
            "nivel": "medio",
            "texto": "A bateria não informa a capacidade de fábrica. Acontece em algumas baterias paralelas "
                     "ou trocadas — é indício, não prova (alguns aparelhos originais também não informam).",
        })
    else:
        indicios.append({
            "peca": "Bateria",
            "nivel": "baixo",
            "texto": "A bateria informa a capacidade de fábrica normalmente — compatível com peça original "
                     "(ou com uma troca de boa qualidade). Não é prova de originalidade.",
        })

    indicios.append({
        "peca": "Tela, câmera e outras peças",
        "nivel": "baixo",
        "texto": "Não é possível verificar originalidade de tela, câmera ou outras peças por USB. "
                 "Isso exige inspeção física (número de série da peça, cola, encaixe).",
    })
    return indicios


def avaliar(bateria: dict[str, Any]) -> dict[str, Any]:
    """Enriquece a bateria com veredito e ciclos restantes, e devolve os indícios de peça."""
    saude_pct = bateria.get("saude_pct")
    ciclos_val = bateria.get("ciclos")
    try:
        ciclos_num = int(ciclos_val) if ciclos_val is not None else None
    except (TypeError, ValueError):
        ciclos_num = None
    extra: dict[str, Any] = {}
    v = veredito_bateria(saude_pct)
    if v:
        extra["veredito"] = v
    cr = ciclos_restantes(saude_pct, ciclos_num)
    if cr:
        extra["ciclos_restantes"] = cr
    return {"bateria_extra": extra, "pecas": indicios_pecas(bateria)}
