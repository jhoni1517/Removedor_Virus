"""v3.2 — itens críticos: validação de pacote, apps essenciais, quarentena, APK malicioso, nomes com truque."""

import io
import json
import sqlite3
import struct
import zipfile
import zlib

import pytest

from celscan.acoes import otimizacao, quarentena, remocao
from celscan.analise import rotulos
from celscan.core import db, seguranca


@pytest.mark.parametrize("pkg", ["com.whatsapp", "android", "com.a_b.c2", "br.gov.meugovbr"])
def test_pacotes_validos(pkg):
    assert seguranca.pacote_valido(pkg)


@pytest.mark.parametrize("pkg", ["", "com.x; rm -rf /sdcard", "com.x && reboot", "$(id)", "a b", "../etc",
                                 "com..x", ".com", "com.x\n", None, 123, "x" * 300])
def test_pacotes_invalidos_nao_chegam_ao_shell(pkg):
    assert not seguranca.pacote_valido(pkg)
    with pytest.raises(ValueError):
        seguranca.exigir_pacote(pkg)


class ApNaoDeveSerChamado:
    serial = "X"

    def sh(self, *a, **k):
        raise AssertionError("não devia executar nada no aparelho")

    adb = sh


def test_remocao_recusa_injecao_e_essenciais():
    with pytest.raises(ValueError):
        remocao.remover(ApNaoDeveSerChamado(), {"pacote": "com.x; reboot"})
    ok, msg = remocao.remover(ApNaoDeveSerChamado(), {"pacote": "com.android.systemui"})
    assert not ok and "essencial" in msg
    ok, _ = remocao.remover(ApNaoDeveSerChamado(), {"pacote": "com.qualquer", "essencial": True})
    assert not ok


def test_debloat_nunca_desativa_essencial():
    assert otimizacao.desativar(ApNaoDeveSerChamado(), "com.google.android.gms") is False
    with pytest.raises(ValueError):
        otimizacao.desativar(ApNaoDeveSerChamado(), "com.x`id`")


@pytest.mark.parametrize("ident", ["../../etc", "..", "a/b", "a\\b", "", "x" * 200])
def test_quarentena_recusa_caminho_fora_da_pasta(ident):
    ok, msg = quarentena.restaurar(ApNaoDeveSerChamado(), ident)
    assert not ok and "inválido" in msg


def test_nome_com_truque_e_limpo():
    limpo, truque = seguranca.limpar_nome("Whats‮ppA​")
    assert truque and limpo == "WhatsppA"
    assert seguranca.limpar_nome("Banco\x00 Inter\n") == ("Banco Inter", False)
    assert seguranca.limpar_nome("🎮 Jogo") == ("🎮 Jogo", False)


def _zip_com_bomba(tamanho_real: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("resources.arsc", b"\0" * tamanho_real)
    return buf.getvalue()


def test_apk_com_bomba_de_descompressao_e_barrado():
    dados = _zip_com_bomba(5 * 1024 * 1024)  # 5 MB de zeros viram poucos KB comprimidos

    def ler(off, n):
        return dados[off:off + n]
    z = rotulos._ZipRemoto(ler, len(dados))
    with pytest.raises(ValueError):
        z.ler_arquivo("resources.arsc", limite=1024 * 1024)
    assert len(z.ler_arquivo("resources.arsc")) == 5 * 1024 * 1024


def test_copia_de_seguranca_do_banco(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "COPIAS", tmp_path / "copias")
    arq = tmp_path / "celscan.db"
    con = db.conectar(arq)
    con.execute("INSERT INTO aparelhos (serial, fabricante, modelo, android, primeiro_visto, ultimo_visto) "
                "VALUES ('S', 'f', 'm', '14', 'x', 'x')")
    con.commit()
    copia = db.copia_de_seguranca(arq)
    assert copia and sqlite3.connect(copia).execute("SELECT COUNT(*) FROM aparelhos").fetchone()[0] == 1
    assert db.copia_de_seguranca(arq) == copia  # só uma por dia
    assert db.copia_de_seguranca(tmp_path / "nao-existe.db") is None


def test_api_recusa_pacote_invalido_e_id_de_quarentena(monkeypatch):
    from fastapi.testclient import TestClient

    from celscan.api.app import criar_app
    with TestClient(criar_app("tok", observar=False)) as c:
        h = {"x-celscan-token": "tok"}
        r = c.post("/api/permissoes", json={"serial": "X", "pacote": "com.x;reboot", "acoes": ["parar"]}, headers=h)
        assert r.status_code == 422
        r = c.post("/api/desfazer", json={"serial": "X", "quarentena_id": "../../x"}, headers=h)
        assert r.status_code == 422
        r = c.post("/api/remover", json={"serial": "X", "varredura_id": 1, "pacotes": ["a b"]}, headers=h)
        assert r.status_code == 422


def test_host_de_teste_nao_vale_fora_do_pytest(monkeypatch):
    from fastapi.testclient import TestClient

    from celscan.api.app import criar_app
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with TestClient(criar_app("tok", observar=False)) as c:
        assert c.get("/api/estado", headers={"x-celscan-token": "tok"}).status_code == 403


_ = (json, struct, zlib)
