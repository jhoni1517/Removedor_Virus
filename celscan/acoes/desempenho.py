"""Teste de desempenho real: tempo de abertura de apps e velocidade do armazenamento.

Tudo é medido no aparelho, sem número inventado:
- abertura: `am start -W` devolve o TotalTime (ms) de uma abertura "a frio" (o app é fechado antes);
- armazenamento: grava um arquivo temporário de 64 MB com `dd` (conv=fsync) e lê de volta;
  o arquivo é SEMPRE apagado no fim. A leitura logo após a gravação pode vir do cache e sair
  otimista — isso é dito no resultado.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from celscan.core.adb import AdbErro, Aparelho

ARQ_TESTE = "/sdcard/Download/.celscan_teste_desempenho"
MB_TESTE = 64
APPS_PADRAO = ("com.android.settings", "com.whatsapp", "com.android.chrome", "com.google.android.youtube",
               "com.instagram.android", "com.android.camera", "com.miui.gallery", "com.sec.android.gallery3d")


def _componente(ap: Aparelho, pacote: str) -> str | None:
    saida = ap.sh(f"cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {shlex.quote(pacote)}")
    linhas = [x.strip() for x in saida.splitlines() if "/" in x]
    return linhas[-1] if linhas else None


def abrir_app(ap: Aparelho, pacote: str) -> dict[str, Any]:
    comp = _componente(ap, pacote)
    if not comp:
        return {"pacote": pacote, "ms": None, "erro": "app não encontrado"}
    ap.sh(f"am force-stop {shlex.quote(pacote)}")
    saida = ap.sh(f"am start -W -n {shlex.quote(comp)}", timeout=60)
    ap.sh("input keyevent KEYCODE_HOME")
    m = re.search(r"TotalTime:\s*(\d+)", saida) or re.search(r"WaitTime:\s*(\d+)", saida)
    return {"pacote": pacote, "ms": int(m.group(1)) if m else None,
            "erro": None if m else "o Android não informou o tempo"}


def _mb_s(saida: str) -> float | None:
    """'67108864 bytes (64 M) copied, 0.5 s, 128 M/s' -> MB/s calculado por bytes/segundos."""
    m = re.search(r"(\d+)\s+bytes.*?([\d.]+)\s*s(?:ec)?\b", saida)
    if not m:
        return None
    b, s = int(m.group(1)), float(m.group(2))
    return round(b / 1048576 / s, 1) if s > 0 else None


def armazenamento(ap: Aparelho) -> dict[str, Any]:
    q = shlex.quote(ARQ_TESTE)
    try:
        grava = ap.sh(f"dd if=/dev/zero of={q} bs=1048576 count={MB_TESTE} conv=fsync 2>&1", timeout=180)
        le = ap.sh(f"dd if={q} of=/dev/null bs=1048576 2>&1", timeout=180)
    finally:
        try:
            ap.sh(f"rm -f {q}")
        except AdbErro:
            pass
    return {"gravacao_mb_s": _mb_s(grava), "leitura_mb_s": _mb_s(le), "tamanho_mb": MB_TESTE,
            "obs": "A leitura logo após gravar pode vir do cache e sair otimista."}


def testar(ap: Aparelho, pacotes: list[str] | None = None, progresso=None) -> dict[str, Any]:
    instalados = set(re.findall(r"^package:([\w.]+)", ap.sh("pm list packages"), re.M))
    alvos = [p for p in (pacotes or APPS_PADRAO) if p in instalados][:6]
    apps = []
    for i, p in enumerate(alvos, 1):
        if progresso:
            progresso({"etapa": "desempenho", "descricao": "Medindo a abertura dos apps", "detalhe": p,
                       "atual": i, "total": len(alvos) + 1, "estimativa_s": 4 * (len(alvos) - i) + 10})
        apps.append(abrir_app(ap, p))
    if progresso:
        progresso({"etapa": "desempenho", "descricao": "Medindo a velocidade do armazenamento", "detalhe": "",
                   "atual": len(alvos) + 1, "total": len(alvos) + 1, "estimativa_s": 10})
    medidos = [a["ms"] for a in apps if a["ms"]]
    return {"apps": apps, "media_abertura_ms": round(sum(medidos) / len(medidos)) if medidos else None,
            "armazenamento": armazenamento(ap)}
