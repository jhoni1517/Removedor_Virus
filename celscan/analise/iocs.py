"""Indicadores de ameaça públicos: Stalkerware (Echap) + spyware (MVT/Amnesty).

Além de pacotes, certificados e hashes, guarda os domínios dos indicadores do MVT (~6,6 mil),
usados para cruzar com as URLs achadas dentro de um APK e com a configuração de rede.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
import yaml

from celscan.core import bases

ECHAP = "https://raw.githubusercontent.com/AssoEchap/stalkerware-indicators/master/ioc.yaml"
MVT = "https://raw.githubusercontent.com/mvt-project/mvt-indicators/main/indicators.yaml"
VALIDADE = 24 * 3600
RX = re.compile(r"(app:id|app:cert\.sha1|app:cert\.sha256|file:hashes\.sha256|domain-name:value|url:value)"
                r"\s*=\s*'([^']+)'")
# Hosts dentro de um texto qualquer (strings de um APK, por exemplo).
RX_HOST = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,24})(?=[:/\s\"'<>)]|$)", re.I)


def normalizar_dominio(valor: str) -> str | None:
    """'https://X.Evil.com:443/p' ou 'x.evil.com.' -> 'x.evil.com'."""
    v = valor.strip().lower()
    if "://" in v:
        v = urlparse(v).hostname or ""
    v = v.split("/")[0].split(":")[0].strip(".")
    return v if "." in v else None


class IOCs:
    def __init__(self, d):
        self.pacotes, self.certs, self.hashes = d["pacotes"], d["certs"], d["hashes"]
        self.dominios = d.get("dominios", {})  # caches antigos não têm
        self.atualizado = d["atualizado"]

    def checar_dominio(self, host):
        """Confere o host e cada domínio-pai (a.b.evil.com -> b.evil.com -> evil.com)."""
        h = normalizar_dominio(host or "")
        if not h:
            return None
        partes = h.split(".")
        for i in range(len(partes) - 1):
            achado = self.dominios.get(".".join(partes[i:]))
            if achado:
                return achado
        return None

    def dominios_em(self, texto):
        """Hosts suspeitos que aparecem num texto: [(host, ameaça)], sem repetir."""
        vistos, res = set(), []
        for host in RX_HOST.findall(texto or ""):
            h = host.lower()
            if h in vistos:
                continue
            vistos.add(h)
            ameaca = self.checar_dominio(h)
            if ameaca:
                res.append((h, ameaca))
        return res

    def checar(self, pacote, cert=None, sha256=None):
        if pacote in self.pacotes:
            return self.pacotes[pacote]
        if cert:
            for k in ("sha1", "sha256"):
                if cert.get(k) in self.certs:
                    return self.certs[cert[k]]
        if sha256 and sha256 in self.hashes:
            return self.hashes[sha256]
        return None

    def __len__(self):
        return len(self.pacotes) + len(self.certs) + len(self.hashes) + len(self.dominios)


def _stix(ent):
    g = ent.get("github") or {}
    if not g:
        return ent, None
    url = f"https://raw.githubusercontent.com/{g['owner']}/{g['repo']}/{g['branch']}/{g['path']}"
    try:
        return ent, requests.get(url, timeout=30).json()
    except Exception:
        return ent, None


def _baixar():
    pac, cer, has, dom = {}, {}, {}, {}
    for e in yaml.safe_load(requests.get(ECHAP, timeout=30).text) or []:
        nome = f"stalkerware {e.get('name', '?')}"
        for p in e.get("packages") or []:
            pac[p] = nome
        for c in e.get("certificates") or []:
            cer[str(c).upper()] = nome
    idx = yaml.safe_load(requests.get(MVT, timeout=30).text) or {}
    with ThreadPoolExecutor(8) as ex:
        for ent, j in ex.map(_stix, idx.get("indicators", [])):
            if not j:
                continue
            nome = ent.get("name", "MVT").replace(" Indicators of Compromise", "")
            for o in j.get("objects", []):
                if o.get("type") != "indicator":
                    continue
                for tipo, val in RX.findall(o.get("pattern", "")):
                    if tipo == "app:id":
                        pac.setdefault(val, nome)
                    elif tipo.startswith("app:cert"):
                        cer.setdefault(val.upper(), nome)
                    elif tipo in ("domain-name:value", "url:value"):
                        d = normalizar_dominio(val)
                        if d:
                            dom.setdefault(d, nome)
                    else:
                        has.setdefault(val.lower(), nome)
    return {"pacotes": pac, "certs": cer, "hashes": has, "dominios": dom, "atualizado": time.time()}


BASE = bases.registrar(bases.Base(
    nome="iocs", descricao="Indicadores de spyware/stalkerware (MVT/Amnesty + Echap)", arquivo="iocs.json",
    validade_s=VALIDADE, baixar=lambda: json.dumps(_baixar()),
))


def carregar(forcar=False, avisar=print):
    """Indicadores da cópia local; atualiza antes se estiver vencida (ou se forcar)."""
    if forcar or bases.vencida(BASE):
        ok, msg = bases.atualizar("iocs", forcar=forcar)
        if not ok:
            avisar(f"Indicadores: {msg}. " + ("Usando cópia local." if BASE.caminho.exists() else "Seguindo sem eles."))
    texto = bases.ler("iocs")
    if not texto:
        return None
    try:
        return IOCs(json.loads(texto))
    except (ValueError, KeyError):
        avisar("Cópia local dos indicadores corrompida; será baixada de novo na próxima vez.")
        BASE.caminho.unlink(missing_ok=True)
        return None
