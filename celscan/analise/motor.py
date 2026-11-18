"""Motor CelScan: antivírus local que lê o CÓDIGO de cada app (sem internet, sem VirusTotal).

Pelo cabo, lê do APK no celular só o necessário (índice do ZIP, os classes*.dex e arquivos suspeitos em assets/)
e procura o que o vírus precisa ter por dentro para funcionar:

- lista de apps de banco embutida + uso da acessibilidade para tocar/digitar sozinho  -> trojan bancário;
- APK ou DEX escondido dentro do app, ou bloco cifrado grande + carregamento de código -> dropper;
- canal de envio por Telegram/Discord embutido                                          -> roubo de dados;
- domínios de espionagem conhecidos (MVT/Amnesty, Echap) nas strings do código           -> spyware;
- envio de SMS, comandos de root, ocultar o próprio ícone, empacotadores usados por vírus.

Cada sinal tem peso próprio e um peso menor quando o app veio da loja oficial (para não acusar app sério).
O resultado é guardado por hash do APK: a segunda varredura do mesmo app é instantânea.
"""

from __future__ import annotations

import json
import math
import re
import struct
from collections import Counter
from typing import Any

from celscan.analise import apksig, pix
from celscan.core.log import LOGGER

VERSAO = 1
MAX_DEX = 40 * 1024 * 1024      # por arquivo .dex
MAX_TOTAL = 96 * 1024 * 1024    # por app (apps gigantes: lê os primeiros dex, onde fica o código principal)
MAX_ASSET = 12 * 1024 * 1024

# empacotadores/"protetores" chineses muito usados para esconder vírus (bancos usam outros, comerciais)
PACKERS = {
    "libjiagu": "Jiagu (360)", "libsecexe": "Bangcle", "libsecmain": "Bangcle", "libDexHelper": "DexHelper",
    "libexec.so": "ijiami", "libexecmain": "ijiami", "libprotectClass": "APKProtect", "libtup": "Tencent Legu",
    "libshell": "Tencent Legu", "libmobisec": "Alibaba", "libSecShell": "SecShell", "libapkprotect": "APKProtect",
    "libnqshield": "NQ Shield", "libbaiduprotect": "Baidu",
}
CARREGA = (b"Ldalvik/system/DexClassLoader;", b"Ldalvik/system/InMemoryDexClassLoader;",
           b"Ldalvik/system/BaseDexClassLoader;")
ACESS_ACAO = (b"dispatchGesture", b"performGlobalAction", b"ACTION_SET_TEXT", b"performAction")
ACESS_BASE = b"Landroid/accessibilityservice/AccessibilityService;"
RX_TELEGRAM = re.compile(rb"api\.telegram\.org/bot|discord(?:app)?\.com/api/webhooks")
RX_PIX = re.compile(rb"chave ?pix|pix copia|copia e cola|qr ?code pix", re.I)
RX_ROOT = re.compile(rb"/system/(?:x?bin)/su\b|\bsu -c\b|magisk")


def _uleb(b: bytes, i: int) -> tuple[int, int]:
    v = s = 0
    while True:
        x = b[i]
        i += 1
        v |= (x & 0x7F) << s
        if x < 0x80:
            return v, i
        s += 7


def strings_dex(dex: bytes) -> list[bytes]:
    """Tabela de strings de um classes.dex (é onde ficam nomes de classes, URLs e textos do código)."""
    if len(dex) < 0x70 or not dex.startswith(b"dex\n"):
        return []
    n, off = struct.unpack_from("<II", dex, 0x38)
    res = []
    for k in range(min(n, 400_000)):
        p = off + 4 * k
        if p + 4 > len(dex):
            break
        (sd,) = struct.unpack_from("<I", dex, p)
        try:
            tam, i = _uleb(dex, sd)
            fim = dex.find(b"\x00", i)
            if fim < 0:
                break
            res.append(dex[i:fim])
        except IndexError:
            break
        del tam
    return res


def entropia(b: bytes) -> float:
    if not b:
        return 0.0
    amostra = b[:262144]
    c = Counter(amostra)
    n = len(amostra)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def analisar_zip(z, pacote: str, iocs: Any = None) -> dict[str, Any]:
    """Recebe um leitor de ZIP (rotulos._ZipRemoto ou um zipfile adaptado) e devolve os sinais achados."""
    nomes = list(z.nomes())
    sinais: dict[str, Any] = {"dex": 0, "lido_mb": 0.0}
    strings: list[bytes] = []
    total = 0
    for nome in sorted(n for n in nomes if re.fullmatch(r"classes\d*\.dex", n)):
        tam = z.tamanho_de(nome)
        if tam > MAX_DEX or total + tam > MAX_TOTAL:
            sinais["incompleto"] = True
            continue
        try:
            dados = z.ler_arquivo(nome, limite=MAX_DEX * 3)
        except ValueError:
            sinais["incompleto"] = True
            continue
        total += tam
        sinais["dex"] += 1
        strings += strings_dex(dados)
    sinais["lido_mb"] = round(total / 1048576, 1)

    # assets/res: APK, DEX ou bloco cifrado escondido (o "vírus de verdade" que o dropper instala depois)
    escondidos = []
    for nome in nomes:
        if not nome.startswith(("assets/", "res/raw/")) or nome.endswith("/"):
            continue
        tam = z.tamanho_de(nome)
        ext = nome.rsplit(".", 1)[-1].lower() if "." in nome.rsplit("/", 1)[-1] else ""
        if ext in ("dex", "apk", "jar") and tam > 2048:
            escondidos.append(nome)
            continue
        if 65536 <= tam <= MAX_ASSET and ext in ("", "dat", "bin", "so", "data", "db", "png", "jpg", "zip", "txt"):
            try:
                b = z.ler_arquivo(nome, limite=MAX_ASSET * 2)
            except ValueError:
                continue
            if b.startswith((b"dex\n", b"PK\x03\x04")) and ext not in ("zip",):
                escondidos.append(nome)
            elif ext in ("", "dat", "bin", "data") and entropia(b) > 7.95:
                escondidos.append(nome + " (cifrado)")
    libs = {n.rsplit("/", 1)[-1] for n in nomes if n.startswith("lib/") and n.endswith(".so")}
    packers = sorted({v for k, v in PACKERS.items() for lib in libs if lib.startswith(k)})
    return montar(pacote, strings, escondidos, packers, iocs, sinais)


def montar(pacote: str, strings: list[bytes], escondidos: list[str], packers: list[str], iocs: Any,
           sinais: dict[str, Any]) -> dict[str, Any]:
    tudo = set(strings)
    texto = b"\n".join(strings)
    carrega = any(c in tudo for c in CARREGA)
    usa_acess = ACESS_BASE in tudo or any(s.startswith(b"Landroid/accessibilityservice/") for s in tudo)
    acoes = [a.decode() for a in ACESS_ACAO if a in tudo]
    bancos = pix.carregar().oficiais
    nomes_curtos = {x.decode("utf-8", "ignore") for x in tudo if len(x) < 80}
    alvos = sorted({bancos[p].nome for p in nomes_curtos & set(bancos) if p != pacote and bancos[p].nome != "WhatsApp"})
    achados: list[dict[str, Any]] = []

    def achar(chave: str, detalhe: str = "", peso_loja: int | None = None) -> None:
        x = {"chave": chave, "detalhe": detalhe}
        if peso_loja is not None:
            x["peso_loja"] = peso_loja
        achados.append(x)

    if len(alvos) >= 3 and usa_acess:
        achar("motor_bancos_alvo", f"{len(alvos)} bancos: {', '.join(alvos[:4])}{'...' if len(alvos) > 4 else ''}",
              peso_loja=60)
    if usa_acess and acoes and RX_PIX.search(texto) and pacote not in bancos:
        achar("motor_pix", "acessibilidade + textos de Pix", peso_loja=40)
    if escondidos:
        achar("motor_payload", ", ".join(escondidos[:3]), peso_loja=30 if carrega else 10)
    elif carrega and packers:
        achar("motor_carrega_codigo", "carrega código extra escondido por empacotador", peso_loja=5)
    m = RX_TELEGRAM.search(texto)
    if m:
        achar("motor_canal_envio", "Telegram" if b"telegram" in m.group(0) else "Discord", peso_loja=25)
    if iocs is not None and getattr(iocs, "dominios", None):
        hits = iocs.dominios_em(texto.decode("utf-8", "ignore"))
        if hits:
            achar("motor_dominio_ameaca", f"{hits[0][0]} ({hits[0][1]})")
    envia_sms = b"sendTextMessage" in tudo or b"sendMultipartTextMessage" in tudo
    if envia_sms:
        achar("motor_envia_sms", peso_loja=0)
    if RX_ROOT.search(texto):
        achar("motor_root", peso_loja=0)
    if packers:
        achar("motor_empacotado", ", ".join(packers), peso_loja=0)
    return {"versao": VERSAO, "achados": achados, "bancos_alvo": alvos, "acessibilidade": usa_acess,
            "acoes_acessibilidade": acoes, "carrega_codigo": carrega, "escondidos": escondidos,
            "empacotadores": packers, "envia_sms": envia_sms, **sinais}


# ---------------------------------------------------------------------------------------------- cache e leitura


def _cache(sha256: str):
    from celscan.config import DIR
    return DIR / "cache" / "motor" / f"{sha256}.json"


def analisar(ap, pacote: str, apk: str, tamanho: int, sha256: str | None, iocs: Any = None) -> dict[str, Any] | None:
    """Analisa um app no celular (ou devolve do cache). Nunca levanta: erro vira None no log."""
    from celscan.analise.rotulos import _memo, _ZipRemoto

    if sha256:
        try:
            d = json.loads(_cache(sha256).read_text(encoding="utf-8"))
            if d.get("versao") == VERSAO:
                return d
        except (OSError, ValueError):
            pass
    try:
        z = _ZipRemoto(_memo(apksig.leitor_remoto(ap, apk)), tamanho)
        r = analisar_zip(z, pacote, iocs)
    except Exception as e:  # noqa: BLE001
        LOGGER.info("motor: %s não analisado (%s)", pacote, e)
        return None
    if sha256:
        try:
            alvo = _cache(sha256)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(json.dumps(r), encoding="utf-8")
        except OSError:
            pass
    return r


def escolher(apps: dict, dados, completo: bool, utilitario) -> list[str]:
    """Quais apps passam pelo motor. Completo: todos os instalados pelo usuário. Rápido: os que dão motivo."""
    from celscan.config import LOJAS

    res = []
    for pkg, a in apps.items():
        if a.sistema or not a.tamanho:
            continue
        if completo:
            res.append(pkg)
            continue
        fora = (a.instalador or "") not in LOJAS
        poder = (pkg in dados.acess or pkg in dados.admins or pkg in dados.notif
                 or "REQUEST_INSTALL_PACKAGES" in a.appops or "PROJECT_MEDIA" in a.appops)
        sem_icone = dados.icones is not None and pkg not in dados.icones
        if fora or poder or sem_icone or utilitario(f"{a.nome or ''} {pkg}"):
            res.append(pkg)
    return res
