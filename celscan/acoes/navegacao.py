"""Atalhos que abrem direto uma tela de ajustes no celular (via 'am start').

Servem junto com o espelho/OTG: em vez de procurar no menu, o técnico cai exatamente
na tela certa. Observação honesta: 'am start' precisa do ADB já funcionando, ou seja,
a depuração USB já tem de estar ligada. Para LIGAR a depuração num aparelho de tela/toque
quebrado, use o modo OTG (o PC vira mouse do celular) e siga o guia em resgate.yaml.
"""

from __future__ import annotations

from celscan.core.adb import Aparelho

# nome curto -> (rótulo amigável, ação/atividade do Android)
AJUSTES: dict[str, tuple[str, str]] = {
    "desenvolvedor": ("Opções do desenvolvedor (depuração USB)",
                      "-a android.settings.APPLICATION_DEVELOPMENT_SETTINGS"),
    "acessibilidade": ("Acessibilidade", "-a android.settings.ACCESSIBILITY_SETTINGS"),
    "administradores": ("Administradores do aparelho",
                        "-n com.android.settings/.DeviceAdminSettings"),
    "fontes_desconhecidas": ("Instalar apps desconhecidos",
                             "-a android.settings.MANAGE_UNKNOWN_APP_SOURCES"),
    "notificacoes": ("Acesso a notificações",
                     "-a android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS"),
    "sobreposicao": ("Sobrepor outras telas",
                     "-a android.settings.action.MANAGE_OVERLAY_PERMISSION"),
    "bateria": ("Bateria e otimização", "-a android.settings.BATTERY_SAVER_SETTINGS"),
    "apps": ("Aplicativos", "-a android.settings.APPLICATION_SETTINGS"),
    "sobre": ("Sobre o telefone", "-a android.settings.DEVICE_INFO_SETTINGS"),
}


def abrir_ajuste(ap: Aparelho, chave: str) -> str:
    """Abre a tela de ajuste no celular e devolve o rótulo amigável dela."""
    if chave not in AJUSTES:
        raise ValueError(f"ajuste desconhecido: {chave}")
    rotulo, alvo = AJUSTES[chave]
    ap.sh(f"am start {alvo}")
    return rotulo
