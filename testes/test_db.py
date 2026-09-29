import pytest

from celscan.core import db

INFO = {"serial": "ABC123", "fabricante": "motorola", "modelo": "moto g54", "android": "14"}


@pytest.fixture
def con(tmp_path):
    return db.conectar(tmp_path / "teste.db")


def test_migracao_idempotente(tmp_path):
    caminho = tmp_path / "x.db"
    db.conectar(caminho).close()
    c = db.conectar(caminho)
    assert c.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRACOES)


def test_salvar_e_ler_varredura(con):
    res = [{"pacote": "a", "nivel": "ALTO"}, {"pacote": "b", "nivel": "OK"}]
    v1 = db.salvar_varredura(con, INFO, 45, "Crítico", [], res, ["aviso x"], 12.5)
    v2 = db.salvar_varredura(con, INFO, 90, "Excelente", [], res[1:])
    linhas = db.varreduras(con, "ABC123")
    assert [v["id"] for v in linhas] == [v2, v1]
    assert linhas[1]["apps_risco"] == 1 and linhas[1]["modelo"] == "moto g54"
    assert db.retrato(con, v1)["avisos"] == ["aviso x"]
    assert db.varredura_anterior(con, "ABC123", v2) == v1
    assert db.varredura_anterior(con, "ABC123", v1) is None


def test_acoes_e_desfazer(con):
    db.registrar_aparelho(con, INFO)
    db.registrar_acao(con, "ABC123", "remocao", "com.x", "removido", "Q1")
    db.marcar_desfeita(con, "Q1")
    assert db.acoes(con, "ABC123")[0]["desfeita_em"]


def test_cliente_exige_consentimento_e_pode_ser_apagado(con):
    with pytest.raises(db.ConsentimentoNecessario):
        db.criar_cliente(con, "Maria", "11999990000", consentimento=False)
    cid = db.criar_cliente(con, " Maria ", "", consentimento=True)
    vid = db.salvar_varredura(con, INFO, 80, "Bom", [], [], cliente_id=cid)
    assert db.clientes(con)[0]["nome"] == "Maria"
    assert db.apagar_cliente(con, cid)
    assert db.clientes(con) == []
    row = con.execute("SELECT cliente_id FROM varreduras WHERE id=?", (vid,)).fetchone()
    assert row[0] is None  # varredura continua, sem vínculo com o cliente
