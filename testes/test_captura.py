"""Print da tela do celular: grava PNG, não sobrescreve, recusa o que não é imagem."""

import base64

import pytest
from test_api import H, cliente  # noqa: F401  (fixture do backend contra o ADB simulado)

from celscan.acoes import captura

PNG_FALSO = captura.PNG + b"\0" * 32


class Ap:
    def __init__(self, dados):
        self.dados = dados

    def bytes(self, cmd, timeout=30):
        assert cmd == "screencap -p"
        return self.dados


def test_grava_png_e_devolve_previa(tmp_path):
    r = captura.capturar(Ap(PNG_FALSO), tmp_path / "Prints")
    assert r["caminho"].endswith(".png")
    assert (tmp_path / "Prints").is_dir()
    assert base64.b64decode(r["png_b64"]) == PNG_FALSO
    assert r["bytes"] == len(PNG_FALSO)


def test_dois_prints_no_mesmo_segundo_nao_se_sobrescrevem(tmp_path):
    a = captura.capturar(Ap(PNG_FALSO), tmp_path)
    b = captura.capturar(Ap(PNG_FALSO), tmp_path)
    assert a["caminho"] != b["caminho"]
    assert len(list(tmp_path.glob("print_*.png"))) == 2


def test_recusa_o_que_nao_e_imagem(tmp_path):
    with pytest.raises(captura.CapturaErro):
        captura.capturar(Ap(b"error: device locked"), tmp_path)
    assert not list(tmp_path.glob("*.png"))


def test_api_captura(cliente, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CELSCAN_BACKUPS", str(tmp_path))
    r = cliente.post("/api/captura", json={"serial": "ABC123"}, headers=H)
    assert r.status_code == 200, r.text
    dados = r.json()
    assert "Prints" in dados["pasta"] and dados["caminho"].endswith(".png")
    assert base64.b64decode(dados["png_b64"]).startswith(captura.PNG)
