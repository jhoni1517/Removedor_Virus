"""Histórico: o que mudou entre duas visitas do mesmo aparelho."""

from fastapi.testclient import TestClient

from celscan.analise import diferencas
from celscan.api.app import criar_app
from celscan.core import db

A = {"achados_aparelho": [{"titulo": "Proxy global"}], "apps": [
    {"pacote": "com.banco", "nome": "Banco", "nivel": "OK", "achados": [], "cert": {"sha256": "AA"}, "versao": "1"},
    {"pacote": "com.jogo", "nome": "Jogo", "nivel": "MÉDIO",
     "achados": [{"chave": "sem_icone", "titulo": "Escondido"}]},
    {"pacote": "com.velho", "nome": "Velho", "nivel": "BAIXO", "achados": []},
]}
D = {"achados_aparelho": [{"titulo": "Patch antigo"}], "apps": [
    {"pacote": "com.banco", "nome": "Banco", "nivel": "ALTO",
     "achados": [{"chave": "acessibilidade", "titulo": "Usa acessibilidade"}], "cert": {"sha256": "BB"}, "versao": "2"},
    {"pacote": "com.jogo", "nome": "Jogo", "nivel": "BAIXO",
     "achados": [{"chave": "sem_icone", "titulo": "Escondido"}]},
    {"pacote": "com.novo", "nome": "Novo", "nivel": "MÉDIO", "achados": []},
]}


def test_comparar():
    d = diferencas.comparar(A, D, 80, 40)
    assert [x["pacote"] for x in d["apps_novos"]] == ["com.novo"]
    assert [x["pacote"] for x in d["apps_removidos"]] == ["com.velho"]
    assert d["risco_subiu"][0]["pacote"] == "com.banco"
    assert d["risco_caiu"][0]["pacote"] == "com.jogo"
    assert d["certificado_trocado"][0]["pacote"] == "com.banco"
    assert d["alertas_novos"][0]["alertas"] == ["Usa acessibilidade"]
    assert d["atualizados"][0]["para"] == "2"
    assert d["aparelho_novos"] == ["Patch antigo"] and d["aparelho_resolvidos"] == ["Proxy global"]
    assert d["nota"] == {"antes": 80, "depois": 40} and not d["sem_mudancas"]


def test_sem_mudancas():
    assert diferencas.comparar(A, A)["sem_mudancas"]


def test_api_diferencas():
    info = {"serial": "DIF1", "fabricante": "X", "modelo": "Y", "android": "14"}
    con = db.conectar()
    v1 = db.salvar_varredura(con, info, 80, "Bom", A["achados_aparelho"], A["apps"])
    v2 = db.salvar_varredura(con, info, 40, "Crítico", D["achados_aparelho"], D["apps"])
    with TestClient(criar_app("t", observar=False)) as c:
        h = {"X-CelScan-Token": "t"}
        assert c.get(f"/api/varreduras/{v1}/diferencas", headers=h).json()["primeira_visita"] is True
        r = c.get(f"/api/varreduras/{v2}/diferencas", headers=h).json()
        assert r["anterior_id"] == v1 and r["certificado_trocado"]
