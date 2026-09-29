"""Laudo em HTML (imprimível) e JSON."""
import html
import json
from datetime import datetime
from pathlib import Path

COR = {"ALTO": "#b3261e", "MÉDIO": "#b7791f", "BAIXO": "#5b6b7a", "OK": "#1f7a4d", "PERMITIDO": "#1f7a4d"}
VEREDITO = {"Excelente": "#1f7a4d", "Bom": "#1f7a4d", "Atenção": "#b7791f", "Crítico": "#b3261e"}

CSS = """
:root{--papel:#f4f1ea;--tinta:#1d1d1b;--fraco:#6b665c;--linha:#d9d3c5}
*{box-sizing:border-box}
body{margin:0;background:#e6e1d6;color:var(--tinta);font:15px/1.55 "Segoe UI",system-ui,sans-serif}
.folha{max-width:880px;margin:32px auto;background:var(--papel);padding:48px 56px;box-shadow:0 1px 3px #0002}
h1,h2{font-family:Bahnschrift,"DIN Alternate","Arial Narrow",sans-serif;font-weight:600;letter-spacing:.01em;margin:0}
h1{font-size:30px}h2{font-size:19px;margin:36px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--tinta)}
.topo{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;border-bottom:1px solid var(--linha);padding-bottom:20px}
.topo p{margin:4px 0 0;color:var(--fraco)}
.carimbo{border:3px solid;border-radius:6px;padding:10px 18px;transform:rotate(-4deg);text-align:center;min-width:150px;font-family:Bahnschrift,"Arial Narrow",sans-serif}
.carimbo b{display:block;font-size:40px;line-height:1}.carimbo span{font-size:17px}
dl{display:grid;grid-template-columns:repeat(3,1fr);gap:10px 24px;margin:20px 0 0}
dt{color:var(--fraco);font-size:13px}dd{margin:0;font-weight:600}
.alerta{border-left:4px solid;padding:8px 12px;margin:8px 0;background:#fff8}
.app{border:1px solid var(--linha);border-left:5px solid;border-radius:4px;padding:12px 16px;margin:10px 0;background:#fff6;break-inside:avoid}
.app header{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
code{font-family:"Cascadia Mono",Consolas,monospace;font-size:14px}
.nivel{font-weight:700;font-size:13px}.app ul{margin:6px 0 0;padding-left:20px;color:#333}
.ameaca{color:#b3261e;font-weight:700}
.sig{color:var(--fraco);font-size:14px;margin:2px 0 0}.fazer{font-size:14px;margin:2px 0 6px}
.fazer:before{content:"O que fazer: ";font-weight:600}
table{width:100%;border-collapse:collapse}td{padding:5px 0;border-bottom:1px solid var(--linha)}td:last-child{text-align:right}
.rodape{margin-top:40px;color:var(--fraco);font-size:13px;border-top:1px solid var(--linha);padding-top:12px}
@media print{body{background:#fff}.folha{box-shadow:none;margin:0;max-width:none;padding:24px}}
"""


def _e(x):
    return html.escape(str(x if x is not None else "—"))


def gerar(pasta, info, nota, rotulo, achados, resultados, loja=None, diag=None, acoes=None):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now()
    base = pasta / f"laudo_{info['modelo'].replace(' ', '_')}_{agora:%Y%m%d_%H%M%S}"
    base.with_suffix(".json").write_text(json.dumps(
        {"data": agora.isoformat(timespec="seconds"), "aparelho": info, "nota": nota, "veredito": rotulo,
         "achados_aparelho": achados, "apps": resultados, "diagnostico": diag, "acoes": acoes},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    cor = VEREDITO[rotulo]
    risco = [r for r in resultados if r["nivel"] in ("ALTO", "MÉDIO")]
    partes = [f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Laudo CelScan — {_e(info['modelo'])}</title>
<style>{CSS}</style><div class="folha">
<div class="topo"><div><h1>Laudo de segurança do celular</h1>
<p>{_e(loja) + ' · ' if loja else ''}{agora:%d/%m/%Y às %H:%M}</p></div>
<div class="carimbo" style="color:{cor};border-color:{cor}"><b>{nota}</b><span>{_e(rotulo)}</span></div></div>
<dl><div><dt>Aparelho</dt><dd>{_e(info['fabricante'])} {_e(info['modelo'])}</dd></div>
<div><dt>Android</dt><dd>{_e(info['android'])}</dd></div>
<div><dt>Atualização de segurança</dt><dd>{_e(info['patch_seguranca'])}</dd></div>
<div><dt>Apps analisados</dt><dd>{len(resultados)}</dd></div>
<div><dt>Com risco médio ou alto</dt><dd>{len(risco)}</dd></div>
<div><dt>Serial</dt><dd><code>{_e(info['serial'])}</code></dd></div></dl>"""]

    partes.append("<h2>Configurações do aparelho</h2>")
    if achados:
        partes += [f'<div class="alerta" style="border-color:{COR[a["nivel"]]}"><span class="nivel" '
                   f'style="color:{COR[a["nivel"]]}">{_e(a["nivel"])}</span> · <b>{_e(a["titulo"])}</b>'
                   f'<p class="sig">{_e(a["significa"])}</p><p class="fazer">{_e(a["fazer"])}</p></div>'
                   for a in achados]
    else:
        partes.append("<p>Nenhum problema encontrado nas configurações.</p>")

    partes.append("<h2>Apps que merecem atenção</h2>")
    if not risco:
        partes.append("<p>Nenhum app com risco médio ou alto.</p>")
    for r in risco:
        c = COR[r["nivel"]]
        amea = f'<p class="ameaca">{_e(r["ameaca"])}</p>' if r.get("ameaca") else ""
        motivos = "".join(f'<li><b>{_e(x["titulo"])}</b><p class="sig">{_e(x["significa"])}</p>'
                          f'<p class="fazer">{_e(x["fazer"])}</p></li>'
                          for x in r.get("achados", []) if x["chave"] != "ameaca_conhecida")
        partes.append(f"""<div class="app" style="border-left-color:{c}"><header><code>{_e(r['pacote'])}</code>
<span class="nivel" style="color:{c}">{_e(r['nivel'])} · {r['score']}</span></header>{amea}<ul>{motivos}</ul></div>""")

    if diag:
        partes.append("<h2>Saúde do aparelho</h2><table>")
        b, a = diag.get("bateria") or {}, diag.get("armazenamento")
        linhas = [("Bateria", f"{_e(b.get('nivel'))}% · saúde {_e(b.get('saude'))} · {_e(b.get('temperatura'))}")]
        if b.get("ciclos"):
            linhas.append(("Ciclos de carga", _e(b["ciclos"])))
        if a:
            linhas.append(("Armazenamento livre", f"{a['livre_gb']:.1f} de {a['total_gb']:.0f} GB"))
        linhas += [(_e(p["pasta"]), f"{p['gb']:.1f} GB") for p in diag.get("pastas", [])[:5]]
        partes += [f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in linhas]
        partes.append("</table>")
    if acoes:
        partes.append("<h2>Ações realizadas</h2><ul>" + "".join(f"<li>{_e(a)}</li>" for a in acoes) + "</ul>")

    partes.append(f"""<div class="rodape">Gerado pelo CelScan. A análise combina indicadores públicos de ameaças
(Amnesty/MVT, Echap), VirusTotal e heurística de permissões. Nenhuma ferramenta garante 100% de detecção.</div></div></html>""")
    arq = base.with_suffix(".html")
    arq.write_text("\n".join(partes), encoding="utf-8")
    return arq
