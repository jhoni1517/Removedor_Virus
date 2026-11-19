"""Turbo: otimização avançada pelo computador (USB ou Wi-Fi ADB), sem instalar nada no celular.

Junta, num lugar só, o que os apps "otimizadores" via Shizuku fazem, mas pelo próprio ADB e com as
regras do CelScan:
- só entra o que tem efeito comprovado no Android (nada de "limpar log" sem root, "turbo de RAM" etc.);
- TODA mudança de configuração grava o valor anterior na quarentena (Histórico > Desfazer);
- cada função diz de qual versão do Android precisa e, se o aparelho não aceitar, avisa em vez de fingir;
- nada é apagado, nenhum app é removido e nenhuma senha/conta é tocada.

Partes: ficha do aparelho, calor e lentidão, nota (medida de verdade), comilões de RAM, compilação dos
apps por modo (rápida/completa/extrema), ajustes reversíveis e perfis prontos, modo de jogo, apps
esquecidos dormindo, rede da partida, editor de configurações e a "receita sob medida".
"""

from __future__ import annotations

import re
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from celscan.acoes import quarentena
from celscan.core import parsers
from celscan.core.adb import AdbErro
from celscan.core.seguranca import essencial, exigir_pacote

Progresso = Callable[[dict[str, Any]], None] | None

# ---------------------------------------------------------------------------------------------- utilidades


def _sdk(ap) -> int:
    try:
        return int(ap.sh("getprop ro.build.version.sdk").strip() or 0)
    except ValueError:
        return 0


def _num(texto: str | None) -> float | None:
    try:
        return float(str(texto).strip().replace(",", ".")) if texto not in (None, "") else None
    except ValueError:
        return None


def _bat(texto: str) -> dict[str, Any]:
    """'dumpsys battery' -> temperatura (°C, número), carregando e saúde."""
    kv = {k.strip().lower(): v.strip() for k, v in re.findall(r"^\s*([\w ]+):\s*(.+)$", texto, re.M)}
    t = kv.get("temperature", "")
    temp = int(t) / 10 if t.lstrip("-").isdigit() else None
    fontes = ("ac powered", "usb powered", "wireless powered")
    return {"temperatura": temp, "carregando": kv.get("status") == "2" or any(kv.get(f) == "true" for f in fontes),
            "saude": (parsers.bateria(texto) or {}).get("saude")}


def _pacotes(saida: str) -> list[str]:
    return re.findall(r"^package:([\w.]+)", saida, re.M)


def _falhou(saida: str) -> bool:
    s = saida.lower()
    return any(p in s for p in ("exception", "error", "unknown command", "not found", "failure", "inaccessible",
                                "permission denial", "no shell command", "not allowed", "invalid"))


# ---------------------------------------------------------------------------------------------- ficha

THERMAL = {0: "normal", 1: "leve", 2: "moderado", 3: "severo", 4: "crítico", 5: "emergência", 6: "desligando"}

FICHA = r"""
sec(){ echo "@@SEC $1"; }
sec props
for k in ro.product.manufacturer ro.product.model ro.product.marketname ro.build.version.release \
  ro.build.version.sdk ro.build.version.security_patch ro.product.cpu.abi ro.soc.model ro.soc.manufacturer \
  ro.board.platform ro.hardware ro.build.version.oneui ro.miui.ui.version.name ro.build.display.id; do
  printf '%s=' "$k"; getprop $k; done
sec kernel; uname -r
sec selinux; getenforce 2>/dev/null
sec cpu; grep -c ^processor /proc/cpuinfo
sec freq; cat /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq 2>/dev/null
sec mem; grep -E 'MemTotal|MemAvailable|SwapTotal|SwapFree' /proc/meminfo
sec display
dumpsys display 2>/dev/null | grep -E 'mActiveSfDisplayMode|supportedModes|HdrCapabilities|renderFrameRate' | head -20
sec gpu; dumpsys SurfaceFlinger 2>/dev/null | grep -m1 GLES
sec features; pm list features 2>/dev/null | grep -E 'vulkan|hardware.nfc$|5g'
sec thermal; dumpsys thermalservice 2>/dev/null | head -60
sec bateria; dumpsys battery
sec uptime; cat /proc/uptime
sec fim
"""


def _props(texto: str) -> dict[str, str]:
    res = {}
    for linha in texto.splitlines():
        if "=" in linha:
            k, v = linha.split("=", 1)
            if v.strip():
                res[k.strip()] = v.strip()
    return res


def _modos_tela(texto: str) -> dict[str, Any]:
    """Resolução e taxas (Hz) da tela, a partir do 'dumpsys display'."""
    modos = re.findall(r"width=(\d+), height=(\d+), fps=([\d.]+)", texto)
    fps = sorted({round(float(f)) for _, _, f in modos})
    ativo = re.search(r"mActiveSfDisplayMode=.*?width=(\d+), height=(\d+), fps=([\d.]+)", texto)
    w, h = (ativo.group(1), ativo.group(2)) if ativo else (modos[0][:2] if modos else (None, None))
    res = None
    if w and h:
        a, b = sorted((int(w), int(h)), reverse=True)
        res = f"{a}×{b}"
    hdr = bool(re.search(r"(mSupportedHdrTypes|supportedHdrTypes)=\[\s*\d", texto))
    return {"resolucao": res, "hz_atual": round(float(ativo.group(3))) if ativo else None,
            "hz_max": max(fps) if fps else None, "hz_suportados": fps, "hdr": hdr}


def _vulkan(features: str) -> str | None:
    m = re.search(r"android\.hardware\.vulkan\.version=(\d+)", features)
    if not m:
        return None
    v = int(m.group(1))
    return f"Vulkan {v >> 22}.{(v >> 12) & 0x3FF}"


def _thermal(texto: str) -> dict[str, Any]:
    """Status térmico do Android (0 normal … 6 desligando) e temperaturas dos sensores."""
    m = re.search(r"Thermal Status:\s*(\d)", texto)
    status = int(m.group(1)) if m else None
    temps: dict[str, float] = {}
    for valor, _tipo, nome in re.findall(r"mValue=([\d.\-]+), mType=(-?\d+), mName=([^,]+)", texto):
        v = float(valor)
        if -20 < v < 150:
            temps.setdefault(nome.strip(), v)
    cpu = [v for k, v in temps.items() if re.search(r"cpu|soc|tsens|ap", k, re.I)]
    return {"status": status, "status_nome": THERMAL.get(status) if status is not None else None,
            "cpu_c": round(max(cpu), 1) if cpu else None, "sensores": temps}


def classe(ram_gb: float | None, nucleos: int | None, ghz: float | None) -> str:
    pontos = (ram_gb or 0) / 12 + ((nucleos or 0) * (ghz or 0)) / 24
    if pontos >= 1.6:
        return "Topo de linha"
    if pontos >= 1.1:
        return "Intermediário avançado"
    if pontos >= 0.7:
        return "Intermediário"
    return "Entrada"


def montar_ficha(s: dict[str, str]) -> dict[str, Any]:
    p = _props(s.get("props", ""))
    mem = dict(re.findall(r"(\w+):\s+(\d+)", s.get("mem", "")))
    khz = [int(x) for x in re.findall(r"\d+", s.get("freq", ""))]
    nucleos = int(s.get("cpu", "0").strip() or 0) or None
    ghz = round(max(khz) / 1e6, 2) if khz else None
    ram_gb = round(int(mem["MemTotal"]) / 1048576, 1) if "MemTotal" in mem else None
    bat = _bat(s.get("bateria", ""))
    th = _thermal(s.get("thermal", ""))
    gpu = re.search(r"GLES:\s*[^,]+,\s*([^,]+)", s.get("gpu", ""))
    up = _num((s.get("uptime", "").split() or [None])[0])
    sdk = int(p.get("ro.build.version.sdk", "0") or 0)
    interface = None
    if p.get("ro.build.version.oneui"):
        o = int(p["ro.build.version.oneui"])
        interface = f"One UI {o // 10000}.{(o // 100) % 100}"
    elif p.get("ro.miui.ui.version.name"):
        interface = f"MIUI/HyperOS {p['ro.miui.ui.version.name']}"
    return {
        "fabricante": p.get("ro.product.manufacturer"), "modelo": p.get("ro.product.model"),
        "nome": p.get("ro.product.marketname") or p.get("ro.product.model"),
        "android": p.get("ro.build.version.release"), "sdk": sdk or None, "interface": interface,
        "patch": p.get("ro.build.version.security_patch"), "abi": p.get("ro.product.cpu.abi"),
        "chip": p.get("ro.soc.model") or p.get("ro.board.platform") or p.get("ro.hardware"),
        "gpu": gpu.group(1).strip() if gpu else None, "vulkan": _vulkan(s.get("features", "")),
        "kernel": s.get("kernel", "").strip() or None, "selinux": s.get("selinux", "").strip() or None,
        "nucleos": nucleos, "ghz_max": ghz, "ram_gb": ram_gb,
        "ram_livre_gb": round(int(mem["MemAvailable"]) / 1048576, 1) if "MemAvailable" in mem else None,
        "ram_virtual_gb": round(int(mem["SwapTotal"]) / 1048576, 1) if int(mem.get("SwapTotal", 0)) else None,
        "tela": _modos_tela(s.get("display", "")), "termico": th,
        "bateria_c": bat.get("temperatura"), "bateria_saude": bat.get("saude"),
        "ligado_h": round(up / 3600, 1) if up else None,
        "classe": classe(ram_gb, nucleos, ghz),
    }


def ficha(ap) -> dict[str, Any]:
    return montar_ficha(ap.script(FICHA, timeout=120))


# ---------------------------------------------------------------------------------------------- calor

CALOR = r"""
sec(){ echo "@@SEC $1"; }
sec thermal; dumpsys thermalservice 2>/dev/null | head -60
sec cpu
for p in /sys/devices/system/cpu/cpufreq/policy*; do
  echo "${p##*/} $(cat $p/scaling_cur_freq 2>/dev/null) $(cat $p/scaling_max_freq 2>/dev/null)" \
       "$(cat $p/cpuinfo_max_freq 2>/dev/null)"
done
sec top; top -b -n 1 -m 8 2>/dev/null
sec bateria; dumpsys battery
sec fim
"""


def _clusters(texto: str) -> list[dict[str, Any]]:
    res = []
    for nome, cur, maxi, teto in re.findall(r"^(policy\d+)\s+(\d+)\s+(\d+)\s+(\d+)", texto, re.M):
        cur, maxi, teto = int(cur), int(maxi), int(teto)
        res.append({"cluster": nome, "atual_ghz": round(cur / 1e6, 2), "limite_ghz": round(maxi / 1e6, 2),
                    "maximo_ghz": round(teto / 1e6, 2), "limite_pct": round(maxi / teto * 100) if teto else None})
    return res


def _top(texto: str) -> list[dict[str, Any]]:
    """Processos que mais usam CPU agora (saída do 'top' do toybox)."""
    linhas = texto.splitlines()
    cab = next((i for i, x in enumerate(linhas) if "%CPU" in x and ("ARGS" in x or "NAME" in x)), None)
    if cab is None:
        return []
    cols = linhas[cab].replace("[%CPU]", " %CPU").split()
    try:
        icpu = next(i for i, c in enumerate(cols) if "%CPU" in c)
    except StopIteration:
        return []
    res = []
    for linha in linhas[cab + 1:]:
        partes = linha.split()
        if len(partes) <= icpu:
            continue
        cpu = _num(partes[icpu].rstrip("%"))
        nome = partes[-1]
        if cpu is None or nome in ("top", "sh"):
            continue
        res.append({"processo": nome, "cpu_pct": cpu})
    return sorted(res, key=lambda x: -x["cpu_pct"])[:5]


def montar_calor(s: dict[str, str]) -> dict[str, Any]:
    th = _thermal(s.get("thermal", ""))
    clusters = _clusters(s.get("cpu", ""))
    bat = _bat(s.get("bateria", ""))
    temp_bat = bat.get("temperatura")
    carregando = bool(bat.get("carregando"))
    segurado = [c for c in clusters if c["limite_pct"] is not None and c["limite_pct"] < 90]
    status = th["status"] or 0
    causas, dicas = [], []
    if segurado:
        pior = min(segurado, key=lambda c: c["limite_pct"])
        causas.append(f"O Android está segurando a CPU abaixo do máximo para esfriar "
                      f"({pior['cluster']} em {pior['limite_pct']}%).")
    if temp_bat is not None and temp_bat >= 40:
        causas.append(f"Bateria quente ({temp_bat:.1f} °C).")
    if carregando and temp_bat is not None and temp_bat >= 37:
        dicas.append("Tire da tomada: carregar enquanto usa é a maior fonte de calor.")
    top = _top(s.get("top", ""))
    pesado = [t for t in top if t["cpu_pct"] >= 25]
    if pesado:
        causas.append("Processos pesados agora: " + ", ".join(f"{t['processo']} ({t['cpu_pct']:.0f}%)"
                                                             for t in pesado[:3]))
        dicas.append("Feche ou reinicie o app que aparece no topo da lista.")
    if status >= 3 or (segurado and min(c["limite_pct"] for c in segurado) < 70):
        nivel, texto = "travando", "Travando: o Android já está cortando desempenho."
        dicas.append("Deixe o celular descansar alguns minutos sem capa e baixe o gráfico do jogo.")
    elif status >= 1 or segurado or (temp_bat or 0) >= 38:
        nivel, texto = "quente", "Quente: o Android está perto de cortar desempenho."
    else:
        nivel, texto = "normal", "Temperatura normal: nada segurando o desempenho."
    return {"nivel": nivel, "texto": texto, "termico": th, "clusters": clusters, "bateria_c": temp_bat,
            "carregando": carregando, "top": top, "causas": causas, "dicas": dicas}


def calor(ap) -> dict[str, Any]:
    return montar_calor(ap.script(CALOR, timeout=60))


# ---------------------------------------------------------------------------------------------- nota

NOTA = r"""
sec(){ echo "@@SEC $1"; }
ms(){ read u r < /proc/uptime; u=${u%.*}${u#*.}; echo $((u * 10)); }
laco(){ i=0; while [ $i -lt 300000 ]; do i=$((i+1)); done; }
sec cpu1; a=$(ms); laco; b=$(ms); echo $((b-a))
sec cpun; n=$(grep -c ^processor /proc/cpuinfo); a=$(ms); j=0
while [ $j -lt $n ]; do laco & j=$((j+1)); done; wait; b=$(ms); echo $((b-a))
sec memoria; dd if=/dev/zero of=/dev/null bs=1048576 count=1024 2>&1
sec gfx; dumpsys gfxinfo com.android.systemui 2>/dev/null | grep -E 'Total frames rendered|Janky frames' | head -2
sec mem; grep -E 'MemTotal|MemAvailable' /proc/meminfo
sec bateria; dumpsys battery
sec fim
"""


def _escala(valor: float | None, bom: float, ruim: float) -> int | None:
    """100 quando atinge `bom`, 0 quando chega em `ruim` (serve para crescer ou decrescer)."""
    if valor is None:
        return None
    return max(0, min(100, round((valor - ruim) / (bom - ruim) * 100)))


def montar_nota(s: dict[str, str], gravacao_mb_s: float | None, latencia_ms: float | None) -> dict[str, Any]:
    cpu1 = _num(s.get("cpu1", "").strip().splitlines()[-1] if s.get("cpu1", "").strip() else None)
    cpun = _num(s.get("cpun", "").strip().splitlines()[-1] if s.get("cpun", "").strip() else None)
    cpu1 = cpu1 if cpu1 and cpu1 > 0 else None  # relógio do aparelho não mediu: sem número inventado
    cpun = cpun if cpun and cpun > 0 else None
    m = re.search(r"(\d+)\s+bytes.*?([\d.]+)\s*s(?:ec)?\b", s.get("memoria", ""))
    mem_gb_s = round(int(m.group(1)) / 1073741824 / float(m.group(2)), 1) if m and float(m.group(2)) > 0 else None
    jank = re.search(r"Janky frames:\s*\d+\s*\(([\d.]+)%\)", s.get("gfx", ""))
    jank_pct = float(jank.group(1)) if jank else None
    mem = dict(re.findall(r"(\w+):\s+(\d+)", s.get("mem", "")))
    tem_mem = {"MemTotal", "MemAvailable"} <= set(mem)
    livre_pct = int(mem["MemAvailable"]) / int(mem["MemTotal"]) * 100 if tem_mem else None
    bat = _bat(s.get("bateria", ""))
    temp = bat.get("temperatura")
    cat = {
        "fluidez": {"nota": _escala(jank_pct, 1, 25),
                    "detalhe": f"{jank_pct:.1f}% de quadros travados" if jank_pct is not None else "sem dados"},
        "processador": {"nota": _media([_escala(cpu1, 500, 5000), _escala(cpun, 600, 6000), _escala(mem_gb_s, 6, 0.5)]),
                        "detalhe": f"1 núcleo {cpu1:.0f} ms · todos {cpun:.0f} ms · memória {mem_gb_s} GB/s"
                        if cpu1 and cpun else "sem dados"},
        "memoria": {"nota": _escala(livre_pct, 45, 5),
                    "detalhe": f"{int(mem['MemAvailable']) / 1048576:.1f} GB livres de "
                               f"{int(mem['MemTotal']) / 1048576:.0f} GB" if livre_pct is not None else "sem dados"},
        "temperatura": {"nota": _escala(temp, 30, 45),
                        "detalhe": f"{temp:.1f} °C na bateria" if temp is not None else "sem dados"},
        "armazenamento": {"nota": _escala(gravacao_mb_s, 400, 20),
                          "detalhe": f"{gravacao_mb_s:.0f} MB/s gravando" if gravacao_mb_s else "sem dados"},
        "conexao": {"nota": _escala(latencia_ms, 10, 200),
                    "detalhe": f"{latencia_ms:.0f} ms por comando" if latencia_ms is not None else "sem dados"},
    }
    pesos = {"fluidez": 3, "processador": 3, "memoria": 2, "temperatura": 2, "armazenamento": 2, "conexao": 1}
    validos = {k: v["nota"] for k, v in cat.items() if v["nota"] is not None}
    total = round(sum(validos[k] * pesos[k] for k in validos) / sum(pesos[k] for k in validos)) if validos else None
    return {"total": total, "categorias": cat,
            "obs": "Nota do CelScan (0 a 100) medida agora neste celular. Compare antes e depois de otimizar; "
                   "não é comparável ao AnTuTu."}


def _media(v: list[int | None]) -> int | None:
    x = [i for i in v if i is not None]
    return round(sum(x) / len(x)) if x else None


def latencia(ap, vezes: int = 5) -> float | None:
    tempos = []
    for _ in range(vezes):
        t = time.perf_counter()
        try:
            ap.sh("true", timeout=10)
        except AdbErro:
            return None
        tempos.append((time.perf_counter() - t) * 1000)
    return round(sorted(tempos)[len(tempos) // 2], 1)


def nota(ap, progresso: Progresso = None) -> dict[str, Any]:
    from celscan.acoes import desempenho

    if progresso:
        progresso({"etapa": "nota", "descricao": "Medindo processador, memória e fluidez", "detalhe": "",
                   "atual": 1, "total": 3, "estimativa_s": 25})
    s = ap.script(NOTA, timeout=180)
    if progresso:
        progresso({"etapa": "nota", "descricao": "Medindo o armazenamento", "detalhe": "", "atual": 2,
                   "total": 3, "estimativa_s": 10})
    arm = desempenho.armazenamento(ap)
    lat = latencia(ap)
    return montar_nota(s, arm.get("gravacao_mb_s"), lat)


# ---------------------------------------------------------------------------------------------- comilões de RAM

# grupos do "Total PSS/RSS by OOM adjustment" -> estado mostrado
OOM_ESTADO = {
    "native": "sistema", "system": "sistema", "persistent": "sistema", "persistent service": "sistema",
    "foreground": "rodando", "visible": "rodando", "perceptible": "rodando", "perceptible low": "rodando",
    "perceptible medium": "rodando", "heavy weight": "rodando", "backup": "segundo_plano",
    "a services": "segundo_plano", "home": "tela_inicial", "previous": "segundo_plano",
    "b services": "segundo_plano", "cached": "segundo_plano",
}


def _kb(t: str) -> int:
    return int(t.replace(",", ""))


def parse_meminfo_oom(texto: str) -> list[dict[str, Any]]:
    """'dumpsys meminfo' -> [{pacote, kb, estado}] por app (soma os processos de cada pacote)."""
    m = re.search(r"Total (?:PSS|RSS) by OOM adjustment:\n(.*?)(?:\n\s*\n|Total (?:PSS|RSS) by category)", texto, re.S)
    if not m:
        return []
    estado, apps = None, {}
    for linha in m.group(1).splitlines():
        g = re.match(r"^\s{0,6}([\d,]+)K(?:\s*\([^)]*\))?:\s*([A-Za-z][A-Za-z ]+?)\s*$", linha)
        if g and len(linha) - len(linha.lstrip()) <= 6 and "(pid" not in linha:
            estado = OOM_ESTADO.get(g.group(2).strip().lower(), "segundo_plano")
            continue
        p = re.match(r"^\s+([\d,]+)K(?:\s*\([^)]*\))?:\s*([\w.]+)(?::[\w.]+)?\s*\(pid\s*\d+", linha)
        if p and estado:
            pkg = p.group(2)
            atual = apps.setdefault(pkg, {"pacote": pkg, "kb": 0, "estado": estado})
            atual["kb"] += _kb(p.group(1))
            ordem = ("rodando", "tela_inicial", "sistema", "segundo_plano")
            if ordem.index(estado) < ordem.index(atual["estado"]):
                atual["estado"] = estado
    return sorted(apps.values(), key=lambda a: -a["kb"])


def _mem_disponivel_mb(ap) -> float | None:
    m = re.search(r"MemAvailable:\s+(\d+)", ap.sh("grep MemAvailable /proc/meminfo"))
    return int(m.group(1)) / 1024 if m else None


def _protegidos(ap) -> set[str]:
    """Teclado, tela inicial e o próprio ADB-helper: nunca fechar."""
    prot = set()
    ime = (quarentena.ler_setting(ap, "secure", "default_input_method") or "").split("/")[0]
    if ime:
        prot.add(ime)
    home = ap.sh("cmd package resolve-activity --brief -c android.intent.category.HOME "
                 "-a android.intent.action.MAIN")
    for linha in home.splitlines():
        if "/" in linha:
            prot.add(linha.strip().split("/")[0])
    prot |= {"moe.shizuku.privileged.api", "com.android.shell"}
    return prot


def comiloes(ap) -> dict[str, Any]:
    terceiros = set(_pacotes(ap.sh("pm list packages -3")))
    apps = parse_meminfo_oom(ap.sh("dumpsys meminfo", timeout=90))
    prot = _protegidos(ap)
    lista = []
    for a in apps:
        if a["pacote"] not in terceiros:
            continue
        a = {**a, "mb": round(a["kb"] / 1024), "protegido": a["pacote"] in prot or essencial(a["pacote"])}
        a["liberavel"] = a["estado"] == "segundo_plano" and not a["protegido"]
        lista.append(a)
    mem = parsers.meminfo(ap.sh("head -3 /proc/meminfo")) or {}
    livre = _mem_disponivel_mb(ap)
    return {"apps": lista, "livre_mb": round(livre) if livre else None,
            "total_gb": round(mem["total_gb"], 1) if mem.get("total_gb") else None,
            "liberavel_mb": sum(a["mb"] for a in lista if a["liberavel"])}


MODOS_RAM = {
    "leve": "Fecha só o que está em segundo plano (o Android reabre se precisar).",
    "soneca": "Fecha e põe o app para 'dormir' (menos alarmes e tarefas até você abrir de novo).",
    "forte": "Força a parada mesmo se estiver ativo: o app só volta quando você abrir (sem alarmes).",
}
BALDES = {5: "exempted", 10: "active", 20: "working_set", 30: "frequent", 40: "rare", 45: "restricted", 50: "never"}


def balde(ap, pkg: str) -> str | None:
    v = ap.sh(f"am get-standby-bucket {pkg}").strip()
    if v.isdigit():
        return BALDES.get(int(v))
    return v if v in BALDES.values() else None


def liberar_ram(ap, pacotes: list[str], modo: str = "leve") -> dict[str, Any]:
    if modo not in MODOS_RAM:
        raise ValueError(f"modo inválido: {modo}")
    prot = _protegidos(ap)
    antes = _mem_disponivel_mb(ap)
    feitos, desfazer = [], []
    for pkg in pacotes:
        exigir_pacote(pkg)
        if pkg in prot or essencial(pkg):
            feitos.append({"pacote": pkg, "ok": False, "motivo": "protegido (teclado, tela inicial ou essencial)"})
            continue
        if modo == "forte":
            ap.sh(f"am force-stop {pkg}")
        else:
            ap.sh(f"am kill {pkg}")
        if modo == "soneca":
            anterior = balde(ap, pkg)
            ap.sh(f"am set-standby-bucket {pkg} rare")
            if anterior and anterior != "rare":
                desfazer.append({"tipo": "cmd", "desfazer": f"am set-standby-bucket {pkg} {anterior}",
                                 "descricao": f"{pkg} acordado ({anterior})"})
        feitos.append({"pacote": pkg, "ok": True})
    time.sleep(1.5)
    depois = _mem_disponivel_mb(ap)
    desfazer_id = None
    if desfazer:
        desfazer_id = quarentena.criar_ajuste(ap, "soneca_apps", f"Apps em soneca ({len(desfazer)})", desfazer).name
    return {"apps": feitos, "antes_mb": round(antes) if antes else None, "depois_mb": round(depois) if depois else None,
            "liberou_mb": round(max(0, depois - antes)) if antes and depois else None, "desfazer_id": desfazer_id}


# ---------------------------------------------------------------------------------------------- compilação

MODOS_COMPILACAO = {
    "rapida": ("speed-profile", "Rápida: compila o que você mais usa de cada app (padrão do Android, equilibrado)."),
    "completa": ("speed", "Completa: compila o app inteiro. Demora mais e ocupa mais espaço; abre e roda mais liso."),
    "extrema": ("everything", "Extrema: compila absolutamente tudo, sem exceção. A mais demorada e a que mais ocupa."),
}
WEBVIEW = ("com.google.android.webview", "com.android.webview", "com.google.android.trichromelibrary")
ESCOPOS = {
    "usuario": "Apps que você instalou",
    "mais_usados": "Os 5 apps mais usados na semana",
    "sistema": "Apps do sistema (Configurações, Telefone, Arquivos, tela inicial...)",
    "google": "Serviços do Google (Play Services, Play Store...)",
    "webview": "WebView (o 'navegador' que os apps usam por dentro)",
    "todos": "Todos os apps do celular",
}


def uso_semana(ap) -> dict[str, int]:
    """Minutos de uso por app (estatística do próprio Android)."""
    texto = ap.sh("dumpsys usagestats --hide-history-pkgs 2>/dev/null || dumpsys usagestats", timeout=90)
    bloco = re.search(r"In-memory weekly stats(.*?)(?:In-memory monthly stats|$)", texto, re.S)
    alvo = bloco.group(1) if bloco else texto
    uso: dict[str, int] = {}
    for pkg, t in re.findall(r'package=([\w.]+) totalTime(?:Used|Visible)?="([\d:]+)"', alvo):
        partes = [int(x) for x in t.split(":")]
        while len(partes) < 3:
            partes.insert(0, 0)
        minutos = partes[-3] * 60 + partes[-2]
        uso[pkg] = max(uso.get(pkg, 0), minutos)
    return uso


def ultimo_uso(ap) -> dict[str, float]:
    """Último uso de cada app (timestamp, em dias atrás), juntando todas as estatísticas guardadas."""
    texto = ap.sh("dumpsys usagestats", timeout=120)
    agora = time.time()
    res: dict[str, float] = {}
    for pkg, data in re.findall(r'package=([\w.]+) .*?lastTimeUsed="(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)"', texto):
        try:
            ts = time.mktime(time.strptime(data, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if ts < 86400 * 365:  # 1970: nunca usado
            continue
        dias = (agora - ts) / 86400
        res[pkg] = min(res.get(pkg, dias), dias)
    return res


def alvos_compilacao(ap, escopo: str) -> list[str]:
    if escopo not in ESCOPOS:
        raise ValueError(f"escopo inválido: {escopo}")
    if escopo == "mais_usados":
        terceiros = set(_pacotes(ap.sh("pm list packages -3")))
        uso = uso_semana(ap)
        return [p for p, _ in sorted(uso.items(), key=lambda x: -x[1]) if p in terceiros][:5]
    if escopo == "usuario":
        return sorted(_pacotes(ap.sh("pm list packages -3 -e")))
    todos = sorted(_pacotes(ap.sh("pm list packages -e")))
    if escopo == "todos":
        return todos
    if escopo == "google":
        return [p for p in todos if p.startswith(("com.google.android.gms", "com.android.vending",
                                                  "com.google.android.gsf"))]
    if escopo == "webview":
        return [p for p in todos if p in WEBVIEW]
    sistema = set(_pacotes(ap.sh("pm list packages -s -e")))
    principais = ("com.android.settings", "com.android.systemui", "com.android.phone", "com.android.dialer",
                  "com.google.android.dialer", "com.samsung.android.dialer", "com.android.documentsui",
                  "com.google.android.documentsui", "com.sec.android.app.launcher", "com.miui.home",
                  "com.google.android.apps.nexuslauncher", "com.android.launcher3", "com.sec.android.app.myfiles",
                  "com.google.android.apps.messaging", "com.samsung.android.messaging", "com.android.camera",
                  "com.sec.android.app.camera", "com.google.android.inputmethod.latin",
                  "com.samsung.android.honeyboard")
    return [p for p in principais if p in sistema]


def compilar_apps(ap, modo: str, pacotes: list[str], progresso: Progresso = None, cancelar=None) -> dict[str, Any]:
    if modo not in MODOS_COMPILACAO:
        raise ValueError(f"modo inválido: {modo}")
    filtro = MODOS_COMPILACAO[modo][0]
    for p in pacotes:
        exigir_pacote(p)
    # tela acesa enquanto compila: com a tela apagada o Android adia ou cancela a compilação
    anterior = quarentena.ler_setting(ap, "global", "stay_on_while_plugged_in")
    ap.sh("svc power stayon true")
    ok, falhas, inicio = [], [], time.time()
    try:
        for i, pkg in enumerate(pacotes, 1):
            if cancelar is not None and cancelar.is_set():
                break
            if progresso:
                feito = time.time() - inicio
                resto = (feito / (i - 1)) * (len(pacotes) - i + 1) if i > 1 else 8 * len(pacotes)
                progresso({"etapa": "compilar", "descricao": f"Otimização {modo}: compilando os apps",
                           "detalhe": pkg, "atual": i, "total": len(pacotes), "estimativa_s": round(resto)})
            try:
                saida = ap.sh(f"cmd package compile -m {filtro} -f {pkg}", timeout=900, erro=True)
            except AdbErro as e:
                falhas.append({"pacote": pkg, "erro": str(e)[:120]})
                continue
            (ok.append(pkg) if "Success" in saida else falhas.append({"pacote": pkg, "erro": saida.strip()[-120:]}))
    finally:
        ap.sh(f"settings put global stay_on_while_plugged_in {shlex.quote(anterior or '0')}")
    return {"modo": modo, "ok": ok, "falhas": falhas, "total": len(pacotes),
            "cancelado": bool(cancelar is not None and cancelar.is_set()),
            "minutos": round((time.time() - inicio) / 60, 1)}


def resetar_compilacao(ap, pacotes: list[str]) -> dict[str, Any]:
    """Volta os apps à compilação padrão do Android (desfaz a otimização e devolve o espaço)."""
    res = []
    for pkg in pacotes:
        exigir_pacote(pkg)
        res.append({"pacote": pkg, "ok": "Success" in ap.sh(f"cmd package compile --reset {pkg}", timeout=300,
                                                             erro=True)})
    return {"apps": res}


# ---------------------------------------------------------------------------------------------- ajustes


@dataclass(frozen=True)
class Ajuste:
    id: str
    grupo: str
    titulo: str
    descricao: str
    mudancas: tuple[tuple[str, str, str, str], ...]  # (tipo settings|device_config, ns, chave, valor)
    sdk_min: int = 0
    aviso: str = ""
    reiniciar: bool = False
    opcional: bool = True
    marcas: tuple[str, ...] = field(default=())


AJUSTES: tuple[Ajuste, ...] = (
    Ajuste("fantasmas", "Desempenho", "Fim dos processos fantasmas",
           "Android 12+ mata processos em segundo plano acima de 32 (fecha Shizuku, Termux, emuladores e jogos "
           "minimizados). Isso tira o limite.",
           (("device_config", "activity_manager", "max_phantom_processes", "2147483647"),
            ("settings", "global", "settings_enable_monitor_phantom_procs", "false")), sdk_min=31, opcional=False),
    Ajuste("congelador", "Desempenho", "Congelador de apps em cache",
           "Apps parados em segundo plano ficam congelados: não gastam CPU nem bateria até você voltar a eles.",
           (("device_config", "activity_manager_native_boot", "use_freezer", "true"),), sdk_min=30, reiniciar=True,
           aviso="Vale depois de reiniciar. Alguns fabricantes já deixam ligado."),
    Ajuste("menos_processos", "Desempenho", "Menos apps escondidos",
           "Limita os apps guardados em segundo plano (economiza RAM em aparelhos de 3–4 GB).",
           (("device_config", "activity_manager", "max_cached_processes", "24"),), sdk_min=29,
           aviso="Os apps reabrem do zero mais vezes. Só use em celular com pouca RAM."),
    Ajuste("mais_processos", "Desempenho", "Mais apps abertos ao mesmo tempo",
           "Guarda mais apps em segundo plano: eles voltam de onde pararam em vez de recomeçar do zero "
           "(bom para aparelho com 8 GB de RAM ou mais).",
           (("device_config", "activity_manager", "max_cached_processes", "64"),), sdk_min=29,
           aviso="Em Xiaomi/HyperOS o gerenciador de memória da marca também fecha apps; combine com "
                 "'Fim dos processos fantasmas' e com o app fora da economia de bateria."),
    Ajuste("animacoes_rapidas", "Desempenho", "Animações mais rápidas",
           "Telas abrem e fecham na metade do tempo (sensação de celular mais rápido).",
           tuple(("settings", "global", k, "0.5") for k in
                 ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")), opcional=False),
    Ajuste("dados_repouso_wifi", "Bateria e rede", "Dados móveis em repouso no Wi-Fi",
           "O rádio de dados móveis dorme enquanto você está no Wi-Fi (economiza bateria).",
           (("settings", "global", "mobile_data_always_on", "0"),), opcional=False,
           aviso="A troca para os dados móveis, quando o Wi-Fi cai, demora 1 ou 2 segundos a mais."),
    Ajuste("sem_busca_wifi", "Bateria e rede", "Sem busca de Wi-Fi/Bluetooth escondida",
           "O celular para de procurar redes e aparelhos Bluetooth com eles desligados (usado só para "
           "melhorar a localização).",
           (("settings", "global", "wifi_scan_always_enabled", "0"),
            ("settings", "global", "ble_scan_always_enabled", "0")), opcional=False),
    Ajuste("sem_wifi_auto", "Bateria e rede", "Wi-Fi não liga sozinho",
           "Quando você desliga o Wi-Fi, ele fica desligado (não religa perto de redes salvas).",
           (("settings", "global", "wifi_wakeup_enabled", "0"),)),
    Ajuste("sem_troca_rede", "Bateria e rede", "Fica no Wi-Fi quando ele oscila",
           "Não troca para os dados móveis a cada oscilação do Wi-Fi (bom para jogo e chamada de vídeo).",
           (("settings", "global", "network_avoid_bad_wifi", "0"),)),
    Ajuste("sem_atualizacao_auto", "Sistema", "Sistema baixa atualização só quando você pedir",
           "Evita download de atualização do Android no meio do uso.",
           (("settings", "global", "ota_disable_automatic_update", "1"),),
           aviso="Algumas marcas usam um atualizador próprio que ignora esta opção. Lembre de atualizar."),
    Ajuste("hz_maximo", "Tela", "Tela sempre na taxa máxima (Hz sem queda)",
           "Mantém a tela em 90/120 Hz o tempo todo, sem cair para 60 Hz.",
           (("settings", "system", "peak_refresh_rate", "{hz_max}"),
            ("settings", "system", "min_refresh_rate", "{hz_max}")),
           aviso="Gasta mais bateria. Samsung e Xiaomi podem ter um controle próprio que manda mais."),
    Ajuste("xiaomi_interface_leve", "Interface", "Interface leve (Xiaomi/HyperOS)",
           "Faz a interface da Xiaomi usar os efeitos de aparelho básico: sem desfoque pesado na barra e nas "
           "pastas, animações mais simples. É o ajuste usado para destravar Xiaomi e TV box lentas.",
           (("settings", "system", "deviceLevelList", "v:1,c:3,g:3"),), marcas=("xiaomi", "redmi", "poco"),
           reiniciar=True,
           aviso="Experimental: vale depois de reiniciar. Desfaça no Histórico se não gostar do visual."),
    Ajuste("hz_economia", "Tela", "Tela em 60 Hz (economia)",
           "Limita a tela a 60 Hz: a bateria dura mais, a rolagem fica menos lisa.",
           (("settings", "system", "peak_refresh_rate", "60"), ("settings", "system", "min_refresh_rate", "60"))),
)
POR_ID = {a.id: a for a in AJUSTES}
PERFIS = {
    "bateria": {"titulo": "Bateria", "descricao": "Mais frio e a bateria dura mais.",
                "ajustes": ["congelador", "dados_repouso_wifi", "sem_busca_wifi", "sem_wifi_auto", "hz_economia",
                            "animacoes_rapidas"]},
    "equilibrio": {"titulo": "Equilíbrio", "descricao": "Desempenho e bateria juntos.",
                   "ajustes": ["fantasmas", "congelador", "dados_repouso_wifi", "sem_busca_wifi",
                               "animacoes_rapidas"]},
    "maximo": {"titulo": "Máximo", "descricao": "Tudo pelo desempenho (esquenta e gasta mais).",
               "ajustes": ["fantasmas", "congelador", "sem_troca_rede", "hz_maximo", "animacoes_rapidas"]},
}


def _ler(ap, tipo: str, ns: str, chave: str) -> str | None:
    if tipo == "settings":
        return quarentena.ler_setting(ap, ns, chave)
    v = ap.sh(f"device_config get {ns} {chave}").strip()
    return None if v in ("", "null") else v


def _valor(ajuste: Ajuste, valor: str, contexto: dict[str, Any]) -> str | None:
    if "{hz_max}" in valor:
        hz = contexto.get("hz_max")
        return f"{float(hz):.1f}" if hz else None
    return valor


def _igual(a: str | None, b: str | None) -> bool:
    if a == b:
        return True
    try:
        return a is not None and b is not None and float(a) == float(b)
    except ValueError:
        return a is not None and b is not None and a.lower() == b.lower()


def _contexto(ap) -> dict[str, Any]:
    tela = _modos_tela(ap.sh("dumpsys display | grep -E 'mActiveSfDisplayMode|supportedModes'"))
    fab = ap.sh("getprop ro.product.manufacturer").strip().lower()
    return {"sdk": _sdk(ap), "hz_max": tela["hz_max"] if (tela["hz_max"] or 0) > 60 else None, "marca": fab}


def _da_marca(a: Ajuste, ctx: dict[str, Any]) -> bool:
    return not a.marcas or any(m in (ctx.get("marca") or "") for m in a.marcas)


def listar_ajustes(ap) -> dict[str, Any]:
    ctx = _contexto(ap)
    itens = []
    for a in AJUSTES:
        suportado, motivo = True, ""
        if ctx["sdk"] and ctx["sdk"] < a.sdk_min:
            suportado, motivo = False, f"Precisa do Android {_versao(a.sdk_min)} ou mais novo."
        valores = [_valor(a, v, ctx) for *_, v in a.mudancas]
        if any(v is None for v in valores):
            suportado, motivo = False, "A tela deste celular só tem 60 Hz."
        if not _da_marca(a, ctx):
            suportado, motivo = False, "Só para " + ", ".join(m.capitalize() for m in a.marcas) + "."
        pares = zip(a.mudancas, valores, strict=True)
        ligado = suportado and all(_igual(_ler(ap, t, ns, ch), v) for (t, ns, ch, _), v in pares)
        itens.append({"id": a.id, "grupo": a.grupo, "titulo": a.titulo, "descricao": a.descricao, "aviso": a.aviso,
                      "reiniciar": a.reiniciar, "opcional": a.opcional, "suportado": suportado, "motivo": motivo,
                      "ligado": ligado})
    return {"ajustes": itens, "perfis": [{"id": k, "titulo": v["titulo"], "descricao": v["descricao"],
                                          "ajustes": v["ajustes"]} for k, v in PERFIS.items()]}


def _versao(sdk: int) -> str:
    return {29: "10", 30: "11", 31: "12", 32: "12L", 33: "13", 34: "14", 35: "15", 36: "16"}.get(sdk, str(sdk))


def aplicar_ajustes(ap, ids: list[str], descricao: str | None = None) -> dict[str, Any]:
    desconhecidos = set(ids) - set(POR_ID)
    if desconhecidos:
        raise ValueError(f"ajuste desconhecido: {', '.join(sorted(desconhecidos))}")
    ids = list(dict.fromkeys(ids))
    if "hz_maximo" in ids and "hz_economia" in ids:
        raise ValueError("escolha só uma opção de taxa da tela (máxima ou economia)")
    if "mais_processos" in ids and "menos_processos" in ids:
        raise ValueError("escolha 'mais apps abertos' ou 'menos apps escondidos', não os dois")
    ctx = _contexto(ap)
    planos, resultado = [], []
    for ident in ids:
        a = POR_ID[ident]
        if ctx["sdk"] and ctx["sdk"] < a.sdk_min:
            resultado.append({"id": ident, "titulo": a.titulo, "ok": False,
                              "motivo": f"precisa do Android {_versao(a.sdk_min)}+"})
            continue
        valores = [_valor(a, v, ctx) for *_, v in a.mudancas]
        if any(v is None for v in valores) or not _da_marca(a, ctx):
            resultado.append({"id": ident, "titulo": a.titulo, "ok": False, "motivo": "não suportado neste celular"})
            continue
        planos.append((a, valores))
    # 1) guarda o estado atual de TUDO antes de mexer
    desfazer = []
    for a, _ in planos:
        for tipo, ns, chave, _v in a.mudancas:
            desfazer.append({"tipo": tipo, "ns": ns, "chave": chave, "anterior": _ler(ap, tipo, ns, chave)})
    pasta = quarentena.criar_ajuste(ap, "turbo", descricao or f"Turbo: {len(planos)} ajuste(s)", desfazer) \
        if desfazer else None
    # 2) aplica e confere
    for a, valores in planos:
        for (tipo, ns, chave, _), v in zip(a.mudancas, valores, strict=True):
            q = shlex.quote(v)
            ap.sh(f"settings put {ns} {chave} {q}" if tipo == "settings" else f"device_config put {ns} {chave} {q}")
        ok = all(_igual(_ler(ap, t, ns, ch), v) for (t, ns, ch, _), v in zip(a.mudancas, valores, strict=True))
        resultado.append({"id": a.id, "titulo": a.titulo, "ok": ok, "reiniciar": a.reiniciar,
                          "motivo": "" if ok else "o Android não aceitou (a marca pode bloquear)"})
    return {"resultado": resultado, "desfazer_id": pasta.name if pasta else None}


def aplicar_perfil(ap, perfil: str) -> dict[str, Any]:
    if perfil not in PERFIS:
        raise ValueError(f"perfil desconhecido: {perfil}")
    p = PERFIS[perfil]
    ids = [i for i in p["ajustes"]
           if not (i == "hz_maximo" and not _contexto(ap)["hz_max"])]
    return {"perfil": perfil, **aplicar_ajustes(ap, ids, f"Perfil {p['titulo']}")}


# ---------------------------------------------------------------------------------------------- jogos

ESCALAS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
FPS = (30, 45, 60, 90, 120)
MODOS_JOGO = {"padrao": "standard", "desempenho": "performance", "bateria": "battery"}


def jogo_info(ap, pkg: str) -> dict[str, Any]:
    exigir_pacote(pkg)
    sdk = _sdk(ap)
    if sdk < 31:
        return {"suportado": False, "motivo": "O modo de jogo do Android precisa do Android 12 ou mais novo."}
    saida = ap.sh(f"cmd game list-modes {pkg} 2>&1")
    config = ap.sh(f"cmd game list-configs {pkg} 2>&1") if sdk >= 33 else ""
    return {"suportado": True, "sdk": sdk, "modos": saida.strip()[:400],
            "config": config.strip()[:400], "resolucao_fps": sdk >= 33}


def ajustar_jogo(ap, pkg: str, modo: str = "desempenho", escala: float | None = None,
                 fps: int | None = None) -> dict[str, Any]:
    """Modo de jogo do Android (desempenho/bateria) + resolução e FPS do jogo (Android 13+)."""
    exigir_pacote(pkg)
    if modo not in MODOS_JOGO:
        raise ValueError(f"modo de jogo inválido: {modo}")
    if escala is not None and escala not in ESCALAS:
        raise ValueError("resolução do jogo: use 100%, 90%, 80%, 70%, 60% ou 50%")
    if fps is not None and fps not in FPS:
        raise ValueError("FPS do jogo: use 30, 45, 60, 90 ou 120")
    sdk = _sdk(ap)
    if sdk < 31:
        raise ValueError("O modo de jogo do Android precisa do Android 12 ou mais novo.")
    passos = []
    saida = ap.sh(f"cmd game mode {MODOS_JOGO[modo]} {pkg} 2>&1")
    passos.append({"passo": f"modo {modo}", "ok": not _falhou(saida), "saida": saida.strip()[:200]})
    if (escala is not None and escala != 1.0) or fps:
        if sdk < 33:
            passos.append({"passo": "resolução/FPS", "ok": False, "saida": "precisa do Android 13+"})
        else:
            args = f"--mode {MODOS_JOGO[modo]}"
            if escala is not None:
                args += f" --downscale {escala:g}"
            if fps:
                args += f" --fps {fps}"
            saida = ap.sh(f"cmd game set {args} {pkg} 2>&1")
            passos.append({"passo": "resolução/FPS", "ok": not _falhou(saida), "saida": saida.strip()[:200]})
    pasta = quarentena.criar_ajuste(ap, f"jogo_{pkg}", f"Modo de jogo em {pkg}",
                                    [{"tipo": "cmd", "desfazer": f"cmd game reset {pkg}",
                                      "descricao": f"modo de jogo de {pkg} no padrão"}])
    return {"pacote": pkg, "passos": passos, "ok": all(p["ok"] for p in passos), "desfazer_id": pasta.name,
            "obs": "O Android só aplica resolução/FPS em apps marcados como jogo e em aparelhos que liberam a "
                   "função. Se não mudar nada no jogo, a marca bloqueou."}


# ---------------------------------------------------------------------------------------------- apps esquecidos


def esquecidos(ap, dias: int = 30) -> list[dict[str, Any]]:
    if not 3 <= dias <= 365:
        raise ValueError("dias: entre 3 e 365")
    terceiros = _pacotes(ap.sh("pm list packages -3 -e"))
    uso = ultimo_uso(ap)
    prot = _protegidos(ap)
    res = []
    for pkg in terceiros:
        d = uso.get(pkg)
        if pkg in prot or essencial(pkg):
            continue
        if d is None or d >= dias:
            res.append({"pacote": pkg, "dias": round(d) if d is not None else None})
    return sorted(res, key=lambda x: -(x["dias"] or 9999))


def dormir(ap, pacotes: list[str], nivel: str = "rare") -> dict[str, Any]:
    """Põe apps sem uso para dormir (balde 'rare' ou 'restricted'). Abrir o app acorda sozinho."""
    if nivel not in ("rare", "restricted"):
        raise ValueError("nível: rare (quase não acorda) ou restricted (parado de vez)")
    if nivel == "restricted" and _sdk(ap) < 30:
        nivel = "rare"
    prot = _protegidos(ap)
    desfazer, res = [], []
    for pkg in pacotes:
        exigir_pacote(pkg)
        if pkg in prot or essencial(pkg):
            res.append({"pacote": pkg, "ok": False})
            continue
        anterior = balde(ap, pkg)
        ap.sh(f"am set-standby-bucket {pkg} {nivel}")
        ok = balde(ap, pkg) == nivel
        if ok and anterior and anterior != nivel:
            desfazer.append({"tipo": "cmd", "desfazer": f"am set-standby-bucket {pkg} {anterior}",
                             "descricao": f"{pkg} acordado ({anterior})"})
        res.append({"pacote": pkg, "ok": ok})
    pasta = quarentena.criar_ajuste(ap, "apps_dormindo", f"Apps dormindo ({len(desfazer)})", desfazer) \
        if desfazer else None
    return {"apps": res, "desfazer_id": pasta.name if pasta else None}


def segundo_plano(ap, pacotes: list[str], permitir: bool = False) -> dict[str, Any]:
    """'Proibidos em segundo plano': o app só roda aberto (appop RUN_ANY_IN_BACKGROUND)."""
    prot = _protegidos(ap)
    desfazer, res = [], []
    for pkg in pacotes:
        exigir_pacote(pkg)
        if pkg in prot or essencial(pkg):
            res.append({"pacote": pkg, "ok": False})
            continue
        m = re.search(r"RUN_ANY_IN_BACKGROUND:\s*(\w+)", ap.sh(f"cmd appops get {pkg} RUN_ANY_IN_BACKGROUND"))
        anterior = m.group(1) if m else "default"
        alvo = "allow" if permitir else "ignore"
        ap.sh(f"cmd appops set {pkg} RUN_ANY_IN_BACKGROUND {alvo}")
        desfazer.append({"tipo": "appops", "pacote": pkg, "op": "RUN_ANY_IN_BACKGROUND", "anterior": anterior})
        res.append({"pacote": pkg, "ok": True})
    pasta = quarentena.criar_ajuste(ap, "segundo_plano", f"Segundo plano de {len(desfazer)} app(s)", desfazer) \
        if desfazer else None
    return {"apps": res, "desfazer_id": pasta.name if pasta else None}


# ---------------------------------------------------------------------------------------------- manutenção

MANUTENCOES = {
    "dexopt": ("Manutenção antecipada", "A faxina de compilação que o Android faria de madrugada roda agora.",
               "cmd package bg-dexopt-job", 3600, 0),
    "art_cleanup": ("Faxina do ART", "Apaga código compilado que sobrou de apps antigos ou removidos.",
                    "pm art cleanup", 600, 34),
    "armazenamento": ("Armazenamento rápido", "Roda a manutenção do armazenamento (TRIM): gravações mais rápidas "
                      "em celular cheio.", "sm idle-maint run", 900, 0),
    "cache": ("Limpar cache geral", "Apaga o cache de todos os apps (eles recriam o que precisarem).",
              "pm trim-caches 999G", 600, 0),
}


def manutencao(ap, ident: str) -> dict[str, Any]:
    if ident not in MANUTENCOES:
        raise ValueError(f"manutenção desconhecida: {ident}")
    titulo, _desc, cmd, timeout, sdk_min = MANUTENCOES[ident]
    if sdk_min and _sdk(ap) < sdk_min:
        return {"id": ident, "titulo": titulo, "ok": False, "saida": f"precisa do Android {_versao(sdk_min)}+"}
    saida = ap.sh(cmd, timeout=timeout, erro=True)
    return {"id": ident, "titulo": titulo, "ok": not _falhou(saida), "saida": saida.strip()[-300:]}


# ---------------------------------------------------------------------------------------------- rede


def montar_rede(wifi: str, ping: str) -> dict[str, Any]:
    info = re.search(r"mWifiInfo (.*)", wifi)
    linha = info.group(1) if info else wifi
    freq = re.search(r"Frequency:\s*(\d+)\s*MHz", linha)
    rssi = re.search(r"RSSI:\s*(-?\d+)", linha)
    vel = re.search(r"Link speed:\s*(\d+)\s*Mbps", linha)
    padrao = re.search(r"Wi-Fi standard:\s*(\S+)", linha)
    perda = re.search(r"([\d.]+)% packet loss", ping)
    rtt = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", ping)
    f = int(freq.group(1)) if freq else None
    banda = None if f is None else ("2,4 GHz" if f < 3000 else "5 GHz" if f < 5925 else "6 GHz")
    r = int(rssi.group(1)) if rssi and int(rssi.group(1)) > -127 else None
    sinal = None if r is None else "ótimo" if r >= -55 else "bom" if r >= -67 else "fraco" if r >= -78 else "ruim"
    dicas = []
    if banda == "2,4 GHz":
        dicas.append("Conectado em 2,4 GHz: se o roteador tiver 5 GHz, use essa rede para jogar (menos ping e "
                     "menos interferência).")
    if sinal in ("fraco", "ruim"):
        dicas.append("Sinal fraco: chegue mais perto do roteador ou use um repetidor.")
    jitter = float(rtt.group(4)) if rtt else None
    if jitter is not None and jitter > 20:
        dicas.append("Ping oscilando muito: alguém pode estar baixando/assistindo na mesma rede.")
    return {"conectado": f is not None, "banda": banda, "frequencia_mhz": f, "rssi_dbm": r, "sinal": sinal,
            "velocidade_mbps": int(vel.group(1)) if vel else None, "padrao": padrao.group(1) if padrao else None,
            "ping_ms": float(rtt.group(2)) if rtt else None, "oscilacao_ms": jitter,
            "perda_pct": float(perda.group(1)) if perda else None, "dicas": dicas}


def rede(ap) -> dict[str, Any]:
    wifi = ap.sh("dumpsys wifi | grep -m1 mWifiInfo", timeout=30)
    ping = ap.sh("ping -c 10 -i 0.3 -W 2 8.8.8.8 2>&1", timeout=30)
    return montar_rede(wifi, ping)


# ---------------------------------------------------------------------------------------------- editor de configurações

NAMESPACES = ("system", "secure", "global")
CHAVE = re.compile(r"[A-Za-z0-9_.\-]{1,120}")
# mexer nisto derruba a própria conexão com o PC ou trava a tela: o editor não deixa
BLOQUEADAS = {"adb_enabled", "adb_wifi_enabled", "development_settings_enabled", "device_provisioned",
              "user_setup_complete", "lock_screen_lock_after_timeout", "package_verifier_enable",
              "verifier_verify_adb_installs", "install_non_market_apps"}


def listar_config(ap, ns: str, filtro: str = "") -> list[dict[str, str]]:
    if ns not in NAMESPACES:
        raise ValueError("namespace: system, secure ou global")
    res = []
    for linha in ap.sh(f"settings list {ns}", timeout=30).splitlines():
        if "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        if filtro and filtro.lower() not in k.lower() and filtro.lower() not in v.lower():
            continue
        res.append({"chave": k, "valor": v, "bloqueada": k in BLOQUEADAS})
    return res[:500]


def editar_config(ap, ns: str, chave: str, valor: str | None) -> dict[str, Any]:
    if ns not in NAMESPACES:
        raise ValueError("namespace: system, secure ou global")
    if not CHAVE.fullmatch(chave):
        raise ValueError("nome de configuração inválido")
    if chave in BLOQUEADAS:
        raise ValueError("essa configuração derruba a conexão com o PC ou a segurança do celular; não é editável aqui")
    if valor is not None and (len(valor) > 500 or "\n" in valor or "\x00" in valor):
        raise ValueError("valor inválido")
    anterior = quarentena.ler_setting(ap, ns, chave)
    pasta = quarentena.criar_ajuste(ap, f"config_{chave}"[:60], f"Configuração {ns}/{chave}",
                                    [{"tipo": "settings", "ns": ns, "chave": chave, "anterior": anterior}])
    if valor is None:
        ap.sh(f"settings delete {ns} {chave}")
    else:
        ap.sh(f"settings put {ns} {chave} {shlex.quote(valor)}")
    atual = quarentena.ler_setting(ap, ns, chave)
    return {"chave": chave, "anterior": anterior, "atual": atual, "ok": atual == valor, "desfazer_id": pasta.name}


# ---------------------------------------------------------------------------------------------- receita sob medida


def receita(ap) -> dict[str, Any]:
    """Plano de otimização feito para ESTE celular, a partir do que foi medido agora."""
    f = ficha(ap)
    sdk = f.get("sdk") or 0
    etapas: list[dict[str, Any]] = []

    def etapa(ident: str, titulo: str, detalhe: str, marcada: bool = True) -> None:
        etapas.append({"id": ident, "titulo": titulo, "detalhe": detalhe, "marcada": marcada})

    status = (f.get("termico") or {}).get("status") or 0
    if status >= 2:
        etapa("aviso_calor", "Esfriar antes", "O celular está quente agora: a compilação pode demorar mais. "
              "Tire da tomada e da capa.", marcada=False)
    etapa("compilar_mais_usados", "Seus apps mais usados compilados",
          "Os 5 apps que você mais abre na semana passam pela otimização completa e abrem mais rápido.")
    etapa("dexopt", "Manutenção antecipada", "A faxina do sistema roda agora, não no meio do jogo.")
    if sdk >= 34:
        etapa("art_cleanup", "Faxina do ART", "Apaga código compilado que sobrou de apps antigos.")
    if sdk >= 31:
        etapa("fantasmas", "Fim dos processos fantasmas",
              f"Android {f.get('android')}: para de matar Shizuku e jogos em segundo plano.")
    if sdk >= 30:
        etapa("congelador", "Congelador de apps", "Apps parados não gastam CPU (vale após reiniciar).")
    etapa("esquecidos", "Apps esquecidos dormindo", "Apps sem uso há 30 dias param de rodar escondidos "
          "(acordam sozinhos quando você abrir).")
    etapa("sistema_leve", "Sistema mais leve", "Tela inicial, barra e Configurações compiladas (sem engasgos).")
    etapa("armazenamento", "Armazenamento rápido", "Manutenção (TRIM) do armazenamento.")
    if (f.get("ram_gb") or 99) <= 4:
        etapa("menos_processos", "Menos apps escondidos", f"Só {f.get('ram_gb')} GB de RAM: guardar menos apps "
              "em segundo plano deixa o que está aberto mais liso.")
    elif (f.get("ram_gb") or 0) >= 7:
        etapa("mais_processos", "Mais apps abertos ao mesmo tempo", f"{f.get('ram_gb')} GB de RAM: os apps "
              "voltam de onde pararam em vez de recomeçar.")
    xiaomi = any(m in (f.get("fabricante") or "").lower() for m in ("xiaomi", "redmi", "poco"))
    etapa("faxina_marca", "Tirar anúncios e apps inúteis da marca",
          "Desativa os serviços de propaganda e os apps duplicados da fabricante (volta pelo Histórico)."
          if xiaomi else "Desativa apps de parceiros pré-instalados (Facebook, operadora...).")
    etapa("camera", "Câmera mais rápida", "Câmera e galeria compiladas por completo e com o cache limpo.")
    etapa("dns_anuncios", "Bloqueio de anúncios (DNS AdGuard)", "Bloqueia propaganda em apps e sites sem instalar "
          "nada. Não pega anúncio do YouTube.", marcada=False)
    if xiaomi:
        etapa("xiaomi_interface_leve", "Interface leve (Xiaomi)", "Tira o desfoque pesado e simplifica as animações "
              "(vale após reiniciar).", marcada=False)
    etapa("animacoes_rapidas", "Animações mais rápidas", "Telas abrem na metade do tempo.", marcada=False)
    return {"ficha": f, "etapas": etapas}


ETAPAS = {"compilar_mais_usados", "dexopt", "art_cleanup", "fantasmas", "congelador", "esquecidos",
          "sistema_leve", "armazenamento", "menos_processos", "mais_processos", "animacoes_rapidas", "aviso_calor",
          "faxina_marca", "camera", "dns_anuncios", "xiaomi_interface_leve"}


def comparar_notas(antes: dict[str, Any], depois: dict[str, Any]) -> dict[str, Any]:
    """Antes x depois: diferença em pontos e ganho em % (só onde as duas medidas existem)."""
    def dif(a, d):
        if a is None or d is None:
            return None
        return {"antes": a, "depois": d, "pontos": d - a, "ganho_pct": round((d - a) / a * 100) if a else None}

    cats = {k: dif(v["nota"], depois["categorias"].get(k, {}).get("nota"))
            for k, v in antes.get("categorias", {}).items()}
    return {"total": dif(antes.get("total"), depois.get("total")), "categorias": {k: v for k, v in cats.items() if v},
            "obs": "Logo depois de compilar o celular ainda está quente e ocupado: meça de novo amanhã para o ganho "
                   "real (costuma ser maior)."}


def aplicar_receita(ap, ids: list[str], progresso: Progresso = None, cancelar=None,
                    medir: bool = False) -> dict[str, Any]:
    desconhecidas = set(ids) - ETAPAS
    if desconhecidas:
        raise ValueError(f"etapa desconhecida: {', '.join(sorted(desconhecidas))}")
    antes = None
    if medir:
        try:
            antes = nota(ap, progresso)
        except AdbErro:
            antes = None
    r = _aplicar_etapas(ap, ids, progresso, cancelar)
    if antes and antes.get("total") is not None and not (cancelar is not None and cancelar.is_set()):
        if progresso:
            progresso({"etapa": "nota", "descricao": "Medindo de novo para comparar", "detalhe": "", "atual": None,
                       "total": None, "estimativa_s": 40})
        try:
            depois = nota(ap)
            r["antes_depois"] = comparar_notas(antes, depois)
        except AdbErro:
            pass
    return r


def _aplicar_etapas(ap, ids: list[str], progresso: Progresso, cancelar) -> dict[str, Any]:
    ids = [i for i in dict.fromkeys(ids) if i != "aviso_calor"]
    feitos, desfazer_ids = [], []
    for n, ident in enumerate(ids, 1):
        if cancelar is not None and cancelar.is_set():
            break
        if progresso:
            progresso({"etapa": "receita", "descricao": "Aplicando a receita", "detalhe": ident, "atual": n,
                       "total": len(ids), "estimativa_s": 60 * (len(ids) - n + 1)})
        try:
            if ident in POR_ID:
                r = aplicar_ajustes(ap, [ident], f"Receita: {POR_ID[ident].titulo}")
                ok = all(x["ok"] for x in r["resultado"])
                if r["desfazer_id"]:
                    desfazer_ids.append(r["desfazer_id"])
            elif ident in MANUTENCOES:
                ok = manutencao(ap, ident)["ok"]
            elif ident == "compilar_mais_usados":
                r = compilar_apps(ap, "completa", alvos_compilacao(ap, "mais_usados"), cancelar=cancelar)
                ok = not r["falhas"]
            elif ident == "sistema_leve":
                r = compilar_apps(ap, "completa", alvos_compilacao(ap, "sistema"), cancelar=cancelar)
                ok = not r["falhas"]
            elif ident == "faxina_marca":
                from celscan.acoes import faxina

                alvos = [a["pacote"] for a in faxina.apps_da_marca(ap)["apps"] if a["marcado"] and a["ativo"]]
                r = faxina.remover_apps(ap, alvos, cancelar=cancelar)
                ok = all(x["ok"] for x in r["apps"])
            elif ident == "camera":
                from celscan.acoes import faxina

                ok = bool(faxina.camera_rapida(ap)["apps"])
            elif ident == "dns_anuncios":
                from celscan.acoes import faxina

                r = faxina.definir_dns(ap, "adguard")
                ok = r["ok"]
                desfazer_ids.append(r["desfazer_id"])
            else:  # esquecidos
                r = dormir(ap, [x["pacote"] for x in esquecidos(ap, 30)], "rare")
                ok = True
                if r["desfazer_id"]:
                    desfazer_ids.append(r["desfazer_id"])
        except (AdbErro, ValueError) as e:
            feitos.append({"id": ident, "ok": False, "erro": str(e)[:150]})
            continue
        feitos.append({"id": ident, "ok": ok})
    return {"etapas": feitos, "desfazer_ids": desfazer_ids}
