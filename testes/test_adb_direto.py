"""Conexão direta com o servidor do adb (adbutils) e fallback para o modo por processo."""

import pytest
from fake_adb_servidor import ServidorAdb

from celscan.core import adb, adb_direto
from conftest import FAKE_ADB


@pytest.fixture
def servidor(monkeypatch):
    s = ServidorAdb({
        "getprop ro.product.model": b"Redmi Note 14\r\n",
        "screencap": b"\x89PNG\r\n\x1a\n\r\nBIN",
        "pm list packages": b"package:a\npackage:b\npackage:c\n",
        "sh /data/local/tmp/celscan.sh": b"@@SEC props\n[ro.x]: [1]\n@@SEC fim\n",
        "rm -f": b"",
    })
    monkeypatch.setenv("ANDROID_ADB_SERVER_PORT", str(s.porta))
    monkeypatch.setenv("CELSCAN_ADB_DIRETO", "1")
    adb_direto.esquecer(religar=True)
    yield s
    s.fechar()
    adb_direto.esquecer(religar=True)


def test_shell_direto_descarta_stderr(servidor):
    ap = adb.Aparelho("ABC123")
    assert ap.sh("getprop ro.product.model") == "Redmi Note 14"
    assert "shell:( getprop ro.product.model ) 2>/dev/null" in servidor.recebidos


def test_binario_direto_sem_converter_quebra(servidor):
    assert adb.Aparelho("ABC123").bytes("screencap -p") == b"\x89PNG\r\n\x1a\n\r\nBIN"
    assert "exec:screencap -p" in servidor.recebidos


def test_linhas_direto(servidor):
    assert list(adb.Aparelho("ABC123").linhas("pm list packages")) == ["package:a", "package:b", "package:c"]


def test_script_envia_por_sync_e_executa(servidor):
    s = adb.Aparelho("ABC123").script("sec(){ echo \"@@SEC $1\"; }\nsec props; getprop\nsec fim\n")
    assert "props" in s and "fim" in s
    assert servidor.arquivos["/data/local/tmp/celscan.sh"].startswith(b"sec(){")


def test_aparelho_inexistente_cai_para_o_modo_por_processo(servidor, monkeypatch):
    monkeypatch.setenv("CELSCAN_ADB", str(FAKE_ADB))
    monkeypatch.setattr(adb, "_ADB", None)
    # O servidor falso não conhece "XYZ": o caminho direto falha e o adb simulado (processo) responde.
    assert adb.Aparelho("XYZ").sh("getprop ro.product.manufacturer") == "motorola"


def _porta_livre():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_sem_servidor_usa_processo(monkeypatch):
    monkeypatch.setenv("ANDROID_ADB_SERVER_PORT", str(_porta_livre()))  # ninguém escuta
    monkeypatch.setenv("CELSCAN_ADB_DIRETO", "1")
    monkeypatch.setenv("CELSCAN_ADB", str(FAKE_ADB))
    monkeypatch.setattr(adb, "_ADB", None)
    adb_direto.esquecer(religar=True)
    assert adb_direto.cliente() is None  # e não liga o adb embutido do adbutils
    assert adb.Aparelho("ABC123").sh("getprop ro.product.manufacturer") == "motorola"
    adb_direto.esquecer(religar=True)
