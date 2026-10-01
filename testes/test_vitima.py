"""Modo proteção à vítima: aviso obrigatório antes de remover app espião e relatório de evidências."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from celscan.api.app import criar_app
from celscan.core import adb, db
from conftest import FAKE_ADB

TOKEN = "t"
H = {"X-CelScan-Token": TOKEN}


@pytest.fixture
def cliente(monkeypatch, tmp_path, apk_debug):
    monkeypatch.setenv("CELSCAN_ADB", str(FAKE_ADB))
    monkeypatch.setenv("APK_TESTE", str(apk_debug))
    monkeypatch.setenv("CELSCAN_FAKE_ESTADO", str(tmp_path / "estado"))
    monkeypatch.setenv("CELSCAN_BACKUPS", str(tmp_path / "backups"))
    monkeypatch.setattr(adb, "_ADB", None)
    with TestClient(criar_app(TOKEN, observar=False)) as c:
        yield c


def esperar(c, t, limite=30):
    fim = time.time() + limite
    while time.time() < fim:
        r = c.get(f"/api/tarefas/{t['id']}", headers=H).json()
        if r["estado"] != "executando":
            return r
        time.sleep(0.05)
    raise AssertionError("tarefa não terminou")


def _varredura_com_espiao():
    info = {"fabricante": "Xiaomi", "modelo": "Teste", "android": "14", "patch_seguranca": "2026-01-01",
            "serial": "ABC123"}
    apps = [{"pacote": "com.systemservice", "nome": "System Service", "ameaca": "stalkerware TheTruthSpy",
             "score": 100, "nivel": "ALTO", "motivos": [], "achados": [], "versao": "1.0",
             "instalado": "2026-09-20T10:00:00", "instalador": "com.google.android.packageinstaller",
             "sha256": "ab" * 32, "sistema": False}]
    return db.salvar_varredura(db.conectar(), info, 20, "Crítico", [], apps)


def test_remover_espiao_exige_ciencia(cliente):
    vid = _varredura_com_espiao()
    r = cliente.post("/api/remover", json={"serial": "ABC123", "varredura_id": vid,
                                           "pacotes": ["com.systemservice"]}, headers=H)
    assert r.status_code == 409 and "MODO_VITIMA" in r.json()["detail"]
    r = cliente.post("/api/remover", json={"serial": "ABC123", "varredura_id": vid,
                                           "pacotes": ["com.systemservice"], "ciente_vitima": True}, headers=H)
    assert r.status_code == 200


def test_apoio_tem_ligue_180(cliente):
    apoio = cliente.get("/api/apoio", headers=H).json()
    assert any(c["contato"] == "180" for c in apoio["contatos"])


def test_evidencias_com_manifesto(cliente):
    vid = _varredura_com_espiao()
    t = esperar(cliente, cliente.post("/api/evidencias", json={"serial": "ABC123", "varredura_id": vid,
                                                                "pacotes": ["com.systemservice"]}, headers=H).json())
    assert t["estado"] == "concluida", t
    pasta = Path(t["resultado"]["pasta"])
    nomes = set(t["resultado"]["arquivos"])
    assert {"resumo.json", "LEIA-ME.txt"} <= nomes and any(n.startswith("tela_") for n in nomes)
    manifesto = (pasta / "MANIFESTO.sha256").read_text(encoding="utf-8")
    assert all(n in manifesto for n in nomes)  # cada arquivo tem seu hash
    assert "Ligue 180" in (pasta / "LEIA-ME.txt").read_text(encoding="utf-8")
