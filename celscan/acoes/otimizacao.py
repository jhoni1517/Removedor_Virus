"""Diagnóstico e otimização real via ADB (sem 'limpador de RAM' de fachada)."""
import json
import re
import time

import requests

from celscan.acoes import quarentena
from celscan.config import DIR

UAD = ("https://raw.githubusercontent.com/Universal-Debloater-Alliance/"
       "universal-android-debloater-next-generation/main/resources/assets/uad_lists.json")
SAUDE = {"1": "desconhecida", "2": "boa", "3": "superaquecida", "4": "morta",
         "5": "sobretensão", "6": "falha", "7": "fria"}
PASTAS = {
    "/sdcard/DCIM": "Fotos e vídeos da câmera",
    "/sdcard/Pictures": "Imagens",
    "/sdcard/Movies": "Vídeos",
    "/sdcard/Download": "Downloads",
    "/sdcard/Android/media/com.whatsapp/WhatsApp/Media": "Mídia do WhatsApp",
    "/sdcard/WhatsApp/Media": "Mídia do WhatsApp (antigo)",
    "/sdcard/Android/media/org.telegram.messenger": "Mídia do Telegram",
}
ANIM = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")

DIAG = r"""
sec(){ echo "@@SEC $1"; }
sec bateria; dumpsys battery
sec df; df -k /data 2>/dev/null
sec pastas; for d in PASTAS; do [ -d "$d" ] && du -sk "$d" 2>/dev/null; done
sec anim; for k in ANIM; do settings get global $k; done
sec mem; head -3 /proc/meminfo
sec uptime; cat /proc/uptime
sec fim
"""


def _kv(txt):
    return {k.strip().lower(): v.strip() for k, v in re.findall(r"^\s*([^:\n]+):\s*(.+)$", txt, re.M)}


def livre_kb(ap):
    linhas = ap.sh("df -k /data").splitlines()
    try:
        return int(linhas[-1].split()[3])
    except (IndexError, ValueError):
        return None


def diagnostico(ap):
    script = DIAG.replace("PASTAS", " ".join(f'"{p}"' for p in PASTAS)).replace("ANIM", " ".join(ANIM))
    s = ap.script(script, timeout=300)
    b = _kv(s.get("bateria", ""))
    bateria = {
        "nivel": b.get("level"), "saude": SAUDE.get(b.get("health", ""), b.get("health")),
        "temperatura": f"{int(b['temperature']) / 10:.1f} °C" if b.get("temperature", "").isdigit() else None,
        "tensao": f"{int(b['voltage']) / 1000:.2f} V" if b.get("voltage", "").isdigit() else None,
        "ciclos": b.get("cycle count") or b.get("battery cycle count"),
    }
    armaz = None
    try:
        p = s["df"].splitlines()[-1].split()
        armaz = {"total_gb": int(p[1]) / 1048576, "livre_gb": int(p[3]) / 1048576}
    except (KeyError, IndexError, ValueError):
        pass
    pastas = []
    for linha in s.get("pastas", "").splitlines():
        m = re.match(r"^(\d+)\s+(.+)$", linha.strip())
        if m and int(m.group(1)) > 0:
            pastas.append({"pasta": PASTAS.get(m.group(2), m.group(2)), "gb": int(m.group(1)) / 1048576})
    mem = _kv(s.get("mem", ""))
    ram = None
    try:
        ram = {"total_gb": int(mem["memtotal"].split()[0]) / 1048576,
               "disponivel_gb": int(mem["memavailable"].split()[0]) / 1048576}
    except (KeyError, ValueError):
        pass
    try:
        dias = float(s.get("uptime", "0").split()[0]) / 86400
    except (ValueError, IndexError):
        dias = None
    anim = [l.strip() for l in s.get("anim", "").splitlines()]
    return {"bateria": bateria, "armazenamento": armaz, "pastas": sorted(pastas, key=lambda x: -x["gb"]),
            "ram": ram, "ligado_dias": dias, "animacoes": anim}


def limpar_cache(ap):
    antes = livre_kb(ap)
    ap.sh("pm trim-caches 999G", timeout=600)
    time.sleep(2)
    depois = livre_kb(ap)
    return (depois - antes) / 1024 if antes is not None and depois is not None else None


def compilar(ap):
    return ap.sh("cmd package bg-dexopt-job", timeout=3600, erro=True)


def animacoes(ap, valor):
    """Muda a velocidade das animações guardando os valores atuais (desfaz com quarentena restaurar)."""
    ajustes = [{"tipo": "settings", "ns": "global", "chave": k, "anterior": quarentena.ler_setting(ap, "global", k)}
               for k in ANIM]
    pasta = quarentena.criar_ajuste(ap, "ajuste_animacoes", f"Animações em {valor}x", ajustes)
    for k in ANIM:
        ap.sh(f"settings put global {k} {valor}")
    return pasta.name


def lista_uad(forcar=False):
    cache = DIR / "uad.json"
    if forcar or not cache.exists() or time.time() - cache.stat().st_mtime > 7 * 86400:
        try:
            r = requests.get(UAD, timeout=60)
            r.raise_for_status()
            cache.write_text(r.text, encoding="utf-8")
        except Exception:
            if not cache.exists():
                return {}
    return json.loads(cache.read_text(encoding="utf-8"))


def sugestoes_debloat(ap):
    """Apps pré-instalados ativos que a comunidade UAD marca como seguros de remover."""
    uad = lista_uad()
    ativos = set(re.findall(r"^package:([\w.]+)", ap.sh("pm list packages -e -s"), re.M))
    res = []
    for pkg in sorted(ativos):
        e = uad.get(pkg)
        if e and e.get("removal") == "Recommended":
            desc = (e.get("description") or "").strip().split("\n")[0]
            res.append({"pacote": pkg, "grupo": e.get("list", ""), "descricao": desc[:110]})
    return res


def desativar(ap, pkg):
    pasta = quarentena.criar(ap, pkg, {"motivos": ["debloat"]}, copiar_apk=False)
    out = ap.sh(f"pm disable-user --user 0 {pkg}", erro=True)
    if "disabled" in out:
        quarentena.registrar(pasta, "desativado")
        return True
    out = ap.sh(f"pm uninstall -k --user 0 {pkg}", erro=True)
    if "Success" in out:
        quarentena.registrar(pasta, "removido_usuario0")
        return True
    return False
