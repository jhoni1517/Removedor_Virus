"""Upgrades de PRIORIDADE da 3.3: atendimento (bateria, conferir, finalizar), ETA, OS automática, bases offline."""

from __future__ import annotations

import json
import zipfile

import pytest


class ApRoteiro:
    serial = "ABC123"

    def __init__(self, respostas):
        self.respostas, self.cmds = respostas, []

    def sh(self, cmd, timeout=120, erro=False):
        self.cmds.append(cmd)
        for k, v in self.respostas.items():
            if cmd.startswith(k):
                return v
        return ""


def test_bateria_baixa_so_sem_carregar():
    from celscan.acoes import atendimento
    assert atendimento.bateria(ApRoteiro({"dumpsys battery": "  level: 8\n  status: 3\n"}))["baixa"]
    b = atendimento.bateria(ApRoteiro({"dumpsys battery": "  level: 8\n  status: 2\n"}))
    assert b["carregando"] and not b["baixa"]
    assert atendimento.bateria(ApRoteiro({}))["nivel"] is None


def test_conferir_aponta_o_que_sobrou():
    from celscan.acoes import atendimento
    ap = ApRoteiro({"pm list packages": "package:com.fica\n",
                    "settings get secure enabled_accessibility_services": "com.saiu/.Acc",
                    "ps": "com.fica\n"})
    res = {r["pacote"]: r for r in atendimento.conferir(ap, ["com.saiu", "com.fica", "com.limpo"])}
    assert res["com.saiu"]["sobrou"] == ["acessibilidade"] and not res["com.saiu"]["limpo"]
    assert res["com.fica"]["instalado"] and "rodando" in res["com.fica"]["sobrou"]
    assert res["com.limpo"]["limpo"]
    with pytest.raises(ValueError):
        atendimento.conferir(ap, ["x; rm -rf /"])


def test_finalizar_limpa_e_desliga_depuracao():
    from celscan.acoes import atendimento
    ap = ApRoteiro({"pm uninstall com.celscan.agente": "Success"})
    feito = atendimento.finalizar(ap)
    assert "settings put global adb_enabled 0" == ap.cmds[-1]  # por último: derruba a conexão
    assert any("development_settings_enabled 0" in c for c in ap.cmds)
    assert any("removido" in f for f in feito)
    ap2 = ApRoteiro({})
    atendimento.finalizar(ap2, desligar_depuracao=False)
    assert not any("adb_enabled" in c for c in ap2.cmds)


def test_abrir_app_nos_ajustes():
    from celscan.acoes import atendimento
    ap = ApRoteiro({})
    atendimento.abrir_app(ap, "com.x")
    assert ap.cmds == ["am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:com.x"]


def test_eta_aprende_com_este_pc(tmp_path, monkeypatch):
    from celscan import config
    from celscan.core import tempos
    monkeypatch.setattr(config, "DIR", tmp_path)
    assert tempos.estimar("hashes", 300, 40) == 80  # sem histórico: padrão escalado pelo nº de apps
    tempos.registrar("hashes", 10, 100)  # 0,1 s por app
    assert tempos.estimar("hashes", 300, 40) == 30
    tempos.registrar("hashes", 20, 100)  # média móvel
    assert 30 < tempos.estimar("hashes", 300, 40) < 60


def test_varredura_liga_na_ordem_de_servico_aberta(tmp_path):
    from celscan.core import balcao, db
    con = db.conectar(tmp_path / "x.db", nova=True)
    db.registrar_aparelho(con, {"serial": "S1", "fabricante": "a", "modelo": "b", "android": "14"})
    oid = balcao.criar_ordem(con, ["checkup"], serial="S1")
    outra = balcao.criar_ordem(con, ["checkup"], serial="S2")
    vid = db.salvar_varredura(con, {"serial": "S1", "fabricante": "a", "modelo": "b", "android": "14"}, 90, "ok",
                              [], [], [], 1.0)
    assert balcao.vincular_varredura(con, "S1", vid) == oid
    linha = con.execute("SELECT varredura_id, status FROM ordens WHERE id=?", (oid,)).fetchone()
    assert linha[0] == vid and linha[1] == "analisando"
    assert balcao.vincular_varredura(con, "S1", vid) is None  # já ligada: não troca
    assert con.execute("SELECT varredura_id FROM ordens WHERE id=?", (outra,)).fetchone()[0] is None


def test_bases_exportar_e_importar(tmp_path, monkeypatch):
    from celscan.core import bases
    monkeypatch.setattr(bases, "PASTA", tmp_path / "origem")
    alvo = bases.todas()[0]
    bases.PASTA.mkdir()
    alvo.caminho.write_text("conteudo", encoding="utf-8")
    pacote = tmp_path / "bases.zip"
    assert alvo.nome in bases.exportar(pacote)
    monkeypatch.setattr(bases, "PASTA", tmp_path / "destino")
    res = dict(bases.importar(pacote))
    assert res[alvo.nome] == "importada" and alvo.caminho.read_text(encoding="utf-8") == "conteudo"
    assert dict(bases.importar(pacote))[alvo.nome].startswith("a cópia deste PC já")


def test_bases_importar_rejeita_zip_estranho(tmp_path, monkeypatch):
    from celscan.core import bases
    monkeypatch.setattr(bases, "PASTA", tmp_path / "d")
    ruim = tmp_path / "ruim.zip"
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("x.txt", "oi")
    with pytest.raises(ValueError):
        bases.importar(ruim)
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr(bases.MANIFESTO, json.dumps({}))
        z.writestr("../../fora.json", "oi")
    assert dict(bases.importar(ruim))["../../fora.json"].startswith("ignorado")
    assert not (tmp_path / "fora.json").exists()
