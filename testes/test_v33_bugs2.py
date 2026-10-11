"""Caçada de bugs 2 (3.3.0b2): cada teste reproduz um problema encontrado na revisão."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from celscan.acoes import backup, quarentena, recuperacao, remocao


@pytest.fixture(autouse=True)
def quarentena_temporaria(tmp_path, monkeypatch):
    monkeypatch.setattr(quarentena, "DIRQ", tmp_path / "q")


class Ap:
    serial = "ABC123"

    def __init__(self, respostas=None):
        self.respostas, self.cmds = respostas or {}, []

    def sh(self, cmd, timeout=120, erro=False):
        self.cmds.append(cmd)
        for k, v in self.respostas.items():
            if cmd.startswith(k):
                if isinstance(v, Exception):
                    raise v
                return v
        return ""

    def adb(self, *args, timeout=120, erro=False):
        self.cmds.append("adb " + " ".join(args))
        if args[0] == "pull":
            Path(args[2]).write_bytes(b"1234567")
            return "1 file pulled"
        return self.respostas.get("adb " + args[0], "Success")


# ---------------------------------------------------------------- backup / recuperação
def test_pastas_do_whatsapp_nao_se_misturam_no_pc():
    rotulos = [backup._rotulo_raiz("whatsapp_midia", r) for r in backup.CATEGORIAS["whatsapp_midia"][1]]
    assert len(set(rotulos)) == len(rotulos)
    a = backup.Arquivo("whatsapp_midia", "/sdcard/WhatsApp/Media/x.jpg", 1, 1)
    b = backup.Arquivo("whatsapp_midia", "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/x.jpg", 1, 1)
    assert backup.destino_local(Path("/b"), a) != backup.destino_local(Path("/b"), b)


def test_nomes_reservados_do_windows():
    assert backup.nome_seguro("CON.jpg") == "_CON.jpg" and backup.nome_seguro("nul") == "_nul"
    assert backup.nome_seguro("Console.jpg") == "Console.jpg"


def test_recuperados_com_mesmo_nome_e_data_nao_colidem():
    a = backup.Arquivo("miniaturas", "/sdcard/DCIM/.thumbnails/1.jpg", 1, 100)
    b = backup.Arquivo("miniaturas", "/sdcard/Pictures/.thumbnails/1.jpg", 1, 100)
    assert recuperacao.destino_recuperado(Path("/r"), a) != recuperacao.destino_recuperado(Path("/r"), b)


# ---------------------------------------------------------------- remoção
def test_app_esquecido_sai_mantendo_os_dados():
    ap = Ap({"pm uninstall": "Success"})
    ok, _ = remocao.remover(ap, {"pacote": "com.whatsapp", "manter_dados": True, "admins": []})
    assert ok and "pm uninstall -k --user 0 com.whatsapp" in ap.cmds
    assert not any(c.startswith("adb uninstall") for c in ap.cmds)


def test_debloat_que_falha_nao_deixa_item_incompleto():
    from celscan.acoes import otimizacao
    assert otimizacao.desativar(Ap({"pm disable-user": "erro", "pm uninstall": "Failure"}), "com.x") is False
    assert quarentena.listar() == []


def test_animacoes_fora_da_faixa():
    from celscan.acoes import otimizacao
    for ruim in ("nan", "inf", -1, 11):
        with pytest.raises(ValueError):
            otimizacao.animacoes(Ap(), ruim)


# ---------------------------------------------------------------- Agente
def test_agente_e_removido_se_der_erro_depois_de_instalar(monkeypatch, tmp_path):
    from celscan.core import adb as adb_mod
    from celscan.core import agente
    apk = tmp_path / "a.apk"
    apk.write_bytes(b"x")
    monkeypatch.setattr(agente, "apk", lambda: apk)
    ap = Ap({"content query": adb_mod.AdbErro("cabo caiu")})
    with pytest.raises(adb_mod.AdbErro), agente.Agente(ap):
        pass
    assert any(c == f"adb uninstall {agente.PACOTE}" for c in ap.cmds)


# ---------------------------------------------------------------- espelho (scrcpy)
def test_stderr_do_scrcpy_e_drenado():
    from celscan.acoes import espelho
    p = subprocess.Popen([sys.executable, "-c", "import sys\nfor i in range(20000): sys.stderr.write('x'*40+'\\n')"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    s = espelho.Sessao(None, "ver", p)
    espelho._drenar(s)
    assert p.wait(timeout=10) == 0 and len(s.log) == 200 and s.log_fechado.is_set()


# ---------------------------------------------------------------- iPhone
def test_iphone_travado_nao_prende_para_sempre(monkeypatch):
    from celscan.ios import mvt

    def lento(*a, **k):
        raise subprocess.TimeoutExpired("ideviceinfo", 1)
    monkeypatch.setattr(mvt.subprocess, "run", lento)
    with pytest.raises(mvt.IOSErro):
        mvt._run(["ideviceinfo"], timeout=1)


# ---------------------------------------------------------------- API
@pytest.fixture
def api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from celscan.api.app import criar_app
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
    monkeypatch.setenv("CELSCAN_BACKUPS", str(tmp_path / "bk"))
    app = criar_app("T", observar=False)
    return app, TestClient(app, raise_server_exceptions=False), {"x-celscan-token": "T"}


def test_wifi_rejeita_endereco_que_vira_opcao_do_adb(api):
    _, c, h = api
    assert c.post("/api/wifi/parear", json={"endereco": "-H evil", "codigo": "123456"}, headers=h).status_code == 422
    assert c.post("/api/wifi/parear", json={"endereco": "1.2.3.4:5555", "codigo": "12"}, headers=h).status_code == 422
    assert c.post("/api/wifi/conectar", json={"endereco": "--help"}, headers=h).status_code == 422


def test_categoria_invalida_e_recusada_na_hora(api):
    _, c, h = api
    for rota in ("/api/recuperacao/procurar", "/api/backup/listar"):
        assert c.post(rota, json={"serial": "X", "categorias": ["zzz"]}, headers=h).status_code == 422


def test_abrir_pasta_nunca_abre_arquivo(api, tmp_path):
    _, c, h = api
    arq = tmp_path / "bk" / "Downloads" / "virus.exe"
    arq.parent.mkdir(parents=True)
    arq.write_bytes(b"MZ")
    assert c.post("/api/abrir-pasta", json={"caminho": str(arq)}, headers=h).status_code == 422


def test_reiniciar_bloqueado_com_operacao_em_andamento(api, monkeypatch):
    import threading
    app, c, h = api
    trava = threading.Event()
    app.state.tarefas.criar("backup", "ABC123", lambda p, cancelar: trava.wait(5))
    monkeypatch.setattr(app.state.aparelhos, "pronto", lambda serial: Ap())
    r = c.post("/api/energia/reiniciar", json={"serial": "ABC123", "modo": "normal"}, headers=h)
    trava.set()
    assert r.status_code == 409


def test_websocket_fechado_deixa_de_ouvir(api):
    app, c, _ = api
    with c.websocket_connect("/api/ws?t=T") as ws:
        ws.receive_json()
        assert len(app.state.tarefas._ouvintes) == 1
    for _ in range(50):
        if not app.state.tarefas._ouvintes:
            break
        time.sleep(0.05)
    assert app.state.tarefas._ouvintes == []
