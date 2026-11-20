"""Por que trava: diagnóstico com prova e 'destravar este app'."""
import re

import pytest

from celscan.acoes import destravar, quarentena

DEX14 = """[com.netflix.mediaclient]
  path: /data/app/x/base.apk
    arm64: [status=verify] [reason=install]
[com.android.camera]
  path: /system/priv-app/MiuiCamera/MiuiCamera.apk
    arm64: [status=speed-profile] [reason=bg-dexopt]
[com.whatsapp]
    arm64: /data/app/y/oat/arm64/base.odex[status=speed-profile] [reason=install-dm]
[com.miui.home]
    arm64: [status=run-from-apk] [reason=unknown]
"""

FICHA = {"fabricante": "Xiaomi", "ram_gb": 8, "ram_livre_gb": 3.0, "termico": {"status": 0}, "bateria_c": 33,
         "ligado_h": 200}


def test_ler_dexopt_dois_formatos():
    d = destravar.ler_dexopt(DEX14)
    assert d == {"com.netflix.mediaclient": "verify", "com.android.camera": "speed-profile",
                 "com.whatsapp": "speed-profile", "com.miui.home": "run-from-apk"}


def test_diagnostico_xiaomi_travando():
    s = {"df": "/dev/block/dm-50 115000000 110000000 5000000 96% /data", "lowpower": "1\n",
         "anim": "1.5\n1.0\n1.0\n", "dexopt": DEX14, "escrita": "7\n",
         "ativos": "package:com.netflix.mediaclient\npackage:com.android.camera\npackage:com.xiaomi.joyose\n"}
    marca = [{"nome": "MSA", "ativo": True, "marcado": True}, {"nome": "Notas", "ativo": True, "marcado": False}]
    r = destravar.montar(FICHA, s, marca, {"xiaomi_interface_leve": False, "fantasmas": False})
    ids = [p["id"] for p in r["problemas"]]
    assert ids[:4] == ["sem_compilar", "armazenamento", "economia", "video"]
    assert {"memoria_xiaomi", "reiniciar", "bloat", "interface", "joyose", "animacoes"} <= set(ids)
    assert "camera" not in ids  # a câmera já está compilada: não acusa
    p = {x["id"]: x for x in r["problemas"]}
    assert "2 de 4 apps (50%)" in p["sem_compilar"]["prova"] and p["armazenamento"]["gravidade"] == "alta"
    assert "Netflix (sem compilar)" in p["video"]["prova"] and p["video"]["etapas"] == ["destravar_video"]
    assert p["bloat"]["prova"].startswith("1 apps") and not p["joyose"]["marcar"]
    assert "Câmera e galeria compiladas" in r["bons"] and r["escrita"] is True


def test_o_que_foi_consertado_nao_volta_a_aparecer():
    dex = DEX14.replace("[status=verify] [reason=install]", "[status=speed] [reason=cmdline]")
    s = {"df": "/dev/block/dm-50 115000000 50000000 65000000 44% /data", "lowpower": "0", "anim": "0.5\n",
         "dexopt": dex.replace("run-from-apk", "speed-profile"), "escrita": "7",
         "ativos": "package:com.netflix.mediaclient\npackage:com.android.camera\n"}
    aj = {"xiaomi_interface_leve": True, "fantasmas": True, "mais_processos": True}
    r = destravar.montar({**FICHA, "ligado_h": 1}, s, [{"nome": "MSA", "ativo": False, "marcado": True}], aj)
    assert r["problemas"] == []
    assert {"Interface leve ligada", "Apps em segundo plano liberados (não resetam)",
            "Sem apps de propaganda da marca ativos", "Modo economia desligado"} <= set(r["bons"])
    assert any(b.startswith("Apps de vídeo destravados") for b in r["bons"])


def test_celular_que_recusa_gravar_vira_critico():
    s = {"escrita": "java.lang.SecurityException: Permission denial\nnull\n", "dexopt": "", "ativos": ""}
    r = destravar.montar(FICHA, s, [], {})
    assert r["problemas"][0]["id"] == "bloqueado" and r["problemas"][0]["gravidade"] == "critica"
    assert "Configurações de segurança" in r["problemas"][0]["conserto"]


def test_diagnostico_celular_saudavel():
    s = {"df": "/dev/block/dm-50 115000000 50000000 65000000 44% /data", "lowpower": "0", "anim": "1.0\n0.5\n",
         "dexopt": "[com.a]\n arm64: [status=speed-profile]\n", "ativos": ""}
    f = {**FICHA, "fabricante": "motorola", "ligado_h": 10}
    assert destravar.montar(f, s, [], {"fantasmas": True, "mais_processos": True})["problemas"] == []


@pytest.fixture(autouse=True)
def quarentena_temporaria(tmp_path, monkeypatch):
    monkeypatch.setattr(quarentena, "DIRQ", tmp_path / "q")


class Celular:
    serial = "ABC"

    def __init__(self):
        self.cmds, self.balde, self.idle, self.ops = [], "45", "", "ignore"

    def sh(self, cmd, timeout=120, erro=False):
        self.cmds.append(cmd)
        if cmd.startswith("pm list packages "):
            return "package:com.netflix.mediaclient"
        if cmd.startswith("am get-standby-bucket"):
            return self.balde
        m = re.match(r"am set-standby-bucket \S+ (\w+)", cmd)
        if m:
            self.balde = m[1]
            return ""
        if cmd == "dumpsys deviceidle whitelist":
            return self.idle
        if cmd.startswith("cmd deviceidle whitelist +"):
            self.idle = "user,com.netflix.mediaclient,10200"
            return "Added: com.netflix.mediaclient"
        if cmd.startswith("cmd deviceidle whitelist -"):
            self.idle = ""
            return "Removed"
        if "RUN_ANY_IN_BACKGROUND" in cmd:
            if cmd.startswith("appops set") or cmd.startswith("cmd appops set"):
                self.ops = cmd.split()[-1]
                return ""
            return f"RUN_ANY_IN_BACKGROUND: {self.ops}"
        if cmd.startswith(("pm clear", "cmd package compile")):
            return "Success"
        return ""


def test_destravar_app_e_desfazer():
    c = Celular()
    r = destravar.destravar_app(c, "com.netflix.mediaclient")
    assert c.balde == "active" and "com.netflix" in c.idle and c.ops == "allow"
    assert "compilado por completo" in r["feitos"] and "cache limpo" in r["feitos"]
    assert any(x.startswith("am force-stop") for x in c.cmds)
    ok, _ = quarentena.restaurar(c, r["desfazer_id"])
    assert ok and c.balde == "restricted" and c.idle == "" and c.ops == "ignore"


def test_destravar_app_recusa():
    with pytest.raises(ValueError):
        destravar.destravar_app(Celular(), "rm -rf")
    c = Celular()
    c.sh = lambda cmd, **k: ""
    with pytest.raises(ValueError):
        destravar.destravar_app(c, "com.nao.instalado")


def test_apps_da_marca_mostra_removidos_e_devolve():
    from celscan.acoes import faxina

    class Xiaomi:
        def __init__(self):
            self.ativos = {"com.miui.msa.global", "com.miui.notes", "com.android.thememanager"}

        def sh(self, cmd, timeout=120, erro=False):
            if cmd == "getprop ro.product.manufacturer":
                return "Xiaomi"
            if cmd == "pm list packages -u":
                return "\n".join(f"package:{p}" for p in (*self.ativos, "com.mi.globalbrowser"))
            if cmd == "pm list packages -e":
                return "\n".join(f"package:{p}" for p in self.ativos)
            if cmd.startswith("cmd package install-existing"):
                self.ativos.add(cmd.split()[-1])
            return ""

    x = Xiaomi()
    r = faxina.apps_da_marca(x)
    por = {a["pacote"]: a for a in r["apps"]}
    assert r["marca"] == "xiaomi" and set(por) == {"com.miui.msa.global", "com.miui.notes",
                                                   "com.android.thememanager", "com.mi.globalbrowser"}
    assert por["com.miui.msa.global"]["marcado"] and not por["com.miui.notes"]["marcado"]
    assert not por["com.android.thememanager"]["marcado"] and not por["com.mi.globalbrowser"]["ativo"]
    assert faxina.devolver(x, "com.mi.globalbrowser")["ok"]


def test_receita_mostra_detalhe_de_cada_etapa_e_confere_no_fim(monkeypatch):
    from celscan.acoes import turbo

    chamadas = []
    monkeypatch.setattr(destravar, "diagnostico", lambda ap, *a, **k: chamadas.append(1) or
                        {"problemas": [{"id": "reiniciar"}], "bons": ["Modo economia desligado"]})

    class Cel:
        serial = "ABC"
        low = "1"

        def sh(self, cmd, timeout=120, erro=False):
            if cmd == "settings get global low_power":
                return self.low
            if cmd == "settings put global low_power 0":
                self.low = "0"
            return ""

    r = turbo.aplicar_receita(Cel(), ["economia_off"])
    assert r["etapas"] == [{"id": "economia_off", "ok": True, "detalhe": "desligado"}]
    assert r["depois"]["problemas"] == [{"id": "reiniciar"}] and chamadas == [1]
