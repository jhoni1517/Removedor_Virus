"""Pop-ups de anúncio, app na tela agora e consumo de dados por app."""

from celscan.acoes import consumo, na_tela
from celscan.analise.rotulos import sdk_de
from celscan.core import parsers


def test_popup_fora_do_app_e_tela_cheia():
    ev = 'time="2026-10-09 {}" type=ACTIVITY_RESUMED package={} class={}\n'
    txt = (ev.format("20:05:00", "launcher", "L")
           + ev.format("20:06:00", "jogo", "com.google.android.gms.ads.AdActivity")
           + ev.format("21:00:00", "jogo", "jogo.Main")
           + ev.format("21:01:00", "jogo", "com.applovin.adview.AppLovinFullscreenActivity") +
           'time="2026-10-09 21:01:00" type=NOTIFICATION_INTERRUPTION package=jogo channelId=promo\n'
           'time="2026-10-09 21:01:00" type=NOTIFICATION_INTERRUPTION package=jogo channelId=promo\n'
           '  package=jogo totalTimeUsed="1:00" lastTimeUsed="2026-10-09 21:05:00"\n')
    telas, ultimo, notif = parsers.uso(txt)
    an = parsers.anuncios(telas, sdk_de)["jogo"]
    assert an["tela_cheia"] == 2 and an["fora_do_app"] == 1
    assert an["sdks"] == {"Google AdMob", "AppLovin"}
    assert ultimo["jogo"].hour == 21 and notif["jogo"] == 1  # evento repetido no dump conta uma vez


def test_tempos_de_appops_nos_dois_formatos():
    txt = ("@@PKG a\nCAMERA: allow; time=+1h ago; duration=+20s\nRECORD_AUDIO: allow\n"
           "    null=[\n      Access: [bg-s] 2026-10-10 09:00:00.000 (-3h2m) duration=+40s\n    ]\n"
           "SYSTEM_ALERT_WINDOW: allow; time=+5m ago\n@@PKG b\nNo operations.\n")
    t = parsers.appops_tempos(txt, {"CAMERA", "RECORD_AUDIO"})
    assert t == {"a": {"CAMERA": 3600, "RECORD_AUDIO": 3 * 3600 + 120}}


def test_rede_dns_vpn():
    r = parsers.rede("hostname\ndns.adguard-dns.com\ncom.vpn.app\n2\n")
    assert r == {"dns_modo": "hostname", "dns_servidor": "dns.adguard-dns.com", "vpn_sempre": "com.vpn.app",
                 "vpn_ativa": True}
    assert parsers.rede("")["vpn_ativa"] is False


def test_app_na_tela():
    class Ap:
        def sh(self, cmd):
            return "  mResumedActivity: ActivityRecord{1 u0 com.jogo/com.google.android.gms.ads.AdActivity t9}"
    assert na_tela.ler(Ap()) == {"pacote": "com.jogo", "classe": "com.google.android.gms.ads.AdActivity",
                                 "anuncio": "Google AdMob"}


def test_consumo_por_app():
    txt = ("9,0,i,uid,10100,com.youtube\n9,0,i,uid,10100,com.youtube.extra\n"
           "9,10100,l,nt,104857600,10485760,209715200,0,1,2,3,4\n9,10200,l,nt,0,0,0,0\n")
    d = consumo.parse(txt)
    assert d["com.youtube"] == {"movel_mb": 110.0, "wifi_mb": 200.0, "enviado_mb": 10.0}
    assert "com.youtube.extra" in d
