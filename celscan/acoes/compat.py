"""O que cada modelo de celular aceita: memória das otimizações feitas neste PC.

Cada vez que uma otimização roda, o resultado de cada etapa (funcionou / recusada e por quê) fica guardado por
modelo + versão do Android. Serve para:
- desmarcar sozinho, no próximo celular igual, a etapa que este modelo sempre recusa (e dizer por quê);
- mostrar na aba Técnico a tabela por marca/modelo, montada com aparelhos de verdade, não com suposição.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from celscan import config

_TRAVA = threading.Lock()


def _arquivo():
    return config.DIR / "compatibilidade.json"


def chave(fabricante: str | None, modelo: str | None, android: str | None) -> str:
    return f"{(fabricante or '?').strip()} {(modelo or '?').strip()} · Android {(android or '?').strip()}"


def ler() -> dict[str, dict[str, dict[str, Any]]]:
    try:
        d = json.loads(_arquivo().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def registrar(modelo: str, etapas: list[dict[str, Any]]) -> None:
    with _TRAVA:
        d = ler()
        m = d.setdefault(modelo, {})
        for e in etapas:
            x = m.setdefault(e["id"], {"ok": 0, "falhou": 0, "motivo": "", "quando": 0})
            if e.get("ok"):
                x["ok"] += 1
            else:
                x["falhou"] += 1
                x["motivo"] = (e.get("detalhe") or e.get("erro") or "")[:160]
            x["quando"] = int(time.time())
        alvo = _arquivo()
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(alvo)


def recusadas(modelo: str) -> dict[str, str]:
    """Etapas que este modelo recusou e nunca aceitou: id -> motivo."""
    return {k: v.get("motivo") or "recusada" for k, v in ler().get(modelo, {}).items()
            if v.get("falhou") and not v.get("ok")}


def tabela() -> list[dict[str, Any]]:
    res = []
    for modelo, etapas in sorted(ler().items()):
        res.append({"modelo": modelo, "etapas": [
            {"id": k, "ok": v.get("ok", 0), "falhou": v.get("falhou", 0), "motivo": v.get("motivo", ""),
             "estado": "aceita" if v.get("ok") and not v.get("falhou") else
             "recusa" if v.get("falhou") and not v.get("ok") else "às vezes"}
            for k, v in sorted(etapas.items())]})
    return res
