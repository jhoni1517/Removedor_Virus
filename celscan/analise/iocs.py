"""Indicadores de ameaça públicos: Stalkerware (Echap) + spyware (MVT/Amnesty)."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import yaml

from celscan.core import bases

ECHAP = "https://raw.githubusercontent.com/AssoEchap/stalkerware-indicators/master/ioc.yaml"
MVT = "https://raw.githubusercontent.com/mvt-project/mvt-indicators/main/indicators.yaml"
VALIDADE = 24 * 3600
RX = re.compile(r"(app:id|app:cert\.sha1|app:cert\.sha256|file:hashes\.sha256)\s*=\s*'([^']+)'")


class IOCs:
    def __init__(self, d):
        self.pacotes, self.certs, self.hashes = d["pacotes"], d["certs"], d["hashes"]
        self.atualizado = d["atualizado"]

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
        return len(self.pacotes) + len(self.certs) + len(self.hashes)


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
    pac, cer, has = {}, {}, {}
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
                    else:
                        has.setdefault(val.lower(), nome)
    return {"pacotes": pac, "certs": cer, "hashes": has, "atualizado": time.time()}


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
