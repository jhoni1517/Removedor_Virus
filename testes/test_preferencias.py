"""Preferências e segredos. Nos testes, CELSCAN_SEM_KEYRING=1 força o fallback para o config.json."""

import json

from celscan.core import preferencias as p


def test_segredo_ida_e_volta(monkeypatch):
    monkeypatch.delenv("VT_API_KEY", raising=False)
    p.gravar_segredo("chave_virustotal", "minha-chave")
    assert p.chave_virustotal() == "minha-chave"
    p.gravar_segredo("chave_virustotal", None)  # apagar
    assert p.chave_virustotal() is None


def test_env_tem_prioridade(monkeypatch):
    p.gravar_segredo("chave_virustotal", "salva")
    monkeypatch.setenv("VT_API_KEY", "do-ambiente")
    assert p.chave_virustotal() == "do-ambiente"


def test_salvar_separa_segredo_de_preferencia(monkeypatch):
    monkeypatch.delenv("VT_API_KEY", raising=False)
    p.salvar(offline=True, tema="escuro", chave_virustotal="k123")
    dados = json.loads(p.ARQUIVO.read_text(encoding="utf-8"))
    assert dados.get("offline") is True and dados.get("tema") == "escuro"
    assert p.chave_virustotal() == "k123"
