"""Autodiagnóstico do próprio CelScan: confere se a instalação está inteira antes de culpar o celular.

Cada item: {"item", "ok", "detalhe", "dica"}. "ok" pode ser None quando é só informativo.
Nada aqui fala com o aparelho nem usa a internet.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sqlite3
import sys
from typing import Any

from celscan import __version__
from celscan.config import DIR

DEPENDENCIAS = [
    ("fastapi", "interface", True), ("uvicorn", "interface", True),
    ("websockets", "atualização em tempo real da interface", True), ("pyaxmlparser", "nome e ícone dos apps", True),
    ("reportlab", "laudo em PDF", True), ("qrcode", "QR code do laudo", True), ("pyzipper", "quarentena cifrada", True),
    ("keyring", "guardar a chave do VirusTotal no cofre do Windows", True),
    ("adbutils", "conexão rápida com o adb", False),
    ("PIL", "ícones no laudo PDF", False), ("yaml", "regras de pontuação", True), ("rich", "linha de comando", True),
]


def _item(item: str, ok: bool | None, detalhe: str, dica: str = "") -> dict[str, Any]:
    return {"item": item, "ok": ok, "detalhe": detalhe, "dica": dica}


def verificar() -> list[dict[str, Any]]:
    res = [_item("CelScan", None, f"versão {__version__} · Python {platform.python_version()} · {platform.system()}")]

    from celscan.core import adb
    caminho = adb.localizar()
    res.append(_item("ADB", bool(caminho), caminho or "não encontrado",
                     "" if caminho else "Abra a tela Conectar: o CelScan baixa o ADB oficial do Google sozinho."))

    for modulo, para_que, obrigatorio in DEPENDENCIAS:
        tem = importlib.util.find_spec(modulo) is not None
        res.append(_item(f"Componente {modulo}", tem if obrigatorio or tem else None,
                         f"{'instalado' if tem else 'ausente'} ({para_que})",
                         "" if tem else "Reinstale o CelScan pelo instalador mais recente."))

    try:
        livre = shutil.disk_usage(DIR).free / 1024 ** 3
        teste = DIR / ".teste_escrita"
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
        res.append(_item("Pasta de dados", livre >= 0.5, f"{DIR} · {livre:.1f} GB livres",
                         "" if livre >= 0.5 else "Libere espaço no disco: backups e quarentena precisam de lugar."))
    except OSError as e:
        res.append(_item("Pasta de dados", False, f"{DIR}: {e}", "Verifique permissões da pasta do usuário."))

    from celscan.core import db
    try:
        con = sqlite3.connect(str(db.ARQUIVO), timeout=5)
        estado = con.execute("PRAGMA quick_check").fetchone()[0] if db.ARQUIVO.exists() else "novo"
        con.close()
        copias = sorted(db.COPIAS.glob("celscan-*.db")) if db.COPIAS.exists() else []
        res.append(_item("Banco do histórico", estado in ("ok", "novo"),
                         f"{estado} · {len(copias)} cópia(s) de segurança"
                         + (f", a última {copias[-1].stem.split('-')[1]}" if copias else ""),
                         "" if estado in ("ok", "novo") else
                         f"O arquivo pode estar danificado. Há cópias em {db.COPIAS}."))
    except sqlite3.Error as e:
        res.append(_item("Banco do histórico", False, str(e), f"Restaure uma cópia de {db.COPIAS}."))

    from celscan.core import bases
    for s in bases.situacao():
        sem = not s["local"] and not s["embutida"]
        # sem a lista de ameaças a varredura perde a detecção por indicador; as outras bases são opcionais
        res.append(_item(f"Base {s['nome']}", (False if s["nome"] == "iocs" else None) if sem
                         else (None if s["vencida"] else True),
                         ("sem cópia" if sem else "vencida" if s["vencida"] else "em dia")
                         + (f" ({s['idade_h']:.0f} h)" if s["idade_h"] is not None else ""),
                         "Conecte à internet e abra o programa: as bases se atualizam sozinhas." if sem or s["vencida"]
                         else ""))

    from celscan.acoes import espelho
    scr = espelho.localizar()
    res.append(_item("Espelhamento (scrcpy)", True if scr else None, scr or "não instalado",
                     "" if scr else "Opcional: baixado automaticamente quando você usar 'Ver a tela'."))
    res.append(_item("Modo de execução", None, "instalado (.exe)" if getattr(sys, "frozen", False) else
                     f"código-fonte ({os.path.dirname(os.path.dirname(os.path.abspath(__file__)))})"))
    return res


def resumo(itens: list[dict[str, Any]]) -> str:
    falhas = [i for i in itens if i["ok"] is False]
    return "Tudo certo com o CelScan." if not falhas else f"{len(falhas)} problema(s) na instalação."
