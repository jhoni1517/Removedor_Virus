"""Começo e fim do atendimento: bateria antes de mexer, conferência depois de remover e o "Finalizar".

- `bateria`: nível e se está carregando. Remover/backup/otimizar com 5% e o celular desligando no meio
  deixa o app pela metade (ou a cópia cortada): avisamos antes.
- `conferir`: depois de remover, confere em 3 segundos se os apps sumiram MESMO e se não sobrou
  acessibilidade, leitor de notificações ou administrador deles (sem refazer a varredura toda).
- `abrir_app`: abre a tela do app nos Ajustes do celular (quando a remoção é bloqueada, o técnico
  tira o administrador ou desinstala por lá).
- `finalizar`: apaga o que o CelScan deixou no celular e desliga a depuração USB/Wi-Fi e as opções do
  desenvolvedor, para o cliente não sair da loja com o celular aberto para qualquer PC.
"""

from __future__ import annotations

from typing import Any

from celscan.config import PROPRIOS
from celscan.core import parsers
from celscan.core.adb import AdbErro, Aparelho
from celscan.core.seguranca import exigir_pacote

BATERIA_MINIMA = 15  # % abaixo do qual pedimos para carregar antes de ações demoradas


def bateria(ap: Aparelho) -> dict[str, Any]:
    """{nivel: int|None, carregando: bool, baixa: bool}."""
    b = parsers.bateria(ap.sh("dumpsys battery")) or {}
    try:
        nivel: int | None = int(b.get("nivel") or "")
    except ValueError:
        nivel = None
    carregando = (b.get("situacao") or "").lower() in ("carregando", "cheia", "charging", "full")
    return {"nivel": nivel, "carregando": carregando,
            "baixa": nivel is not None and nivel < BATERIA_MINIMA and not carregando}


def abrir_app(ap: Aparelho, pkg: str) -> str:
    exigir_pacote(pkg)
    ap.sh(f"am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:{pkg}")
    return f"Tela do app {pkg} aberta no celular"


def conferir(ap: Aparelho, pacotes: list[str]) -> list[dict[str, Any]]:
    """Para cada pacote: ainda instalado? com acessibilidade/notificações/admin? rodando?"""
    for p in pacotes:
        exigir_pacote(p)
    instalados = set(parsers.pacotes(ap.sh("pm list packages")).keys())
    acess = parsers.componentes(ap.sh("settings get secure enabled_accessibility_services"))
    notif = parsers.componentes(ap.sh("settings get secure enabled_notification_listeners"))
    admins = parsers.admins(ap.sh("dumpsys device_policy"))
    vivos = parsers.rodando(ap.sh("ps -A -o NAME 2>/dev/null || ps"))
    res = []
    for p in pacotes:
        sobrou = [nome for nome, cond in (("acessibilidade", p in acess), ("leitor de notificações", p in notif),
                                          ("administrador", p in admins), ("rodando", p in vivos)) if cond]
        ainda = p in instalados
        res.append({"pacote": p, "instalado": ainda, "sobrou": sobrou, "limpo": not ainda and not sobrou})
    return res


def finalizar(ap: Aparelho, desligar_depuracao: bool = True) -> list[str]:
    """Limpa os rastros do CelScan e (opcional) desliga a depuração. A conexão cai no fim: é o esperado."""
    feito: list[str] = []
    for pkg in PROPRIOS:
        if "Success" in ap.sh(f"pm uninstall {pkg}", erro=True):
            feito.append(f"{pkg} (ferramenta do CelScan) removido do celular")
    ap.sh("rm -f /data/local/tmp/celscan_* /data/local/tmp/celscan*.sh 2>/dev/null")
    feito.append("arquivos temporários do CelScan apagados")
    if desligar_depuracao:
        try:
            ap.sh("settings put global adb_wifi_enabled 0")
            ap.sh("settings put global development_settings_enabled 0")
            ap.sh("settings put global adb_enabled 0", timeout=10)
        except AdbErro:
            pass  # o próprio comando derruba a conexão do adb em vários aparelhos
        feito.append("depuração USB/Wi-Fi e opções do desenvolvedor desligadas")
    return feito
