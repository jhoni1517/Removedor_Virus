"""Nome e ícone reais dos apps, para a lista ficar legível para leigos.

Lê só o AndroidManifest.xml e o resources.arsc do APK (pelo cabo, com dd), sem baixar o app inteiro,
e guarda em cache por hash do APK em ~/.celscan/icones. Se algo falhar, cai no nome do pacote.
"""

from __future__ import annotations

import base64
import struct
import zlib
from dataclasses import dataclass

from celscan.config import DIR
from celscan.core.log import LOGGER

CACHE = DIR / "icones"
NS = "{http://schemas.android.com/apk/res/android}"
DENSIDADES = ("xxhdpi", "xhdpi", "xxxhdpi", "hdpi", "mdpi", "anydpi", "")  # preferência de tamanho do ícone
MAX_ICONE = 512 * 1024


@dataclass
class Rotulo:
    pacote: str
    nome: str
    icone_png: bytes | None = None  # PNG do ícone, quando encontrado


class _ZipRemoto:
    """Lê um ZIP (APK) no celular sem baixá-lo todo: pega o índice central e só as entradas pedidas."""

    def __init__(self, ler, tamanho: int):
        self.ler, self.tamanho = ler, tamanho
        self._diretorio: dict[str, tuple[int, int, int]] = {}
        self._carregar_indice()

    def _carregar_indice(self) -> None:
        n = min(self.tamanho, 65557)
        fim = self.ler(self.tamanho - n, n)
        i = fim.rfind(b"PK\x05\x06")
        if i < 0:
            raise ValueError("APK sem fim de diretório (EOCD)")
        total, tam_cd, off_cd = struct.unpack_from("<HxxxxII", fim, i + 8)[0:3] if False else (
            struct.unpack_from("<H", fim, i + 10)[0], struct.unpack_from("<I", fim, i + 12)[0],
            struct.unpack_from("<I", fim, i + 16)[0])
        cd = self.ler(off_cd, tam_cd)
        pos = 0
        for _ in range(total):
            if cd[pos:pos + 4] != b"PK\x01\x02":
                break
            metodo, = struct.unpack_from("<H", cd, pos + 10)
            tam_comp, tam_desc = struct.unpack_from("<II", cd, pos + 20)
            n_nome, n_extra, n_com = struct.unpack_from("<HHH", cd, pos + 28)
            off_local, = struct.unpack_from("<I", cd, pos + 42)
            nome = cd[pos + 46:pos + 46 + n_nome].decode("utf-8", "replace")
            self._diretorio[nome] = (off_local, tam_comp, metodo)
            pos += 46 + n_nome + n_extra + n_com

    def __contains__(self, nome: str) -> bool:
        return nome in self._diretorio

    def ler_arquivo(self, nome: str) -> bytes:
        off_local, tam_comp, metodo = self._diretorio[nome]
        cab = self.ler(off_local, 30)
        n_nome, n_extra = struct.unpack_from("<HH", cab, 26)
        dados = self.ler(off_local + 30 + n_nome + n_extra, tam_comp)
        # método 8 = deflate cru (sem cabeçalho zlib): wbits negativo
        return dados if metodo == 0 else zlib.decompress(dados, -15)


def _resolver(arsc, ref: str):
    if not ref or not ref.startswith("@"):
        return ref
    try:
        return int(ref[1:], 16)
    except ValueError:
        return ref


def extrair(ler, tamanho: int) -> tuple[str | None, str | None]:
    """Devolve (nome do app, caminho do ícone no APK) lendo o APK remoto."""
    from pyaxmlparser.arscparser import ARSCParser
    from pyaxmlparser.axmlprinter import AXMLPrinter

    z = _ZipRemoto(ler, tamanho)
    if "AndroidManifest.xml" not in z or "resources.arsc" not in z:
        return None, None
    man = AXMLPrinter(z.ler_arquivo("AndroidManifest.xml")).get_xml_obj()
    app = man.find("application")
    if app is None:
        return None, None
    arsc = ARSCParser(z.ler_arquivo("resources.arsc"))
    nome = _texto(arsc, app.get(NS + "label"))
    icone = _caminho_icone(arsc, app.get(NS + "icon"), z)
    return nome, icone


def _texto(arsc, ref) -> str | None:
    alvo = _resolver(arsc, ref)
    if isinstance(alvo, str):
        return alvo or None
    try:
        valores = {str(c.get_qualifier()): v for c, v in arsc.get_resolved_res_configs(alvo)}
    except Exception:
        return None
    return valores.get("") or (next(iter(valores.values()), None))


def _caminho_icone(arsc, ref, z) -> str | None:
    alvo = _resolver(arsc, ref)
    if not isinstance(alvo, int):
        return None
    try:
        por_config = {str(c.get_qualifier()): v for c, v in arsc.get_resolved_res_configs(alvo)}
    except Exception:
        return None
    for densidade in DENSIDADES:
        for config, caminho in por_config.items():
            if densidade in config and caminho.endswith(".png") and caminho in z:
                return caminho
    return next((c for c in por_config.values() if c.endswith(".png") and c in z), None)


def obter(ap, pacote: str, apk: str, tamanho: int, sha256: str | None) -> Rotulo:
    """Nome e ícone do app, usando o cache por hash quando houver."""
    from celscan.analise import apksig

    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"{sha256}.png" if sha256 else None
    cache_nome = CACHE / f"{sha256}.nome" if sha256 else None
    if cache_nome and cache_nome.exists():
        icone = cache.read_bytes() if cache and cache.exists() else None
        return Rotulo(pacote, cache_nome.read_text(encoding="utf-8"), icone)

    ler = apksig.leitor_remoto(ap, apk)
    try:
        nome, caminho = extrair(ler, tamanho)
    except Exception as e:
        LOGGER.info("rótulo de %s indisponível: %s", pacote, e)
        nome, caminho = None, None
    nome = nome or pacote
    icone = None
    if caminho:
        try:
            dados = _ZipRemoto(ler, tamanho).ler_arquivo(caminho)
            if dados[:8] == b"\x89PNG\r\n\x1a\n" and len(dados) <= MAX_ICONE:
                icone = dados
        except Exception:
            icone = None
    if cache_nome:
        cache_nome.write_text(nome, encoding="utf-8")
        if icone:
            cache.write_bytes(icone)
    return Rotulo(pacote, nome, icone)


def icone_data_uri(icone: bytes | None) -> str | None:
    return "data:image/png;base64," + base64.b64encode(icone).decode() if icone else None
