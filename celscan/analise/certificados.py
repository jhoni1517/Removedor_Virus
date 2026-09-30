"""Certificados oficiais de apps (bancos, carteiras, gov.br...) para detectar cópias falsificadas."""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from celscan.config import DADOS
from celscan.core import bases

PLAY_STORE = "com.android.vending"

BASE = bases.registrar(bases.Base(
    nome="certificados", descricao="Certificados oficiais de bancos e apps populares (Brasil)",
    arquivo="certificados_oficiais.yaml", validade_s=7 * 86400,
    baixar=None,  # ainda sem fonte on-line confiável: só a lista conferida que vem com o programa
    embutido=DADOS / "certificados_oficiais.yaml",
))


@dataclass(frozen=True)
class AppOficial:
    pacote: str
    nome: str
    sha256: frozenset[str]


def carregar() -> dict[str, AppOficial]:
    texto = bases.ler("certificados") or ""
    dados = yaml.safe_load(texto) or {}
    res = {}
    for item in dados.get("apps") or []:
        certs = frozenset(str(c).replace(":", "").upper() for c in item.get("sha256") or [])
        if item.get("pacote") and certs:
            res[item["pacote"]] = AppOficial(item["pacote"], item.get("nome", item["pacote"]), certs)
    return res


def conferir(pacote: str, cert: dict | None, oficiais: dict[str, AppOficial]) -> str | None:
    """'falso' se o pacote é de um app oficial mas o certificado é outro; 'ok' se bate; None se não se aplica."""
    oficial = oficiais.get(pacote)
    if not oficial or not cert or not cert.get("sha256"):
        return None
    return "ok" if cert["sha256"].upper() in oficial.sha256 else "falso"


def registrar_do_aparelho(ap) -> list[dict]:
    """Lê o certificado dos apps de banco oficiais instalados PELA PLAY STORE neste aparelho e guarda na
    lista local (~/.celscan/bases/certificados_oficiais.yaml). Apps de outra origem são ignorados, para
    nunca registrar uma cópia falsa como se fosse a oficial."""
    import shlex

    from celscan.analise import apksig, pix
    from celscan.core import parsers

    b = pix.carregar()
    novos = []
    for pkg, (apk, instalador) in parsers.pacotes(ap.sh("pm list packages -f -i -3")).items():
        if pkg not in b.oficiais or instalador != PLAY_STORE or not apk:
            continue
        tamanho = ap.sh(f"stat -c %s {shlex.quote(apk)}").strip()
        if not tamanho.isdigit():
            continue
        cert = apksig.ler_remoto(ap, apk, int(tamanho))
        if cert and not cert.get("debug"):
            novos.append({"pacote": pkg, "nome": b.oficiais[pkg].nome, "sha256": [cert["sha256"]]})
    if novos:
        _mesclar_local(novos)
    return novos


def _mesclar_local(novos: list[dict]) -> None:
    dados = yaml.safe_load(bases.ler("certificados") or "") or {}
    por_pacote = {a["pacote"]: a for a in dados.get("apps") or []}
    for n in novos:
        atual = por_pacote.setdefault(n["pacote"], {"pacote": n["pacote"], "nome": n["nome"], "sha256": []})
        atual["sha256"] = sorted({*atual.get("sha256", []), *n["sha256"]})
    bases.PASTA.mkdir(parents=True, exist_ok=True)
    cabecalho = "# Certificados conferidos neste computador (celscan certificados-bancos).\n"
    corpo = yaml.safe_dump({"versao": 1, "apps": list(por_pacote.values())}, allow_unicode=True, sort_keys=False)
    BASE.caminho.write_text(cabecalho + corpo, encoding="utf-8")
