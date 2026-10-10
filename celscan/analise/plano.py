"""Plano de ação em passos (mesma lógica do plano.ts da interface), para o laudo em PDF e a CLI."""

from __future__ import annotations

from typing import Any

PALAVRAS_ESPIAO = ("stalkerware", "spyware", "pegasus", "predator", "espião")


def _nome(r: dict[str, Any]) -> str:
    return r.get("nome") or r.get("pacote") or "?"


def _espiao(r: dict[str, Any]) -> bool:
    if r.get("vigilancia") or any(a.get("chave") == "padrao_espiao" for a in r.get("achados") or []):
        return True
    ameaca = (r.get("ameaca") or "").lower()
    return any(p in ameaca for p in PALAVRAS_ESPIAO)


def plano_de_acao(apps: list[dict[str, Any]], achados_aparelho: list[dict[str, Any]],
                  removidos: set[str] | None = None) -> list[str]:
    """Do mais urgente ao menos. `removidos`: apps que já saíram neste atendimento (não entram no plano)."""
    fora = removidos or set()
    vivos = [r for r in apps if r.get("pacote") not in fora]
    altos = [r for r in vivos if r.get("nivel") == "ALTO" and not r.get("sistema")]
    medios = [r for r in vivos if r.get("nivel") == "MÉDIO" and not r.get("sistema")]
    passos: list[str] = []
    if any(_espiao(r) for r in vivos):
        passos.append("Há sinal de app espião: leia o aviso de segurança antes de remover qualquer coisa.")
    if any(a.get("chave") in ("administrador", "device_owner") for r in vivos for a in r.get("achados") or []):
        passos.append("Retire o administrador do aparelho antes de remover o app (senão ele se protege).")
    if any(r.get("removido_antes") for r in vivos):
        passos.append("Um app removido antes voltou: procure e remova primeiro quem instala outros apps, "
                      "depois os demais.")
    if altos:
        nomes = ", ".join(_nome(r) for r in altos[:4]) + ("…" if len(altos) > 4 else "")
        passos.append(f"Remova {'o app de risco alto' if len(altos) == 1 else f'os {len(altos)} apps de risco alto'}: "
                      f"{nomes}.")
    if medios:
        passos.append(f"Revise {len(medios)} app(s) de risco médio: remova os que o cliente não reconhecer.")
    passos += [a["fazer"] for a in achados_aparelho if a.get("nivel") != "BAIXO" and a.get("fazer")][:3]
    if passos:
        passos.append("Faça uma nova varredura para confirmar que ficou tudo limpo.")
    return passos
