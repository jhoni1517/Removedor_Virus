"""Proteção Pix: imitação de apps, padrão de trojan bancário e certificados oficiais."""

from datetime import datetime

from celscan.analise import certificados, pix, pontuacao
from celscan.core import bases
from celscan.core.coleta import AppBruto, DadosAparelho

AGORA = datetime(2026, 9, 30)


def app(pkg, instalador=None, appops=(), cert=None):
    return AppBruto(pkg, f"/data/app/{pkg}/base.apk", instalador, False, appops=set(appops), cert=cert)


def dados(*apps, acess=()):
    return DadosAparelho("X", {"ro.build.version.security_patch": "2026-09-01"}, {a.pacote: a for a in apps},
                         acess=set(acess), icones={a.pacote for a in apps})


def test_imitacao():
    assert pix.imitacao("com.whatsaap") == "WhatsApp"  # uma letra trocada
    assert pix.imitacao("com.nubank.seguranca.atualizar") == "Nubank"
    assert pix.imitacao("br.com.correios.rastreio.app") == "Correios"
    assert pix.imitacao("com.whatsapp") is None  # o oficial nunca é imitação
    assert pix.imitacao("com.exemplo.jogo") is None


def test_app_falso_de_banco_fica_alto():
    _, res = pontuacao.pontuar(dados(app("com.nubank.atualizacao", "com.google.android.packageinstaller")), agora=AGORA)
    r = res[0]
    assert r["nivel"] == "ALTO" and any(a["chave"] == "imita_app_conhecido" for a in r["achados"])
    assert "Nubank" in r["motivos"][0]


def test_mesmo_nome_vindo_da_play_nao_e_acusado():
    _, res = pontuacao.pontuar(dados(app("com.nubank.atualizacao", "com.android.vending")), agora=AGORA)
    assert not any(a["chave"] == "imita_app_conhecido" for a in res[0]["achados"])


def test_padrao_trojan_com_app_de_banco_gera_alerta_no_aparelho():
    d = dados(app("com.nu.production", "com.android.vending"),
              app("com.leitor.pdf", "com.google.android.packageinstaller", ["PROJECT_MEDIA"]),
              acess=["com.leitor.pdf"])
    achados, res = pontuacao.pontuar(d, agora=AGORA)
    assert achados[0]["chave"] == "risco_pix" and "Nubank" in achados[0]["titulo"]
    suspeito = next(r for r in res if r["pacote"] == "com.leitor.pdf")
    chaves = {a["chave"] for a in suspeito["achados"]}
    assert {"trojan_bancario", "acessibilidade", "PROJECT_MEDIA"} <= chaves and suspeito["nivel"] == "ALTO"


def test_sem_app_de_banco_nao_ha_alerta_pix():
    d = dados(app("com.leitor.pdf", None, ["SYSTEM_ALERT_WINDOW"]), acess=["com.leitor.pdf"])
    achados, _ = pontuacao.pontuar(d, agora=AGORA)
    assert not any(a["chave"] == "risco_pix" for a in achados)


def test_certificado_falso_e_registro_do_aparelho(monkeypatch, tmp_path):
    monkeypatch.setattr(bases, "PASTA", tmp_path)
    monkeypatch.setattr(pontuacao, "_certs", None)

    class Aparelho:
        serial = "X"

        def sh(self, cmd, **kw):
            if cmd.startswith("pm list"):
                return ("package:/data/app/a/base.apk=com.nu.production installer=com.android.vending\n"
                        "package:/data/app/b/base.apk=com.itau installer=com.google.android.packageinstaller")
            return "12345" if cmd.startswith("stat") else ""

    monkeypatch.setattr("celscan.analise.apksig.ler_remoto", lambda ap, apk, t: {"sha256": "AA" * 32, "debug": False})
    novos = certificados.registrar_do_aparelho(Aparelho())
    assert [n["pacote"] for n in novos] == ["com.nu.production"]  # o Itaú de fora da Play é ignorado
    assert "com.nu.production" in certificados.carregar()

    falso = app("com.nu.production", "com.google.android.packageinstaller", cert={"sha256": "BB" * 32})
    _, res = pontuacao.pontuar(dados(falso), agora=AGORA)
    assert res[0]["achados"][0]["chave"] == "certificado_falso" and res[0]["nivel"] == "ALTO"
    oficial = app("com.nu.production", "com.android.vending", cert={"sha256": "AA" * 32})
    _, res = pontuacao.pontuar(dados(oficial), agora=AGORA)
    assert res[0]["nivel"] == "OK"
