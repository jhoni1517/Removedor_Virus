"""Quem gasta a bateria e quem ocupa o espaço."""
from celscan.acoes import gastos

BAT = """    Capacity: 5000, Computed drain: 1200, actual drain: 1100-1300
    UID u0a164: 600.0 fg: 12.0 bg: 588.0 fgs: 0 cached: 0
    UID 1000: 300.0
    UID u0a20: 50.5
    Uid u0a99: 0.4
  Wake lock u0a164 *job*/com.lanterna/.Sync: 1h 2m 3s 4ms (120 times) realtime
  Wake lock u0a164 alarme: 30s 0ms (3 times) realtime
  Wake lock 1000 *alarm*: 5m 0s 0ms (9 times) realtime
"""


def test_uid_e_duracao():
    assert gastos.uid_num("u0a164") == 10164 and gastos.uid_num("u10a1") == 1010001 and gastos.uid_num("1000") == 1000
    assert gastos.duracao_s("1h 2m 3s 4ms") == 3723.004


def test_bateria_ordena_e_mostra_acordado():
    r = gastos.montar_bateria(BAT, {10164: ["com.lanterna"], 10020: ["com.whatsapp"]})
    assert r["dreno_mah"] == 1200 and r["capacidade_mah"] == 5000
    top = r["apps"][0]
    assert top["pacotes"] == ["com.lanterna"] and top["pct"] == 50.0 and top["acordado_min"] == 62.6
    assert r["apps"][1]["nome"] == "Sistema Android" and not r["apps"][1]["usuario"]
    assert any(a["uid"] == 10099 for a in r["apps"])


def test_espaco_grandes_duplicados_e_velhos():
    s = {"df": "/dev/block/dm-50 115000000 100000000 15000000 87% /data",
         "grandes": "524288000|1700000000|/sdcard/Movies/filme.mp4\n",
         "dupes": "2097152|/sdcard/DCIM/a.jpg\n2097152|/sdcard/Download/a (1).jpg\n2097152|/sdcard/DCIM/b.jpg\n"
                  "3000000|/sdcard/DCIM/sozinho.jpg\n",
         "velho_whatsapp": "120 1048576000"}
    hashes = {"/sdcard/DCIM/a.jpg": "x" * 32, "/sdcard/Download/a (1).jpg": "x" * 32, "/sdcard/DCIM/b.jpg": "y" * 32}
    r = gastos.montar_espaco(s, hashes)
    assert r["livre_gb"] == 14.3 and r["grandes"][0]["mb"] == 500.0
    assert r["duplicados"] == [{"mb": 2.0, "arquivos": ["/sdcard/DCIM/a.jpg", "/sdcard/Download/a (1).jpg"],
                                "sobra_mb": 2.0}]
    assert r["velhos"][0] == {"id": "whatsapp", "nome": "Mídia do WhatsApp",
                              "pasta": gastos.MIDIA_VELHA["whatsapp"][0], "arquivos": 120, "mb": 1000.0}


def test_so_apaga_pasta_do_usuario(tmp_path):
    assert gastos.seguro("/sdcard/DCIM/a.jpg")
    for ruim in ("/data/data/x", "/sdcard/../data/x", "/sdcard/Android/data/com.x/f", "/system/app"):
        assert not gastos.seguro(ruim)

    class Cel:
        def __init__(self):
            self.cmds = []

        def adb(self, *a, timeout=0):
            (tmp_path / "b" / "sdcard" / "DCIM").mkdir(parents=True, exist_ok=True)
            (tmp_path / "b" / "sdcard" / "DCIM" / "a.jpg").write_bytes(b"x")
            return ""

        def sh(self, cmd, timeout=0):
            self.cmds.append(cmd)
            return ""

    c = Cel()
    r = gastos.apagar(c, ["/sdcard/DCIM/a.jpg", "/data/x"], tmp_path / "b")
    assert [x["caminho"] for x in r["apagados"]] == ["/sdcard/DCIM/a.jpg"] and len(r["falhas"]) == 1
    assert c.cmds[0] == "rm -f /sdcard/DCIM/a.jpg"
