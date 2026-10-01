"""Assinatura digital dos laudos (Ed25519) para verificação pelo QR code, sem servidor.

Cada instalação do CelScan cria uma chave própria na primeira vez (guardada no cofre do sistema).
O laudo leva no QR: os dados resumidos + a assinatura + a chave pública. A página de verificação
(estática, roda no navegador do cliente) confere a assinatura: se alguém alterar a nota, a data
ou o aparelho, a assinatura deixa de bater. A "impressão digital" da chave identifica a loja/técnico
que emitiu — a loja pode mostrá-la no balcão ou no site para o cliente comparar.

Nada pessoal vai no QR: só número do laudo, data, modelo, nota, veredito e o hash dos dados.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from Cryptodome.PublicKey import ECC
from Cryptodome.Signature import eddsa

from celscan.core import preferencias

SEGREDO = "chave_laudo"
PAGINA = "https://jhoni1517.github.io/Removedor_Virus/v/"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _de_b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _chave() -> ECC.EccKey:
    pem = preferencias.ler_segredo(SEGREDO)
    if pem:
        try:
            return ECC.import_key(pem)
        except ValueError:
            pass  # chave corrompida: gera outra (laudos antigos continuam verificáveis pela chave deles)
    k = ECC.generate(curve="ed25519")
    preferencias.gravar_segredo(SEGREDO, k.export_key(format="PEM"))
    return k


def chave_publica() -> bytes:
    return _chave().public_key().export_key(format="raw")


def impressao_digital(pub: bytes | None = None) -> str:
    """Identificador curto da chave (ex.: 3F2A-91C0-7D44-B1E8), para a loja divulgar."""
    h = hashlib.sha256(pub if pub is not None else chave_publica()).hexdigest().upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def mensagem(dados: dict[str, Any]) -> bytes:
    """Forma canônica do que é assinado (a página recalcula exatamente igual)."""
    campos = ("i", "d", "m", "n", "v", "h")
    return ("CELSCAN1|" + "|".join(str(dados.get(c, "")) for c in campos)).encode("utf-8")


def assinar_laudo(laudo_id: int, data: str, modelo: str, nota: int, veredito: str, hash_hex: str) -> dict[str, Any]:
    dados = {"i": laudo_id, "d": data[:16], "m": modelo[:40], "n": nota, "v": veredito, "h": hash_hex[:32]}
    k = _chave()
    dados["k"] = _b64(k.public_key().export_key(format="raw"))
    dados["s"] = _b64(eddsa.new(k, "rfc8032").sign(mensagem(dados)))
    return dados


def url_verificacao(dados: dict[str, Any], pagina: str = PAGINA) -> str:
    """Os dados vão depois do '#': o navegador não os envia a servidor nenhum."""
    payload = _b64(json.dumps(dados, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return f"{pagina}#{payload}"


def verificar(dados: dict[str, Any]) -> bool:
    """Mesma conferência que a página faz (usada nos testes e no "Verificar laudo" local)."""
    try:
        pub = eddsa.import_public_key(_de_b64(dados["k"]))
        eddsa.new(pub, "rfc8032").verify(mensagem(dados), _de_b64(dados["s"]))
        return True
    except (KeyError, ValueError):
        return False


def ler_url(url: str) -> dict[str, Any]:
    return json.loads(_de_b64(url.split("#", 1)[1]))
