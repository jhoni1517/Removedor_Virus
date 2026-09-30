"""Conexão pelo Wi-Fi com QR code (Android 11+), no mesmo formato do Android Studio.

O celular lê o QR "WIFI:T:ADB;S:<nome>;P:<senha>;;" e anuncia na rede (mDNS) um serviço
_adb-tls-pairing com esse nome. O computador acha o serviço, pareia com a senha e conecta.
"""

from __future__ import annotations

import re
import secrets
import string
import threading
import time
from dataclasses import dataclass
from typing import Any

import qrcode
import qrcode.image.svg

from celscan.core import adb

TEMPO_LIMITE = 120


@dataclass
class Convite:
    nome: str
    senha: str

    @property
    def texto(self) -> str:
        return f"WIFI:T:ADB;S:{self.nome};P:{self.senha};;"

    def svg(self) -> str:
        img = qrcode.make(self.texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
        return img.to_string(encoding="unicode")

    def publico(self) -> dict[str, Any]:
        return {"nome": self.nome, "texto": self.texto, "qr_svg": self.svg()}


def novo_convite() -> Convite:
    letras = string.ascii_letters + string.digits
    return Convite("celscan-" + "".join(secrets.choice(letras) for _ in range(6)),
                   "".join(secrets.choice(letras) for _ in range(10)))


def servicos_mdns() -> list[tuple[str, str, str]]:
    """`adb mdns services` -> [(nome, tipo, ip:porta)]."""
    saida = adb.run(["mdns", "services"], timeout=15).stdout or ""
    res = []
    for linha in saida.splitlines():
        m = re.match(r"^(\S+)\s+(_adb[\w-]*\._tcp)\.?\s+(\S+:\d+)\s*$", linha.strip())
        if m:
            res.append((m.group(1), m.group(2), m.group(3)))
    return res


def esperar_pareamento(convite: Convite, progresso, cancelar: threading.Event) -> dict[str, Any]:
    from celscan.servicos import Cancelado

    progresso({"etapa": "wifi", "descricao": "Esperando o celular ler o código QR", "detalhe": convite.nome,
               "atual": None, "total": None, "estimativa_s": 30})
    limite = time.time() + TEMPO_LIMITE
    endereco = None
    while endereco is None:
        if cancelar.is_set():
            raise Cancelado("Pareamento cancelado.")
        if time.time() > limite:
            raise adb.AdbErro("O celular não apareceu na rede. Confira se os dois estão no mesmo Wi-Fi "
                              "e tente de novo.")
        endereco = next((e for n, t, e in servicos_mdns() if n == convite.nome and "pairing" in t), None)
        if endereco is None:
            cancelar.wait(1.5)
    progresso({"etapa": "wifi", "descricao": "Pareando", "detalhe": endereco, "atual": None, "total": None,
               "estimativa_s": 5})
    resposta = adb.parear(endereco, convite.senha)
    if "Successfully paired" not in resposta:
        raise adb.AdbErro(f"O pareamento falhou: {resposta or 'sem resposta'}")
    ip = endereco.rsplit(":", 1)[0]
    progresso({"etapa": "wifi", "descricao": "Conectando", "detalhe": ip, "atual": None, "total": None,
               "estimativa_s": 5})
    for _ in range(10):  # o serviço de conexão aparece alguns segundos depois do pareamento
        conexoes = [e for _n, t, e in servicos_mdns() if "connect" in t and e.startswith(ip + ":")]
        for e in conexoes:
            if "connected" in adb.conectar(e):
                return {"conectado": e}
        cancelar.wait(1.5)
    return {"pareado": endereco, "aviso": "Pareado. Se não conectar sozinho, use o endereço de 'Depuração por Wi-Fi'."}
