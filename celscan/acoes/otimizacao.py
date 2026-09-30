"""Diagnóstico e otimização real via ADB (sem 'limpador de RAM' de fachada)."""
import json
import re
import time

import requests

from celscan.acoes import quarentena
from celscan.core import bases, parsers

UAD = ("https://raw.githubusercontent.com/Universal-Debloater-Alliance/"
       "universal-android-debloater-next-generation/main/resources/assets/uad_lists.json")
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
SAUDE = ("charge_full", "charge_full_design", "cycle_count")  # /sys/class/power_supply/battery/
PROPS = ("ro.product.manufacturer", "ro.product.model", "ro.product.marketname",
         "ro.serialno", "ro.build.version.release", "ro.build.version.security_patch")

DIAG = r"""
sec(){ echo "@@SEC $1"; }
sec bateria; dumpsys battery
sec saude; for f in SAUDE; do printf '%s=' "$f"; cat /sys/class/power_supply/battery/$f 2>/dev/null; echo; done
sec ident; for k in PROPS; do printf '%s=' "$k"; getprop $k; done
sec imei; service call iphonesubinfo 1 2>/dev/null
sec df; df -k /data 2>/dev/null
sec pastas; for d in PASTAS; do [ -d "$d" ] && du -sk "$d" 2>/dev/null; done
sec anim; for k in ANIM; do settings get global $k; done
sec mem; head -3 /proc/meminfo
sec uptime; cat /proc/uptime
sec fim
"""


def livre_kb(ap):
    return parsers.livre_kb(ap.sh("df -k /data"))


def diagnostico(ap):
    script = (DIAG.replace("PASTAS", " ".join(f'"{p}"' for p in PASTAS)).replace("ANIM", " ".join(ANIM))
              .replace("SAUDE", " ".join(SAUDE)).replace("PROPS", " ".join(PROPS)))
    return montar_diagnostico(ap.script(script, timeout=300))


def montar_diagnostico(s):
    """Seções brutas -> diagnóstico. Itens que não puderam ser lidos viram avisos visíveis."""
    avisos = []
    bateria = parsers.bateria(s.get("bateria", ""))
    saude = parsers.saude_bateria(s.get("saude", ""))
    if bateria and saude:
        bateria = {**bateria, **saude}
    armaz = parsers.df(s.get("df", ""))
    ram = parsers.meminfo(s.get("mem", ""))
    dias = parsers.uptime_dias(s.get("uptime", ""))
    ident = parsers.identificacao(s.get("ident", ""))
    imei = parsers.imei(s.get("imei", ""))
    if imei:
        ident["imei"] = imei
    for valor, nome in ((bateria, "bateria"), (armaz, "armazenamento"), (ram, "memória RAM"),
                        (dias, "tempo ligado")):
        if valor is None:
            avisos.append(f"Verificação de {nome} não disponível neste aparelho.")
    if not imei:
        avisos.append("IMEI não disponível por USB (o Android moderno bloqueia sem permissão especial).")
    pastas = [{"pasta": PASTAS.get(p, p), "gb": kb / 1048576}
              for p, kb in parsers.tamanhos_pastas(s.get("pastas", "")).items() if kb > 0]
    anim = [linha.strip() for linha in s.get("anim", "").splitlines()]
    return {"bateria": bateria or {}, "armazenamento": armaz, "pastas": sorted(pastas, key=lambda x: -x["gb"]),
            "ram": ram, "ligado_dias": dias, "animacoes": anim, "identificacao": ident, "avisos": avisos}


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


def _baixar_uad():
    r = requests.get(UAD, timeout=60)
    r.raise_for_status()
    json.loads(r.text)  # valida antes de gravar
    return r.text


BASE_UAD = bases.registrar(bases.Base(
    nome="uad", descricao="Lista de apps pré-instalados (Universal Android Debloater)", arquivo="uad.json",
    validade_s=7 * 86400, baixar=_baixar_uad,
))


def lista_uad(forcar=False):
    if forcar or bases.vencida(BASE_UAD):
        bases.atualizar("uad", forcar=forcar)
    texto = bases.ler("uad")
    try:
        return json.loads(texto) if texto else {}
    except ValueError:
        return {}


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
