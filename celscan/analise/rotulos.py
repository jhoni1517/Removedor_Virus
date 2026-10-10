"""Nome e ícone reais dos apps, para a lista ficar legível para leigos.

Lê só o AndroidManifest.xml, o resources.arsc e o ícone do APK (pelo cabo, com dd), sem baixar o app
inteiro, e guarda em cache por hash do APK em ~/.celscan/icones. Também aproveita o manifesto para
achar redes de anúncio, gatilhos de pop-up e "disfarces" (atalhos alternativos de ícone).

- Nome em português quando o app tem tradução (pt-BR > pt > padrão).
- Usa o nome e o ícone da tela inicial (atividade principal), que é o que o usuário reconhece.
- Ícones PNG/WebP e também vetoriais/adaptativos (convertidos para SVG).
Se algo falhar, cai no nome do pacote.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import struct
import zlib
from dataclasses import asdict, dataclass, field

from celscan.config import DIR
from celscan.core.log import LOGGER

logging.getLogger("pyaxmlparser").setLevel(logging.ERROR)  # avisos internos de recursos ofuscados

CACHE = DIR / "icones"
NS = "{http://schemas.android.com/apk/res/android}"
MAX_ICONE = 512 * 1024
VERSAO_CACHE = 3

# Classes de SDKs de anúncio que abrem tela cheia (intersticial / pop-up)
SDK_ANUNCIO = {
    "com.google.android.gms.ads": "Google AdMob", "com.applovin": "AppLovin",
    "com.unity3d.ads": "Unity Ads", "com.unity3d.services.ads": "Unity Ads", "com.ironsource": "ironSource",
    "com.facebook.ads": "Meta Audience Network", "com.mbridge.msdk": "Mintegral", "com.vungle": "Vungle/Liftoff",
    "com.bytedance.sdk.openadsdk": "Pangle (TikTok)", "com.inmobi": "InMobi", "com.chartboost": "Chartboost",
    "com.adcolony": "AdColony", "com.startapp": "Start.io", "com.my.target": "myTarget",
    "com.yandex.mobile.ads": "Yandex Ads", "com.fyber": "Fyber/DT", "com.smaato": "Smaato",
    "com.tapjoy": "Tapjoy", "com.appodeal": "Appodeal", "com.bigossp": "BIGO Ads",
}
# Avisos do sistema que adware usa para abrir anúncio fora do app
GATILHOS = {
    "android.intent.action.USER_PRESENT": "ao desbloquear a tela",
    "android.intent.action.SCREEN_ON": "ao ligar a tela",
    "android.intent.action.ACTION_POWER_CONNECTED": "ao conectar o carregador",
    "android.intent.action.ACTION_POWER_DISCONNECTED": "ao desconectar o carregador",
    "android.intent.action.PACKAGE_ADDED": "ao instalar outro app",
    "android.intent.action.PACKAGE_REMOVED": "ao remover outro app",
    "android.net.conn.CONNECTIVITY_CHANGE": "ao mudar de rede",
}
GATILHOS_POPUP = {"ao desbloquear a tela", "ao ligar a tela", "ao conectar o carregador",
                  "ao desconectar o carregador", "ao instalar outro app", "ao remover outro app"}


def sdk_de(classe: str) -> str | None:
    """Rede de anúncio dona de uma tela (classe da Activity), se for de anúncio."""
    for prefixo, nome in SDK_ANUNCIO.items():
        if classe.startswith(prefixo):
            return nome
    return None


@dataclass
class Rotulo:
    pacote: str
    nome: str
    icone_png: bytes | None = None   # PNG/WebP do ícone, quando encontrado
    icone_svg: str | None = None     # ícone vetorial convertido, quando não há bitmap
    icone_fundo: str | None = None   # cor de fundo do ícone adaptativo (#RRGGBBAA)
    sdks_anuncio: list[str] = field(default_factory=list)
    gatilhos: list[str] = field(default_factory=list)
    disfarces: list[str] = field(default_factory=list)  # nomes de atalhos de ícone desativados
    anuncio_escondido: bool = False  # tela de anúncio fora da lista de recentes


class _ZipRemoto:
    """Lê um ZIP (APK) no celular sem baixá-lo todo: pega o índice central e só as entradas pedidas."""

    def __init__(self, ler, tamanho: int):
        self.ler, self.tamanho = ler, tamanho
        self._diretorio: dict[str, tuple[int, int, int]] = {}
        self._carregar_indice()

    def _carregar_indice(self) -> None:
        n = min(self.tamanho, 65557)
        ini_cauda = self.tamanho - n
        fim = self.ler(ini_cauda, n)
        i = fim.rfind(b"PK\x05\x06")
        if i < 0:
            raise ValueError("APK sem fim de diretório (EOCD)")
        total = struct.unpack_from("<H", fim, i + 10)[0]
        tam_cd, off_cd = struct.unpack_from("<II", fim, i + 12)
        # o índice quase sempre já veio junto com o fim do arquivo: evita uma leitura a mais
        cd = fim[off_cd - ini_cauda: off_cd - ini_cauda + tam_cd] if off_cd >= ini_cauda else self.ler(off_cd, tam_cd)
        pos = 0
        for _ in range(total):
            if cd[pos:pos + 4] != b"PK\x01\x02":
                break
            metodo, = struct.unpack_from("<H", cd, pos + 10)
            tam_comp, _tam_desc = struct.unpack_from("<II", cd, pos + 20)
            n_nome, n_extra, n_com = struct.unpack_from("<HHH", cd, pos + 28)
            off_local, = struct.unpack_from("<I", cd, pos + 42)
            nome = cd[pos + 46:pos + 46 + n_nome].decode("utf-8", "replace")
            self._diretorio[nome] = (off_local, tam_comp, metodo)
            pos += 46 + n_nome + n_extra + n_com

    def __contains__(self, nome: str) -> bool:
        return nome in self._diretorio

    def tamanho_de(self, nome: str) -> int:
        return self._diretorio[nome][1]

    def ler_arquivo(self, nome: str) -> bytes:
        off_local, tam_comp, metodo = self._diretorio[nome]
        # uma leitura só: cabeçalho local + margem para o "extra" (o zipalign usa para alinhar) + dados
        bloco = self.ler(off_local, 30 + 1024 + tam_comp)
        n_nome, n_extra = struct.unpack_from("<HH", bloco, 26)
        ini = 30 + n_nome + n_extra
        dados = bloco[ini:ini + tam_comp]
        if len(dados) < tam_comp:
            dados += self.ler(off_local + ini + len(dados), tam_comp - len(dados))
        # método 8 = deflate cru (sem cabeçalho zlib): wbits negativo
        return dados if metodo == 0 else zlib.decompress(dados, -15)


def _resolver(arsc, ref: str):
    if not isinstance(ref, str) or not ref.startswith("@"):
        return ref
    try:
        return int(ref[1:].split(":")[-1], 16)
    except ValueError:
        return ref


def _texto(arsc, ref) -> str | None:
    """Texto de um recurso, preferindo português do Brasil."""
    alvo = _resolver(arsc, ref)
    if isinstance(alvo, str):
        return alvo.strip() or None
    if alvo is None or arsc is None:
        return None
    try:
        cands = arsc.get_resolved_res_configs(alvo)
    except Exception:
        return None
    melhor, prioridade = None, -1
    for cfg, valor in cands:
        if not isinstance(valor, str) or not valor.strip():
            continue
        lingua, pais = cfg.get_language() or "", cfg.get_country() or ""
        p = 3 if (lingua, pais) == ("pt", "BR") else 2 if lingua == "pt" else 1 if not lingua else 0
        if p > prioridade:
            melhor, prioridade = valor.strip(), p
    return melhor


def _arquivos(arsc, rid) -> list[tuple[int, str]]:
    try:
        return [(cfg.get_density(), v) for cfg, v in arsc.get_resolved_res_configs(rid) if isinstance(v, str)]
    except Exception:
        return []


def _cor(arsc, rid) -> str | None:
    try:
        for _, v in arsc.get_resolved_res_configs(rid):
            if isinstance(v, str) and v.startswith("#"):
                return v
    except Exception:
        pass
    return None


def css_cor(v) -> str | None:
    """'#AARRGGBB' (Android) -> '#RRGGBBAA' (CSS)."""
    if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{8}", v):
        return "#" + v[3:] + v[1:3]
    return v if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{3,6}", v) else None


def _bitmap(arsc, rid, z) -> str | None:
    """Maior bitmap (até xxxhdpi) de um recurso de imagem."""
    cands = [(d, n) for d, n in _arquivos(arsc, rid) if n.lower().endswith((".png", ".webp")) and n in z]
    pequenos = [c for c in cands if c[0] <= 640]
    escolha = max(pequenos or cands, default=None)
    return escolha[1] if escolha else None


def _num(v, padrao: float = 0.0) -> float:
    m = re.match(r"-?[\d.]+", v or "")
    return float(m.group()) if m else padrao


def _attr(t: str) -> str:
    return t.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def vetor_svg(raiz, arsc, adaptativo: bool = False, fundo: str | None = None) -> str | None:
    """VectorDrawable do Android -> SVG (caminhos, grupos e cores; gradiente vira cor sólida)."""
    if raiz is None or raiz.tag != "vector":
        return None
    vw, vh = _num(raiz.get(NS + "viewportWidth"), 24), _num(raiz.get(NS + "viewportHeight"), 24)

    def cor(v):
        if isinstance(v, str) and v.startswith("@") and arsc is not None:
            v = _cor(arsc, _resolver(arsc, v))
        return css_cor(v)

    def nos(el) -> list[str]:
        out = []
        for f in el:
            if f.tag == "group":
                tx, ty = _num(f.get(NS + "translateX")), _num(f.get(NS + "translateY"))
                sx, sy = _num(f.get(NS + "scaleX"), 1), _num(f.get(NS + "scaleY"), 1)
                px, py, rot = _num(f.get(NS + "pivotX")), _num(f.get(NS + "pivotY")), _num(f.get(NS + "rotation"))
                t = f"translate({tx + px} {ty + py}) rotate({rot}) scale({sx} {sy}) translate({-px} {-py})"
                out.append(f'<g transform="{t}">{"".join(nos(f))}</g>')
            elif f.tag == "path" and f.get(NS + "pathData"):
                attrs = f'd="{_attr(f.get(NS + "pathData"))}" fill="{cor(f.get(NS + "fillColor")) or "none"}"'
                if f.get(NS + "fillAlpha"):
                    attrs += f' fill-opacity="{_num(f.get(NS + "fillAlpha"), 1)}"'
                if f.get(NS + "fillType") in ("evenOdd", "1"):
                    attrs += ' fill-rule="evenodd"'
                traco = cor(f.get(NS + "strokeColor"))
                if traco:
                    attrs += f' stroke="{traco}" stroke-width="{_num(f.get(NS + "strokeWidth"), 1)}"'
                out.append(f"<path {attrs}/>")
        return out

    corpo = "".join(nos(raiz))
    if not corpo:
        return None
    if adaptativo:  # só a área visível (72 de 108 dp) do ícone adaptativo
        ix, iy = vw * 18 / 108, vh * 18 / 108
        caixa = f"{ix} {iy} {vw - 2 * ix} {vh - 2 * iy}"
        bg = f'<rect x="{ix}" y="{iy}" width="{vw - 2 * ix}" height="{vh - 2 * iy}" fill="{fundo}"/>' if fundo else ""
    else:
        caixa, bg = f"0 0 {vw} {vh}", ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{caixa}">{bg}{corpo}</svg>'


def _xml(dados: bytes):
    from pyaxmlparser.axmlprinter import AXMLPrinter
    return AXMLPrinter(dados).get_xml_obj()


def _icone(z, arsc, ref) -> dict | None:
    """{'png': bytes} | {'svg': str} | {'fundo': cor} — o melhor que der para mostrar."""
    rid = _resolver(arsc, ref)
    if not isinstance(rid, int) or arsc is None:
        return None
    nome = _bitmap(arsc, rid, z)
    if nome:
        dados = z.ler_arquivo(nome)
        return {"png": dados} if len(dados) <= MAX_ICONE else None
    xmls = [n for _, n in _arquivos(arsc, rid) if n.endswith(".xml") and n in z]
    if not xmls:
        return None
    try:
        raiz = _xml(z.ler_arquivo(xmls[0]))
    except Exception:
        return None
    if raiz.tag == "vector":
        svg = vetor_svg(raiz, arsc)
        return {"svg": svg} if svg else None
    frente, fundo = raiz.find("foreground"), raiz.find("background")  # ícone adaptativo
    fundo_cor = None
    if fundo is not None:
        fr = _resolver(arsc, fundo.get(NS + "drawable"))
        fundo_cor = css_cor(_cor(arsc, fr)) if isinstance(fr, int) else css_cor(fr)
    if frente is not None:
        fr = _resolver(arsc, frente.get(NS + "drawable"))
        if isinstance(fr, int):
            nome = _bitmap(arsc, fr, z)
            if nome:  # camada da frente em bitmap: compõe com o fundo num SVG (área visível 72/108)
                b64 = base64.b64encode(z.ler_arquivo(nome)).decode()
                tipo = "webp" if nome.lower().endswith(".webp") else "png"
                return {"svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="18 18 72 72">'
                               f'<rect x="18" y="18" width="72" height="72" fill="{fundo_cor or "#ffffff"}"/>'
                               f'<image href="data:image/{tipo};base64,{b64}" width="108" height="108"/></svg>'}
            vx = [n for _, n in _arquivos(arsc, fr) if n.endswith(".xml") and n in z]
            if vx:
                try:
                    svg = vetor_svg(_xml(z.ler_arquivo(vx[0])), arsc, adaptativo=True, fundo=fundo_cor or "#ffffff")
                    if svg:
                        return {"svg": svg}
                except Exception:
                    pass
    return {"fundo": fundo_cor} if fundo_cor else None


def analisar(z: _ZipRemoto, pacote: str = "") -> Rotulo:
    """Lê manifesto + recursos de um APK aberto e devolve o rótulo completo."""
    from pyaxmlparser.arscparser import ARSCParser

    r = Rotulo(pacote, "")
    if "AndroidManifest.xml" not in z:
        return r
    man = _xml(z.ler_arquivo("AndroidManifest.xml"))
    app = man.find("application")
    if app is None:
        return r
    arsc = None
    if "resources.arsc" in z:
        try:
            arsc = ARSCParser(z.ler_arquivo("resources.arsc"))
        except Exception as e:
            LOGGER.info("resources.arsc ilegível em %s: %s", pacote, e)

    # entradas da tela inicial: a ativa define nome/ícone; as desativadas são "disfarces" possíveis
    principal, desativadas = None, []
    for comp in app:
        if comp.tag not in ("activity", "activity-alias"):
            continue
        for f in comp.findall("intent-filter"):
            acoes = {a.get(NS + "name") for a in f.findall("action")}
            cats = {c.get(NS + "name") for c in f.findall("category")}
            if "android.intent.action.MAIN" in acoes and "android.intent.category.LAUNCHER" in cats:
                if comp.get(NS + "enabled") == "false":
                    desativadas.append(comp)
                elif principal is None:
                    principal = comp
                break
    rotulo, icone = app.get(NS + "label"), app.get(NS + "icon") or app.get(NS + "roundIcon")
    if principal is not None:
        rotulo = principal.get(NS + "label") or rotulo
        icone = principal.get(NS + "icon") or icone
    r.nome = _texto(arsc, rotulo) or ""
    r.disfarces = sorted({d for d in (_texto(arsc, a.get(NS + "label")) for a in desativadas) if d and d != r.nome})

    sdks, gatilhos = set(), set()
    for comp in app:
        if comp.tag not in ("activity", "activity-alias", "service", "receiver", "provider"):
            continue
        classe = comp.get(NS + "name") or ""
        if classe.startswith("."):
            classe = pacote + classe
        sdk = sdk_de(classe)
        if sdk:
            sdks.add(sdk)
            if comp.tag == "activity" and comp.get(NS + "excludeFromRecents") == "true":
                r.anuncio_escondido = True
        if comp.tag == "receiver":
            for f in comp.findall("intent-filter"):
                for a in f.findall("action"):
                    if g := GATILHOS.get(a.get(NS + "name")):
                        gatilhos.add(g)
    r.sdks_anuncio, r.gatilhos = sorted(sdks), sorted(gatilhos)

    try:
        ic = _icone(z, arsc, icone) or {}
    except Exception as e:
        LOGGER.info("ícone de %s indisponível: %s", pacote, e)
        ic = {}
    png = ic.get("png")
    if png and (png[:8] == b"\x89PNG\r\n\x1a\n" or png[:4] == b"RIFF"):
        r.icone_png = png
    r.icone_svg, r.icone_fundo = ic.get("svg"), ic.get("fundo")
    return r


def extrair(ler, tamanho: int) -> tuple[str | None, str | None]:
    """Compatibilidade: (nome do app, caminho do ícone PNG no APK)."""
    from pyaxmlparser.arscparser import ARSCParser

    z = _ZipRemoto(ler, tamanho)
    if "AndroidManifest.xml" not in z or "resources.arsc" not in z:
        return None, None
    r = analisar(z)
    app = _xml(z.ler_arquivo("AndroidManifest.xml")).find("application")
    arsc = ARSCParser(z.ler_arquivo("resources.arsc"))
    rid = _resolver(arsc, app.get(NS + "icon")) if app is not None else None
    caminho = _bitmap(arsc, rid, z) if isinstance(rid, int) else None
    return r.nome or None, caminho


# ---------------------------------------------------------------- cache
def _de_cache(sha256: str | None) -> Rotulo | None:
    if not sha256:
        return None
    meta = CACHE / f"{sha256}.json"
    if not meta.exists():
        return None
    try:
        d = json.loads(meta.read_text(encoding="utf-8"))
        if d.pop("versao", None) != VERSAO_CACHE:
            return None
        png = CACHE / f"{sha256}.png"
        return Rotulo(icone_png=png.read_bytes() if png.exists() else None, **d)
    except (OSError, ValueError, TypeError):
        return None


def _gravar_cache(sha256: str, r: Rotulo) -> None:
    d = asdict(r)
    png = d.pop("icone_png")
    (CACHE / f"{sha256}.json").write_text(json.dumps({**d, "versao": VERSAO_CACHE}, ensure_ascii=False),
                                          encoding="utf-8")
    if png:
        (CACHE / f"{sha256}.png").write_bytes(png)


def obter(ap, pacote: str, apk: str, tamanho: int, sha256: str | None) -> Rotulo:
    """Nome, ícone e sinais do manifesto do app, usando o cache por hash quando houver."""
    from celscan.analise import apksig

    CACHE.mkdir(parents=True, exist_ok=True)
    cache = _de_cache(sha256)
    if cache:
        cache.pacote = pacote
        return cache
    try:
        r = analisar(_ZipRemoto(apksig.leitor_remoto(ap, apk), tamanho), pacote)
        ok = True
    except Exception as e:
        LOGGER.info("rótulo de %s indisponível: %s", pacote, e)
        r, ok = Rotulo(pacote, ""), False
    if sha256 and ok and r.nome:  # sem nome lido do APK não grava: tenta de novo na próxima varredura
        _gravar_cache(sha256, r)
    r.nome = r.nome or pacote
    return r


def icone_data_uri(icone) -> str | None:
    """Ícone pronto para <img src>: aceita bytes PNG/WebP ou um Rotulo (PNG ou SVG)."""
    if isinstance(icone, Rotulo):
        if icone.icone_png:
            return icone_data_uri(icone.icone_png)
        if icone.icone_svg:
            return "data:image/svg+xml;base64," + base64.b64encode(icone.icone_svg.encode()).decode()
        return None
    if not icone:
        return None
    tipo = "image/webp" if icone[:4] == b"RIFF" else "image/png"
    return f"data:{tipo};base64," + base64.b64encode(icone).decode()
