from celscan.analise import apksig
from conftest import criar_apk


def test_le_certificado_v2(apk_debug):
    r = apksig.ler_local(apk_debug)
    assert r["debug"] is True
    assert len(r["sha256"]) == 64 and r["sha256"].isupper()


def test_sem_bloco_de_assinatura(tmp_path):
    assert apksig.ler_local(criar_apk(tmp_path / "v1.apk", None)) is None


def test_certificado_normal(tmp_path):
    r = apksig.ler_local(criar_apk(tmp_path / "ok.apk", b"0\x82cert CN=Empresa"))
    assert r["debug"] is False
