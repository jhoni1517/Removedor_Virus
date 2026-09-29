import json
import os
import time

import pytest

from celscan import config
from celscan.analise import certificados, iocs
from celscan.core import bases


@pytest.fixture
def base_teste(tmp_path, monkeypatch):
    monkeypatch.setattr(bases, "PASTA", tmp_path)
    monkeypatch.setattr(config, "OFFLINE", False)
    chamadas = []

    def baixar():
        chamadas.append(1)
        return "conteudo novo"

    b = bases.registrar(bases.Base("teste", "Base de teste", "teste.txt", 3600, baixar,
                                   embutido=tmp_path / "embutido.txt"))
    yield b, chamadas
    bases._REGISTRO.pop("teste", None)


def test_atualiza_so_quando_vencida(base_teste):
    b, chamadas = base_teste
    assert bases.vencida(b)
    assert bases.atualizar("teste") == (True, "atualizada")
    assert bases.ler("teste") == "conteudo novo"
    assert bases.atualizar("teste") == (True, "já está atualizada")
    assert len(chamadas) == 1
    velho = time.time() - 7200
    os.utime(b.caminho, (velho, velho))
    assert bases.vencida(b)


def test_modo_offline_nao_baixa(base_teste, monkeypatch):
    b, chamadas = base_teste
    monkeypatch.setattr(config, "OFFLINE", True)
    ok, msg = bases.atualizar("teste", forcar=True)
    assert not ok and "offline" in msg and chamadas == []


def test_falha_de_rede_mantem_copia(base_teste):
    b, _ = base_teste
    b.caminho.write_text("cópia antiga", encoding="utf-8")
    ruim = bases.registrar(bases.Base("teste", "x", "teste.txt", 0, lambda: 1 / 0))
    ok, msg = bases.atualizar("teste", forcar=True)
    assert not ok and "não foi possível" in msg
    assert bases.ler("teste") == "cópia antiga"
    assert ruim.caminho == b.caminho


def test_usa_copia_embutida_sem_local(base_teste):
    b, _ = base_teste
    b.embutido.write_text("vem com o programa", encoding="utf-8")
    assert bases.ler("teste") == "vem com o programa"


def test_segundo_plano(base_teste):
    b, chamadas = base_teste
    t = bases.atualizar_em_segundo_plano(["teste"])
    t.join(5)
    assert chamadas == [1] and b.caminho.exists()


def test_situacao_lista_todas_as_bases():
    nomes = {s["nome"] for s in bases.situacao()}
    assert {"iocs", "uad", "certificados"} <= nomes


def test_iocs_offline_usa_copia_local(monkeypatch, tmp_path):
    monkeypatch.setattr(bases, "PASTA", tmp_path)
    monkeypatch.setattr(config, "OFFLINE", True)
    avisos = []
    assert iocs.carregar(avisar=avisos.append) is None and avisos
    (tmp_path / "iocs.json").write_text(json.dumps(
        {"pacotes": {"com.spy": "stalkerware X"}, "certs": {"AB": "Y"}, "hashes": {}, "atualizado": time.time()}),
        encoding="utf-8")
    i = iocs.carregar()
    assert i.checar("com.spy") == "stalkerware X"
    assert i.checar("com.outro", {"sha1": "AB"}) == "Y"


def test_certificados_oficiais(monkeypatch, tmp_path):
    monkeypatch.setattr(bases, "PASTA", tmp_path)
    assert certificados.carregar() == {}  # lista embutida começa vazia de propósito
    (tmp_path / "certificados_oficiais.yaml").write_text(
        "apps:\n  - pacote: com.banco\n    nome: Banco\n    sha256: ['ab:cd']\n", encoding="utf-8")
    oficiais = certificados.carregar()
    assert certificados.conferir("com.banco", {"sha256": "ABCD"}, oficiais) == "ok"
    assert certificados.conferir("com.banco", {"sha256": "FFFF"}, oficiais) == "falso"
    assert certificados.conferir("com.outro", {"sha256": "FFFF"}, oficiais) is None
