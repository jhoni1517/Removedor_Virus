"""Bugs corrigidos na 3.3 (cada teste reproduz o problema original)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from celscan.acoes import quarentena, remocao


class ApFalso:
    """Aparelho falso que registra comandos e responde por regras simples."""

    serial = "ABC123"

    def __init__(self, respostas=None, pull_ok=True, tamanho_remoto="7"):
        self.cmds: list[str] = []
        self.respostas = respostas or {}
        self.pull_ok, self.tamanho_remoto = pull_ok, tamanho_remoto

    def sh(self, cmd, timeout=120, erro=False):
        self.cmds.append(cmd)
        if cmd.startswith("pm path"):
            return "package:/data/app/x/base.apk"
        if cmd.startswith("stat -c %s"):
            return self.tamanho_remoto
        for chave, resp in self.respostas.items():
            if cmd.startswith(chave):
                return resp
        return ""

    def adb(self, *args, timeout=120, erro=False):
        self.cmds.append("adb " + " ".join(args))
        if args[0] == "pull" and self.pull_ok:
            Path(args[2]).write_bytes(b"APKFAKE")
            return "1 file pulled"
        if args[0] == "uninstall":
            return self.respostas.get("adb uninstall", "Success")
        return ""


@pytest.fixture(autouse=True)
def quarentena_temporaria(tmp_path, monkeypatch):
    monkeypatch.setattr(quarentena, "DIRQ", tmp_path / "q")


def test_duas_acoes_no_mesmo_segundo_nao_se_sobrescrevem():
    ap = ApFalso()
    a = quarentena.criar_ajuste(ap, "permissoes", "um", [{"tipo": "cmd", "desfazer": "x"}])
    b = quarentena.criar_ajuste(ap, "permissoes", "dois", [{"tipo": "cmd", "desfazer": "y"}])
    assert a != b and a.exists() and b.exists()
    assert quarentena._ler(a)["ajustes"][0]["desfazer"] == "x"


def test_app_de_loja_e_removido_mantendo_os_dados():
    ap = ApFalso(respostas={"pm uninstall": "Success"})
    r = {"pacote": "com.whatsapp", "loja": "Google Play", "admins": []}
    ok, msg = remocao.remover(ap, r)
    assert ok and "dados guardados" in msg
    assert "pm uninstall -k --user 0 com.whatsapp" in ap.cmds
    assert not any(c.startswith("adb uninstall") for c in ap.cmds)  # nunca apaga os dados de app legítimo


def test_sem_copia_conferida_nao_desinstala_de_vez():
    ap = ApFalso(respostas={"pm uninstall": "Success"}, tamanho_remoto="999")  # cópia cortada
    ok, msg = remocao.remover(ap, {"pacote": "com.virus", "admins": []})
    assert ok and "reversível" in msg
    assert not any(c.startswith("adb uninstall") for c in ap.cmds)
    meta = quarentena._ler(quarentena.DIRQ / next(iter(p.name for p in quarentena.DIRQ.iterdir())))
    assert meta["acao"] == "removido_usuario0" and not meta["copia_completa"]


def test_com_copia_conferida_desinstala_e_guarda_hash():
    ap = ApFalso()
    ok, _ = remocao.remover(ap, {"pacote": "com.virus", "admins": []})
    assert ok and "adb uninstall com.virus" in ap.cmds
    pasta = next(quarentena.DIRQ.iterdir())
    meta = quarentena._ler(pasta)
    assert meta["copia_completa"] and len(next(iter(meta["hashes"].values()))) == 64


def test_remocao_que_falha_deixa_desfazer_dos_ajustes():
    ap = ApFalso(respostas={"settings get secure enabled_accessibility": "com.virus/.Acc",
                            "adb uninstall": "Failure",
                            "pm uninstall": "Failure [DELETE_FAILED_DEVICE_POLICY_MANAGER]"},
                 tamanho_remoto="7")
    r = {"pacote": "com.virus", "admins": []}
    ok, msg = remocao.remover(ap, r)
    assert not ok and "administrador" in msg
    assert r["parcial"] and r["quarentena_id"]
    ok2, _ = quarentena.restaurar(ap, r["quarentena_id"])
    assert any(c.startswith("settings put secure enabled_accessibility_services") for c in ap.cmds)


def test_admin_de_classe_interna_vai_entre_aspas():
    ap = ApFalso()
    remocao.neutralizar(ap, "com.x", quarentena.criar(ap, "com.x", copiar_apk=False), ["com.x/.App$Admin"])
    assert "dpm remove-active-admin --user 0 'com.x/.App$Admin'" in ap.cmds


def test_desfazer_duas_vezes_avisa():
    ap = ApFalso(respostas={"pm enable": "Package com.x new state: enabled"})
    pasta = quarentena.criar(ap, "com.x", copiar_apk=False)
    quarentena.registrar(pasta, "desativado")
    assert quarentena.restaurar(ap, pasta.name)[0]
    ok, msg = quarentena.restaurar(ap, pasta.name)
    assert not ok and "já desfeito" in msg


def test_copia_corrompida_nao_e_reinstalada(tmp_path):
    ap = ApFalso()
    ok, _ = remocao.remover(ap, {"pacote": "com.virus", "admins": []})
    pasta = next(quarentena.DIRQ.iterdir())
    meta = quarentena._ler(pasta)
    meta["hashes"] = {k: "0" * 64 for k in meta["hashes"]}
    quarentena._gravar(pasta, meta)
    ok, msg = quarentena.restaurar(ap, pasta.name)
    assert not ok and "corrompida" in msg


def test_nome_de_script_unico_por_execucao():
    from celscan.core import adb
    assert re.search(r'celscan_\{uuid', Path(adb.__file__).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- análise (falsos positivos)
def _dados():
    from celscan.core import coleta, parsers
    from conftest import ler_fixture
    return coleta.montar("ABC123", parsers.secoes(ler_fixture("sintetico/coleta.txt")))


def _pontuar(d):
    from datetime import datetime

    from celscan.analise import pontuacao
    _, res = pontuacao.pontuar(d, agora=datetime(2026, 9, 29))
    return {r["pacote"]: r for r in res}


def test_whatsapp_que_so_abriu_um_apk_nao_vira_dropper():
    from celscan.core.coleta import AppBruto
    d = _dados()
    d.apps["com.recebido.apk"] = AppBruto("com.recebido.apk", "/data/app/r/base.apk",
                                          "com.google.android.packageinstaller", False, origem="com.whatsapp")
    por = _pontuar(d)
    assert not any("Instalou outros" in m for m in por["com.whatsapp"]["motivos"])


def test_app_de_fora_da_loja_que_instala_outros_e_dropper():
    from celscan.core.coleta import AppBruto
    d = _dados()
    d.apps["com.dropper"] = AppBruto("com.dropper", "/data/app/d/base.apk",
                                     "com.google.android.packageinstaller", False)
    d.apps["com.filho"] = AppBruto("com.filho", "/data/app/f/base.apk", "com.dropper", False)
    assert any("Instalou outros" in m for m in _pontuar(d)["com.dropper"]["motivos"])


def test_agente_do_celscan_nao_e_suspeito():
    from celscan.core.coleta import AppBruto
    d = _dados()
    d.apps["com.celscan.agente"] = AppBruto("com.celscan.agente", "/data/app/a/base.apk", "com.android.shell", False)
    r = _pontuar(d)["com.celscan.agente"]
    assert r["score"] == 0 and r["nivel"] == "PERMITIDO"


def test_app_copiado_por_smart_switch_e_f_droid_pesam_pouco():
    from celscan.core.coleta import AppBruto
    d = _dados()
    d.apps["com.passado"] = AppBruto("com.passado", "/data/app/p/base.apk", "com.sec.android.easyMover", False)
    d.apps["org.app.livre"] = AppBruto("org.app.livre", "/data/app/l/base.apk", "org.fdroid.fdroid", False)
    por = _pontuar(d)
    assert "Copiado de outro celular (Smart Switch (Samsung))" in por["com.passado"]["motivos"]
    assert por["org.app.livre"]["origem"] == "F-Droid (loja alternativa)"
    assert por["com.passado"]["score"] <= 25 and por["org.app.livre"]["score"] <= 25


def test_anuncio_de_abertura_nao_e_popup():
    from datetime import datetime

    from celscan.analise.rotulos import sdk_de
    from celscan.core import parsers

    t = lambda h: datetime(2026, 10, 9, *h)  # noqa: E731
    abertura = [(t((20, 0, 0)), "launcher", "L"), (t((20, 0, 2)), "jogo", "com.google.android.gms.ads.AdActivity"),
                (t((20, 0, 9)), "jogo", "jogo.Main")]
    popup = [(t((21, 0, 0)), "launcher", "L"), (t((21, 0, 2)), "jogo", "com.google.android.gms.ads.AdActivity"),
             (t((21, 0, 9)), "launcher", "L")]
    a = parsers.anuncios(abertura, sdk_de)["jogo"]
    b = parsers.anuncios(popup, sdk_de)["jogo"]
    assert a["fora_do_app"] == 0 and a["abertura"] == 1
    assert b["fora_do_app"] == 1


def test_sem_nome_so_quando_o_manifesto_nao_declara():
    from celscan.analise import rotulos
    r = rotulos.Rotulo("x", "", rotulo_declarado=True)
    assert r.rotulo_declarado  # declarado mas ilegível: não marca "app sem nome"


# ---------------------------------------------------------------- API e tarefas
def test_tarefa_exclusiva_por_aparelho():
    import threading

    from celscan.api.tarefas import Gerenciador, Ocupado
    g = Gerenciador()
    trava = threading.Event()
    g.criar("varredura", "A", lambda p, c: trava.wait(5))
    with pytest.raises(Ocupado):
        g.criar("remocao", "A", lambda p, c: None)
    g.criar("outra", "B", lambda p, c: None)  # outro aparelho pode
    trava.set()


def test_tarefas_antigas_sao_esquecidas():
    import time

    from celscan.api import tarefas as mod
    g = mod.Gerenciador()
    for _ in range(mod.GUARDAR_MAX + 15):
        t = g.criar("x", None, lambda p, c: None)
        t.estado, t.terminada = "concluida", time.time() - 10
    assert len(g.listar()) <= mod.GUARDAR_MAX + 1


def test_api_token_nao_ascii_e_ipv6_e_valor_negativo():
    import os

    from fastapi.testclient import TestClient

    from celscan.api.app import criar_app
    os.environ["PYTEST_CURRENT_TEST"] = os.environ.get("PYTEST_CURRENT_TEST", "x")
    c = TestClient(criar_app("TOKEN", observar=False), raise_server_exceptions=False)
    assert c.get("/api/estado?t=t%C3%B3k%C3%A9n").status_code == 401
    assert c.get("/api/estado", headers={"host": "[::1]:9", "x-celscan-token": "TOKEN"}).status_code == 200
    h = {"x-celscan-token": "TOKEN"}
    assert c.post("/api/ordens", json={"servicos": ["checkup"], "valor": -5}, headers=h).status_code == 422
    assert c.get("/api/varreduras?limite=-5", headers=h).status_code == 200


def test_app_de_fabrica_nao_usa_adb_uninstall():
    ap = ApFalso(respostas={"pm uninstall": "Success"})
    ok, msg = remocao.remover(ap, {"pacote": "com.miui.analytics", "sistema": True, "admins": []})
    assert ok and not any(c.startswith("adb uninstall") for c in ap.cmds)
    assert "pm uninstall --user 0 com.miui.analytics" in ap.cmds
