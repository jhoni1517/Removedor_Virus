"""Blindagem pós-limpeza: fecha as portas por onde o vírus entrou (tudo reversível).

- Play Protect ligado (verificação de apps do Google);
- tira a permissão "instalar apps desconhecidos" de quem NÃO é loja (é assim que dropper instala o vírus de volta);
- DNS contra golpes (Cloudflare Security: bloqueia sites de phishing e malware);
- lista do que só a pessoa pode fazer (senhas, Pix, WhatsApp Web).
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from celscan.acoes import faxina, quarentena
from celscan.config import LOJAS, LOJAS_ALTERNATIVAS

PLAY_PROTECT = (("global", "package_verifier_enable", "1"),)
DNS_GOLPES = "cloudflare_seguro"
ITENS = ("play_protect", "instaladores", "dns")
CHECKLIST = (
    ("senhas", "Troque a senha do e-mail principal (Google) e ative a verificação em 2 etapas."),
    ("banco", "Abra o app do banco: confira limites do Pix, chaves cadastradas e aparelhos autorizados."),
    ("whatsapp", "WhatsApp > Aparelhos conectados: desconecte tudo que você não reconhece. Ative a confirmação "
                 "em duas etapas (PIN)."),
    ("google", "myaccount.google.com > Segurança > Seus dispositivos: remova os que não são seus."),
    ("chip", "Peça à operadora o PIN do chip (evita clonagem/portabilidade sem você saber)."),
)
RX_PKG = re.compile(r"^package:([\w.]+)\s+installer=(\S*)", re.M)


def _terceiros(ap) -> dict[str, str]:
    """Apps instalados pelo usuário e quem instalou cada um."""
    return {p: (i if i != "null" else "") for p, i in RX_PKG.findall(ap.sh("pm list packages -3 -i"))}


def instaladores(ap) -> list[str]:
    """Apps de fora da loja que podem instalar outros apps sozinhos."""
    lojas = set(LOJAS) | set(LOJAS_ALTERNATIVAS)
    res = []
    for pkg, inst in sorted(_terceiros(ap).items()):
        if pkg in lojas or inst in LOJAS:
            continue
        if re.search(r"REQUEST_INSTALL_PACKAGES: allow", ap.sh(f"appops get {pkg} REQUEST_INSTALL_PACKAGES")):
            res.append(pkg)
    return res


def estado(ap) -> dict[str, Any]:
    pp = all(quarentena.ler_setting(ap, ns, k) == v for ns, k, v in PLAY_PROTECT)
    dns = faxina.dns_atual(ap)
    abertos = instaladores(ap)
    return {
        "play_protect": pp, "instaladores": abertos, "dns": dns["servidor"],
        "dns_golpes": dns["provedor"] in ("cloudflare_seguro", "adguard", "adguard_familia", "mullvad"),
        "checklist": [{"id": i, "texto": t} for i, t in CHECKLIST],
        "nota": sum((pp, not abertos, dns["servidor"] is not None)),
    }


def aplicar(ap, itens: list[str]) -> dict[str, Any]:
    desconhecidos = set(itens) - set(ITENS)
    if desconhecidos:
        raise ValueError(f"item desconhecido: {', '.join(sorted(desconhecidos))}")
    feitos, desfazer = [], []
    if "play_protect" in itens:
        desfazer += [{"tipo": "settings", "ns": ns, "chave": k, "anterior": quarentena.ler_setting(ap, ns, k)}
                     for ns, k, _ in PLAY_PROTECT]
    abertos = instaladores(ap) if "instaladores" in itens else []
    desfazer += [{"tipo": "appops", "pacote": p, "op": "REQUEST_INSTALL_PACKAGES", "anterior": "allow"}
                 for p in abertos]
    pasta = quarentena.criar_ajuste(ap, "blindagem", "Blindagem pós-limpeza", desfazer) if desfazer else None
    if "play_protect" in itens:
        for ns, k, v in PLAY_PROTECT:
            ap.sh(f"settings put {ns} {k} {v}")
        feitos.append({"id": "play_protect", "ok": all(quarentena.ler_setting(ap, ns, k) == v
                                                         for ns, k, v in PLAY_PROTECT)})
    for p in abertos:
        ap.sh(f"appops set {shlex.quote(p)} REQUEST_INSTALL_PACKAGES deny")
    if "instaladores" in itens:
        feitos.append({"id": "instaladores", "ok": True, "apps": abertos})
    res: dict[str, Any] = {"feitos": feitos, "desfazer_id": pasta.name if pasta else None}
    if "dns" in itens:
        d = faxina.definir_dns(ap, DNS_GOLPES)
        feitos.append({"id": "dns", "ok": d["ok"], "servidor": d["servidor"]})
        res["desfazer_dns_id"] = d["desfazer_id"]
    res["estado"] = estado(ap)
    return res
