"""Assinaturas de vírus offline: impressão digital (SHA-256) de APKs maliciosos conhecidos.

Fontes, todas usadas SEM internet na hora da verificação:
- MalwareBazaar (abuse.ch): os APKs maliciosos mais recentes enviados por pesquisadores, com o nome da família
  (Anatsa, SpyNote, Cerberus...). Precisa da chave gratuita do abuse.ch (Configurações). Atualiza 1x por dia.
- Arquivos próprios: qualquer .txt/.csv em ~/.celscan/assinaturas/ com um SHA-256 por linha (e, opcional, o
  nome da ameaça depois de vírgula, tab ou espaço). Serve para listas da sua equipe ou de relatórios públicos.

O app cujo APK bate com uma assinatura vira "ameaça confirmada" (é a prova mais forte que existe).
"""

from __future__ import annotations

import json
import re
import time

import requests

from celscan import config
from celscan.core import bases, preferencias

URL_MB = "https://mb-api.abuse.ch/api/v1/"
RX_LINHA = re.compile(r"^\s*([0-9a-fA-F]{64})(?:[\s,;|]+(.+?))?\s*$")


def _baixar_malwarebazaar() -> str:
    chave = (preferencias.chave_abusech() or "").strip()
    if not chave:
        raise RuntimeError("sem a chave gratuita do abuse.ch (Configurações)")
    hashes: dict[str, str] = {}
    for consulta in ({"query": "get_file_type", "file_type": "apk", "limit": "1000"},
                     {"query": "get_taginfo", "tag": "android", "limit": "1000"}):
        r = requests.post(URL_MB, data=consulta, headers={"Auth-Key": chave}, timeout=60)
        r.raise_for_status()
        j = r.json()
        if j.get("query_status") not in ("ok", "no_results"):
            raise RuntimeError(f"MalwareBazaar respondeu: {j.get('query_status')}")
        for x in j.get("data") or []:
            h = (x.get("sha256_hash") or "").lower()
            if re.fullmatch(r"[0-9a-f]{64}", h):
                hashes[h] = f"MalwareBazaar: {x.get('signature') or 'malware Android'}"
    return json.dumps({"hashes": hashes, "atualizado": time.time()})


BASE = bases.registrar(bases.Base(
    nome="assinaturas", descricao="APKs maliciosos conhecidos (MalwareBazaar/abuse.ch)", arquivo="assinaturas.json",
    validade_s=24 * 3600, baixar=_baixar_malwarebazaar,
))


def ler_arquivo(texto: str, origem: str) -> dict[str, str]:
    res = {}
    for linha in texto.splitlines():
        m = RX_LINHA.match(linha)
        if m:
            res[m.group(1).lower()] = m.group(2).strip().strip('"') if m.group(2) else f"lista {origem}"
    return res


def locais() -> dict[str, str]:
    pasta = config.DIR / "assinaturas"
    res: dict[str, str] = {}
    if pasta.is_dir():
        for arq in sorted(pasta.glob("*")):
            if arq.suffix.lower() in (".txt", ".csv") and arq.stat().st_size < 50 * 1024 * 1024:
                res.update(ler_arquivo(arq.read_text(encoding="utf-8", errors="ignore"), arq.stem))
    return res


def carregar(atualizar: bool = True) -> dict[str, str]:
    """Todas as assinaturas: base baixada + arquivos próprios. Nunca levanta."""
    if atualizar and preferencias.chave_abusech() and bases.vencida(BASE):
        bases.atualizar("assinaturas")
    res: dict[str, str] = {}
    try:
        texto = bases.ler("assinaturas")
        if texto:
            res.update(json.loads(texto).get("hashes", {}))
    except (OSError, ValueError):
        pass
    res.update(locais())
    return res


def importar(nome: str, conteudo: str) -> int:
    """Grava uma lista de assinaturas enviada pela interface. Devolve quantas foram lidas."""
    n = ler_arquivo(conteudo, nome)
    if not n:
        raise ValueError("nenhum SHA-256 válido no arquivo")
    pasta = config.DIR / "assinaturas"
    pasta.mkdir(parents=True, exist_ok=True)
    seguro = re.sub(r"[^\w.-]", "_", nome)[:60] or "lista"
    (pasta / f"{seguro}.txt").write_text(conteudo, encoding="utf-8")
    return len(n)


def resumo() -> dict:
    idade = bases.idade_s(BASE)
    return {"baixadas": len(json.loads(bases.ler("assinaturas") or "{}").get("hashes", {})) if BASE.caminho.exists()
            else 0, "proprias": len(locais()), "idade_h": round(idade / 3600, 1) if idade is not None else None,
            "tem_chave": bool(preferencias.chave_abusech())}
