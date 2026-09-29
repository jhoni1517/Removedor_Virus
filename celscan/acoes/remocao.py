"""Remoção de apps com cópia na quarentena."""

from __future__ import annotations

import shlex

from celscan.acoes import quarentena
from celscan.core.adb import Aparelho


def remover(ap: Aparelho, r: dict) -> tuple[bool, str]:
    pkg = r["pacote"]
    pasta = quarentena.criar(ap, pkg, r, copiar_apk=True)
    ap.sh(f"am force-stop {pkg}")
    for chave in ("enabled_accessibility_services", "enabled_notification_listeners"):
        atual = ap.sh(f"settings get secure {chave}")
        if atual and atual != "null" and pkg + "/" in atual:
            novo = ":".join(c for c in atual.split(":") if not c.startswith(pkg + "/"))
            ap.sh(f"settings put secure {chave} {shlex.quote(novo)}" if novo else f"settings delete secure {chave}")

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
                       "desative o app em 'Apps de administrador' e rode de novo.")
    out3 = ap.sh(f"pm disable-user --user 0 {pkg}", erro=True)
    if "disabled" in out3:
        quarentena.registrar(pasta, "desativado")
        return True, "desativado (não foi possível desinstalar)"
    return False, f"falhou: {out or out2 or out3}"
