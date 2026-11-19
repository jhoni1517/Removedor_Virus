"""Modo flagrante: anúncio por cima de outro app, sobreposição e internet em segundo plano."""
from celscan.acoes import flagrante

TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F90 0100007F:A000 01 00000000:00000000 00:00000000 00000000 10200 0 1
   1: 0A00000F:B000 8EFA4D8E:01BB 01 00000000:00000000 00:00000000 00000000 10300 0 2
   2: 0A00000F:B001 8EFA4D8E:01BB 0A 00000000:00000000 00:00000000 00000000 10400 0 3
"""


def amostra(foco, atividade, overlay=(), tcp=TCP):
    ov = "\n".join(f"  mOwnerUid=1 showForAllUsers=false package={p} appop=SYSTEM_ALERT_WINDOW" for p in overlay)
    return (f"@@foco\n  mCurrentFocus=Window{{abc u0 {foco}/{atividade}}}\n@@ov\n{ov}\n@@tcp\n{tcp}")


def test_conexoes_ignora_loopback_e_escuta():
    assert flagrante.conexoes(TCP) == {10300: 1}


def test_amostrar_reconhece_anuncio():
    a = flagrante.amostrar(amostra("com.lanterna", "com.google.android.gms.ads.AdActivity", ["com.lanterna"]))
    assert a["foco"] == "com.lanterna" and a["anuncio"] and a["sobreposicao"] == ["com.lanterna"]
    assert not flagrante.amostrar(amostra("com.whatsapp", "com.whatsapp.HomeActivity"))["anuncio"]


class Celular:
    def __init__(self, amostras):
        self.amostras = list(amostras)

    def sh(self, cmd, timeout=120, erro=False):
        if cmd.startswith("pm list packages -U"):
            return "package:com.lanterna uid:10300\npackage:com.whatsapp uid:10200\npackage:com.jogo uid:10400"
        return self.amostras.pop(0)


def test_observar_pega_adware():
    cel = Celular([
        amostra("com.whatsapp", "com.whatsapp.HomeActivity"),
        amostra("com.lanterna", "com.google.android.gms.ads.AdActivity", ["com.lanterna"]),
        amostra("com.whatsapp", "com.whatsapp.HomeActivity"),
        amostra("com.whatsapp", "com.whatsapp.HomeActivity"),
    ])
    passos = []
    r = flagrante.observar(cel, duracao_s=12, progresso=passos.append, intervalo=3, dormir=lambda s: None)
    assert r["amostras"] == 4 and len(passos) == 4 and r["rede_disponivel"]
    top = r["apps"][0]
    assert top["pacote"] == "com.lanterna" and top["nivel"] == "ALTO" and top["anuncio_fora"] == 1
    assert "por cima de outro app" in top["motivos"][0]
    assert r["eventos"][0]["texto"].endswith("com.whatsapp")
    assert all(a["pacote"] != "com.whatsapp" for a in r["apps"])


def test_rede_escondida():
    cel = Celular([amostra("com.whatsapp", "com.whatsapp.HomeActivity")] * 4)
    r = flagrante.observar(cel, duracao_s=12, intervalo=3, dormir=lambda s: None)
    assert r["apps"][0]["pacote"] == "com.lanterna" and r["apps"][0]["rede_fundo_pct"] == 100
