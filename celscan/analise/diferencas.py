"""O que mudou no aparelho desde a última visita (compara dois retratos de varredura).

Destaques em linguagem leiga: apps novos, apps que sumiram, risco que subiu ou caiu, alertas
novos num app que já existia e — o mais sério — certificado de assinatura trocado no mesmo
pacote (sinal clássico de app legítimo substituído por uma cópia adulterada).
"""

from __future__ import annotations

from typing import Any

ORDEM = {"OK": 0, "PERMITIDO": 0, "BAIXO": 1, "MÉDIO": 2, "ALTO": 3}


def _nome(a: dict[str, Any]) -> str:
    return a.get("nome") or a.get("pacote") or "?"


def _cert(a: dict[str, Any]) -> str | None:
    c = a.get("cert") or {}
    return c.get("sha256") if isinstance(c, dict) else None


def _chaves(a: dict[str, Any]) -> set[str]:
    return {x.get("chave") for x in (a.get("achados") or []) if x.get("chave")}


def _titulos(a: dict[str, Any]) -> dict[str, str]:
    return {x["chave"]: x.get("titulo", x["chave"]) for x in (a.get("achados") or []) if x.get("chave")}


def comparar(antes: dict[str, Any], depois: dict[str, Any], nota_antes: int | None = None,
             nota_depois: int | None = None) -> dict[str, Any]:
    a_apps = {a["pacote"]: a for a in antes.get("apps", [])}
    d_apps = {a["pacote"]: a for a in depois.get("apps", [])}

    novos = [{"pacote": p, "nome": _nome(d_apps[p]), "nivel": d_apps[p].get("nivel")}
             for p in sorted(set(d_apps) - set(a_apps))]
    removidos = [{"pacote": p, "nome": _nome(a_apps[p])} for p in sorted(set(a_apps) - set(d_apps))]

    piorou, melhorou, alertas_novos, cert_trocado, atualizados = [], [], [], [], []
    for p in sorted(set(a_apps) & set(d_apps)):
        a, d = a_apps[p], d_apps[p]
        na, nd = ORDEM.get(a.get("nivel", "OK"), 0), ORDEM.get(d.get("nivel", "OK"), 0)
        item = {"pacote": p, "nome": _nome(d), "de": a.get("nivel"), "para": d.get("nivel")}
        if nd > na:
            piorou.append(item)
        elif nd < na:
            melhorou.append(item)
        novas = _chaves(d) - _chaves(a)
        if novas:
            t = _titulos(d)
            alertas_novos.append({"pacote": p, "nome": _nome(d), "alertas": sorted(t[k] for k in novas)})
        ca, cd = _cert(a), _cert(d)
        if ca and cd and ca != cd:
            cert_trocado.append({"pacote": p, "nome": _nome(d), "antes": ca, "depois": cd})
        if a.get("versao") and d.get("versao") and a["versao"] != d["versao"]:
            atualizados.append({"pacote": p, "nome": _nome(d), "de": a["versao"], "para": d["versao"]})

    t_antes = {x.get("titulo") for x in antes.get("achados_aparelho", [])}
    t_depois = {x.get("titulo") for x in depois.get("achados_aparelho", [])}

    return {
        "nota": {"antes": nota_antes, "depois": nota_depois},
        "apps_novos": novos,
        "apps_removidos": removidos,
        "risco_subiu": piorou,
        "risco_caiu": melhorou,
        "alertas_novos": alertas_novos,
        "certificado_trocado": cert_trocado,
        "atualizados": atualizados,
        "aparelho_novos": sorted(t for t in t_depois - t_antes if t),
        "aparelho_resolvidos": sorted(t for t in t_antes - t_depois if t),
        "sem_mudancas": not (novos or removidos or piorou or melhorou or alertas_novos or cert_trocado
                             or t_depois ^ t_antes),
    }
