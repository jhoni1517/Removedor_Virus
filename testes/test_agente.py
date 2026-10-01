"""CelScan Agente: instalação temporária, leitura de nomes/ícones/uso e remoção no fim."""

from pathlib import Path

import pytest

from celscan.core import adb, agente
from conftest import FAKE_ADB


@pytest.fixture
def ap(monkeypatch, tmp_path):
    apk = tmp_path / "celscan-agente.apk"
    apk.write_bytes(b"PK\x03\x04agente")
    monkeypatch.setenv("CELSCAN_AGENTE_APK", str(apk))
    monkeypatch.setenv("CELSCAN_ADB", str(FAKE_ADB))
    monkeypatch.setenv("CELSCAN_FAKE_ESTADO", str(tmp_path / "estado"))
    monkeypatch.setattr(adb, "_ADB", None)
    return adb.Aparelho("ABC123")


def comandos(tmp_path: Path) -> str:
    return (tmp_path / "estado" / "comandos.log").read_text(encoding="utf-8")


def test_parse_com_virgula_no_nome():
    linhas = agente.parse_linhas("Row: 0 pacote=a.b, nome=SsOp, icone=NULL\nNo result found.\nlixo\n")
    assert linhas == [{"pacote": "a.b", "nome": "SsOp", "icone": ""}]


def test_agente_le_e_remove_no_fim(ap, tmp_path):
    with agente.Agente(ap) as ag:
        apps = ag.apps()
        uso = ag.uso(90)
    assert apps["com.exemplo.jogo"]["nome"] == "Jogo das Frutas, Edição 2"  # vírgula no nome não quebra
    assert apps["com.whatsapp"]["icone"].startswith("data:image/png;base64,")
    assert apps["com.android.settings"]["sistema"] and "com.celscan.agente" not in apps
    assert uso["com.whatsapp"]["frente_min"] == 90 and uso["com.exemplo.jogo"]["ultimo_uso"] is None
    log = comandos(tmp_path)
    assert "install -r" in log and "appops set com.celscan.agente GET_USAGE_STATS allow" in log
    assert "uninstall com.celscan.agente" in log  # removido ao sair


def test_apps_esquecidos(ap):
    r = agente.apps_esquecidos(ap, 90)
    assert [a["pacote"] for a in r["apps"]] == ["com.exemplo.jogo"]  # WhatsApp foi usado; sistema fica fora


def test_sem_apk(monkeypatch, ap):
    monkeypatch.setenv("CELSCAN_AGENTE_APK", "/nao/existe.apk")
    monkeypatch.setattr(agente, "apk", lambda: None)
    with pytest.raises(agente.AgenteIndisponivel):
        with agente.Agente(ap):
            pass
