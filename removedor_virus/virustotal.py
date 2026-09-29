"""Consulta de hashes no VirusTotal (API v3). Plano gratuito: 4 consultas/min."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

URL = "https://www.virustotal.com/api/v3/files/{}"
INTERVALO_GRATUITO = 15.5  # segundos entre consultas

_trava = threading.Lock()
_ultima = 0.0


class ErroVirusTotal(Exception):
    pass


def consultar_hash(sha256: str, chave: str, intervalo: float = INTERVALO_GRATUITO) -> dict:
    """Devolve {"conhecido": bool, "malicioso": int, "suspeito": int, "rotulo": str|None}."""
    global _ultima
    with _trava:
        espera = intervalo - (time.monotonic() - _ultima)
        if espera > 0:
            time.sleep(espera)
        _ultima = time.monotonic()

    pedido = urllib.request.Request(URL.format(sha256), headers={"x-apikey": chave})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            dados = json.load(resposta)
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            return {"conhecido": False}
        if erro.code in (401, 403):
            raise ErroVirusTotal("chave do VirusTotal inválida") from erro
        if erro.code == 429:
            raise ErroVirusTotal("limite de consultas do VirusTotal atingido") from erro
        raise ErroVirusTotal(f"VirusTotal respondeu {erro.code}") from erro
    except (urllib.error.URLError, TimeoutError, ValueError) as erro:
        raise ErroVirusTotal(f"falha ao consultar o VirusTotal: {erro}") from erro

    atributos = dados.get("data", {}).get("attributes", {})
    estatisticas = atributos.get("last_analysis_stats", {})
    return {
        "conhecido": True,
        "malicioso": estatisticas.get("malicious", 0),
        "suspeito": estatisticas.get("suspicious", 0),
        "rotulo": atributos.get("popular_threat_classification", {}).get("suggested_threat_label"),
    }
