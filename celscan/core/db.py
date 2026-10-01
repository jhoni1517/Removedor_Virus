"""Banco local (~/.celscan/celscan.db): aparelhos, varreduras, ações, clientes e cache do VirusTotal."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from celscan.config import DIR

ARQUIVO = DIR / "celscan.db"

# Cada item é uma migração; a posição + 1 é a versão do esquema.
MIGRACOES = [
    """
    CREATE TABLE aparelhos (
        serial TEXT PRIMARY KEY, fabricante TEXT, modelo TEXT, android TEXT,
        primeiro_visto TEXT NOT NULL, ultimo_visto TEXT NOT NULL
    );
    CREATE TABLE clientes (
        id INTEGER PRIMARY KEY, nome TEXT NOT NULL, telefone TEXT,
        consentimento_em TEXT NOT NULL, criado_em TEXT NOT NULL
    );
    CREATE TABLE varreduras (
        id INTEGER PRIMARY KEY, serial TEXT NOT NULL REFERENCES aparelhos(serial),
        cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
        data TEXT NOT NULL, modo TEXT NOT NULL, nota INTEGER, veredito TEXT, duracao_s REAL,
        apps_total INTEGER, apps_risco INTEGER, resultado_json TEXT NOT NULL
    );
    CREATE INDEX varreduras_serial ON varreduras(serial, data);
    CREATE TABLE acoes (
        id INTEGER PRIMARY KEY, serial TEXT NOT NULL, data TEXT NOT NULL, tipo TEXT NOT NULL,
        pacote TEXT, detalhe TEXT, quarentena_id TEXT, desfeita_em TEXT
    );
    CREATE TABLE vt_cache (sha TEXT PRIMARY KEY, ts REAL NOT NULL, dados TEXT NOT NULL);
    """,
    """
    CREATE TABLE laudos (
        hash TEXT PRIMARY KEY, varredura_id INTEGER NOT NULL REFERENCES varreduras(id), criado_em TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE ordens (
        id INTEGER PRIMARY KEY, cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
        serial TEXT, aparelho TEXT, imei TEXT, servicos TEXT NOT NULL, valor_centavos INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'aguardando', observacoes TEXT, varredura_id INTEGER,
        criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL, entregue_em TEXT
    );
    CREATE INDEX ordens_status ON ordens(status, criado_em);
    """,
]


class ConsentimentoNecessario(Exception):
    """LGPD: não guardamos dados de cliente sem consentimento."""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conectar(caminho: Path | str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(caminho or ARQUIVO), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRACOES[versao:], start=versao + 1):
        con.executescript(sql)
        con.execute(f"PRAGMA user_version = {i}")
    con.commit()
    return con


def registrar_aparelho(con: sqlite3.Connection, info: dict[str, str]) -> None:
    agora = _agora()
    con.execute(
        """INSERT INTO aparelhos (serial, fabricante, modelo, android, primeiro_visto, ultimo_visto)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(serial) DO UPDATE SET fabricante=excluded.fabricante, modelo=excluded.modelo,
               android=excluded.android, ultimo_visto=excluded.ultimo_visto""",
        (info["serial"], info.get("fabricante"), info.get("modelo"), info.get("android"), agora, agora),
    )
    con.commit()


def salvar_varredura(con: sqlite3.Connection, info: dict[str, str], nota: int, veredito: str,
                     achados: list[dict], resultados: list[dict], avisos: list[str] | None = None,
                     duracao_s: float | None = None, modo: str = "android",
                     cliente_id: int | None = None) -> int:
    """Guarda o "retrato" completo do aparelho nesta varredura. Devolve o id."""
    registrar_aparelho(con, info)
    retrato = {"aparelho": info, "achados_aparelho": achados, "apps": resultados, "avisos": avisos or []}
    risco = sum(1 for r in resultados if r.get("nivel") in ("ALTO", "MÉDIO"))
    cur = con.execute(
        """INSERT INTO varreduras (serial, cliente_id, data, modo, nota, veredito, duracao_s, apps_total,
                                   apps_risco, resultado_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (info["serial"], cliente_id, _agora(), modo, nota, veredito, duracao_s, len(resultados), risco,
         json.dumps(retrato, ensure_ascii=False, default=str)),
    )
    con.commit()
    return int(cur.lastrowid or 0)


def varreduras(con: sqlite3.Connection, serial: str | None = None, limite: int = 20) -> list[sqlite3.Row]:
    sql = """SELECT v.id, v.serial, v.data, v.modo, v.nota, v.veredito, v.duracao_s, v.apps_total, v.apps_risco,
                    a.fabricante, a.modelo FROM varreduras v JOIN aparelhos a USING (serial)"""
    params: tuple[Any, ...] = ()
    if serial:
        sql += " WHERE v.serial = ?"
        params = (serial,)
    return con.execute(sql + " ORDER BY v.id DESC LIMIT ?", (*params, limite)).fetchall()


def retrato(con: sqlite3.Connection, varredura_id: int) -> dict[str, Any] | None:
    row = con.execute("SELECT resultado_json FROM varreduras WHERE id = ?", (varredura_id,)).fetchone()
    return json.loads(row[0]) if row else None


def varredura_anterior(con: sqlite3.Connection, serial: str, antes_de: int) -> int | None:
    row = con.execute("SELECT id FROM varreduras WHERE serial = ? AND id < ? ORDER BY id DESC LIMIT 1",
                      (serial, antes_de)).fetchone()
    return int(row[0]) if row else None


def registrar_acao(con: sqlite3.Connection, serial: str, tipo: str, pacote: str | None = None,
                   detalhe: str | None = None, quarentena_id: str | None = None) -> int:
    cur = con.execute(
        "INSERT INTO acoes (serial, data, tipo, pacote, detalhe, quarentena_id) VALUES (?, ?, ?, ?, ?, ?)",
        (serial, _agora(), tipo, pacote, detalhe, quarentena_id),
    )
    con.commit()
    return int(cur.lastrowid or 0)


def marcar_desfeita(con: sqlite3.Connection, quarentena_id: str) -> None:
    con.execute("UPDATE acoes SET desfeita_em = ? WHERE quarentena_id = ? AND desfeita_em IS NULL",
                (_agora(), quarentena_id))
    con.commit()


def acoes(con: sqlite3.Connection, serial: str | None = None, limite: int = 50) -> list[sqlite3.Row]:
    if serial:
        return con.execute("SELECT * FROM acoes WHERE serial = ? ORDER BY id DESC LIMIT ?",
                           (serial, limite)).fetchall()
    return con.execute("SELECT * FROM acoes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()


def meta_varredura(con: sqlite3.Connection, varredura_id: int) -> dict[str, Any] | None:
    row = con.execute("SELECT id, serial, data, modo, nota, veredito, duracao_s FROM varreduras WHERE id = ?",
                      (varredura_id,)).fetchone()
    return dict(row) if row else None


def acoes_da_varredura(con: sqlite3.Connection, varredura_id: int) -> list[dict[str, Any]]:
    """Ações feitas no aparelho depois desta varredura e antes da próxima."""
    meta = meta_varredura(con, varredura_id)
    if not meta:
        return []
    prox = con.execute("SELECT data FROM varreduras WHERE serial = ? AND id > ? ORDER BY id LIMIT 1",
                       (meta["serial"], varredura_id)).fetchone()
    fim = prox[0] if prox else "9999"
    return [dict(r) for r in con.execute(
        "SELECT * FROM acoes WHERE serial = ? AND data >= ? AND data < ? ORDER BY id",
        (meta["serial"], meta["data"], fim)).fetchall()]


# ---------------------------------------------------------------- laudos

def registrar_laudo(con: sqlite3.Connection, varredura_id: int, hash_hex: str) -> None:
    con.execute("INSERT OR IGNORE INTO laudos (hash, varredura_id, criado_em) VALUES (?, ?, ?)",
                (hash_hex, varredura_id, _agora()))
    con.commit()


def verificar_laudo(con: sqlite3.Connection, codigo: str) -> dict[str, Any] | None:
    """Aceita o código curto (XXXX-XXXX-XXXX-XXXX), o hash inteiro ou o texto do QR."""
    texto = codigo.strip().split("|")[-1].replace("-", "").lower()
    if len(texto) < 16 or any(c not in "0123456789abcdef" for c in texto):
        return None
    row = con.execute(
        """SELECT l.hash, l.criado_em, v.id AS varredura_id, v.data, v.nota, v.veredito, a.serial, a.fabricante,
                  a.modelo FROM laudos l JOIN varreduras v ON v.id = l.varredura_id JOIN aparelhos a USING (serial)
           WHERE l.hash LIKE ?""", (texto + "%",)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------- clientes (LGPD)

def criar_cliente(con: sqlite3.Connection, nome: str, telefone: str | None, consentimento: bool) -> int:
    """Guarda só nome e telefone, e só com consentimento registrado."""
    if not consentimento:
        raise ConsentimentoNecessario("Peça o consentimento do cliente antes de guardar os dados dele.")
    agora = _agora()
    cur = con.execute("INSERT INTO clientes (nome, telefone, consentimento_em, criado_em) VALUES (?, ?, ?, ?)",
                      (nome.strip(), (telefone or "").strip() or None, agora, agora))
    con.commit()
    return int(cur.lastrowid or 0)


def apagar_cliente(con: sqlite3.Connection, cliente_id: int) -> bool:
    """Apaga o cliente (direito de exclusão da LGPD). As varreduras ficam sem vínculo com ele."""
    cur = con.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
    con.commit()
    return cur.rowcount > 0


def clientes(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
