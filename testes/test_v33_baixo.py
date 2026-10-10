"""Upgrades de nível BAIXO da 3.3."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_versao_na_linha_de_comando():
    from celscan.config import VERSAO
    r = subprocess.run([sys.executable, str(RAIZ / "celscan.py"), "--version"], capture_output=True, encoding="utf-8",
                       timeout=60)
    assert r.returncode == 0 and VERSAO in r.stdout


def test_novas_redes_de_anuncio():
    from celscan.analise.rotulos import sdk_de
    assert sdk_de("com.kwad.sdk.api.proxy.app.AdWebViewActivity") == "Kwai Ads"
    assert sdk_de("com.anythink.basead.ui.ATPortraitTranslucentActivity") == "TopOn"
    assert sdk_de("com.exemplo.Main") is None


def test_contato_da_loja_no_rodape(monkeypatch):
    from celscan.core import preferencias
    from celscan.relatorio import pdf
    monkeypatch.setattr(preferencias, "ler", lambda: {"contato_loja": "Loja Ç · (11) 99999-0000 · 😀"})
    meta = {"id": 1, "data": "2026-10-10T10:00:00", "nota": 95, "veredito": "ok", "modo": "rapido", "duracao_s": 3}
    retrato = {"aparelho": {"serial": "S", "fabricante": "Moto", "modelo": "G", "android": "14"},
               "achados_aparelho": [], "avisos": [], "apps": []}
    dados, _ = pdf.gerar_pdf(meta, retrato)  # emoji fora da fonte não derruba o laudo
    assert dados.startswith(b"%PDF")
