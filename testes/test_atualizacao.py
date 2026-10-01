"""Atualização automática: ordem de versões, canal, e conferência do SHA-256."""

import hashlib

import pytest

from celscan import config
from celscan.core import atualizacao as at


def rel(tag, pre=False, digest="sha256:" + "0" * 64):
    return {"tag_name": tag, "prerelease": pre, "draft": False, "html_url": f"https://github.com/x/{tag}",
            "body": "notas", "assets": [{"name": f"CelScan-Setup-{tag.lstrip('v')}.exe", "size": 50 * 1048576,
                                         "browser_download_url": f"https://github.com/r/{tag}.exe", "digest": digest}]}


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setattr(config, "OFFLINE", False)


def test_ordem_das_versoes():
    v = ["3.0.0b4", "3.0.0b10", "3.0.0rc1", "3.0.0", "3.0.1a1", "2.9.9"]
    assert sorted(v, key=at.chave_versao) == ["2.9.9", "3.0.0b4", "3.0.0b10", "3.0.0rc1", "3.0.0", "3.0.1a1"]


def test_canal_beta_e_estavel():
    lista = [rel("v3.0.0b7", pre=True), rel("v3.0.0b6", pre=True), rel("v2.9.0")]
    assert at.verificar("beta", "3.0.0b6", lista)["versao"] == "3.0.0b7"
    assert at.verificar("estavel", "3.0.0b6", lista)["disponivel"] is False  # estável mais nova é 2.9.0
    assert at.verificar("beta", "3.0.0b7", lista)["disponivel"] is False


def test_offline_nao_consulta(monkeypatch):
    monkeypatch.setattr(config, "OFFLINE", True)
    assert at.verificar("beta", "1.0.0", [rel("v9.0.0")]) == {"disponivel": False, "motivo": "modo offline"}


class Resp:
    def __init__(self, dados, url):
        self.dados, self.url = dados, url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield self.dados


def test_baixar_confere_sha256(monkeypatch, tmp_path):
    import requests

    dados = b"instalador"
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(dados, url))
    info = {"versao": "9", "url": "https://github.com/r/x.exe", "sha256": hashlib.sha256(dados).hexdigest()}
    assert at.baixar(info, tmp_path / "ok.exe").read_bytes() == dados
    ruim = {**info, "sha256": "0" * 64}
    with pytest.raises(at.ErroAtualizacao):
        at.baixar(ruim, tmp_path / "ruim.exe")
    assert not (tmp_path / "ruim.exe").exists()
    with pytest.raises(at.ErroAtualizacao):
        at.baixar({**info, "url": "https://evil.example.com/x.exe"}, tmp_path / "x.exe")
    with pytest.raises(at.ErroAtualizacao):
        at.baixar({**info, "sha256": None}, tmp_path / "x.exe")
