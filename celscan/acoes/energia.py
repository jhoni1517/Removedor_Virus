"""Reiniciar o celular pelo USB, inclusive nos modos de manutenção (recovery e fastboot).

Reiniciar NÃO apaga nada e NÃO mexe na senha nem na conta Google — é o mesmo que segurar o botão
de ligar. Serve para destravar um aparelho lento/travado ou entrar nos modos de manutenção.

Cada modo é explicado em linguagem simples, com o aviso do que esperar (o aparelho some do CelScan
ao reiniciar; no fastboot ele sai do Android e o cabo comum deixa de enxergá-lo).
"""

from __future__ import annotations

from typing import Any

from celscan.core.adb import AdbErro, Aparelho

MODOS: dict[str, dict[str, str]] = {
    "normal": {
        "nome": "Reiniciar",
        "alvo": "",
        "descricao": "Desliga e liga o aparelho, como segurar o botão. Resolve travamentos e lentidão.",
        "aviso": "O celular vai sumir do CelScan por alguns segundos e voltar sozinho quando ligar.",
    },
    "recovery": {
        "nome": "Modo recovery",
        "alvo": "recovery",
        "descricao": "Abre o menu de manutenção do Android (limpar cache, aplicar atualização oficial).",
        "aviso": "O aparelho entra no menu de recovery. Para sair, escolha 'Reboot system now' ou reinicie.",
    },
    "bootloader": {
        "nome": "Modo fastboot (bootloader)",
        "alvo": "bootloader",
        "descricao": "Tela de manutenção de baixo nível, usada por técnicos com a ferramenta fastboot.",
        "aviso": "O Android sai do ar e o cabo USB comum (adb) deixa de enxergar o aparelho — isto é "
                 "normal. Para voltar ao Android, segure o botão de ligar por alguns segundos.",
    },
}


def reiniciar(ap: Aparelho, modo: str = "normal") -> dict[str, Any]:
    """Manda o aparelho reiniciar no modo escolhido. A conexão cai logo depois (esperado)."""
    if modo not in MODOS:
        raise ValueError(f"modo de reinício inválido: {modo}")
    alvo = MODOS[modo]["alvo"]
    args = ["reboot", alvo] if alvo else ["reboot"]
    try:
        # O 'reboot' devolve na hora e o aparelho cai; um timeout curto evita travar a interface.
        ap.adb(*args, timeout=15, erro=True)
    except AdbErro:
        pass  # a conexão cair ao reiniciar é o esperado, não é falha
    return {"enviado": True, "modo": modo, "nome": MODOS[modo]["nome"], "aviso": MODOS[modo]["aviso"]}


def modos() -> list[dict[str, str]]:
    """Lista os modos para a interface montar os botões (chave + textos)."""
    return [{"chave": k, **{c: v[c] for c in ("nome", "descricao", "aviso")}} for k, v in MODOS.items()]
