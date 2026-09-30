"""Gerenciador de permissões: revoga poderes perigosos de um app em 1 clique, com desfazer.

Cada ação fica registrada na quarentena (tipo "ajuste"), então "quarentena restaurar ID" devolve
o app ao estado anterior. Não desinstala nada.
"""

from __future__ import annotations

import shlex

from celscan.acoes import quarentena
from celscan.core.adb import Aparelho

# ação -> (nome curto, o que faz)
ACOES = {
    "acessibilidade": "Tirar do controle de tela (acessibilidade)",
    "notificacoes": "Tirar do acesso às notificações",
    "sobreposicao": "Bloquear janelas sobre outros apps",
    "captura_tela": "Bloquear a captura/transmissão de tela",
    "instalar_apps": "Bloquear a instalação de outros apps",
    "parar": "Forçar a parada do app agora",
}
# permissão perigosa -> texto para o usuário
PERMISSOES = {
    "android.permission.READ_SMS": "Ler SMS",
    "android.permission.RECEIVE_SMS": "Receber SMS",
    "android.permission.SEND_SMS": "Enviar SMS",
    "android.permission.READ_CALL_LOG": "Ler chamadas",
    "android.permission.RECORD_AUDIO": "Usar o microfone",
    "android.permission.CAMERA": "Usar a câmera",
    "android.permission.ACCESS_FINE_LOCATION": "Localização precisa",
    "android.permission.ACCESS_BACKGROUND_LOCATION": "Localização em segundo plano",
    "android.permission.READ_CONTACTS": "Ler contatos",
}
_APPOP = {"sobreposicao": "SYSTEM_ALERT_WINDOW", "captura_tela": "PROJECT_MEDIA",
          "instalar_apps": "REQUEST_INSTALL_PACKAGES"}


def _tirar_componente(ap: Aparelho, pkg: str, chave: str, pasta) -> bool:
    atual = quarentena.ler_setting(ap, "secure", chave)
    if not atual or pkg + "/" not in atual:
        return False
    quarentena.adicionar_ajuste(pasta, {"tipo": "settings", "ns": "secure", "chave": chave, "anterior": atual})
    novo = ":".join(c for c in atual.split(":") if not c.startswith(pkg + "/"))
    ap.sh(f"settings put secure {chave} {shlex.quote(novo)}" if novo else f"settings delete secure {chave}")
    return True


def _negar_appop(ap: Aparelho, pkg: str, op: str, pasta) -> None:
    liberada = "allow" in ap.sh(f"appops get {pkg} {op}")
    quarentena.adicionar_ajuste(pasta, {"tipo": "appops", "pacote": pkg, "op": op,
                                        "anterior": "allow" if liberada else "default"})
    ap.sh(f"appops set {pkg} {op} ignore")


def aplicar(ap: Aparelho, pkg: str, acoes: list[str], permissoes_revogar: list[str] | None = None) -> dict:
    """Executa as ações pedidas e devolve {quarentena_id, feitas:[...]}. Tudo é reversível."""
    invalidas = [a for a in acoes if a not in ACOES]
    if invalidas:
        raise ValueError(f"ação desconhecida: {', '.join(invalidas)}")
    pasta = quarentena.criar_ajuste(ap, "permissoes", f"Permissões de {pkg}", [])
    feitas: list[str] = []
    for acao in acoes:
        if acao == "parar":
            ap.sh(f"am force-stop {pkg}")
            feitas.append(ACOES[acao])
        elif acao == "acessibilidade":
            if _tirar_componente(ap, pkg, "enabled_accessibility_services", pasta):
                feitas.append(ACOES[acao])
        elif acao == "notificacoes":
            if _tirar_componente(ap, pkg, "enabled_notification_listeners", pasta):
                feitas.append(ACOES[acao])
        elif acao in _APPOP:
            _negar_appop(ap, pkg, _APPOP[acao], pasta)
            feitas.append(ACOES[acao])
    for perm in permissoes_revogar or []:
        if perm in PERMISSOES:
            quarentena.adicionar_ajuste(pasta, {"tipo": "permissao", "pacote": pkg, "permissao": perm})
            ap.sh(f"pm revoke {pkg} {perm}", erro=True)
            feitas.append(f"Revogar: {PERMISSOES[perm]}")
    quarentena.registrar(pasta, "ajuste")
    return {"quarentena_id": pasta.name, "feitas": feitas}
