from datetime import datetime

import pytest

from celscan.analise import pontuacao, regras
from celscan.config import permitidos
from celscan.core import coleta, parsers
from celscan.core.adb import AdbErro
from conftest import ler_fixture

AGORA = datetime(2026, 9, 29)


def dados_sinteticos():
    return coleta.montar("ABC123", parsers.secoes(ler_fixture("sintetico/coleta.txt")))


def test_montar_coleta_sintetica():
    d = dados_sinteticos()
    assert set(d.apps) == {"com.whatsapp", "com.systemservice", "com.x8bit.bitwarden", "com.exemplo.jogo"}
    ss = d.apps["com.systemservice"]
    assert ss.appops == {"SYSTEM_ALERT_WINDOW", "REQUEST_INSTALL_PACKAGES"}
    assert "android.permission.READ_SMS" in ss.perms
    assert d.admins == {"com.systemservice": ["com.systemservice/com.systemservice.AdminRcv"]}
    assert d.info()["modelo"] == "moto g54 5G"
    assert d.avisos == []


def test_coleta_interrompida():
    with pytest.raises(AdbErro):
        coleta.montar("X", {"props": ""})


def test_avisos_visiveis_quando_verificacao_falha():
    s = parsers.secoes(ler_fixture("sintetico/coleta.txt"))
    s["launcher"] = "Error: unknown command 'query-activities'"
    s["admins"] = "/system/bin/sh: dumpsys: inaccessible or not found"
    s["appops"] = ler_fixture("sintetico/variantes/appops_erro.txt")
    del s["idle"]
    d = coleta.montar("X", s)
    texto = " ".join(d.avisos)
    assert "apps escondidos" in texto and "administradores" in texto
    assert "economia de bateria" in texto and "sobreposição de tela" in texto
    assert d.icones is None


def test_pontuacao_igual_ao_v2():
    d = dados_sinteticos()
    achados, res = pontuacao.pontuar(d, permitidos=permitidos(), agora=AGORA)
    por = {r["pacote"]: r for r in res}
    assert res[0]["pacote"] == "com.systemservice"
    assert por["com.systemservice"]["score"] == 100 and por["com.systemservice"]["nivel"] == "ALTO"
    assert por["com.x8bit.bitwarden"]["nivel"] == "PERMITIDO"
    assert por["com.exemplo.jogo"]["nivel"] == "OK"
    assert [a["chave"] for a in achados] == ["patch_muito_antigo"]
    assert pontuacao.nota(achados, res) == (45, "Crítico")


def test_achados_tem_texto_leigo():
    _, res = pontuacao.pontuar(dados_sinteticos(), agora=AGORA)
    for ach in res[0]["achados"]:
        assert ach["titulo"] and ach["significa"] and ach["fazer"]
    assert res[0]["achados"][0]["chave"] == "acessibilidade"  # maior peso primeiro


def test_ameaca_conhecida_limita_nota():
    class IOCs:
        def checar(self, pkg, cert, sha):
            return "stalkerware Teste" if pkg == "com.exemplo.jogo" else None

    achados, res = pontuacao.pontuar(dados_sinteticos(), iocs=IOCs(), agora=AGORA)
    jogo = next(r for r in res if r["pacote"] == "com.exemplo.jogo")
    assert jogo["ameaca"] == "stalkerware Teste" and jogo["nivel"] == "ALTO"
    assert pontuacao.nota(achados, res)[0] <= 20


def test_regras_usuario_sobrescreve(tmp_path):
    extra = tmp_path / "regras.yaml"
    extra.write_text("apps:\n  acessibilidade:\n    peso: 5\n", encoding="utf-8")
    r = regras.carregar(usuario=extra)
    assert r.apps["acessibilidade"].peso == 5
    assert r.apps["acessibilidade"].significa  # texto original mantido


def test_regras_invalidas(tmp_path):
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text("apps:\n  x:\n    titulo: T\n", encoding="utf-8")
    with pytest.raises(regras.RegrasInvalidas, match="apps.x"):
        regras.carregar(ruim, usuario=None)
