"""v3.2 — regressões dos bugs encontrados na revisão (banco, período de uso, decomposição, CLI)."""

import json
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from celscan.analise import pontuacao
from celscan.core import db, parsers


def test_conexao_reaproveitada_e_reaberta(tmp_path):
    arq = tmp_path / "x.db"
    a = db.conectar(arq)
    assert db.conectar(arq) is a  # mesma thread: mesma conexão (antes vazava uma por requisição)
    a.close()
    b = db.conectar(arq)  # fechada por quem usou: reabre sozinha
    assert b is not a
    b.execute("SELECT 1")
    assert db.conectar(arq, nova=True) is not b
    db.fechar_conexoes()
    with pytest.raises(sqlite3.ProgrammingError):
        b.execute("SELECT 1")


def test_periodo_conta_notificacoes_e_telas():
    txt = ('time="2026-10-01 10:00:00" type=NOTIFICATION_INTERRUPTION package=com.loja\n'
           'time="2026-10-05 09:00:00" type=ACTIVITY_RESUMED package=com.a class=com.a.Main\n'
           'time="2026-10-08 10:00:00" type=NOTIFICATION_INTERRUPTION package=com.loja\n')
    ini, fim = parsers.periodo_eventos(txt)
    assert ini == datetime(2026, 10, 1, 10) and fim == datetime(2026, 10, 8, 10)
    assert parsers.periodo_eventos("") is None


@pytest.mark.parametrize("horas,dias", [(0, 1), (20, 1), (36, 2), (24 * 7, 7)])
def test_dias_de_uso_arredonda_para_cima(horas, dias):
    t = datetime(2026, 10, 1)
    assert pontuacao.dias_de_uso(SimpleNamespace(periodo_uso=(t, t + timedelta(hours=horas)))) == dias
    assert pontuacao.dias_de_uso(SimpleNamespace(periodo_uso=None)) == 1


def test_decomposicao_soma_bate_com_a_nota():
    achados = [{"nivel": "MÉDIO", "titulo": "Patch antigo"}]
    res = [{"pacote": "com.mal", "nome": "Mal", "nivel": "ALTO", "ameaca": "Joker"},
           {"pacote": "com.b", "nome": "B", "nivel": "OK", "ameaca": None}]
    n, _ = pontuacao.nota(achados, res)
    itens = pontuacao.decompor(achados, res)
    assert 100 + sum(i["pontos"] for i in itens) == n
    assert itens[0]["texto"].startswith("Ameaça conhecida")
    # sem ameaça: sem a linha do teto
    res[0]["ameaca"] = None
    assert 100 + sum(i["pontos"] for i in pontuacao.decompor(achados, res)) == pontuacao.nota(achados, res)[0]


def test_cli_json_puro(capsys):
    from celscan import cli
    cli._json({"nome": "Câmera", "n": 1})
    assert json.loads(capsys.readouterr().out) == {"nome": "Câmera", "n": 1}
