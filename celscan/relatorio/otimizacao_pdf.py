"""Relatório da otimização em PDF: o que estava errado, o que foi feito (com o resultado de cada etapa) e o que
foi medido depois. Serve para entregar ao cliente no balcão ou guardar o antes e depois do próprio celular."""

from __future__ import annotations

import io
import json
import re
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from celscan import __version__, config
from celscan.relatorio.pdf import CINZA, LINHA, VERDE, VERMELHO, _estilos, _t

GRAV = {"critica": ("CRÍTICO", VERMELHO), "alta": ("ALTO", VERMELHO), "media": ("MÉDIO", colors.HexColor("#b7791f")),
        "baixa": ("BAIXO", CINZA)}


def _pasta():
    return config.DIR / "otimizacoes"


def listar(serial: str | None = None) -> list[dict[str, Any]]:
    res = []
    for arq in sorted(_pasta().glob("*.json"), reverse=True)[:200]:
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if serial and d.get("serial") != serial:
            continue
        etapas = d.get("etapas") or []
        res.append({"id": d.get("id"), "data": d.get("data"), "modelo": d.get("modelo"),
                    "ok": sum(1 for e in etapas if e.get("ok")), "total": len(etapas),
                    "nota": (d.get("antes_depois") or {}).get("total")})
    return res


def ler(ident: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9]{1,24}-\d{6,12}", ident or ""):
        raise ValueError("relatório inválido")
    return json.loads((_pasta() / f"{ident}.json").read_text(encoding="utf-8"))


def _problemas(lista: list[dict[str, Any]], e: dict) -> list:
    if not lista:
        return [Paragraph("Nenhum problema encontrado.", e["normal"])]
    linhas = []
    for p in lista:
        rot, cor = GRAV.get(p.get("gravidade"), ("", CINZA))
        linhas.append([Paragraph(f'<font color="{cor.hexval()}"><b>{rot}</b></font>', e["normal"]),
                       Paragraph(f"<b>{_t(p.get('titulo'))}</b><br/>{_t(p.get('prova'))}", e["normal"])])
    t = Table(linhas, colWidths=[22 * mm, 150 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return [t]


def gerar(d: dict[str, Any], titulos: dict[str, str] | None = None) -> bytes:
    from celscan.acoes.turbo import NOMES_ETAPA

    titulos = {**NOMES_ETAPA, **(titulos or {})}
    e = _estilos()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="Relatório de otimização CelScan")
    data = datetime.fromtimestamp(d.get("data") or 0).strftime("%d/%m/%Y %H:%M")
    h: list = [Paragraph("Relatório de otimização", e["titulo"]),
                Paragraph(f"{_t(d.get('modelo'))} · {data} · CelScan {__version__}", e["normal"]), Spacer(1, 6 * mm)]
    nota = (d.get("antes_depois") or {}).get("total")
    if nota:
        sinal = "+" if nota["pontos"] >= 0 else ""
        h += [Paragraph(f"<b>Nota do celular: {nota['antes']} para {nota['depois']} ({sinal}{nota['pontos']} pontos"
                        + (f", {sinal}{nota['ganho_pct']}%" if nota.get("ganho_pct") is not None else "") + ")</b>",
                        e["normal"]), Spacer(1, 4 * mm)]
    h += [Paragraph("O que estava errado", e["h2"])] + _problemas((d.get("antes") or {}).get("problemas") or [], e)
    h += [Spacer(1, 4 * mm), Paragraph("O que foi feito", e["h2"])]
    linhas = []
    for et in d.get("etapas") or []:
        cor = VERDE if et.get("ok") else VERMELHO
        linhas.append([Paragraph(f'<font color="{cor.hexval()}"><b>{"OK" if et.get("ok") else "X"}</b></font>',
                                 e["normal"]),
                       Paragraph(f"<b>{_t(titulos.get(et['id'], et['id']))}</b> - {_t(et.get('detalhe') or '')}",
                                 e["normal"])])
    if linhas:
        t = Table(linhas, colWidths=[12 * mm, 160 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA)]))
        h.append(t)
    depois = d.get("depois") or {}
    h += [Spacer(1, 4 * mm), Paragraph("Conferido depois (medido de novo)", e["h2"])]
    h += _problemas(depois.get("problemas") or [], e)
    if depois.get("bons"):
        h += [Spacer(1, 2 * mm), Paragraph("<b>Está bom:</b> " + _t(" · ".join(depois["bons"])), e["normal"])]
    h += [Spacer(1, 6 * mm), Paragraph("Todos os ajustes podem ser desfeitos no Histórico do CelScan.", e["fraco"])]
    doc.build(h)
    return buf.getvalue()
