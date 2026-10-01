"""Laudo em PDF (cliente, técnico e seminovo), com QR code de autenticidade.

Autenticidade: o código do laudo é o SHA-256 dos dados da varredura. O código fica guardado no
banco local; "Verificar laudo" (ou `celscan verificar CÓDIGO`) confirma que o laudo saiu deste
computador e que os dados são os mesmos. Obs.: as fontes padrão do PDF só têm caracteres latinos,
por isso o texto evita setas e símbolos especiais.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from typing import Any

import qrcode
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from celscan import __version__

VERDE, AMBAR, VERMELHO = colors.HexColor("#1f7a4d"), colors.HexColor("#b7791f"), colors.HexColor("#b3261e")
CINZA, TINTA, LINHA = colors.HexColor("#5b6b7a"), colors.HexColor("#1d1d1b"), colors.HexColor("#d9d3c5")
COR_NIVEL = {"ALTO": VERMELHO, "MÉDIO": AMBAR, "BAIXO": CINZA, "OK": VERDE, "PERMITIDO": VERDE}
TIPOS = {"rapido": "Rápida", "completo": "Completa", "profundo": "Profunda"}
TROCAS = {"→": "-", "✔": "OK", "✘": "X", "…": "...", "•": "-"}


def _t(texto: Any) -> str:
    """Escapa para o Paragraph e troca símbolos que a fonte padrão não tem."""
    s = "—" if texto is None else str(texto)
    for a, b in TROCAS.items():
        s = s.replace(a, b)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hash_varredura(meta: dict[str, Any], retrato: dict[str, Any]) -> str:
    dados = {"id": meta["id"], "data": meta["data"], "nota": meta["nota"], "retrato": retrato}
    return hashlib.sha256(json.dumps(dados, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def codigo_curto(h: str) -> str:
    return "-".join(h[i:i + 4] for i in range(0, 16, 4)).upper()


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20,
                                 leading=24, alignment=0, spaceAfter=2, textColor=TINTA),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=9.5, textColor=CINZA),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16,
                             spaceBefore=12, spaceAfter=6, textColor=TINTA),
        "normal": ParagraphStyle("normal", parent=base["Normal"], fontSize=9.5, leading=13, textColor=TINTA),
        "fraco": ParagraphStyle("fraco", parent=base["Normal"], fontSize=8.5, leading=11, textColor=CINZA),
        "mono": ParagraphStyle("mono", parent=base["Normal"], fontName="Courier", fontSize=8, leading=10),
        "nota": ParagraphStyle("nota", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=30, leading=32,
                               alignment=TA_CENTER),
        "rotulo": ParagraphStyle("rotulo", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11,
                                 alignment=TA_CENTER),
    }


class QR(Flowable):
    def __init__(self, texto: str, lado: float = 26 * mm):
        super().__init__()
        self.texto, self.lado = texto, lado
        self.width = self.height = lado

    def draw(self) -> None:
        matriz = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        matriz.add_data(self.texto)
        matriz.make(fit=True)
        m = matriz.get_matrix()
        n = len(m)
        passo = self.lado / n
        d = Drawing(self.lado, self.lado)
        for y, linha in enumerate(m):
            for x, cheio in enumerate(linha):
                if cheio:
                    d.add(Rect(x * passo, self.lado - (y + 1) * passo, passo, passo, fillColor=colors.black,
                               strokeColor=None))
        renderPDF.draw(d, self.canv, 0, 0)


def _cor_nota(n: int) -> colors.Color:
    return VERDE if n >= 70 else AMBAR if n >= 50 else VERMELHO


def _cabecalho(meta: dict, retrato: dict, e: dict, versao: str, loja: str | None) -> list:
    ap = retrato.get("aparelho", {})
    data = datetime.fromisoformat(meta["data"]).strftime("%d/%m/%Y às %H:%M")
    titulo = {"tecnico": "Laudo técnico de segurança do celular",
              "seminovo": "Laudo de seminovo: condições do aparelho"}.get(versao, "Laudo de segurança do celular")
    esquerda = [Paragraph(_t(titulo), e["titulo"]),
                Paragraph(_t(f"{loja + ' · ' if loja else ''}{data} · varredura nº {meta['id']}"), e["sub"])]
    cor = _cor_nota(meta["nota"])
    carimbo = Table([[Paragraph(f'<font color="{cor.hexval()}">{meta["nota"]}</font>', e["nota"])],
                     [Paragraph(f'<font color="{cor.hexval()}">{_t(meta["veredito"])}</font>', e["rotulo"])]],
                    colWidths=[38 * mm], rowHeights=[13 * mm, 7 * mm])
    carimbo.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 2, cor), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    topo = Table([[esquerda, carimbo]], colWidths=[132 * mm, 40 * mm])
    topo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINHA),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    apps = retrato.get("apps", [])
    risco = sum(1 for r in apps if r.get("nivel") in ("ALTO", "MÉDIO"))
    campos = [("Aparelho", f"{ap.get('fabricante', '?')} {ap.get('modelo', '?')}"),
              ("Android", ap.get("android")), ("Atualização de segurança", ap.get("patch_seguranca")),
              ("Apps analisados", len(apps)), ("Com risco médio ou alto", risco),
              ("Tipo de varredura", TIPOS.get(meta.get("modo") or "", meta.get("modo")))]
    linhas = [[Paragraph(_t(k), e["fraco"]) for k, _ in campos[i:i + 3]] for i in (0, 3)]
    valores = [[Paragraph(f"<b>{_t(v)}</b>", e["normal"]) for _, v in campos[i:i + 3]] for i in (0, 3)]
    grade = Table([linhas[0], valores[0], linhas[1], valores[1]], colWidths=[58 * mm] * 3)
    grade.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                               ("BOTTOMPADDING", (0, 1), (-1, 1), 6)]))
    return [topo, Spacer(1, 6), grade]


def _achado(a: dict, e: dict, nivel: str | None = None) -> list:
    cor = COR_NIVEL.get(nivel or a.get("nivel") or "", CINZA)
    return [Paragraph(f'<font color="{cor.hexval()}"><b>{_t(nivel or a.get("nivel") or "")}</b></font> '
                      f'<b>{_t(a["titulo"])}</b>', e["normal"]),
            Paragraph(_t(a["significa"]), e["fraco"]),
            Paragraph(f"<b>O que fazer:</b> {_t(a['fazer'])}", e["normal"]), Spacer(1, 5)]


def _cartao_app(r: dict, e: dict, tecnico: bool) -> KeepTogether:
    cor = COR_NIVEL.get(r["nivel"], CINZA)
    itens = [Paragraph(f'<font face="Courier-Bold">{_t(r["pacote"])}</font> '
                       f'<font color="{cor.hexval()}"><b>{_t(r["nivel"])} · {r["score"]}</b></font>', e["normal"])]
    if r.get("ameaca"):
        itens.append(Paragraph(f'<font color="{VERMELHO.hexval()}"><b>{_t(r["ameaca"])}</b></font>', e["normal"]))
    for a in r.get("achados", []):
        if a["chave"] == "ameaca_conhecida":
            continue
        itens += [Paragraph(f"- <b>{_t(a['titulo'])}</b>: {_t(a['significa'])}", e["fraco"])]
    if r.get("achados"):
        itens.append(Paragraph(f"<b>O que fazer:</b> {_t(r['achados'][0]['fazer'])}", e["normal"]))
    if tecnico:
        cert = (r.get("cert") or {}).get("sha256")
        extras = [f"instalador: {r.get('instalador') or 'desconhecido'}", f"versão: {r.get('versao') or '?'}",
                  f"SHA-256 do APK: {r.get('sha256') or '?'}", f"certificado: {cert or '?'}"]
        itens += [Paragraph(_t(x), e["mono"]) for x in extras]
    caixa = Table([[itens]], colWidths=[172 * mm])
    caixa.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 3, cor), ("BOX", (0, 0), (-1, -1), 0.4, LINHA),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return KeepTogether([caixa, Spacer(1, 5)])


def _tabela_apps(apps: list[dict], e: dict) -> Table:
    dados = [[Paragraph(f"<b>{x}</b>", e["fraco"]) for x in ("Pontos", "Nível", "App", "Origem")]]
    for r in apps:
        dados.append([Paragraph(str(r["score"]), e["fraco"]), Paragraph(_t(r["nivel"]), e["fraco"]),
                      Paragraph(_t(r["pacote"]), e["mono"]), Paragraph(_t(r.get("loja") or r.get("instalador")
                                                                             or "desconhecida"), e["fraco"])])
    t = Table(dados, colWidths=[16 * mm, 22 * mm, 90 * mm, 44 * mm], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


CHECKLIST = ("Tela (manchas, toque em toda a área)", "Câmera traseira", "Câmera frontal", "Alto-falante",
             "Microfone", "Fone/conector", "Botões (volume, liga)", "Biometria (digital/rosto)", "Carregamento",
             "Wi-Fi", "Bluetooth", "Chip e sinal", "Vibração", "Sensor de proximidade")


def _veredito_bateria(pct: Any) -> tuple[str, colors.Color]:
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return "não verificado neste aparelho", CINZA
    if p >= 80:
        return "boa", VERDE
    if p >= 60:
        return "desgastada (dura menos que nova)", AMBAR
    return "recomenda-se trocar", VERMELHO


def _tabela_campos(campos: list[tuple[str, Any]], e: dict) -> Table:
    t = Table([[Paragraph(_t(k), e["fraco"]), Paragraph(f"<b>{_t(v)}</b>", e["normal"])] for k, v in campos],
              colWidths=[55 * mm, 117 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _secao_seminovo(retrato: dict, diag: dict | None, e: dict) -> list:
    ap = retrato.get("aparelho", {})
    d = diag or {}
    ident, b = d.get("identificacao") or {}, d.get("bateria") or {}
    arm, ram = d.get("armazenamento"), d.get("ram")
    h: list = [Paragraph("Identificação", e["h2"]), _tabela_campos([
        ("Modelo", ident.get("marketname") or f"{ap.get('fabricante', '?')} {ap.get('modelo', '?')}"),
        ("IMEI", ident.get("imei") or "não disponível por USB (confira em *#06#)"),
        ("Android / atualização", f"{ap.get('android', '?')} / {ap.get('patch_seguranca', '?')}"),
        ("Número de série", ident.get("serial") or ap.get("serial")),
    ], e)]
    texto, cor = _veredito_bateria(b.get("saude_pct"))
    capacidade = (f"~{b['saude_pct']}% da original ({b.get('capacidade_mah', '?')} de "
                  f"{b.get('capacidade_projeto_mah', '?')} mAh)") if b.get("saude_pct") else "não verificado"
    h += [Paragraph("Bateria", e["h2"]),
          Paragraph(f'Condição: <font color="{cor.hexval()}"><b>{_t(texto)}</b></font>', e["normal"]), Spacer(1, 3),
          _tabela_campos([("Capacidade real", capacidade), ("Ciclos de carga", b.get("ciclos") or "não informado"),
                          ("Saúde informada pelo sistema", b.get("saude") or "não informado"),
                          ("Temperatura na hora do teste", b.get("temperatura") or "não informado")], e)]
    h += [Paragraph("Armazenamento e memória", e["h2"]), _tabela_campos([
        ("Armazenamento", f"{arm['total_gb']:.0f} GB ({arm['livre_gb']:.1f} GB livres)" if arm else "não verificado"),
        ("Memória RAM", f"{ram['total_gb']:.1f} GB" if ram else "não verificado"),
    ], e)]
    if not diag:
        h.append(Paragraph("Diagnóstico de hardware não disponível: o aparelho não estava conectado ao gerar o laudo.",
                           e["fraco"]))
    apps = retrato.get("apps", [])
    ameacas = [r for r in apps if r.get("ameaca")]
    risco = sum(1 for r in apps if r.get("nivel") in ("ALTO", "MÉDIO"))
    h += [Paragraph("Segurança", e["h2"]), _tabela_campos([
        ("Ameaças conhecidas", f"{len(ameacas)} encontrada(s)" if ameacas else "nenhuma encontrada"),
        ("Apps com risco médio ou alto", risco), ("Apps analisados", len(apps)),
    ], e)]
    caixa = "[   ]"
    linhas = [[Paragraph("<b>Item conferido pelo técnico</b>", e["fraco"]), Paragraph("<b>OK</b>", e["fraco"]),
               Paragraph("<b>Problema</b>", e["fraco"]), Paragraph("<b>Não testado</b>", e["fraco"])]]
    linhas += [[Paragraph(_t(i), e["normal"]), caixa, caixa, caixa] for i in CHECKLIST]
    t = Table(linhas, colWidths=[100 * mm, 24 * mm, 24 * mm, 24 * mm], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                           ("FONTNAME", (1, 1), (-1, -1), "Courier")]))
    h += [Paragraph("Checklist de hardware", e["h2"]), t, Spacer(1, 14),
          Paragraph("Observações: ______________________________________________________________________", e["normal"]),
          Spacer(1, 18),
          Paragraph("Assinatura do técnico: ______________________________    "
                    "Assinatura do cliente: ______________________________", e["normal"])]
    return h


def gerar_pdf(meta: dict[str, Any], retrato: dict[str, Any], versao: str = "cliente",
              loja: str | None = None, acoes: list[dict] | None = None,
              diagnostico: dict | None = None) -> tuple[bytes, str]:
    """Devolve (bytes do PDF, hash de autenticidade). 'seminovo' usa o diagnóstico de hardware, se houver."""
    if versao not in ("cliente", "tecnico", "seminovo"):
        raise ValueError("versao deve ser 'cliente', 'tecnico' ou 'seminovo'")
    tecnico = versao == "tecnico"
    e = _estilos()
    h = hash_varredura(meta, retrato)
    codigo = codigo_curto(h)
    historia: list = _cabecalho(meta, retrato, e, versao, loja)
    if versao == "seminovo":
        historia += _secao_seminovo(retrato, diagnostico, e)
        return _finalizar(historia, meta, h, codigo, e)

    achados = retrato.get("achados_aparelho", [])
    historia.append(Paragraph("Configurações do aparelho", e["h2"]))
    if achados:
        for a in achados:
            historia += _achado(a, e)
    else:
        historia.append(Paragraph("Nenhum problema encontrado nas configurações.", e["normal"]))

    apps = retrato.get("apps", [])
    risco = [r for r in apps if r.get("nivel") in ("ALTO", "MÉDIO")]
    historia.append(Paragraph("Apps que merecem atenção", e["h2"]))
    if not risco:
        historia.append(Paragraph("Nenhum app com risco médio ou alto.", e["normal"]))
    historia += [_cartao_app(r, e, tecnico) for r in risco]

    if acoes:
        historia.append(Paragraph("Ações realizadas", e["h2"]))
        for a in acoes:
            desfeita = " (desfeita depois)" if a.get("desfeita_em") else ""
            historia.append(Paragraph(_t(f"- {a.get('pacote') or ''} {a.get('detalhe') or ''}{desfeita}"),
                                      e["normal"]))
    avisos = retrato.get("avisos") or []
    if avisos:
        historia.append(Paragraph("Verificações não disponíveis neste aparelho", e["h2"]))
        historia += [Paragraph(_t(f"- {a}"), e["fraco"]) for a in avisos]
    if tecnico:
        historia.append(Paragraph("Todos os apps analisados", e["h2"]))
        historia.append(_tabela_apps(apps, e))
        duracao = meta.get("duracao_s")
        historia.append(Spacer(1, 6))
        historia.append(Paragraph(_t(f"Serial: {retrato.get('aparelho', {}).get('serial')} · duração: "
                                     f"{duracao:.0f} s · CelScan {__version__} · SHA-256 dos dados: {h}")
                                  if duracao is not None else _t(f"SHA-256 dos dados: {h}"), e["mono"]))

    return _finalizar(historia, meta, h, codigo, e)


def _finalizar(historia: list, meta: dict, h: str, codigo: str, e: dict) -> tuple[bytes, str]:
    texto_qr = f"CELSCAN-LAUDO|{meta['id']}|{h}"
    rodape = Table([[QR(texto_qr), [
        Paragraph(f"<b>Código de verificação: {codigo}</b>", e["normal"]),
        Paragraph("Para conferir a autenticidade, abra o CelScan no computador que emitiu este laudo e use "
                  "\"Verificar laudo\" (ou o comando <font face='Courier'>celscan verificar " + codigo + "</font>).",
                  e["fraco"]),
        Paragraph("A análise combina indicadores públicos de ameaças (Amnesty/MVT, Echap), VirusTotal quando "
                  "disponível e regras de permissões. Nenhuma ferramenta garante 100% de detecção.", e["fraco"]),
    ]]], colWidths=[30 * mm, 142 * mm])
    rodape.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINHA),
                                ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    historia += [Spacer(1, 12), KeepTogether([rodape])]

    def numerar(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(CINZA)
        canvas.drawString(18 * mm, 10 * mm, f"CelScan · laudo nº {meta['id']} · verificação {codigo}")
        canvas.drawRightString(192 * mm, 10 * mm, f"página {doc.page}")
        canvas.restoreState()

    saida = io.BytesIO()
    doc = SimpleDocTemplate(saida, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"Laudo CelScan nº {meta['id']}", author="CelScan",
                            subject=f"Verificação {codigo}")
    doc.build(historia, onFirstPage=numerar, onLaterPages=numerar)
    return saida.getvalue(), h
