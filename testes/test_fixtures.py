from celscan.core.fixtures import anonimizar


def test_anonimizar():
    texto = """[ro.serialno]: [ZY22ABCD]
[ro.product.model]: [moto g54]
[persist.radio.imei]: [356938035643809]
conta=usuario.teste@gmail.com imei 356938035643809
wlan0 mac 3c:28:6d:aa:bb:cc SSID: "MinhaCasa"
LinkAddresses: [ 192.168.0.15/24 ] versionName=1.2.3
adb ZY22ABCD"""
    r = anonimizar(texto, "ZY22ABCD")
    assert "ZY22ABCD" not in r and "356938035643809" not in r and "gmail" not in r
    assert "3c:28:6d" not in r and "MinhaCasa" not in r and "192.168.0.15" not in r
    assert "[ro.product.model]: [moto g54]" in r and "versionName=1.2.3" in r
    assert "[ro.serialno]: [ANONIMIZADO]" in r


def test_comando_fixtures_com_fake_adb(ambiente_fake, tmp_path):
    import subprocess
    import sys

    from conftest import RAIZ

    r = subprocess.run([sys.executable, str(RAIZ / "celscan.py"), "fixtures", "--pasta", str(tmp_path / "fx")],
                       env=ambiente_fake, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    pasta = next((tmp_path / "fx").iterdir())
    nomes = {p.name for p in pasta.iterdir()}
    assert {"props.txt", "pkgdump.txt", "coleta.txt", "diag.txt", "LEIAME.md"} <= nomes
    assert "@@SEC pkgs" in (pasta / "coleta.txt").read_text(encoding="utf-8")
