"""Tela quebrada: espelhamento (scrcpy) e cópia dos dados para o PC."""

import hashlib
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from celscan.acoes import backup
from celscan.acoes.espelho import Espelhos, OpcoesEspelho, montar_comando
from celscan.api.app import criar_app
from celscan.core import adb
from celscan.core.adb import Aparelho
from conftest import FAKE_ADB

FAKE_SCRCPY = Path(__file__).resolve().parent / "fake_scrcpy.py"
TOKEN = "t"
H = {"X-CelScan-Token": TOKEN}


@pytest.fixture
def fake(monkeypatch, tmp_path, apk_debug):
    monkeypatch.setenv("CELSCAN_ADB", str(FAKE_ADB))
    monkeypatch.setenv("APK_TESTE", str(apk_debug))
    monkeypatch.setenv("CELSCAN_SCRCPY", str(FAKE_SCRCPY))
    monkeypatch.setenv("CELSCAN_FAKE_ESTADO", str(tmp_path / "estado"))
    monkeypatch.setattr(adb, "_ADB", None)
    monkeypatch.setattr(backup, "pasta_padrao", lambda: tmp_path / "Backups")
    return tmp_path


def test_montar_comando():
    base = ["s", "--window-title", "CelScan - tela do celular"]
    assert montar_comando("s", "X", OpcoesEspelho()) == [*base, "--serial", "X", "--stay-awake"]
    assert montar_comando("s", "X", OpcoesEspelho(modo="ver")) == [*base, "--serial", "X", "--no-control"]
    cmd = montar_comando("s", "X", OpcoesEspelho(tela_desligada=True, gravar="a.mp4", acordado=False))
    assert cmd[-3:] == ["--turn-screen-off", "--record", "a.mp4"]
    assert montar_comando("s", None, OpcoesEspelho(modo="otg")) == [*base, "--otg"]
    with pytest.raises(ValueError):
        montar_comando("s", "X", OpcoesEspelho(modo="x"))


def test_montar_comando_compativel():
    cmd = montar_comando("s", "X", OpcoesEspelho.compativel())
    assert "--max-size" in cmd and "1280" in cmd
    assert "--max-fps" in cmd and "30" in cmd
    assert cmd[cmd.index("--display-buffer") + 1] == "120"
    assert cmd[cmd.index("--video-codec") + 1] == "h264"
    assert "--no-audio" in cmd


def test_montar_comando_opcoes_avulsas():
    cmd = montar_comando("s", "X", OpcoesEspelho(bitrate_mbps=4, ligar_tela=False))
    assert cmd[cmd.index("--video-bit-rate") + 1] == "4M"
    assert "--no-power-on" in cmd


def test_espelho_abre_e_para(fake):
    esp = Espelhos()
    s = esp.abrir("ABC123", OpcoesEspelho())
    assert esp.erro_inicial(s, espera=0.5) is None and s.ativa
    assert esp.ativas() == [{"serial": "ABC123", "modo": "controlar"}]
    assert esp.parar("ABC123") and not esp.ativas()


def test_espelho_erro_do_scrcpy_aparece(fake, monkeypatch):
    monkeypatch.setenv("CELSCAN_FAKE_SCRCPY_ERRO", "1")
    esp = Espelhos()
    assert "unauthorized" in esp.erro_inicial(esp.abrir("ABC123", OpcoesEspelho()), espera=5)


def test_listar_e_copiar_com_retomada(fake):
    ap = Aparelho("ABC123")
    arquivos = backup.listar(ap, ["fotos", "whatsapp_midia", "whatsapp_backup", "downloads"])
    assert len(arquivos) == 5 and sum(a.tamanho for a in arquivos) == 2048 + 4096 + 300 + 700 + 512
    resumo = backup.resumo_listagem(arquivos)
    assert resumo["fotos"]["arquivos"] == 2 and resumo["imagens"]["arquivos"] == 0

    raiz = fake / "Backups" / "moto"
    eventos = []
    r = backup.copiar(ap, arquivos, raiz, eventos.append, verificar_hash=True, info={"modelo": "moto"})
    assert r.copiados == 5 and not r.falhas and eventos[-1]["atual"] == 5
    foto = raiz / "Fotos e vídeos" / "Camera" / "IMG_20260901_101010.jpg"
    zap = raiz / "WhatsApp - mídia" / "WhatsApp" / "WhatsApp Images" / "IMG-20260903-WA0001.jpg"
    assert zap.exists() and (raiz / "WhatsApp - backup das conversas" / "WhatsApp" / "msgstore.db.crypt14").exists()
    esperado = hashlib.sha256((b"/sdcard/DCIM/Camera/IMG_20260901_101010.jpg" * 100)[:2048]).hexdigest()
    assert hashlib.sha256(foto.read_bytes()).hexdigest() == esperado
    assert int(foto.stat().st_mtime) == 1727600000  # data original preservada
    assert (raiz / "LEIA-ME.txt").exists() and (raiz / "relatorio_backup.json").exists()
    assert not list(raiz.rglob("*.parcial"))

    foto.unlink()  # simula cópia interrompida: rodar de novo só copia o que falta
    r2 = backup.copiar(ap, arquivos, raiz)
    assert r2.copiados == 1 and r2.pulados == 4


def test_copiar_cancelado_explica_retomada(fake):
    from celscan.servicos import Cancelado

    cancelar = threading.Event()
    cancelar.set()
    ap = Aparelho("ABC123")
    with pytest.raises(Cancelado, match="rode de novo"):
        backup.copiar(ap, backup.listar(ap, ["fotos"]), fake / "b", cancelar=cancelar)


def test_nome_seguro_windows():
    assert backup.nome_seguro('a:b*c?"d') == "a_b_c__d"


def test_pastas_curtas_no_pc(tmp_path):
    a = backup.Arquivo("audio", "/sdcard/Recordings/Call/gravacao.m4a", 1, 0)
    assert backup.destino_local(tmp_path, a) == tmp_path / "Áudio" / "Recordings" / "Call" / "gravacao.m4a"
    b = backup.Arquivo("whatsapp_midia", "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Media/x.jpg", 1, 0)
    assert backup.destino_local(tmp_path, b) == tmp_path / "WhatsApp - mídia" / "WhatsApp Business" / "x.jpg"


def esperar(cliente, tarefa):
    for _ in range(300):
        t = cliente.get(f"/api/tarefas/{tarefa['id']}", headers=H).json()
        if t["estado"] != "executando":
            return t
        time.sleep(0.05)
    raise AssertionError("tarefa não terminou")


def test_api_resgate(fake):
    with TestClient(criar_app(TOKEN, observar=False)) as c:
        guia = c.get("/api/resgate", headers=H).json()
        assert {"autorizado", "toque", "imagem", "morto"} <= set(guia["casos"])
        assert c.get("/api/espelho", headers=H).json()["disponivel"] is True

        r = c.post("/api/espelho", json={"serial": "ABC123", "gravar": True}, headers=H).json()
        assert r["ok"] and r["gravacao"].endswith(".mp4")
        assert c.get("/api/espelho", headers=H).json()["ativas"][0]["serial"] == "ABC123"
        assert c.post("/api/espelho/parar", json={"serial": "ABC123"}, headers=H).json()["parado"]
        assert c.post("/api/espelho", json={"serial": "NAO_EXISTE"}, headers=H).status_code == 409

        assert "desenvolvedor" in c.get("/api/ajustes", headers=H).json()
        r = c.post("/api/ajustes/abrir", json={"serial": "ABC123", "ajuste": "desenvolvedor"}, headers=H).json()
        assert "desenvolvedor" in r["aberto"].lower()
        assert c.post("/api/ajustes/abrir", json={"serial": "ABC123", "ajuste": "xxx"},
                      headers=H).status_code == 422

        lista = esperar(c, c.post("/api/backup/listar", json={"serial": "ABC123"}, headers=H).json())
        assert lista["resultado"]["total_arquivos"] == 6
        t = esperar(c, c.post("/api/backup/copiar", json={"serial": "ABC123", "categorias": ["fotos"]},
                              headers=H).json())
        assert t["estado"] == "concluida" and t["resultado"]["copiados"] == 2
        destino = Path(t["resultado"]["destino"])
        assert (destino / "apps_instalados.txt").read_text(encoding="utf-8").startswith("com.")
        assert c.post("/api/abrir-pasta", json={"caminho": os.path.expanduser("~")}, headers=H).status_code == 403


def test_api_espelho_otg_pausa_o_adb(fake):
    with TestClient(criar_app(TOKEN, observar=False)) as c:
        pausa = c.app.state.aparelhos.pausa
        r = c.post("/api/espelho", json={"modo": "otg"}, headers=H).json()
        assert r["ok"] and pausa.is_set()  # adb solta a porta USB enquanto o modo mouse está aberto
        c.post("/api/espelho/parar", json={"modo": "otg"}, headers=H)
        for _ in range(100):
            if not pausa.is_set():
                break
            time.sleep(0.05)
        assert not pausa.is_set()  # fechou o modo mouse: volta a vigiar os aparelhos
        assert "--otg" in (fake / "estado" / "scrcpy.log").read_text(encoding="utf-8")


def test_permissoes_aplicar_e_desfazer(fake):
    from celscan.acoes import permissoes, quarentena
    from celscan.core.adb import Aparelho

    ap = Aparelho("ABC123")  # fake_adb responde settings/appops
    r = permissoes.aplicar(ap, "com.systemservice", ["acessibilidade", "sobreposicao", "parar"],
                           ["android.permission.READ_SMS"])
    assert r["quarentena_id"] and "Forçar a parada do app agora" in r["feitas"]
    log = (fake / "estado" / "comandos.log").read_text(encoding="utf-8")
    assert "appops set com.systemservice SYSTEM_ALERT_WINDOW ignore" in log
    assert "pm revoke com.systemservice android.permission.READ_SMS" in log
    item = next(m for m in quarentena.listar() if m["id"] == r["quarentena_id"])
    tipos = {a["tipo"] for a in item["ajustes"]}
    assert {"settings", "appops", "permissao"} <= tipos
    ok, _ = quarentena.restaurar(ap, r["quarentena_id"])
    assert ok
    log2 = (fake / "estado" / "comandos.log").read_text(encoding="utf-8")
    assert "pm grant com.systemservice android.permission.READ_SMS" in log2


def test_permissoes_acao_invalida(fake):
    from celscan.acoes import permissoes
    from celscan.core.adb import Aparelho

    with pytest.raises(ValueError):
        permissoes.aplicar(Aparelho("ABC123"), "com.x", ["voar"])
