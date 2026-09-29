"""Pontuação de risco: aplica as regras (regras.yaml) aos dados coletados.

Não fala com o aparelho. Cada achado vem com título curto, "o que significa" e "o que fazer".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from celscan.analise import regras as regras_mod
from celscan.analise.regras import Regras
from celscan.config import LOJAS, SMS_CONHECIDOS
from celscan.core.coleta import AppBruto, DadosAparelho

Achado = dict[str, Any]

_padrao: Regras | None = None


def regras_padrao() -> Regras:
    global _padrao
    if _padrao is None:
        _padrao = regras_mod.carregar()
    return _padrao


def nivel(score: int, regras: Regras | None = None) -> str:
    lim = (regras or regras_padrao()).limites
    if score >= lim.get("alto", 60):
        return "ALTO"
    if score >= lim.get("medio", 30):
        return "MÉDIO"
    return "BAIXO" if score > 0 else "OK"


def achados_aparelho(dados: DadosAparelho, regras: Regras | None = None,
                     agora: datetime | None = None) -> list[Achado]:
    r = regras or regras_padrao()
    ra, par = r.aparelho, r.parametros
    a: list[Achado] = []
    agora = agora or datetime.now()
    try:
        patch = datetime.strptime(dados.info()["patch_seguranca"], "%Y-%m-%d")
        meses = (agora - patch).days // 30
        if meses >= par.get("patch_alto_meses", 24):
            a.append(ra["patch_muito_antigo"].achado(meses))
        elif meses >= par.get("patch_medio_meses", 12):
            a.append(ra["patch_antigo"].achado(meses))
    except ValueError:
        pass
    if dados.proxy and dados.proxy not in ("null", ":0"):
        a.append(ra["proxy_global"].achado(dados.proxy))
    if dados.su:
        a.append(ra["root"].achado(", ".join(dados.su)))
    if dados.props.get("ro.boot.verifiedbootstate") == "orange" or dados.props.get("ro.boot.flash.locked") == "0":
        a.append(ra["bootloader"].achado())
    for o in sorted(dados.owners):
        a.append(ra["gerenciado"].achado(o))
    if dados.sms and dados.sms not in SMS_CONHECIDOS:
        a.append(ra["sms_incomum"].achado(dados.sms))
    return a


def pontuar_app(app: AppBruto, dados: DadosAparelho, iocs: Any = None, permitidos: set[str] | None = None,
                agora: datetime | None = None, regras: Regras | None = None) -> dict[str, Any]:
    r = regras or regras_padrao()
    ra, par, lim = r.apps, r.parametros, r.limites
    agora = agora or datetime.now()
    pkg = app.pacote
    a: list[Achado] = []
    ioc = iocs.checar(pkg, app.cert, app.sha256) if iocs else None
    if ioc:
        a.append(ra["ameaca_conhecida"].achado(ioc))
    loja = LOJAS.get(app.instalador or "")
    if pkg in dados.acess:
        a.append(ra["acessibilidade"].achado())
    if pkg in dados.admins:
        a.append(ra["administrador"].achado())
    if pkg in dados.owners:
        a.append(ra["device_owner"].achado())
    if pkg in dados.notif:
        a.append(ra["leitor_notificacoes"].achado())
    if not app.sistema:
        if dados.icones is not None and pkg not in dados.icones:
            a.append(ra["sem_icone"].achado())
        if not loja:
            a.append(ra["fora_da_loja"].achado(app.instalador or "origem desconhecida"))
    if pkg == dados.sms and pkg not in SMS_CONHECIDOS:
        a.append(ra["sms_padrao"].achado())
    a += [r.permissoes[p].achado() for p in sorted(app.perms) if p in r.permissoes]
    a += [r.appops[o].achado() for o in sorted(app.appops) if o in r.appops]
    if app.cert and app.cert.get("debug"):
        a.append(ra["certificado_debug"].achado())
    vt = app.vt or {}
    if vt.get("malicioso"):
        a.append(ra["virustotal_detectado"].achado(
            f"{vt['malicioso']} antivírus detectaram ({vt.get('rotulo') or 'sem rótulo'})"))
    elif vt.get("conhecido") is False and not loja and not app.sistema:
        a.append(ra["virustotal_desconhecido"].achado())
    if pkg in dados.sempre_ativo:
        a.append(ra["sempre_ativo"].achado())
    if app.instalado and (agora - app.instalado).days < par.get("recente_dias", 7):
        a.append(ra["instalado_recente"].achado((agora - app.instalado).days))

    a.sort(key=lambda x: x["peso"], reverse=True)
    score = min(lim.get("maximo", 100), sum(x["peso"] for x in a))
    permitido = pkg in (permitidos or set()) and bool(loja) and not ioc
    if permitido:
        score = min(score, lim.get("permitido_teto", 10))
    return {
        "pacote": pkg, "score": score, "nivel": "PERMITIDO" if permitido else nivel(score, r),
        "motivos": [x["titulo"] for x in a], "achados": a, "ameaca": ioc,
        "instalador": app.instalador, "loja": loja, "sistema": app.sistema,
        "desativado": pkg in dados.desativados, "versao": app.versao,
        "instalado": app.instalado.isoformat() if app.instalado else None,
        "sha256": app.sha256, "cert": app.cert, "virustotal": app.vt,
        "admins": dados.admins.get(pkg, []),
    }


def pontuar(dados: DadosAparelho, iocs: Any = None, permitidos: set[str] | None = None,
            agora: datetime | None = None, regras: Regras | None = None) -> tuple[list[Achado], list[dict[str, Any]]]:
    resultados = [pontuar_app(app, dados, iocs, permitidos, agora, regras) for app in dados.apps.values()]
    resultados.sort(key=lambda r: r["score"], reverse=True)
    return achados_aparelho(dados, regras, agora), resultados


def nota(achados: list[Achado], resultados: list[dict[str, Any]], regras: Regras | None = None) -> tuple[int, str]:
    cfg = (regras or regras_padrao()).nota
    n = 100
    n -= sum(cfg.get("aparelho_alto", 25) if a["nivel"] == "ALTO" else cfg.get("aparelho_outro", 10) for a in achados)
    n -= sum(cfg.get("app_alto", 30) if r["nivel"] == "ALTO" else cfg.get("app_medio", 8) if r["nivel"] == "MÉDIO"
             else 0 for r in resultados)
    n = max(0, n)
    if any(r.get("ameaca") for r in resultados):
        n = min(n, cfg.get("teto_com_ameaca", 20))  # ameaça conhecida = crítico, sempre
    rotulos = cfg.get("rotulos") or [[90, "Excelente"], [70, "Bom"], [50, "Atenção"], [0, "Crítico"]]
    rot = next(nome for minimo, nome in rotulos if n >= minimo)
    return n, rot
