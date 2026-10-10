"""Rótulos v3: ícones vetoriais/adaptativos, disfarces e redes de anúncio no manifesto."""

import os
import xml.etree.ElementTree as ET
import zipfile

import pytest

from celscan.analise import rotulos

NS = "http://schemas.android.com/apk/res/android"


def test_vetor_vira_svg_com_area_visivel():
    v = ET.fromstring(f'<vector xmlns:a="{NS}" a:viewportWidth="108.0" a:viewportHeight="108.0">'
                      f'<group a:translateX="2"><path a:pathData="M0 0L10 10z" a:fillColor="#FF106D1F"/>'
                      f'</group></vector>')
    svg = rotulos.vetor_svg(v, None, adaptativo=True, fundo="#fff")
    assert 'viewBox="18.0 18.0 72.0 72.0"' in svg
    assert 'fill="#106D1FFF"' in svg and "translate(2.0 0.0)" in svg


def test_cor_android_para_css():
    assert rotulos.css_cor("#FF106D1F") == "#106D1FFF"
    assert rotulos.css_cor("#abc") == "#abc"
    assert rotulos.css_cor("@7f01") is None


def test_rede_de_anuncio_pela_classe():
    assert rotulos.sdk_de("com.google.android.gms.ads.AdActivity") == "Google AdMob"
    assert rotulos.sdk_de("com.applovin.adview.AppLovinFullscreenActivity") == "AppLovin"
    assert rotulos.sdk_de("com.exemplo.Main") is None


def test_icone_svg_vira_data_uri():
    r = rotulos.Rotulo("x", "X", icone_svg="<svg/>")
    assert rotulos.icone_data_uri(r).startswith("data:image/svg+xml;base64,")
    assert rotulos.icone_data_uri(b"RIFFxxxxWEBP").startswith("data:image/webp")


def test_disfarce_e_nome_reais_no_fdroid():
    caminho = os.getenv("APK_TESTE", "/tmp/fdroid.apk")
    if not os.path.exists(caminho) or not zipfile.is_zipfile(caminho):
        pytest.skip("APK_TESTE não disponível")
    f = open(caminho, "rb")

    def ler(off, n):
        f.seek(off)
        return f.read(n)
    r = rotulos.analisar(rotulos._ZipRemoto(ler, os.path.getsize(caminho)), "org.fdroid.fdroid")
    assert r.nome == "F-Droid"
    assert r.disfarces  # o F-Droid tem um atalho alternativo desativado (modo disfarçado)
    assert r.icone_png or r.icone_svg
