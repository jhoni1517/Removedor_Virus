"""Backend da interface contra o ADB simulado (em processo, com TestClient)."""

import time

import pytest
from fastapi.testclient import TestClient

from celscan.api.app import criar_app, marca_de
from celscan.core import adb
from conftest import FAKE_ADB

TOKEN = "segredo-de-teste"
H = {"X-CelScan-Token": TOKEN}


@pytest.fixture
def cliente(monkeypatch, tmp_path, apk_debug):
    monkeypatch.setenv("CELSCAN_ADB", str(FAKE_ADB))
    monkeypatch.setenv("APK_TESTE", str(apk_debug))
    monkeypatch.setenv("CELSCAN_FAKE_ESTADO", str(tmp_path / "estado"))
    monkeypatch.setattr(adb, "_ADB", None)
    with TestClient(criar_app(TOKEN, observar=False)) as c:
        yield c


def esperar(cliente, tarefa, limite=60):
    fim = time.time() + limite
    while time.time() < fim:
        t = cliente.get(f"/api/tarefas/{tarefa['id']}", headers=H).json()
        if t["estado"] != "executando":
            return t
        time.sleep(0.1)
    raise AssertionError("tarefa não terminou")


def test_exige_token_e_host_local(cliente):
    assert cliente.get("/api/estado").status_code == 401
    assert cliente.get("/api/estado", headers={"X-CelScan-Token": "errado"}).status_code == 401
    assert cliente.get("/api/estado", headers={**H, "Host": "site-malicioso.com"}).status_code == 403
    assert cliente.get("/api/estado", params={"t": TOKEN}).status_code == 200


def test_estado_e_ajuda(cliente):
    e = cliente.get("/api/estado", headers=H).json()
    assert e["adb"] is True and "rapido" in e["modos"]
    ajuda = cliente.get("/api/ajuda/conexao", headers=H).json()
    assert {"samsung", "motorola", "xiaomi", "oppo", "vivo", "generico"} <= set(ajuda["marcas"])
    assert marca_de("Xiaomi") == "xiaomi" and marca_de("realme") == "oppo" and marca_de("nokia") == "generico"


def test_varredura_remocao_e_desfazer(cliente):
    t = cliente.post("/api/varreduras", json={"serial": "ABC123", "modo": "rapido"}, headers=H).json()
    t = esperar(cliente, t)
    assert t["estado"] == "concluida", t
    res = t["resultado"]
    assert res["resultados"][0]["pacote"] == "com.systemservice"
    assert res["resultados"][0]["achados"][0]["significa"]

    detalhe = cliente.get(f"/api/varreduras/{res['varredura_id']}", headers=H).json()
    assert detalhe["nota"] == res["nota"] and len(detalhe["apps"]) == 4
    assert cliente.get("/api/varreduras", headers=H).json()[0]["id"] == res["varredura_id"]

    t = cliente.post("/api/remover", json={"serial": "ABC123", "varredura_id": res["varredura_id"],
                                           "pacotes": ["com.systemservice"]}, headers=H).json()
    t = esperar(cliente, t)
    feito = t["resultado"][0]
    assert feito["ok"] and feito["quarentena_id"]

    t = cliente.post("/api/desfazer", json={"serial": "ABC123", "quarentena_id": feito["quarentena_id"]},
                     headers=H).json()
    assert esperar(cliente, t)["resultado"]["ok"]
    assert cliente.get("/api/acoes", headers=H).json()[0]["desfeita_em"]


def test_erros_claros(cliente):
    r = cliente.post("/api/varreduras", json={"serial": "NAO_EXISTE"}, headers=H)
    assert r.status_code == 409 and "não conectado" in r.json()["detail"]
    r = cliente.post("/api/varreduras", json={"serial": "ABC123", "modo": "profundo"}, headers=H)
    assert r.status_code == 422
    r = cliente.post("/api/remover", json={"serial": "ABC123", "varredura_id": 999, "pacotes": ["x"]}, headers=H)
    assert r.status_code == 404


def test_cancelar_varredura(cliente):
    t = cliente.post("/api/varreduras", json={"serial": "ABC123"}, headers=H).json()
    cliente.post(f"/api/tarefas/{t['id']}/cancelar", headers=H)
    t = esperar(cliente, t)
    assert t["estado"] in ("cancelada", "concluida")  # pode terminar antes do cancelamento chegar


def test_config_esconde_a_chave(cliente):
    r = cliente.put("/api/config", json={"chave_virustotal": "abcdef123456"}, headers=H).json()
    assert r["chave_virustotal"] == "…3456"
    assert cliente.get("/api/estado", headers=H).json()["vt"] is True
    cliente.put("/api/config", json={"chave_virustotal": ""}, headers=H)


def test_websocket_manda_estado_e_progresso(cliente):
    with cliente.websocket_connect(f"/api/ws?t={TOKEN}") as ws:
        assert ws.receive_json()["tipo"] == "estado"
        cliente.post("/api/varreduras", json={"serial": "ABC123"}, headers=H)
        tipos = set()
        for _ in range(200):
            m = ws.receive_json()
            tipos.add(m["tipo"])
            if m["tipo"] == "tarefa" and m["tarefa"]["estado"] != "executando":
                break
        assert {"tarefa", "progresso"} <= tipos


def test_websocket_sem_token_fecha(cliente):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), cliente.websocket_connect("/api/ws?t=errado") as ws:
        ws.receive_json()


def test_wifi_qr(cliente):
    r = cliente.post("/api/wifi/qr", headers=H).json()
    assert r["texto"].startswith("WIFI:T:ADB;S:celscan-") and "<svg" in r["qr_svg"]
    cliente.post(f"/api/tarefas/{r['tarefa']['id']}/cancelar", headers=H)
    assert esperar(cliente, r["tarefa"])["estado"] in ("cancelada", "erro")


def test_servicos_mdns(monkeypatch):
    import subprocess

    from celscan.api import wifi

    saida = ("List of discovered mdns services\n"
             "celscan-Ab12Cd\t_adb-tls-pairing._tcp.\t192.168.0.20:37123\n"
             "adb-R58M123-xyz\t_adb-tls-connect._tcp.\t192.168.0.20:41555\n")
    monkeypatch.setattr(wifi.adb, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, saida, ""))
    assert wifi.servicos_mdns() == [("celscan-Ab12Cd", "_adb-tls-pairing._tcp", "192.168.0.20:37123"),
                                   ("adb-R58M123-xyz", "_adb-tls-connect._tcp", "192.168.0.20:41555")]


def test_laudo_pdf_e_verificacao(cliente):
    t = esperar(cliente, cliente.post("/api/varreduras", json={"serial": "ABC123"}, headers=H).json())
    vid = t["resultado"]["varredura_id"]
    r = cliente.get(f"/api/varreduras/{vid}/laudo.pdf", params={"t": TOKEN, "versao": "tecnico"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
    from celscan.core import db

    codigo = db.conectar().execute("SELECT hash FROM laudos WHERE varredura_id=?", (vid,)).fetchone()[0][:16]
    assert cliente.get("/api/laudos/verificar", params={"codigo": codigo}, headers=H).json()["varredura_id"] == vid
    assert cliente.get("/api/laudos/verificar", params={"codigo": "f" * 16}, headers=H).status_code == 404
    assert cliente.get(f"/api/varreduras/{vid}/laudo.pdf", params={"versao": "x"}, headers=H).status_code == 422


def test_registrar_certificados_via_api(cliente):
    t = cliente.post("/api/certificados/registrar", params={"serial": "ABC123"}, headers=H).json()
    t = esperar(cliente, t)
    assert t["estado"] == "concluida" and t["resultado"] == []  # o celular simulado não tem app de banco
    assert cliente.post("/api/certificados/registrar", params={"serial": "NAO"}, headers=H).status_code == 409


def test_reconectar(cliente):
    r = cliente.post("/api/adb/reconectar", headers=H)
    assert r.status_code == 200 and "dispositivos" in r.json()


def test_token_injetado_no_index(cliente):
    from celscan.api.app import WEB

    if not (WEB / "index.html").exists():
        pytest.skip("interface não compilada (celscan/web/dist)")
    r = cliente.get("/", headers={"Host": "127.0.0.1"})
    assert r.status_code == 200 and f'window.__CELSCAN_TOKEN__="{TOKEN}"' in r.text
