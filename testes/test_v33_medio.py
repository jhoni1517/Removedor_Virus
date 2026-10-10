"""Upgrades de nível MÉDIO da 3.3."""

from __future__ import annotations

from datetime import datetime


def test_por_que_esta_ok():
    from celscan.analise import pontuacao
    from celscan.core import coleta, parsers
    from conftest import ler_fixture
    d = coleta.montar("ABC123", parsers.secoes(ler_fixture("sintetico/coleta.txt")))
    _, res = pontuacao.pontuar(d, agora=datetime(2026, 9, 29))
    zap = next(r for r in res if r["pacote"] == "com.whatsapp")
    assert "instalado pela Google Play" in zap["seguro_porque"]


def test_pdf_usa_inicial_quando_nao_ha_icone():
    from reportlab.graphics.shapes import Drawing

    from celscan.relatorio import pdf
    assert isinstance(pdf._icone_pdf({"pacote": "com.x", "nome": "Ônibus"}, 20), Drawing)
    svg = {"pacote": "com.x", "nome": "微信", "icone": "data:image/svg+xml,..."}
    assert isinstance(pdf._icone_pdf(svg, 20), Drawing)
    assert isinstance(pdf._icone_pdf({"pacote": "com.x", "icone": "data:image/png;base64,lixo"}, 20), Drawing)


def test_revisao_desligada_com_zero(tmp_path, monkeypatch):
    from celscan.core import balcao, db, preferencias
    monkeypatch.setattr(preferencias, "ler", lambda: {"dias_retorno": 0})
    con = db.conectar(tmp_path / "z.db", nova=True)
    oid = balcao.criar_ordem(con, ["checkup"])
    balcao.mudar_status(con, oid, "entregue")
    assert con.execute("SELECT retorno_em FROM ordens WHERE id=?", (oid,)).fetchone()[0] is None
