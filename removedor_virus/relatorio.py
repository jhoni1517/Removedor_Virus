"""Saída no terminal (com cores) e relatórios em JSON."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .adb import nome_seguro
from .caminhos import pasta_relatorios
from .heuristicas import App

# No programa com janela (sem console) sys.stdout é None.
_CORES = bool(sys.stdout) and sys.stdout.isatty() and not os.environ.get("NO_COLOR")
if _CORES and os.name == "nt":
    os.system("")  # ativa cores ANSI no terminal do Windows 10+
CORES_NIVEL = {"ALTO": "91", "MEDIO": "93", "BAIXO": "96", "LIMPO": "92"}


def cor(texto: str, codigo: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m" if _CORES else texto


def imprimir_apps(apps: list[App], mostrar_limpos: bool = False) -> list[App]:
    """Imprime a tabela numerada e devolve a lista na ordem exibida."""
    visiveis = [a for a in apps if mostrar_limpos or a.nivel != "LIMPO"]
    if not visiveis:
        print(cor("Nenhum app suspeito encontrado.", "92"))
        return visiveis
    for numero, app in enumerate(visiveis, 1):
        nivel = cor(f"{app.nivel:<5}", CORES_NIVEL[app.nivel])
        print(f"{numero:>3}. [{nivel}] {app.pontuacao:>3} pts  {app.pacote}")
        for motivo in app.motivos:
            print(f"        - {motivo}")
    return visiveis


def resumo(apps: list[App]) -> str:
    contagem = {n: sum(1 for a in apps if a.nivel == n) for n in CORES_NIVEL}
    partes = [cor(f"{n}: {q}", CORES_NIVEL[n]) for n, q in contagem.items()]
    return f"{len(apps)} apps analisados | " + " | ".join(partes)


def salvar_relatorio(apps: list[App], dispositivo: dict, pasta: Path | None = None) -> Path:
    pasta = Path(pasta) if pasta else pasta_relatorios()
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now()
    caminho = pasta / f"relatorio_{nome_seguro(dispositivo.get('serial', ''))}_{agora:%Y%m%d-%H%M%S}.json"
    dados = {
        "versao_programa": __version__,
        "data": agora.isoformat(timespec="seconds"),
        "dispositivo": dispositivo,
        "apps": [a.como_dict() for a in apps],
    }
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    return caminho
