"""Remoção de apps com cópia na quarentena."""

from __future__ import annotations

import shlex

from celscan.acoes import quarentena
from celscan.core.adb import Aparelho


def neutralizar(ap: Aparelho, pkg: str, pasta, admins: list[str]) -> list[str]:
    """Tira os "poderes" do app antes de remover. Tudo fica registrado para desfazer."""
    avisos = []
    ap.sh(f"am force-stop {pkg}")
    for chave in ("enabled_accessibility_services", "enabled_notification_listeners"):
        atual = quarentena.ler_setting(ap, "secure", chave)
        if atual and pkg + "/" in atual:
            quarentena.adicionar_ajuste(pasta, {"tipo": "settings", "ns": "secure", "chave": chave, "anterior": atual})
            novo = ":".join(c for c in atual.split(":") if not c.startswith(pkg + "/"))
            ap.sh(f"settings put secure {chave} {shlex.quote(novo)}" if novo else f"settings delete secure {chave}")
    if "allow" in ap.sh(f"appops get {pkg} SYSTEM_ALERT_WINDOW"):
        quarentena.adicionar_ajuste(pasta, {"tipo": "appops", "pacote": pkg, "op": "SYSTEM_ALERT_WINDOW",
                                            "anterior": "allow"})
        ap.sh(f"appops set {pkg} SYSTEM_ALERT_WINDOW deny")
    for comp in admins:
        out = ap.sh(f"dpm remove-active-admin --user 0 {comp}", erro=True)
        if "Success" not in out:
            avisos.append(f"não consegui tirar o administrador {comp} pelo cabo")
    return avisos


def remover(ap: Aparelho, r: dict) -> tuple[bool, str]:
    pkg = r["pacote"]
    pasta = quarentena.criar(ap, pkg, r, copiar_apk=True)
    avisos = neutralizar(ap, pkg, pasta, r.get("admins") or [])

    out = ap.adb("uninstall", pkg, erro=True, timeout=180)
    if "Success" in out:
        quarentena.registrar(pasta, "removido")
        return True, "removido (cópia na quarentena)"
    out2 = ap.sh(f"pm uninstall --user 0 {pkg}", erro=True)
    if "Success" in out2:
        quarentena.registrar(pasta, "removido_usuario0")
        return True, "removido para o usuário (reversível)"
    if "DEVICE_POLICY" in out + out2:
        ap.sh("am start -a android.settings.SECURITY_SETTINGS")
        return False, ("bloqueado por ser administrador. Abri as Configurações de Segurança no celular: "
                       "desative o app em 'Apps de administrador' e rode de novo."
                       + (f" ({'; '.join(avisos)})" if avisos else ""))
    out3 = ap.sh(f"pm disable-user --user 0 {pkg}", erro=True)
    if "disabled" in out3:
        quarentena.registrar(pasta, "desativado")
        return True, "desativado (não foi possível desinstalar)"
    return False, f"falhou: {out or out2 or out3}"
