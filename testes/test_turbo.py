"""Turbo (otimização avançada): leitura das medidas, ajustes reversíveis e segurança."""

from __future__ import annotations

import re

import pytest

from celscan.acoes import quarentena, turbo


@pytest.fixture(autouse=True)
def quarentena_temporaria(tmp_path, monkeypatch):
    monkeypatch.setattr(quarentena, "DIRQ", tmp_path / "q")


class Celular:
    """Celular simulado com estado: settings, device_config, baldes e appops mudam de verdade."""

    def __init__(self, sdk=34, hz="fps=60.0, width=1080, height=2340, fps=120.0"):
        self.serial = "ABC123"
        self.sdk = sdk
        self.settings = {("global", "window_animation_scale"): "1.0", ("global", "mobile_data_always_on"): "1"}
        self.dc: dict[tuple[str, str], str] = {}
        self.baldes = {"com.jogo": "10", "com.velho": "20"}
        self.appops: dict[str, str] = {}
        self.cmds: list[str] = []
        self.display = f"mActiveSfDisplayMode=DisplayMode{{id=1, width=1080, height=2340, {hz}}}"

    def sh(self, cmd, timeout=120, erro=False):
        self.cmds.append(cmd)
        if cmd == "getprop ro.build.version.sdk":
            return str(self.sdk)
        if cmd.startswith("getprop ro.product.manufacturer"):
            return "samsung"
        if cmd.startswith("dumpsys display"):
            return self.display
        m = re.fullmatch(r"settings get (\w+) (\S+)", cmd)
        if m:
            return self.settings.get((m[1], m[2]), "null")
        m = re.fullmatch(r"settings put (\w+) (\S+) '?([^']*)'?", cmd)
        if m:
            self.settings[(m[1], m[2])] = m[3]
            return ""
        m = re.fullmatch(r"settings delete (\w+) (\S+)", cmd)
        if m:
            self.settings.pop((m[1], m[2]), None)
            return ""
        m = re.fullmatch(r"device_config get (\S+) (\S+)", cmd)
        if m:
            return self.dc.get((m[1], m[2]), "null")
        m = re.fullmatch(r"device_config put (\S+) (\S+) '?([^']*)'?", cmd)
        if m:
            self.dc[(m[1], m[2])] = m[3]
            return "Successfully set"
        m = re.fullmatch(r"device_config delete (\S+) (\S+)", cmd)
        if m:
            self.dc.pop((m[1], m[2]), None)
            return ""
        m = re.fullmatch(r"am get-standby-bucket (\S+)", cmd)
        if m:
            return self.baldes.get(m[1], "10")
        m = re.fullmatch(r"am set-standby-bucket (\S+) (\S+)", cmd)
        if m:
            nomes = {v: str(k) for k, v in turbo.BALDES.items()}
            self.baldes[m[1]] = nomes.get(m[2], m[2])
            return ""
        m = re.fullmatch(r"cmd appops get (\S+) RUN_ANY_IN_BACKGROUND", cmd)
        if m:
            return f"RUN_ANY_IN_BACKGROUND: {self.appops.get(m[1], 'allow')}"
        m = re.fullmatch(r"(?:cmd )?appops set (\S+) RUN_ANY_IN_BACKGROUND (\w+)", cmd)
        if m:
            self.appops[m[1]] = m[2]
            return ""
        if cmd.startswith("cmd package compile"):
            return "Failure: erro" if "com.ruim" in cmd else "Success"
        if cmd.startswith("cmd package resolve-activity") and "HOME" in cmd:
            return "priority=0\ncom.sec.android.app.launcher/.Home"
        if cmd.startswith("grep MemAvailable"):
            return "MemAvailable:    3500000 kB"
        return ""

    def script(self, texto, timeout=600):
        raise AssertionError("não usado nestes testes")


# ---------------------------------------------------------------------------------------------- leituras
DISPLAY = """  mActiveSfDisplayMode=DisplayMode{id=1, width=1080, height=2340, xDpi=450, yDpi=450, refreshRate=120.0}
  supportedModes [{id=1, width=1080, height=2340, fps=120.0}, {id=2, width=1080, height=2340, fps=60.0}]
  mActiveSfDisplayMode=DisplayMode{id=1, width=1080, height=2340, fps=120.0, alternativeRefreshRates=[60.0]}
  HdrCapabilities{mSupportedHdrTypes=[2, 3, 4]}"""


def test_ficha_le_tela_vulkan_e_termico():
    s = {
        "props": "ro.product.manufacturer=samsung\nro.product.model=SM-S931B\nro.build.version.release=17\n"
                 "ro.build.version.sdk=37\nro.soc.model=SM8750\nro.build.version.oneui=90000\n",
        "kernel": "6.6.127", "selinux": "Enforcing", "cpu": "8",
        "freq": "3530000\n3530000\n4470000", "mem": "MemTotal: 11427000 kB\nMemAvailable: 3700000 kB\n"
                                                       "SwapTotal: 8388604 kB\n",
        "display": DISPLAY, "features": "feature:android.hardware.vulkan.version=4206592",
        "thermal": "Thermal Status: 1\nTemperature{mValue=52.0, mType=0, mName=cpu-0-0, mStatus=0}",
        "bateria": "  status: 2\n  level: 54\n  temperature: 377\n  health: 2\n", "uptime": "129600.00 1.0",
        "gpu": "GLES: Qualcomm, Adreno (TM) 830, OpenGL ES 3.2",
    }
    f = turbo.montar_ficha(s)
    assert f["tela"] == {"resolucao": "2340×1080", "hz_atual": 120, "hz_max": 120, "hz_suportados": [60, 120],
                         "hdr": True}
    assert f["vulkan"] == "Vulkan 1.3" and f["interface"] == "One UI 9.0" and f["ghz_max"] == 4.47
    assert f["ram_virtual_gb"] == 8.0 and f["termico"]["cpu_c"] == 52.0 and f["termico"]["status_nome"] == "leve"
    assert f["bateria_c"] == 37.7 and f["ligado_h"] == 36.0 and f["classe"] == "Topo de linha"
    assert f["gpu"] == "Adreno (TM) 830"


def test_calor_aponta_cpu_segurada_e_tomada():
    s = {"thermal": "Thermal Status: 3",
         "cpu": "policy0 1200000 2000000 2000000\npolicy6 1800000 2400000 4470000",
         "top": "  PID USER PR NI VIRT RES SHR S[%CPU] %MEM TIME+ ARGS\n"
                " 123 u0_a1 10 0 1G 1M 1M S 61.0 3 1:0 com.jogo\n",
         "bateria": "  AC powered: true\n  status: 2\n  level: 50\n  temperature: 412\n"}
    c = turbo.montar_calor(s)
    assert c["nivel"] == "travando" and c["carregando"]
    assert any("54%" in x for x in c["causas"]) and any("com.jogo" in x for x in c["causas"])
    assert any("tomada" in d for d in c["dicas"])


def test_nota_usa_so_o_que_foi_medido():
    s = {"cpu1": "300", "cpun": "400", "memoria": "1073741824 bytes (1.0 G) copied, 0.2 s, 5 G/s",
         "gfx": "Total frames rendered: 1000\nJanky frames: 5 (0.50%)",
         "mem": "MemTotal: 11427000 kB\nMemAvailable: 3700000 kB", "bateria": "level: 50\ntemperature: 377\n"}
    n = turbo.montar_nota(s, gravacao_mb_s=830, latencia_ms=None)
    assert n["categorias"]["fluidez"]["nota"] == 100 and n["categorias"]["armazenamento"]["nota"] == 100
    assert n["categorias"]["conexao"]["nota"] is None and 0 < n["total"] <= 100


MEMINFO = """Total RSS by OOM adjustment:
    900,000K: Native
        50,000K: surfaceflinger (pid 500)
    300,000K: Foreground
       240,000K: com.instagram.android (pid 2000 / activities)
    200,000K: Home
       200,000K: com.sec.android.app.launcher (pid 1500 / activities)
    250,000K: Cached
       119,000K: com.twitter.android (pid 3000)
        91,000K: com.openai.chatgpt (pid 3100)
        20,000K: com.openai.chatgpt:push (pid 3101)

Total RSS by category:
"""


def test_comiloes_separa_rodando_e_segundo_plano():
    apps = {a["pacote"]: a for a in turbo.parse_meminfo_oom(MEMINFO)}
    assert apps["com.instagram.android"]["estado"] == "rodando"
    assert apps["com.openai.chatgpt"]["kb"] == 111000 and apps["com.openai.chatgpt"]["estado"] == "segundo_plano"
    assert "surfaceflinger" not in apps or apps["surfaceflinger"]["estado"] == "sistema"


def test_rede_explica_banda_e_ping():
    r = turbo.montar_rede("mWifiInfo SSID: <unknown>, RSSI: -71, Link speed: 72Mbps, Frequency: 2437MHz",
                          "10 packets transmitted, 10 received, 0% packet loss\nrtt min/avg/max/mdev = "
                          "10.1/35.2/90.0/25.3 ms")
    assert r["banda"] == "2,4 GHz" and r["sinal"] == "fraco" and r["ping_ms"] == 35.2
    assert len(r["dicas"]) == 3


# ---------------------------------------------------------------------------------------------- ajustes
def test_ajuste_grava_valor_anterior_e_desfaz():
    ap = Celular()
    r = turbo.aplicar_ajustes(ap, ["fantasmas", "dados_repouso_wifi"])
    assert all(x["ok"] for x in r["resultado"])
    assert ap.dc[("activity_manager", "max_phantom_processes")] == "2147483647"
    assert ap.settings[("global", "mobile_data_always_on")] == "0"
    ok, _ = quarentena.restaurar(ap, r["desfazer_id"])
    assert ok and ("activity_manager", "max_phantom_processes") not in ap.dc
    assert ap.settings[("global", "mobile_data_always_on")] == "1"


def test_ajuste_respeita_versao_do_android():
    r = turbo.aplicar_ajustes(Celular(sdk=29), ["fantasmas"])
    assert not r["resultado"][0]["ok"] and "12" in r["resultado"][0]["motivo"] and r["desfazer_id"] is None


def test_hz_maximo_usa_a_tela_do_aparelho_e_nao_existe_em_60hz():
    ap = Celular()
    turbo.aplicar_ajustes(ap, ["hz_maximo"])
    assert ap.settings[("system", "min_refresh_rate")] == "120.0"
    lento = Celular(hz="fps=60.0")
    item = next(a for a in turbo.listar_ajustes(lento)["ajustes"] if a["id"] == "hz_maximo")
    assert not item["suportado"]
    with pytest.raises(ValueError):
        turbo.aplicar_ajustes(ap, ["hz_maximo", "hz_economia"])


def test_listar_mostra_o_que_ja_esta_ligado():
    ap = Celular()
    ap.settings[("global", "mobile_data_always_on")] = "0"
    itens = {a["id"]: a for a in turbo.listar_ajustes(ap)["ajustes"]}
    assert itens["dados_repouso_wifi"]["ligado"] and not itens["fantasmas"]["ligado"]


def test_ajuste_desconhecido_e_recusado():
    with pytest.raises(ValueError):
        turbo.aplicar_ajustes(Celular(), ["rm -rf /"])


# ---------------------------------------------------------------------------------------------- apps
def test_dormir_e_acordar_apps():
    ap = Celular()
    r = turbo.dormir(ap, ["com.velho"], "restricted")
    assert ap.baldes["com.velho"] == "45" and r["apps"][0]["ok"]
    quarentena.restaurar(ap, r["desfazer_id"])
    assert ap.baldes["com.velho"] == "20"


def test_nunca_mexe_na_tela_inicial():
    ap = Celular()
    r = turbo.liberar_ram(ap, ["com.sec.android.app.launcher", "com.twitter.android"], "forte")
    assert not r["apps"][0]["ok"] and r["apps"][1]["ok"]
    assert "am force-stop com.sec.android.app.launcher" not in ap.cmds


def test_pacote_invalido_nunca_chega_ao_shell():
    with pytest.raises(ValueError):
        turbo.liberar_ram(Celular(), ["x; reboot"], "leve")
    with pytest.raises(ValueError):
        turbo.compilar_apps(Celular(), "extrema", ["a b"])


def test_segundo_plano_reversivel():
    ap = Celular()
    r = turbo.segundo_plano(ap, ["com.jogo"])
    assert ap.appops["com.jogo"] == "ignore"
    quarentena.restaurar(ap, r["desfazer_id"])
    assert ap.appops["com.jogo"] == "allow"


def test_compilacao_conta_falhas_e_devolve_tela():
    ap = Celular()
    ap.settings[("global", "stay_on_while_plugged_in")] = "0"
    r = turbo.compilar_apps(ap, "extrema", ["com.jogo", "com.ruim"])
    assert r["ok"] == ["com.jogo"] and r["falhas"][0]["pacote"] == "com.ruim"
    assert "cmd package compile -m everything -f com.jogo" in ap.cmds
    assert ap.settings[("global", "stay_on_while_plugged_in")] == "0"


def test_editor_bloqueia_config_que_derruba_o_adb():
    ap = Celular()
    with pytest.raises(ValueError):
        turbo.editar_config(ap, "global", "adb_enabled", "0")
    with pytest.raises(ValueError):
        turbo.editar_config(ap, "global", "x;reboot", "1")
    r = turbo.editar_config(ap, "global", "window_animation_scale", "0.5")
    assert r["ok"] and r["anterior"] == "1.0"


def test_jogo_valida_resolucao_e_fps():
    with pytest.raises(ValueError):
        turbo.ajustar_jogo(Celular(), "com.jogo", escala=0.33)
    with pytest.raises(ValueError):
        turbo.ajustar_jogo(Celular(), "com.jogo", fps=144)
    r = turbo.ajustar_jogo(Celular(), "com.jogo", "desempenho", 0.8, 60)
    assert r["ok"] and r["desfazer_id"]


def test_receita_recusa_etapa_desconhecida():
    with pytest.raises(ValueError):
        turbo.aplicar_receita(Celular(), ["formatar"])


# ---------------------------------------------------------------------------------------------- API
@pytest.fixture
def api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from celscan.api.app import criar_app
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
    app = criar_app("T", observar=False)
    cel = Celular()
    monkeypatch.setattr(app.state.aparelhos, "pronto", lambda serial: cel)
    return TestClient(app, base_url="http://127.0.0.1"), {"x-celscan-token": "T"}, cel


def test_api_ajustes_aplica_e_valida(api):
    c, h, cel = api
    assert c.post("/api/turbo/ajustes", json={"serial": "ABC123", "ids": ["nao_existe"]}, headers=h).status_code == 422
    r = c.post("/api/turbo/ajustes", json={"serial": "ABC123", "ids": ["dados_repouso_wifi"]}, headers=h)
    assert r.status_code == 200 and r.json()["desfazer_id"]
    assert cel.settings[("global", "mobile_data_always_on")] == "0"


def test_api_recusa_pacote_e_modo_invalidos(api):
    c, h, _ = api
    corpo = {"serial": "ABC123", "pacotes": ["-k; reboot"], "modo": "leve"}
    assert c.post("/api/turbo/ram/liberar", json=corpo, headers=h).status_code == 422
    corpo = {"serial": "ABC123", "modo": "turbo", "escopo": "usuario"}
    assert c.post("/api/turbo/compilar", json=corpo, headers=h).status_code == 422
    corpo = {"serial": "ABC123", "pacote": "com.jogo", "fps": 144}
    assert c.post("/api/turbo/jogo", json=corpo, headers=h).status_code == 422
    corpo = {"serial": "ABC123", "ns": "global", "chave": "adb_enabled", "valor": "0"}
    assert c.post("/api/turbo/config", json=corpo, headers=h).status_code == 422


def test_api_escolhidos_sem_apps(api):
    c, h, _ = api
    corpo = {"serial": "ABC123", "modo": "rapida", "escopo": "escolhidos"}
    assert c.post("/api/turbo/compilar", json=corpo, headers=h).status_code == 422
