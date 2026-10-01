"""Balcão: ordens de serviço, pacotes de serviço e painel da loja.

Status (colunas do quadro): aguardando -> analisando -> pronto -> entregue.
Valores guardados em centavos (sem erro de arredondamento). Dados do cliente só com
consentimento (ver db.criar_cliente); a OS guarda o mínimo necessário.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime
from typing import Any
from urllib.parse import quote

import yaml

from celscan.config import DADOS
from celscan.core import preferencias
from celscan.core.db import _agora

STATUS = ("aguardando", "analisando", "pronto", "entregue")
NOMES_STATUS = {"aguardando": "Aguardando", "analisando": "Analisando", "pronto": "Pronto", "entregue": "Entregue"}


def catalogo() -> dict[str, dict[str, Any]]:
    """Pacotes de serviço com os preços ajustados pelo técnico (preferências) por cima do padrão."""
    base = yaml.safe_load((DADOS / "servicos.yaml").read_text(encoding="utf-8"))
    precos = preferencias.ler().get("precos_servicos") or {}
    for k, v in base.items():
        if k in precos:
            v["preco"] = float(precos[k])
    return base


def _centavos(reais: float) -> int:
    return int(round(float(reais) * 100))


def criar_ordem(con: sqlite3.Connection, servicos: list[str], cliente_id: int | None = None,
                serial: str | None = None, aparelho: str | None = None, imei: str | None = None,
                observacoes: str | None = None, valor: float | None = None) -> int:
    cat = catalogo()
    desconhecidos = [s for s in servicos if s not in cat]
    if not servicos or desconhecidos:
        raise ValueError(f"Serviço desconhecido: {', '.join(desconhecidos) or '(nenhum)'}")
    total = _centavos(valor) if valor is not None else sum(_centavos(cat[s]["preco"]) for s in servicos)
    agora = _agora()
    cur = con.execute(
        """INSERT INTO ordens (cliente_id, serial, aparelho, imei, servicos, valor_centavos, status, observacoes,
                               criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, 'aguardando', ?, ?, ?)""",
        (cliente_id, serial, aparelho, (imei or "").strip() or None, json.dumps(servicos), total,
         observacoes, agora, agora))
    con.commit()
    return int(cur.lastrowid or 0)


def mudar_status(con: sqlite3.Connection, ordem_id: int, status: str, varredura_id: int | None = None) -> bool:
    if status not in STATUS:
        raise ValueError(f"Status inválido: {status}")
    agora = _agora()
    cur = con.execute(
        """UPDATE ordens SET status=?, atualizado_em=?, entregue_em=CASE WHEN ?='entregue' THEN ? ELSE entregue_em END,
                             varredura_id=COALESCE(?, varredura_id) WHERE id=?""",
        (status, agora, status, agora, varredura_id, ordem_id))
    con.commit()
    return cur.rowcount > 0


def _linha(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["servicos"] = json.loads(d["servicos"])
    d["valor"] = d.pop("valor_centavos") / 100
    return d


def ordens(con: sqlite3.Connection, status: str | None = None, limite: int = 200) -> list[dict[str, Any]]:
    sql = """SELECT o.*, c.nome AS cliente, c.telefone FROM ordens o LEFT JOIN clientes c ON c.id = o.cliente_id"""
    params: tuple[Any, ...] = ()
    if status:
        sql += " WHERE o.status = ?"
        params = (status,)
    return [_linha(r) for r in con.execute(sql + " ORDER BY o.id DESC LIMIT ?", (*params, limite))]


def ordem(con: sqlite3.Connection, ordem_id: int) -> dict[str, Any] | None:
    r = con.execute("""SELECT o.*, c.nome AS cliente, c.telefone FROM ordens o
                       LEFT JOIN clientes c ON c.id = o.cliente_id WHERE o.id = ?""", (ordem_id,)).fetchone()
    return _linha(r) if r else None


def real(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mensagem_whatsapp(o: dict[str, Any], loja: str = "nossa loja") -> dict[str, str]:
    """Texto pronto para o cliente e link wa.me (abre o WhatsApp do técnico com a mensagem)."""
    cat = catalogo()
    nomes = ", ".join(cat.get(s, {}).get("nome", s) for s in o["servicos"])
    situacao = {"aguardando": "foi recebido e está na fila", "analisando": "está em análise",
                "pronto": "está pronto para retirada", "entregue": "foi entregue. Obrigado!"}[o["status"]]
    texto = (f"Olá{', ' + o['cliente'].split()[0] if o.get('cliente') else ''}! Seu aparelho "
             f"{o.get('aparelho') or ''} (OS nº {o['id']}) {situacao}. Serviços: {nomes}. "
             f"Valor: {real(o['valor'])}. — {loja}").replace("  ", " ")
    tel = "".join(ch for ch in (o.get("telefone") or "") if ch.isdigit())
    if tel and not tel.startswith("55") and len(tel) <= 11:
        tel = "55" + tel
    return {"texto": texto, "link": f"https://wa.me/{tel}?text={quote(texto)}" if tel else ""}


def painel(con: sqlite3.Connection, agora: datetime | None = None) -> dict[str, Any]:
    """Números do dia e do mês: atendimentos, faturamento (entregues), por serviço e tempo médio."""
    agora = agora or datetime.now()
    dia, mes = agora.strftime("%Y-%m-%d"), agora.strftime("%Y-%m")
    cat = catalogo()

    def periodo(prefixo: str) -> dict[str, Any]:
        linhas = [_linha(r) for r in con.execute("SELECT * FROM ordens WHERE substr(criado_em,1,?) = ?",
                                                 (len(prefixo), prefixo))]
        entregues = [o for o in linhas if o["status"] == "entregue"]
        por_servico: dict[str, dict[str, Any]] = {}
        for o in entregues:
            parte = o["valor"] / max(1, len(o["servicos"]))
            for s in o["servicos"]:
                x = por_servico.setdefault(s, {"nome": cat.get(s, {}).get("nome", s), "qtd": 0, "valor": 0.0})
                x["qtd"] += 1
                x["valor"] = round(x["valor"] + parte, 2)
        tempos = []
        for o in entregues:
            if o.get("entregue_em"):
                ini, fim = datetime.fromisoformat(o["criado_em"]), datetime.fromisoformat(o["entregue_em"])
                tempos.append((fim - ini).total_seconds() / 60)
        return {"atendimentos": len(linhas), "entregues": len(entregues),
                "faturamento": round(sum(o["valor"] for o in entregues), 2),
                "por_servico": sorted(por_servico.values(), key=lambda x: -x["valor"]),
                "tempo_medio_min": round(sum(tempos) / len(tempos)) if tempos else None}

    abertas = {s: con.execute("SELECT COUNT(*) FROM ordens WHERE status=?", (s,)).fetchone()[0] for s in STATUS}
    return {"dia": periodo(dia), "mes": periodo(mes), "por_status": abertas}


def csv_ordens(con: sqlite3.Connection) -> str:
    cat = catalogo()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["OS", "Data", "Cliente", "Aparelho", "Serviços", "Valor (R$)", "Status", "Entregue em"])
    for o in ordens(con, limite=100000):
        w.writerow([o["id"], o["criado_em"], o.get("cliente") or "", o.get("aparelho") or "",
                    ", ".join(cat.get(s, {}).get("nome", s) for s in o["servicos"]),
                    f"{o['valor']:.2f}".replace(".", ","), NOMES_STATUS[o["status"]], o.get("entregue_em") or ""])
    return "﻿" + buf.getvalue()  # BOM: o Excel abre com acentos certos
