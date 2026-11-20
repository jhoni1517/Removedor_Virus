"""Tempo que cada etapa leva NESTE computador (média móvel), para a barra de progresso dar um prazo real.

O valor fixo (pensado para ~150 apps num PC médio) errava muito em PC lento ou celular com 400 apps.
Guardamos segundos por app de cada etapa e estimamos com o número de apps do aparelho da vez.
"""

from __future__ import annotations

import json
import os
import threading

from celscan import config

_trava = threading.Lock()
PESO_NOVO = 0.3  # média móvel: a última varredura conta 30%


def _arquivo():
    return config.DIR / "tempos.json"


def _ler() -> dict[str, float]:
    try:
        dados = json.loads(_arquivo().read_text(encoding="utf-8"))
        return {k: float(v) for k, v in dados.items() if isinstance(v, (int, float)) and v >= 0}
    except (OSError, ValueError, AttributeError):
        return {}


def registrar(etapa: str, segundos: float, n_apps: int) -> None:
    """Grava quanto a etapa levou (por app). Etapas curtas demais (cache) também entram: refletem a realidade."""
    if n_apps <= 0 or segundos < 0:
        return
    por_app = segundos / n_apps
    with _trava:
        dados = _ler()
        anterior = dados.get(etapa)
        dados[etapa] = por_app if anterior is None else anterior * (1 - PESO_NOVO) + por_app * PESO_NOVO
        try:
            config.DIR.mkdir(parents=True, exist_ok=True)
            tmp = _arquivo().with_suffix(".tmp")
            tmp.write_text(json.dumps(dados), encoding="utf-8")
            os.replace(tmp, _arquivo())
        except OSError:
            pass


def estimar(etapa: str, n_apps: int | None, padrao_150: float) -> int:
    """Segundos previstos para a etapa. Sem histórico, escala o padrão (feito para 150 apps)."""
    n = n_apps or 150
    por_app = _ler().get(etapa)
    if por_app is None:
        return round(padrao_150 * n / 150)
    return max(1, round(por_app * n))
