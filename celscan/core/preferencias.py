"""Preferências do usuário.

Segredos (chave do VirusTotal, chave de IA) ficam no cofre do sistema (keyring): no Windows, o
Gerenciador de Credenciais. As demais preferências (modo offline, tema) ficam em
~/.celscan/config.json. Se o cofre não estiver disponível, o segredo cai para o config.json com um
aviso — nunca falhamos por causa disso.
"""

from __future__ import annotations

import json
import os
from typing import Any

from celscan import config
from celscan.core.log import LOGGER

ARQUIVO = config.DIR / "config.json"
SERVICO = "CelScan"
SEGREDOS = ("chave_virustotal", "chave_ia")  # nunca vão para o config.json em texto puro


def _keyring():
    """Devolve o módulo keyring se houver um cofre utilizável, senão None (sem quebrar)."""
    if os.getenv("CELSCAN_SEM_KEYRING"):
        return None
    try:
        import keyring
        keyring.get_keyring()  # dispara a detecção do backend (pode falhar em sistema sem cofre)
        return keyring
    except BaseException:  # noqa: BLE001 — backend nativo pode falhar duro; é opcional
        return None


def ler() -> dict[str, Any]:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_json(dados: dict[str, Any]) -> None:
    ARQUIVO.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def ler_segredo(nome: str) -> str | None:
    """Lê um segredo do cofre; migra do config.json antigo (texto puro) para o cofre quando achar."""
    kr = _keyring()
    if kr:
        try:
            valor = kr.get_password(SERVICO, nome)
            if valor:
                return valor
        except BaseException:  # noqa: BLE001
            pass
    legado = ler().get(nome)  # config.json de versões antigas
    if legado and kr:
        gravar_segredo(nome, legado)  # migra e limpa o texto puro
    return legado or None


def gravar_segredo(nome: str, valor: str | None) -> None:
    """Grava (ou apaga, se valor vazio) um segredo no cofre; sempre remove a cópia em texto puro."""
    dados = ler()
    tinha_texto_puro = dados.pop(nome, None) is not None
    kr = _keyring()
    if kr:
        try:
            if valor:
                kr.set_password(SERVICO, nome, valor)
            else:
                try:
                    kr.delete_password(SERVICO, nome)
                except BaseException:  # noqa: BLE001 — já não existia
                    pass
            if tinha_texto_puro:
                _gravar_json(dados)  # tira o segredo do arquivo
            return
        except BaseException:  # noqa: BLE001
            LOGGER.warning("Cofre do sistema indisponível; guardando %s no config.json.", nome)
    # Sem cofre: cai para o arquivo (aviso já dado).
    if valor:
        dados[nome] = valor
    _gravar_json(dados)


def salvar(**valores: Any) -> dict[str, Any]:
    """Salva preferências. Segredos vão para o cofre; o resto, para o config.json."""
    for nome in SEGREDOS:
        if nome in valores:
            v = valores.pop(nome)
            if v is not None:
                gravar_segredo(nome, v)
    atual = ler()
    atual.update({k: v for k, v in valores.items() if v is not None})
    _gravar_json(atual)
    if valores.get("offline") is not None:
        config.OFFLINE = bool(valores["offline"])
    return atual


def chave_virustotal() -> str | None:
    """A variável VT_API_KEY tem prioridade sobre a chave guardada."""
    return os.getenv("VT_API_KEY") or ler_segredo("chave_virustotal")


def aplicar() -> None:
    """Liga o modo offline se estiver salvo nas preferências."""
    if ler().get("offline"):
        config.OFFLINE = True
