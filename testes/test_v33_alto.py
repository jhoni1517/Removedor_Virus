"""Upgrades de nível ALTO da 3.3."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from celscan.acoes import quarentena


@pytest.fixture(autouse=True)
def quarentena_temporaria(tmp_path, monkeypatch):
    monkeypatch.setattr(quarentena, "DIRQ", tmp_path / "q")


SHA = "a" * 64


class ApArquivos:
    serial = "ABC123"

    def __init__(self):
        self.arquivos = {"/sdcard/Download/Banco.apk": b"APK1", "/sdcard/WhatsApp/x.apk": b"APK22"}
        self.cmds: list[str] = []

    def sh(self, cmd, timeout=120, erro=False):
        self.cmds.append(cmd)
        if cmd.startswith("find /sdcard"):
            return "\n".join(f"{len(v)}\t{SHA}\t{k}" for k, v in self.arquivos.items())
        if cmd.startswith("rm -f "):
            import shlex
            self.arquivos.pop(shlex.split(cmd)[2], None)
        return ""

    def adb(self, *args, timeout=120, erro=False):
        self.cmds.append("adb " + " ".join(args))
        if args[0] == "pull":
            Path(args[2]).write_bytes(self.arquivos[args[1]])
            return "1 file pulled"
        if args[0] == "push":
            self.arquivos[args[2]] = Path(args[1]).read_bytes()
            return "1 file pushed"
        return ""


def test_apagar_apk_guardado_com_desfazer():
    from celscan.acoes import apks
    ap = ApArquivos()
    r = apks.apagar(ap, ["/sdcard/Download/Banco.apk"])
    assert "/sdcard/Download/Banco.apk" not in ap.arquivos and r["quarentena_id"]
    ok, msg = quarentena.restaurar(ap, r["quarentena_id"])
    assert ok and ap.arquivos["/sdcard/Download/Banco.apk"] == b"APK1", msg


def test_apagar_apk_so_o_que_a_listagem_achou():
    from celscan.acoes import apks
    ap = ApArquivos()
    for ruim in ("/data/data/x.apk", "/sdcard/../data/x.apk", "/sdcard/foto.jpg", "/sdcard/nao_existe.apk"):
        with pytest.raises(ValueError):
            apks.apagar(ap, [ruim])
    assert not any(c.startswith("rm ") for c in ap.cmds)


def test_apagar_apk_com_copia_cortada_nao_apaga():
    from celscan.acoes import apks
    ap = ApArquivos()
    original = ap.adb

    def corta(*args, **kw):
        res = original(*args, **kw)
        if args[0] == "pull":
            Path(args[2]).write_bytes(b"A")
        return res
    ap.adb = corta
    with pytest.raises(OSError):
        apks.apagar(ap, ["/sdcard/Download/Banco.apk"])
    assert "/sdcard/Download/Banco.apk" in ap.arquivos


def test_poderes_do_app():
    from celscan.analise import pontuacao
    from celscan.core.coleta import AppBruto, DadosAparelho
    d = DadosAparelho.__new__(DadosAparelho)
    d.admins, d.acess, d.notif, d.teclado, d.sms = {"x": []}, {"x"}, set(), "x", None
    app = AppBruto("x", "/a", None, False, appops={"SYSTEM_ALERT_WINDOW", "REQUEST_INSTALL_PACKAGES"})
    assert pontuacao.poderes(app, d) == ["administrador", "controla a tela", "janela sobre outros apps",
                                         "instala apps", "teclado"]


def _con(tmp_path):
    from celscan.core import db
    con = db.conectar(tmp_path / "h.db", nova=True)
    info = {"serial": "S1", "fabricante": "Moto", "modelo": "G", "android": "14"}
    apps = [{"pacote": "com.sync.services", "nome": "Sync Services", "nivel": "ALTO", "score": 90,
             "motivos": ["Controla a tela"]}, {"pacote": "com.whatsapp", "nome": "WhatsApp", "nivel": "OK", "score": 0}]
    for _ in range(2):
        db.salvar_varredura(con, info, 40, "ruim", [], apps, [], 1.0)
    return con


def test_buscar_app_no_historico(tmp_path):
    from celscan.core import db
    con = _con(tmp_path)
    achou = db.buscar_app(con, "sync serv")
    assert len(achou) == 2 and achou[0]["aparelho"] == "Moto G" and achou[0]["nivel"] == "ALTO"
    assert db.buscar_app(con, "ab") == []  # termo curto demais
    assert db.buscar_app(con, "100%_") == []  # curinga do LIKE não vaza


def test_ameacas_do_mes(tmp_path):
    from celscan.core import db
    top = db.ameacas_frequentes(_con(tmp_path), "2000-01-01")
    assert top == [{"pacote": "com.sync.services", "nome": "Sync Services", "vezes": 2, "ameaca": None,
                    "motivo": "Controla a tela"}]


def test_retorno_depois_da_entrega(tmp_path):
    from celscan.core import balcao, db
    con = db.conectar(tmp_path / "r.db", nova=True)
    cid = db.criar_cliente(con, "Maria Souza", "(11) 98888-7777", True)
    oid = balcao.criar_ordem(con, ["checkup"], cliente_id=cid, aparelho="Moto G")
    balcao.mudar_status(con, oid, "entregue")
    assert balcao.retornos(con) == []  # 30 dias à frente: ainda não aparece
    lista = balcao.retornos(con, datetime(2099, 1, 1))
    assert lista[0]["id"] == oid and lista[0]["atrasado"] and lista[0]["whatsapp"].startswith("https://wa.me/5511988887777")
    assert "Maria" in lista[0]["mensagem"]
    assert balcao.concluir_retorno(con, oid) and balcao.retornos(con, datetime(2099, 1, 1)) == []


def test_plano_de_acao_no_laudo():
    from celscan.analise.plano import plano_de_acao
    apps = [{"pacote": "a", "nome": "Espião", "nivel": "ALTO", "vigilancia": True, "achados": []},
            {"pacote": "b", "nome": "Jogo", "nivel": "MÉDIO", "achados": []}]
    passos = plano_de_acao(apps, [{"nivel": "ALTO", "fazer": "Desligue a instalação de apps desconhecidos."}])
    assert passos[0].startswith("Há sinal de app espião") and "Espião" in passos[1]
    assert "Desligue a instalação" in passos[-2] and passos[-1].startswith("Faça uma nova varredura")
    assert plano_de_acao(apps, [], removidos={"a", "b"}) == []


def test_pdf_tem_plano(tmp_path):
    from celscan.relatorio import pdf
    meta = {"id": 1, "data": "2026-10-10T10:00:00", "nota": 40, "veredito": "ruim", "modo": "rapido", "duracao_s": 3}
    retrato = {"aparelho": {"serial": "S", "fabricante": "Moto", "modelo": "G", "android": "14"},
               "achados_aparelho": [], "avisos": [],
               "apps": [{"pacote": "a", "nome": "Golpe", "nivel": "ALTO", "score": 90, "achados": [], "motivos": []}]}
    dados, _ = pdf.gerar_pdf(meta, retrato)
    assert dados.startswith(b"%PDF")


def test_busca_e_ranking_sem_json1(tmp_path, monkeypatch):
    from celscan.core import db
    con = _con(tmp_path)
    monkeypatch.setattr(db, "_json_sql", lambda c: False)
    assert len(db.buscar_app(con, "SYNC")) == 2
    assert db.ameacas_frequentes(con, "2000-01-01")[0]["vezes"] == 2
