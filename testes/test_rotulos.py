"""Nome e ícone reais lidos de um APK (ZIP remoto), sem baixar o arquivo inteiro."""

import os
import zipfile

import pytest

from celscan.analise import rotulos


def _apk_de_teste():
    caminho = os.getenv("APK_TESTE", "/tmp/fdroid.apk")
    if not os.path.exists(caminho) or not zipfile.is_zipfile(caminho):
        pytest.skip("APK_TESTE não disponível")
    return caminho


def _leitor(caminho):
    f = open(caminho, "rb")

    def ler(off, n):
        f.seek(off)
        return f.read(n)

    return ler, os.path.getsize(caminho)


def test_zip_remoto_le_entradas():
    caminho = _apk_de_teste()
    ler, tam = _leitor(caminho)
    z = rotulos._ZipRemoto(ler, tam)
    assert "AndroidManifest.xml" in z and "resources.arsc" in z
    real = zipfile.ZipFile(caminho)
    assert z.ler_arquivo("AndroidManifest.xml") == real.read("AndroidManifest.xml")


def test_extrai_nome_e_icone():
    caminho = _apk_de_teste()
    ler, tam = _leitor(caminho)
    nome, icone = rotulos.extrair(ler, tam)
    assert nome and icone and icone.endswith(".png")
    png = rotulos._ZipRemoto(ler, tam).ler_arquivo(icone)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_obter_usa_cache(tmp_path, monkeypatch):
    caminho = _apk_de_teste()
    monkeypatch.setattr(rotulos, "CACHE", tmp_path)
    tam = os.path.getsize(caminho)

    class Aparelho:
        def __init__(self):
            self.leituras = 0

        def bytes(self, cmd, timeout=60):
            import re
            self.leituras += 1
            m = re.search(r"bs=(\d+) skip=(\d+) count=(\d+)", cmd)
            bs, sk, ct = int(m.group(1)), int(m.group(2)), int(m.group(3))
            with open(caminho, "rb") as f:
                f.seek(bs * sk)
                return f.read(bs * ct)

    ap = Aparelho()
    r1 = rotulos.obter(ap, "org.fdroid.fdroid", "/data/app/x/base.apk", tam, "hashfake")
    assert r1.nome and r1.icone_png
    ap.leituras = 0
    r2 = rotulos.obter(ap, "org.fdroid.fdroid", "/data/app/x/base.apk", tam, "hashfake")
    assert ap.leituras == 0 and r2.nome == r1.nome  # veio do cache, sem ler o aparelho


def test_icone_data_uri():
    assert rotulos.icone_data_uri(b"\x89PNG").startswith("data:image/png;base64,")
    assert rotulos.icone_data_uri(None) is None
