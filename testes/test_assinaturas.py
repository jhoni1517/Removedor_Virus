"""Assinaturas de vírus offline (listas próprias + MalwareBazaar)."""
import json

import pytest
from fastapi.testclient import TestClient

from celscan import config
from celscan.analise import assinaturas, iocs
from celscan.core import bases

H1 = "a" * 64
H2 = "B" * 64


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR", tmp_path)
    monkeypatch.setattr(assinaturas.preferencias, "chave_abusech", lambda: None)
    monkeypatch.setattr(iocs.bases, "vencida", lambda b: False)
    return tmp_path


def test_ler_arquivo_aceita_formatos():
    t = f"# comentário\n{H1},Anatsa\n{H2}\tSpyNote\nlixo\n{'c' * 63}\n"
    r = assinaturas.ler_arquivo(t, "equipe")
    assert r == {H1: "Anatsa", H2.lower(): "SpyNote"}
    assert assinaturas.ler_arquivo("d" * 64, "x") == {"d" * 64: "lista x"}


def test_importar_e_carregar(pasta):
    with pytest.raises(ValueError):
        assinaturas.importar("vazia", "nada aqui")
    assert assinaturas.importar("../minha lista", f"{H1} Cerberus\n") == 1
    assert (pasta / "assinaturas" / ".._minha_lista.txt").exists()
    assert assinaturas.carregar() == {H1: "Cerberus"}
    r = assinaturas.resumo()
    assert r["proprias"] == 1 and r["baixadas"] == 0 and not r["tem_chave"]


def test_iocs_usa_assinaturas_sem_base_baixada(pasta, monkeypatch):
    original = bases.ler
    monkeypatch.setattr(bases, "ler", lambda nome: None if nome in ("iocs", "assinaturas") else original(nome))
    assinaturas.importar("l", f"{H1},Anatsa\n")
    i = iocs.carregar()
    assert i is not None and i.checar("com.qualquer", None, H1) == "Anatsa"


def test_baixar_malwarebazaar(monkeypatch):
    monkeypatch.setattr(assinaturas.preferencias, "chave_abusech", lambda: "k")
    vistos = []

    class R:
        def __init__(self, d):
            self.d = d

        def raise_for_status(self):
            pass

        def json(self):
            return self.d

    def post(url, data, headers, timeout):
        vistos.append(headers["Auth-Key"])
        return R({"query_status": "ok", "data": [{"sha256_hash": H1, "signature": "Hook"}, {"sha256_hash": "x"}]})

    monkeypatch.setattr(assinaturas.requests, "post", post)
    d = json.loads(assinaturas._baixar_malwarebazaar())
    assert d["hashes"] == {H1: "MalwareBazaar: Hook"} and vistos == ["k", "k"]
    monkeypatch.setattr(assinaturas.preferencias, "chave_abusech", lambda: None)
    with pytest.raises(RuntimeError):
        assinaturas._baixar_malwarebazaar()


def test_api_assinaturas(pasta):
    from celscan.api.app import criar_app
    c = TestClient(criar_app(token="T", observar=False), base_url="http://127.0.0.1")
    h = {"x-celscan-token": "T"}
    assert c.get("/api/assinaturas", headers=h).json()["proprias"] == 0
    assert c.post("/api/assinaturas/atualizar", headers=h).status_code == 409
    r = c.post("/api/assinaturas/importar", json={"nome": "eq", "conteudo": f"{H1}\n"}, headers=h)
    assert r.status_code == 200 and r.json()["importadas"] == 1 and r.json()["proprias"] == 1
    assert c.post("/api/assinaturas/importar", json={"nome": "eq", "conteudo": "z" * 80}, headers=h).status_code == 422
