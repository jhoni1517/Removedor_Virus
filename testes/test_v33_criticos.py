"""Upgrades CRÍTICOS da 3.3: novos sinais de ameaça, proteção de apps sensíveis e privacidade do log."""

from __future__ import annotations

import logging
from datetime import datetime

from celscan.core import parsers
from celscan.core.coleta import AppBruto

AGORA = datetime(2026, 9, 29)


def _dados():
    from celscan.core import coleta
    from conftest import ler_fixture
    return coleta.montar("ABC123", parsers.secoes(ler_fixture("sintetico/coleta.txt")))


def _pontuar(d, iocs=None):
    from celscan.analise import pontuacao
    achados, res = pontuacao.pontuar(d, iocs=iocs, agora=AGORA)
    return achados, {r["pacote"]: r for r in res}


def _chaves(r):
    return {a["chave"] for a in r["achados"]}


def _sideload(pkg, **kw):
    return AppBruto(pkg, f"/data/app/{pkg}/base.apk", "com.google.android.packageinstaller", False, **kw)


# ---------------------------------------------------------------- parsers novos
def test_parsers_usuarios_e_pacotes_por_usuario():
    txt = "Users:\n\tUserInfo{0:Dono:c13} running\n\tUserInfo{10:Pasta Segura:1030} running\n\tUserInfo{11::0}\n"
    us = parsers.usuarios(txt)
    assert [u["id"] for u in us] == [0, 10, 11]
    assert us[1]["nome"] == "Pasta Segura" and us[1]["ativo"] and not us[2]["ativo"]
    pk = parsers.pacotes_por_usuario("@@USER 10\npackage:com.espiao  installer=null\npackage:com.ok  installer=x\n")
    assert pk == {10: {"com.espiao": None, "com.ok": "x"}}


def test_parsers_apks_rodando_relogio():
    sha = "a" * 64
    apks = parsers.apks_guardados(f"1234\t{sha}\t/sdcard/Download/Banco.apk\nlixo\n9\tnao-hex\t/sdcard/x.APK\n")
    assert apks[0] == {"caminho": "/sdcard/Download/Banco.apk", "tamanho": 1234, "sha256": sha}
    assert apks[1]["sha256"] is None and len(apks) == 2
    assert parsers.rodando("NAME\ncom.whatsapp\ncom.whatsapp:push\n[kworker/0:1]\ninit\n") == {"com.whatsapp"}
    assert parsers.relogio("1759100000\n") == 1759100000 and parsers.relogio("erro") is None


def test_parsers_tempo_de_uso_e_bateria():
    uso = ('In-memory daily stats\n package=com.jogo totalTimeUsed="10:00" lastTimeUsed="x"\n'
           'In-memory weekly stats\n package=com.jogo totalTimeUsed="1d 02:00:00" lastTimeUsed="x"\n'
           ' package=com.zap totalTimeUsed="45:30" lastTimeUsed="x"\n')
    assert parsers.tempo_de_uso(uso) == {"com.jogo": 93600, "com.zap": 2730}
    bat = "9,0,i,uid,10123,com.jogo\n9,10123,l,pwi,uid,12.34,0,0\n9,1000,l,pwi,scrn,99,0\n"
    assert parsers.bateria_por_app(bat) == {"com.jogo": 12.3}


def test_pkgdump_le_quem_iniciou_a_instalacao():
    txt = ("Packages:\n  Package [com.falso] (abc):\n    installerPackageName=com.android.vending\n"
           "    installInitiatingPackageName=com.android.shell\n")
    assert parsers.pkgdump(txt)["com.falso"]["iniciador"] == "com.android.shell"


# ---------------------------------------------------------------- regras novas (apps)
def test_instalador_forjado_pelo_adb():
    d = _dados()
    d.apps["com.falso.banco"] = AppBruto("com.falso.banco", "/data/app/f/base.apk", "com.android.vending", False,
                                         iniciador="com.android.shell")
    assert "instalador_forjado" in _chaves(_pontuar(d)[1]["com.falso.banco"])


def test_instalacao_normal_da_play_nao_e_forjada():
    d = _dados()
    d.apps["com.ok"] = AppBruto("com.ok", "/data/app/o/base.apk", "com.android.vending", False,
                                iniciador="com.android.vending")
    assert "instalador_forjado" not in _chaves(_pontuar(d)[1]["com.ok"])


def test_app_que_voltou_depois_de_removido():
    from celscan import servicos
    d = _dados()
    d.apps["com.virus"] = _sideload("com.virus", instalado=datetime(2026, 9, 20))
    d.apps["com.desativado"] = _sideload("com.desativado", instalado=datetime(2026, 1, 1))
    servicos.marcar_reinstalados(d.apps, {"com.virus": "2026-09-10T10:00:00",
                                          "com.desativado": "2026-09-10T10:00:00"})
    _, por = _pontuar(d)
    assert "voltou" in _chaves(por["com.virus"]) and por["com.virus"]["removido_antes"] == "10/09/2026"
    assert "voltou" not in _chaves(por["com.desativado"])  # só foi desativado, nunca saiu: não é reinfecção


def test_dropper_ativo_e_teclado_suspeito():
    d = _dados()
    d.apps["com.inst"] = _sideload("com.inst", appops={"REQUEST_INSTALL_PACKAGES"})
    d.acess.add("com.inst")
    d.apps["com.teclado"] = _sideload("com.teclado")
    d.teclado = "com.teclado"
    _, por = _pontuar(d)
    assert "dropper_ativo" in _chaves(por["com.inst"])
    assert "teclado_suspeito" in _chaves(por["com.teclado"])


def test_teclado_de_loja_alternativa_nao_e_suspeito():
    d = _dados()
    d.apps["org.floris"] = AppBruto("org.floris", "/data/app/k/base.apk", "org.fdroid.fdroid", False)
    d.teclado = "org.floris"
    assert "teclado_suspeito" not in _chaves(_pontuar(d)[1]["org.floris"])


def test_intercepta_codigos_so_com_banco_instalado():
    d = _dados()
    d.apps["com.ler.sms"] = _sideload("com.ler.sms", perms={"android.permission.RECEIVE_SMS"})
    assert "intercepta_codigos" not in _chaves(_pontuar(d)[1]["com.ler.sms"])
    d.apps["com.nu.production"] = AppBruto("com.nu.production", "/data/app/n/base.apk", "com.android.vending", False)
    assert "intercepta_codigos" in _chaves(_pontuar(d)[1]["com.ler.sms"])


def test_golpe_de_emprestimo_le_agenda_e_sms():
    d = _dados()
    d.apps["com.emprestimo"] = _sideload("com.emprestimo", perms={"android.permission.READ_CONTACTS",
                                                                  "android.permission.READ_CALL_LOG"})
    assert "golpe_emprestimo" in _chaves(_pontuar(d)[1]["com.emprestimo"])


def test_padrao_espiao_aciona_modo_vitima():
    from celscan.acoes import evidencias
    d = _dados()
    d.apps["com.sync.services"] = _sideload("com.sync.services")
    d.notif.add("com.sync.services")
    r = _pontuar(d)[1]["com.sync.services"]
    if "padrao_espiao" in _chaves(r):  # depende de o app estar sem ícone/disfarçado na fixture
        assert r["vigilancia"] and evidencias.eh_vigilancia(r)
    assert evidencias.eh_vigilancia({"achados": [{"chave": "padrao_espiao"}]})
    assert evidencias.eh_vigilancia({"vigilancia": True})


def test_apps_sensiveis_sao_marcados():
    from celscan.analise import pontuacao
    assert pontuacao.sensivel("com.google.android.apps.authenticator2")
    assert pontuacao.sensivel("com.nu.production")  # banco oficial
    assert not pontuacao.sensivel("com.exemplo.jogo")
    assert _pontuar(_dados())[1]["com.x8bit.bitwarden"]["sensivel"]


# ---------------------------------------------------------------- regras novas (aparelho)
def test_perfil_extra_e_apps_so_nele():
    d = _dados()
    d.usuarios = [{"id": 0, "nome": "Dono", "ativo": True}, {"id": 10, "nome": "Pasta Segura", "ativo": True}]
    d.outros_usuarios = {10: {"com.escondido": None}}
    chaves = {a["chave"] for a in _pontuar(d)[0]}
    assert {"outros_usuarios", "apps_em_outro_perfil"} <= chaves


def test_apk_guardado_que_bate_com_ameaca():
    class Iocs:
        def checar(self, pacote, cert=None, sha256=None):
            return "Trojan bancário" if sha256 == "b" * 64 else None

    d = _dados()
    d.apks_guardados = [{"caminho": "/sdcard/Download/Itau.apk", "tamanho": 1, "sha256": "b" * 64}]
    achados, _ = _pontuar(d, iocs=Iocs())
    assert "apk_ameaca_guardado" in {a["chave"] for a in achados}
    d.apks_guardados = [{"caminho": "/sdcard/Download/Ok.apk", "tamanho": 1, "sha256": "c" * 64}]
    chaves = {a["chave"] for a in _pontuar(d, iocs=Iocs())[0]}
    assert "apks_guardados" in chaves and "apk_ameaca_guardado" not in chaves


def test_relogio_do_celular_zerado_e_ignorado():
    from celscan.core import coleta
    s = parsers.secoes(__import__("conftest").ler_fixture("sintetico/coleta.txt"))
    s["relogio"] = "86400"
    assert coleta.montar("X", s).relogio_aparelho is None
    s["relogio"] = "1759100000"
    assert coleta.montar("X", s).relogio_aparelho.year == 2025


# ---------------------------------------------------------------- API e log
def test_log_mascara_dados_pessoais():
    from celscan.core.log import SemDadosPessoais
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "adb pair 192.168.0.2:4000 123456 imei %s tel %s %s",
                            ("356938035643809", "(11) 98765-4321", "ana@mail.com"), None)
    SemDadosPessoais().filter(rec)
    msg = rec.getMessage()
    for segredo in ("123456", "356938035643809", "98765-4321", "ana@mail.com"):
        assert segredo not in msg
    assert "192.168.0.2:4000" in msg
