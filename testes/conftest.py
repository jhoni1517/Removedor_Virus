"""Configuração comum dos testes: pasta de dados temporária e APK sintético."""

from __future__ import annotations

import io
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

# Antes de importar o celscan: dados em pasta temporária e nada de internet.
os.environ["CELSCAN_HOME"] = tempfile.mkdtemp(prefix="celscan_teste_")
os.environ["CELSCAN_OFFLINE"] = "1"

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE_ADB = Path(__file__).resolve().parent / "fake_adb.py"


def ler_fixture(caminho: str) -> str:
    return (FIXTURES / caminho).read_text(encoding="utf-8")


def _lp(b: bytes) -> bytes:
    return struct.pack("<I", len(b)) + b


def criar_apk(caminho: Path, der: bytes | None) -> Path:
    """APK mínimo; com `der`, inclui um bloco de assinatura v2 contendo esse certificado."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("AndroidManifest.xml", "manifesto")
        z.writestr("classes.dex", b"\0" * 64)
    dados = buf.getvalue()
    if der is not None:
        eocd = dados.rfind(b"PK\x05\x06")
        cd = struct.unpack_from("<I", dados, eocd + 16)[0]
        dados_assinados = _lp(b"") + _lp(_lp(der)) + _lp(b"")  # digests, certificados, atributos
        signer = _lp(dados_assinados) + _lp(b"") + _lp(b"")
        valor = _lp(_lp(signer))
        par = struct.pack("<QI", len(valor) + 4, 0x7109871A) + valor
        tam = len(par) + 24
        bloco = struct.pack("<Q", tam) + par + struct.pack("<Q", tam) + b"APK Sig Block 42"
        dados = bytearray(dados[:cd] + bloco + dados[cd:])
        eocd += len(bloco)
        struct.pack_into("<I", dados, eocd + 16, cd + len(bloco))
        dados = bytes(dados)
    caminho.write_bytes(dados)
    return caminho


@pytest.fixture
def apk_debug(tmp_path: Path) -> Path:
    return criar_apk(tmp_path / "debug.apk", b"0\x82certificado CN=Android Debug, O=Android")


@pytest.fixture
def ambiente_fake(tmp_path: Path, apk_debug: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Variáveis para rodar a CLI contra o ADB simulado."""
    env = dict(os.environ)
    env.update({
        "CELSCAN_ADB": str(FAKE_ADB), "APK_TESTE": str(apk_debug),
        "CELSCAN_HOME": str(tmp_path / "home"), "CELSCAN_FAKE_ESTADO": str(tmp_path / "estado"),
        "CELSCAN_OFFLINE": "1", "PYTHONPATH": str(RAIZ), "COLUMNS": "200",
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
    })
    return env
