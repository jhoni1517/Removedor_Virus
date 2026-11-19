"""Quem gasta a bateria e quem ocupa o espaço (com backup no PC antes de apagar).

Bateria: 'dumpsys batterystats --charged' (desde a última carga completa): mAh estimados por app e tempo de
wakelock (o app que impede o celular de dormir). Espaço: maiores arquivos, duplicados por tamanho+hash e mídia
velha do WhatsApp/Downloads, só nas pastas do usuário (/sdcard).
"""

from __future__ import annotations

import re
import shlex
from collections import defaultdict
from pathlib import Path
from typing import Any

from celscan.core.adb import AdbErro

RX_UID_MAH = re.compile(r"^\s+(?:Uid|UID) (u\d+a\d+|\d+|u\d+i\d+)\s*:\s*([\d.]+)", re.M)
RX_WAKE = re.compile(r"^\s+Wake lock (u\d+a\d+|\d+) (.+?): ((?:\d+(?:ms|[dhms])\s*)+)", re.M)
RX_DRENO = re.compile(r"Computed drain:\s*([\d.]+)")
RX_CAP = re.compile(r"Capacity:\s*(\d+)")
RX_PKG_UID = re.compile(r"^package:([\w.]+) uid:(\d+)", re.M)
SISTEMA_UID = {"0": "Kernel/root", "1000": "Sistema Android", "1001": "Rádio (sinal do celular)", "1002": "Bluetooth",
               "1010": "Wi-Fi", "1013": "Mídia", "1041": "Áudio", "1047": "Câmera"}
FILTRO = ("dumpsys batterystats --charged | grep -E '^ +(Uid|UID) |Wake lock |Computed drain|Capacity:' "
          "| head -n 4000")


def uid_num(u: str) -> int:
    """'u0a234' -> 10234; '1000' -> 1000."""
    m = re.fullmatch(r"u(\d+)a(\d+)", u)
    if m:
        return int(m.group(1)) * 100000 + 10000 + int(m.group(2))
    m = re.fullmatch(r"u(\d+)i(\d+)", u)
    if m:
        return int(m.group(1)) * 100000 + 90000 + int(m.group(2))
    return int(u)


def duracao_s(t: str) -> float:
    total = 0.0
    for n, un in re.findall(r"(\d+)(ms|d|h|m|s)", t):
        total += int(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}[un]
    return total


def montar_bateria(texto: str, pacotes_uid: dict[int, list[str]]) -> dict[str, Any]:
    mah: dict[int, float] = defaultdict(float)
    for u, v in RX_UID_MAH.findall(texto):
        mah[uid_num(u)] += float(v)
    wake: dict[int, float] = defaultdict(float)
    for u, _tag, t in RX_WAKE.findall(texto):
        wake[uid_num(u)] += duracao_s(t)
    m = RX_DRENO.search(texto)
    dreno = float(m.group(1)) if m else sum(mah.values())
    cap = RX_CAP.search(texto)
    apps = []
    for uid in set(mah) | set(wake):
        base = uid % 100000
        pkgs = pacotes_uid.get(base, [])
        if not pkgs and base < 10000 and str(base) not in SISTEMA_UID:
            continue
        apps.append({
            "uid": base, "pacotes": pkgs, "nome": None if pkgs else SISTEMA_UID.get(str(base), f"uid {base}"),
            "usuario": base >= 10000, "mah": round(mah.get(uid, 0.0), 1),
            "pct": round(100 * mah.get(uid, 0.0) / dreno, 1) if dreno else None,
            "acordado_min": round(wake.get(uid, 0.0) / 60, 1),
        })
    apps.sort(key=lambda a: (-a["mah"], -a["acordado_min"]))
    return {"dreno_mah": round(dreno, 1), "capacidade_mah": int(cap.group(1)) if cap else None,
            "apps": apps[:25], "obs": "Desde a última carga completa. 'Acordado' = tempo que o app impediu o "
                                     "celular de dormir (wakelock): muito tempo acordado com tela desligada é o "
                                     "que drena a bateria de madrugada."}


def bateria(ap) -> dict[str, Any]:
    pac: dict[int, list[str]] = defaultdict(list)
    for p, u in RX_PKG_UID.findall(ap.sh("pm list packages -U")):
        pac[int(u) % 100000].append(p)
    return montar_bateria(ap.sh(FILTRO, timeout=90), pac)


# ---------------------------------------------------------------------------------------------- espaço

RAIZ = "/sdcard"
MIDIA_VELHA = {
    "whatsapp": ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media", "Mídia do WhatsApp"),
    "whatsapp_antigo": ("/sdcard/WhatsApp/Media", "Mídia do WhatsApp (pasta antiga)"),
    "downloads": ("/sdcard/Download", "Downloads"),
    "telegram": ("/sdcard/Android/media/org.telegram.messenger/Telegram", "Telegram"),
}
ESPACO = r"""
sec(){ echo "@@SEC $1"; }
sec df; df /data 2>/dev/null | tail -n 1
sec grandes; find /sdcard/ -type f -size +50M ! -path '*/Android/data/*' ! -path '*/Android/obb/*' \
  -exec stat -c '%s|%Y|%n' {} + 2>/dev/null | sort -t'|' -k1 -nr | head -n 40
sec dupes; find /sdcard/DCIM /sdcard/Pictures /sdcard/Download /sdcard/Movies /sdcard/Android/media/com.whatsapp \
  -type f -size +1M -exec stat -c '%s|%n' {} + 2>/dev/null | sort -t'|' -k1 -n | head -n 6000
""" + "".join(
    f"sec velho_{k}; find {shlex.quote(p)} -type f -mtime +180 -exec stat -c '%s' {{}} + 2>/dev/null "
    f"| awk '{{s+=$1; n++}} END {{print n+0, s+0}}'\n" for k, (p, _n) in MIDIA_VELHA.items())


def montar_espaco(s: dict[str, str], hashes: dict[str, str] | None = None) -> dict[str, Any]:
    p = s.get("df", "").split()
    livre_gb = total_gb = None
    if len(p) >= 4 and p[1].isdigit() and p[3].isdigit():
        total_gb, livre_gb = round(int(p[1]) / 1048576, 1), round(int(p[3]) / 1048576, 1)
    grandes = []
    for linha in s.get("grandes", "").splitlines():
        partes = linha.split("|", 2)
        if len(partes) == 3 and partes[0].isdigit():
            grandes.append({"caminho": partes[2], "mb": round(int(partes[0]) / 1048576, 1),
                            "modificado": int(partes[1]) if partes[1].isdigit() else None})
    por_tam: dict[int, list[str]] = defaultdict(list)
    for linha in s.get("dupes", "").splitlines():
        partes = linha.split("|", 1)
        if len(partes) == 2 and partes[0].isdigit():
            por_tam[int(partes[0])].append(partes[1])
    candidatos = {t: c for t, c in por_tam.items() if len(c) > 1}
    duplicados = []
    if hashes is not None:
        grupos: dict[str, list[str]] = defaultdict(list)
        for t, cams in candidatos.items():
            for c in cams:
                if c in hashes:
                    grupos[f"{t}:{hashes[c]}"].append(c)
        for k, cams in grupos.items():
            if len(cams) > 1:
                mb = int(k.split(":")[0]) / 1048576
                duplicados.append({"mb": round(mb, 1), "arquivos": sorted(cams),
                                   "sobra_mb": round(mb * (len(cams) - 1), 1)})
        duplicados.sort(key=lambda d: -d["sobra_mb"])
    velhos = []
    for k, (caminho, nome) in MIDIA_VELHA.items():
        v = s.get(f"velho_{k}", "").split()
        if len(v) == 2 and v[0].isdigit() and int(v[0]):
            velhos.append({"id": k, "nome": nome, "pasta": caminho, "arquivos": int(v[0]),
                           "mb": round(int(float(v[1])) / 1048576, 1)})
    return {"livre_gb": livre_gb, "total_gb": total_gb, "grandes": grandes[:40], "duplicados": duplicados[:30],
            "velhos": velhos, "candidatos_dup": sum(len(c) for c in candidatos.values())}


def espaco(ap, progresso=None) -> dict[str, Any]:
    if progresso:
        progresso({"etapa": "espaco", "descricao": "Procurando o que ocupa espaço", "detalhe": "arquivos grandes",
                   "atual": 1, "total": 2, "estimativa_s": 40})
    s = ap.script(ESPACO, timeout=300)
    por_tam: dict[int, list[str]] = defaultdict(list)
    for linha in s.get("dupes", "").splitlines():
        partes = linha.split("|", 1)
        if len(partes) == 2 and partes[0].isdigit():
            por_tam[int(partes[0])].append(partes[1])
    cands = [c for cams in por_tam.values() if len(cams) > 1 for c in cams][:400]
    hashes: dict[str, str] = {}
    if cands:
        if progresso:
            progresso({"etapa": "espaco", "descricao": "Conferindo arquivos repetidos", "detalhe":
                       f"{len(cands)} arquivo(s)", "atual": 2, "total": 2, "estimativa_s": 30})
        for i in range(0, len(cands), 40):
            lote = " ".join(shlex.quote(c) for c in cands[i:i + 40])
            for linha in ap.sh(f"md5sum {lote} 2>/dev/null", timeout=180).splitlines():
                h, _, c = linha.partition("  ")
                if len(h) == 32 and c:
                    hashes[c.strip()] = h
    return montar_espaco(s, hashes)


def seguro(caminho: str) -> bool:
    """Só apaga dentro de /sdcard, nunca em Android/data|obb nem fora (caminho absoluto, sem '..')."""
    c = caminho.strip()
    return (c.startswith(("/sdcard/", "/storage/emulated/0/")) and ".." not in c.split("/")
            and "/Android/data/" not in c and "/Android/obb/" not in c and "\n" not in c)


def apagar(ap, caminhos: list[str], backup_dir: Path | None, progresso=None) -> dict[str, Any]:
    """Copia cada arquivo para o PC (backup_dir) e só então apaga no celular."""
    res = []
    for n, c in enumerate(caminhos, 1):
        if not seguro(c):
            res.append({"caminho": c, "ok": False, "erro": "fora das pastas do usuário"})
            continue
        if progresso:
            progresso({"etapa": "espaco", "descricao": "Guardando no PC e apagando", "detalhe": c.rsplit("/", 1)[-1],
                       "atual": n, "total": len(caminhos), "estimativa_s": None})
        try:
            if backup_dir is not None:
                destino = backup_dir / c.lstrip("/").replace("storage/emulated/0/", "sdcard/")
                destino.parent.mkdir(parents=True, exist_ok=True)
                ap.adb("pull", c, str(destino), timeout=900)
                if not destino.exists():
                    raise AdbErro("cópia para o PC falhou")
            ap.sh(f"rm -f {shlex.quote(c)}")
            res.append({"caminho": c, "ok": True})
        except (AdbErro, OSError) as e:
            res.append({"caminho": c, "ok": False, "erro": str(e)[:120]})
    if any(r["ok"] for r in res):
        try:  # avisa a galeria que os arquivos sumiram
            ap.sh("cmd media.scanner rescan /sdcard 2>/dev/null || true", timeout=30)
        except AdbErro:
            pass
    return {"apagados": [r for r in res if r["ok"]], "falhas": [r for r in res if not r["ok"]],
            "backup": str(backup_dir) if backup_dir else None}


def listar_velhos(ap, ident: str) -> list[str]:
    if ident not in MIDIA_VELHA:
        raise ValueError(f"pasta desconhecida: {ident}")
    pasta = MIDIA_VELHA[ident][0]
    saida = ap.sh(f"find {shlex.quote(pasta)} -type f -mtime +180 2>/dev/null | head -n 5000", timeout=120)
    return [x for x in saida.splitlines() if x.strip()]
