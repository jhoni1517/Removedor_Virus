"""Diagnóstico e otimização real via ADB (sem 'limpador de RAM' de fachada)."""
import json
import re
import shlex
import time

import requests

from celscan.acoes import quarentena, saude
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
# Campos de saúde da bateria procurados em TODOS os medidores (/sys/class/power_supply/*): cada
# fabricante guarda num lugar (battery, bms, qg...). Saída: "medidor.campo=valor".
SAUDE_CAMPOS = ("charge_full", "charge_full_design", "cycle_count", "battery_cycle")
PROPS = ("ro.product.manufacturer", "ro.product.model", "ro.product.marketname",
         "ro.serialno", "ro.build.version.release", "ro.build.version.security_patch")

DIAG = r"""
sec(){ echo "@@SEC $1"; }
sec bateria; dumpsys battery
sec saude
for d in /sys/class/power_supply/*; do
  n=${d##*/}
  for f in SAUDE_CAMPOS; do
    v=$(cat "$d/$f" 2>/dev/null)
    [ -n "$v" ] && echo "$n.$f=$v"
  done
done
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
              .replace("SAUDE_CAMPOS", " ".join(SAUDE_CAMPOS)).replace("PROPS", " ".join(PROPS)))
    return montar_diagnostico(ap.script(script, timeout=300))


def montar_diagnostico(s):
    """Seções brutas -> diagnóstico. Itens que não puderam ser lidos viram avisos visíveis."""
    avisos = []
    bateria = parsers.bateria(s.get("bateria", ""))
    saude_sys = parsers.saude_bateria(s.get("saude", ""))
    if bateria and saude_sys:
        bateria = {**bateria, **saude_sys}
    pecas: list[dict[str, str]] = []
    if bateria:
        aval = saude.avaliar(bateria)
        bateria = {**bateria, **aval["bateria_extra"]}
        pecas = aval["pecas"]
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
            "ram": ram, "ligado_dias": dias, "animacoes": anim, "identificacao": ident,
            "pecas": pecas, "avisos": avisos}


def limpar_cache(ap):
    antes = livre_kb(ap)
    ap.sh("pm trim-caches 999G", timeout=600)
    time.sleep(2)
    depois = livre_kb(ap)
    return (depois - antes) / 1024 if antes is not None and depois is not None else None


# Lixo seguro: o celular refaz sozinho. NUNCA inclui fotos, vídeos ou documentos do dono (isso é irreversível).
LIXO: dict[str, tuple[str, tuple[str, ...]]] = {
    "miniaturas": ("Miniaturas (o celular refaz sozinho)",
                   ("/sdcard/DCIM/.thumbnails", "/sdcard/Pictures/.thumbnails", "/sdcard/Movies/.thumbnails")),
    "temporarios": ("Arquivos temporários e de log", ("/sdcard/LOST.DIR", "/sdcard/.temp", "/sdcard/temp")),
    "cache_telegram": ("Cache do Telegram (as mídias salvas continuam)",
                       ("/sdcard/Android/data/org.telegram.messenger/cache",)),
}


def medir_lixo(ap):
    """Mede, sem apagar, quanto cada tipo de lixo seguro ocupa (kB)."""
    res = []
    for chave, (nome, pastas) in LIXO.items():
        kb = 0
        for p in pastas:
            q = shlex.quote(p)
            saida = ap.sh(f"[ -d {q} ] && du -sk {q} 2>/dev/null || true")
            for tam, _pasta in re.findall(r"^(\d+)\s+(.+)$", saida, re.M):
                kb += int(tam)
        if kb > 0:
            res.append({"chave": chave, "nome": nome, "kb": kb})
    return res


def limpar_lixo(ap, categorias):
    """Apaga só o lixo seguro escolhido (conteúdo das pastas rebuildáveis). Nunca mídia pessoal."""
    antes = livre_kb(ap)
    for chave in categorias:
        if chave not in LIXO:
            raise ValueError(f"tipo de lixo desconhecido: {chave}")
        for p in LIXO[chave][1]:
            q = shlex.quote(p)
            ap.sh(f"[ -d {q} ] && rm -rf {q}/* 2>/dev/null || true", timeout=300)
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


# Níveis da comunidade UAD, traduzidos. Cumulativos: "avançado" inclui "recomendado".
# "Unsafe" (pode deixar o celular sem ligar) NUNCA é oferecido.
NIVEIS_DEBLOAT = {
    "recomendado": ("Recommended", 1, "Seguro desativar: propaganda, apps da operadora, duplicados."),
    "avancado": ("Advanced", 2, "Pode desligar uma função secundária (ex.: tema, widget). Revise um por um."),
    "especialista": ("Expert", 3, "Só para quem sabe o que o app faz: pode afetar recursos do sistema."),
}
_UAD_PARA_NIVEL = {v[0]: (k, v[1]) for k, v in NIVEIS_DEBLOAT.items()}


def sugestoes_debloat(ap, nivel="recomendado"):
    """Apps pré-instalados ativos que a comunidade UAD lista até o nível escolhido (nunca 'Unsafe')."""
    if nivel not in NIVEIS_DEBLOAT:
        raise ValueError(f"nível inválido: {nivel}")
    teto = NIVEIS_DEBLOAT[nivel][1]
    uad = lista_uad()
    ativos = set(re.findall(r"^package:([\w.]+)", ap.sh("pm list packages -e -s"), re.M))
    res = []
    for pkg in sorted(ativos):
        e = uad.get(pkg) or {}
        nome_nivel, ordem = _UAD_PARA_NIVEL.get(e.get("removal", ""), (None, 99))
        if nome_nivel and ordem <= teto:
            desc = (e.get("description") or "").strip().split("\n")[0]
            res.append({"pacote": pkg, "grupo": e.get("list", ""), "descricao": desc[:110], "nivel": nome_nivel})
    res.sort(key=lambda x: (NIVEIS_DEBLOAT[x["nivel"]][1], x["pacote"]))
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
