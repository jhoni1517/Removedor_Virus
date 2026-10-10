"""Banco local (~/.celscan/celscan.db): aparelhos, varreduras, ações, clientes e cache do VirusTotal."""

from __future__ import annotations

import json
import sqlite3
import threading
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
    """
    ALTER TABLE ordens ADD COLUMN retorno_em TEXT;
    CREATE INDEX ordens_retorno ON ordens(retorno_em);
    """,
]


class ConsentimentoNecessario(Exception):
    """LGPD: não guardamos dados de cliente sem consentimento."""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


COPIAS = DIR / "copias_banco"


def copia_de_seguranca(origem: Path | str | None = None, manter: int = 7, motivo: str = "diaria") -> Path | None:
    """Cópia consistente do banco (API de backup do SQLite) em ~/.celscan/copias_banco; guarda as últimas `manter`.

    A diária só é feita uma vez por dia. Histórico, clientes e ordens de serviço não se perdem se o arquivo
    corromper ou uma atualização der errado."""
    origem = Path(origem or ARQUIVO)
    if not origem.exists() or origem.stat().st_size == 0:
        return None
    COPIAS.mkdir(parents=True, exist_ok=True)
    destino = COPIAS / f"celscan-{datetime.now():%Y%m%d}-{motivo}.db"
    if motivo == "diaria" and destino.exists():
        return destino
    fonte = sqlite3.connect(str(origem))
    alvo = sqlite3.connect(str(destino))
    try:
        fonte.backup(alvo)
    finally:
        alvo.close()
        fonte.close()
    for velha in sorted(COPIAS.glob("celscan-*.db"))[:-manter]:
        velha.unlink(missing_ok=True)
    return destino


_LOCAL = threading.local()


_CONFERIDOS: set[str] = set()


def _integro(arquivo: Path) -> bool:
    try:
        con = sqlite3.connect(str(arquivo), timeout=15)
        try:
            return con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            con.close()
    except sqlite3.DatabaseError:
        return False


def _recuperar_se_corrompido(arquivo: Path) -> None:
    """Na 1ª abertura do dia: se o banco estiver corrompido (queda de energia, disco cheio), guarda o arquivo
    estragado ao lado e volta a cópia de segurança mais recente. O histórico de clientes não some."""
    chave = str(arquivo.resolve()) if arquivo.exists() else str(arquivo)
    if chave in _CONFERIDOS or not arquivo.exists() or arquivo.stat().st_size == 0:
        _CONFERIDOS.add(chave)
        return
    _CONFERIDOS.add(chave)
    if _integro(arquivo):
        return
    estragado = arquivo.with_name(f"{arquivo.stem}.corrompido-{datetime.now():%Y%m%d-%H%M%S}{arquivo.suffix}")
    arquivo.replace(estragado)
    for sufixo in ("-wal", "-shm"):
        Path(str(arquivo) + sufixo).unlink(missing_ok=True)
    copias = sorted(COPIAS.glob("celscan-*.db"), reverse=True) if COPIAS.exists() else []
    boa = next((c for c in copias if _integro(c)), None)
    if boa:
        import shutil

        shutil.copy2(boa, arquivo)
    from celscan.core.log import LOGGER

    LOGGER.error("banco corrompido guardado em %s; %s", estragado,
                 f"restaurada a cópia {boa.name}" if boa else "nenhuma cópia boa: começando um banco novo")


def _abrir(caminho: Path | str | None) -> sqlite3.Connection:
    arquivo = Path(caminho or ARQUIVO)
    _recuperar_se_corrompido(arquivo)
    # timeout: várias tarefas gravam ao mesmo tempo (varredura + remoção); espera em vez de "database is locked"
    con = sqlite3.connect(str(arquivo), check_same_thread=False, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:  # WAL: o histórico pode ser lido enquanto uma varredura grava, sem travar a interface
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.DatabaseError:
        pass
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    if 0 < versao < len(MIGRACOES):  # antes de mudar o esquema, guarda uma cópia
        try:
            copia_de_seguranca(caminho, motivo=f"antes-v{len(MIGRACOES)}")
        except (sqlite3.Error, OSError):
            pass
    for i, sql in enumerate(MIGRACOES[versao:], start=versao + 1):
        # migração e número da versão na MESMA transação: se o programa fechar no meio, nada fica pela
        # metade (antes a tabela era criada, a versão não subia e o CelScan não abria mais: "table exists")
        con.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {i};\nCOMMIT;")
    con.commit()
    return con


def conectar(caminho: Path | str | None = None, nova: bool = False) -> sqlite3.Connection:
    """Conexão com o banco, reaproveitada por fio de execução (thread).

    Antes cada requisição da API abria uma conexão nova (e conferia as migrações) e nunca fechava: com o
    programa aberto o dia todo, centenas de conexões ficavam penduradas. Agora cada thread reaproveita a
    sua; uma conexão fechada por quem a usou é reaberta. Não desfazemos transação pendente aqui: a mesma
    thread pode estar no meio de uma gravação (chamada aninhada). `nova=True` devolve uma conexão exclusiva.
    """
    if nova:
        return _abrir(caminho)
    chave = str(Path(caminho or ARQUIVO).resolve())
    cache: dict[str, sqlite3.Connection] = _LOCAL.__dict__.setdefault("cons", {})
    con = cache.get(chave)
    if con is not None:
        try:
            con.execute("SELECT 1")
            return con
        except sqlite3.ProgrammingError:  # fechada por quem usou
            pass
    con = cache[chave] = _abrir(caminho)
    return con


def fechar_conexoes() -> None:
    """Fecha as conexões desta thread (testes e encerramento)."""
    for con in getattr(_LOCAL, "cons", {}).values():
        try:
            con.close()
        except sqlite3.Error:
            pass
    _LOCAL.__dict__["cons"] = {}


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


def serial_da_varredura(con: sqlite3.Connection, varredura_id: int) -> str | None:
    row = con.execute("SELECT serial FROM varreduras WHERE id = ?", (varredura_id,)).fetchone()
    return str(row[0]) if row else None


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


def removidos_antes(con: sqlite3.Connection, serial: str) -> dict[str, str]:
    """Apps que o CelScan já removeu deste aparelho (e não foram desfeitos): {pacote: data}."""
    rows = con.execute("SELECT pacote, MAX(data) FROM acoes WHERE serial = ? AND tipo = 'remocao' "
                       "AND pacote IS NOT NULL AND desfeita_em IS NULL GROUP BY pacote", (serial,)).fetchall()
    return {r[0]: r[1] for r in rows}


def buscar_app(con: sqlite3.Connection, termo: str, limite: int = 50) -> list[dict[str, Any]]:
    """Procura um app (nome ou pacote) em TODAS as varreduras: 'esse app já apareceu em outro cliente?'."""
    t = (termo or "").strip().lower()
    if len(t) < 3:
        return []
    padrao = "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    linhas = con.execute(
        "SELECT v.id, v.data, v.serial, a.fabricante, a.modelo, v.resultado_json FROM varreduras v "
        "LEFT JOIN aparelhos a ON a.serial = v.serial WHERE v.resultado_json LIKE ? ESCAPE '\\' "
        "ORDER BY v.id DESC LIMIT 500", (padrao,)).fetchall()
    res: list[dict[str, Any]] = []
    for vid, data, serial, fab, modelo, bruto in linhas:
        try:
            apps = json.loads(bruto).get("apps") or []
        except (ValueError, AttributeError):
            continue
        for r in apps:
            if t in (r.get("pacote") or "").lower() or t in (r.get("nome") or "").lower():
                res.append({"varredura_id": vid, "data": data, "serial": serial,
                            "aparelho": " ".join(x for x in (fab, modelo) if x) or serial,
                            "pacote": r.get("pacote"), "nome": r.get("nome") or r.get("pacote"),
                            "nivel": r.get("nivel"), "score": r.get("score"), "ameaca": r.get("ameaca")})
                if len(res) >= limite:
                    return res
    return res


def ameacas_frequentes(con: sqlite3.Connection, desde: str, limite: int = 8) -> list[dict[str, Any]]:
    """Apps de risco ALTO mais vistos desde a data (ISO): o que está circulando entre os clientes da loja."""
    cont: dict[str, dict[str, Any]] = {}
    for (bruto,) in con.execute("SELECT resultado_json FROM varreduras WHERE data >= ? ORDER BY id DESC LIMIT 2000",
                                (desde,)):
        try:
            apps = json.loads(bruto).get("apps") or []
        except (ValueError, AttributeError):
            continue
        vistos = set()
        for r in apps:
            pkg = r.get("pacote")
            if r.get("nivel") != "ALTO" or not pkg or pkg in vistos:
                continue
            vistos.add(pkg)  # conta 1 por varredura
            x = cont.setdefault(pkg, {"pacote": pkg, "nome": r.get("nome") or pkg, "vezes": 0,
                                      "ameaca": r.get("ameaca"), "motivo": (r.get("motivos") or [None])[0]})
            x["vezes"] += 1
    return sorted(cont.values(), key=lambda x: (-x["vezes"], x["nome"].lower()))[:limite]


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
