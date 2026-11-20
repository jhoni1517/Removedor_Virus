"""Memória por modelo, relatório PDF da otimização e otimizar ao conectar."""
import time

from celscan import config
from celscan.acoes import compat


def test_compat_aprende_o_que_o_modelo_recusa(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR", tmp_path)
    m = compat.chave("Xiaomi", "24115RA8EG", "15")
    compat.registrar(m, [{"id": "fantasmas", "ok": False, "detalhe": "o Android não aceitou"},
                         {"id": "dexopt", "ok": True}])
    assert compat.recusadas(m) == {"fantasmas": "o Android não aceitou"}
    compat.registrar(m, [{"id": "fantasmas", "ok": True}])
    assert compat.recusadas(m) == {}
    t = compat.tabela()
    assert t[0]["modelo"] == m and {e["id"]: e["estado"] for e in t[0]["etapas"]} == {
        "dexopt": "aceita", "fantasmas": "às vezes"}


def test_relatorio_pdf(tmp_path, monkeypatch):
    import json

    from celscan.relatorio import otimizacao_pdf
    monkeypatch.setattr(config, "DIR", tmp_path)
    (tmp_path / "otimizacoes").mkdir()
    d = {"id": "ABC-1700000000", "data": time.time(), "serial": "ABC", "modelo": "Xiaomi X · Android 15",
         "etapas": [{"id": "dexopt", "ok": True, "detalhe": "feita"}, {"id": "fantasmas", "ok": False}],
         "antes": {"problemas": [{"gravidade": "critica", "titulo": "Bloqueado", "prova": "teste"}]},
         "depois": {"problemas": [], "bons": ["Modo economia desligado"]},
         "antes_depois": {"total": {"antes": 60, "depois": 70, "pontos": 10, "ganho_pct": 17}}}
    (tmp_path / "otimizacoes" / "ABC-1700000000.json").write_text(json.dumps(d))
    assert otimizacao_pdf.listar("ABC")[0]["ok"] == 1 and otimizacao_pdf.listar("OUTRO") == []
    assert otimizacao_pdf.gerar(otimizacao_pdf.ler("ABC-1700000000")).startswith(b"%PDF")
    import pytest
    with pytest.raises(ValueError):
        otimizacao_pdf.ler("../../etc")


def test_aparelho_que_chega_dispara_o_gancho():
    from celscan.api.app import Aparelhos
    from celscan.api.tarefas import Gerenciador

    a = Aparelhos(Gerenciador())
    a._info["X"] = {"modelo": "m"}
    vistos = []
    a.ao_conectar = vistos.append
    a.atualizar([("X", "unauthorized")])
    a.atualizar([("X", "device")])
    a.atualizar([("X", "device"), ("Y", "offline")])
    time.sleep(0.2)
    assert vistos == ["X"]
