"""Níveis de debloat (UAD): cumulativos e sem 'Unsafe'."""

import pytest

from celscan.acoes import otimizacao

UAD = {
    "com.operadora.app": {"removal": "Recommended", "list": "Carrier", "description": "App da operadora"},
    "com.tema": {"removal": "Advanced", "list": "Oem", "description": "Temas"},
    "com.servico": {"removal": "Expert", "list": "Oem", "description": "Serviço"},
    "com.android.systemui": {"removal": "Unsafe", "list": "Aosp", "description": "Interface"},
}


class Ap:
    def sh(self, cmd, **kw):
        return "\n".join(f"package:{p}" for p in [*UAD, "com.desconhecido"])


@pytest.fixture(autouse=True)
def _uad(monkeypatch):
    monkeypatch.setattr(otimizacao, "lista_uad", lambda forcar=False: UAD)


def pacotes(nivel):
    return [x["pacote"] for x in otimizacao.sugestoes_debloat(Ap(), nivel)]


def test_niveis_sao_cumulativos_e_sem_unsafe():
    assert pacotes("recomendado") == ["com.operadora.app"]
    assert pacotes("avancado") == ["com.operadora.app", "com.tema"]
    assert pacotes("especialista") == ["com.operadora.app", "com.tema", "com.servico"]
    assert "com.android.systemui" not in pacotes("especialista")


def test_nivel_invalido():
    with pytest.raises(ValueError):
        otimizacao.sugestoes_debloat(Ap(), "inseguro")
