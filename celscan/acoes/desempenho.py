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

from celscan.core import parsers
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
    arm = armazenamento(ap)
    hw = hardware(ap)
    cams = cameras(ap)
    medidos = [a["ms"] for a in apps if a["ms"]]
    media_ms = round(sum(medidos) / len(medidos)) if medidos else None
    return {"apps": apps, "media_abertura_ms": media_ms, "armazenamento": arm,
            "hardware": hw, "cameras": cams, "pontuacao": pontuar(hw, arm, media_ms)}


# ---- Hardware (CPU, RAM) --------------------------------------------------

def _parse_cpu(cpuinfo: str, freqs: str) -> dict[str, Any]:
    """Núcleos de /proc/cpuinfo e maior clock de cpufreq/cpuinfo_max_freq (em kHz)."""
    nucleos = len(re.findall(r"^processor\s*:", cpuinfo, re.M)) or None
    khz = [int(x) for x in re.findall(r"\d+", freqs)]
    ghz_max = round(max(khz) / 1_000_000, 2) if khz else None
    return {"nucleos": nucleos, "ghz_max": ghz_max}


def hardware(ap: Aparelho) -> dict[str, Any]:
    cpu = _parse_cpu(ap.sh("cat /proc/cpuinfo", erro=True),
                     ap.sh("cat /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq 2>/dev/null", erro=True))
    mem = parsers.meminfo(ap.sh("head -3 /proc/meminfo", erro=True))
    return {**cpu, "ram_gb": round(mem["total_gb"], 1) if mem else None}


# ---- Câmeras (inventário, não "nota de qualidade") -----------------------

def _parse_cameras(dumpsys: str) -> dict[str, Any]:
    """Conta as câmeras e tenta a maior resolução (megapixels). Qualidade NÃO é medível por USB."""
    ids = set(re.findall(r"Camera (\d+) information", dumpsys))
    if not ids:
        ids = set(re.findall(r"Device (\d+) ", dumpsys))
    mp = None
    pares = re.findall(r"(\d{3,5})\s*[x×]\s*(\d{3,5})", dumpsys)
    if pares:
        mp = round(max(int(w) * int(h) for w, h in pares) / 1_000_000, 1)
    return {"quantidade": len(ids) or None, "megapixels_max": mp,
            "obs": "Só o inventário; a qualidade da foto precisa de teste real com a câmera."}


def cameras(ap: Aparelho) -> dict[str, Any]:
    return _parse_cameras(ap.sh("dumpsys media.camera", timeout=30, erro=True))


# ---- Pontuação (estimativa própria do CelScan, 0 a 1000) -----------------

def _nota(valor: float | None, referencia: float) -> int | None:
    """Quanto o valor atinge de uma referência de aparelho topo de linha (0 a 100)."""
    if valor is None:
        return None
    return max(0, min(100, round(valor / referencia * 100)))


def pontuar(hw: dict[str, Any], arm: dict[str, Any], media_abertura_ms: int | None) -> dict[str, Any]:
    """Nota 0–1000 por categoria. É ESTIMATIVA interna do CelScan, não comparável ao AnTuTu."""
    ghz_nucleo = hw["nucleos"] * hw["ghz_max"] if hw.get("nucleos") and hw.get("ghz_max") else None
    cpu = _nota(ghz_nucleo, 24)        # ref.: 8 núcleos a 3,0 GHz
    ram = _nota(hw.get("ram_gb"), 12)  # ref.: 12 GB
    hardware_nota = _media([cpu, ram])
    arm_nota = _media([_nota(arm.get("leitura_mb_s"), 1000), _nota(arm.get("gravacao_mb_s"), 500)])
    fluidez = None
    if media_abertura_ms:  # 300 ms (rápido) -> 100; 2000 ms (lento) -> 0
        fluidez = max(0, min(100, round((2000 - media_abertura_ms) / (2000 - 300) * 100)))
    categorias = {"hardware": hardware_nota, "armazenamento": arm_nota, "fluidez": fluidez}
    pesos = {"hardware": 0.4, "armazenamento": 0.3, "fluidez": 0.3}
    validos = {k: v for k, v in categorias.items() if v is not None}
    total = None
    if validos:
        total = round(sum(validos[k] * pesos[k] for k in validos) / sum(pesos[k] for k in validos) * 10)
    return {"total": total, "categorias": categorias,
            "obs": "Pontuação própria do CelScan (0 a 1000), estimativa — não comparável ao AnTuTu."}


def _media(valores: list[int | None]) -> int | None:
    v = [x for x in valores if x is not None]
    return round(sum(v) / len(v)) if v else None
