"""Remoção de apps com cópia na quarentena."""

from __future__ import annotations

import shlex

from celscan.acoes import quarentena
from celscan.core.adb import Aparelho
from celscan.core.seguranca import essencial, exigir_pacote


def neutralizar(ap: Aparelho, pkg: str, pasta, admins: list[str]) -> list[str]:
    """Tira os "poderes" do app antes de remover. Tudo fica registrado para desfazer."""
    avisos = []
    exigir_pacote(pkg)
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
        # componentes de classe interna têm "$" (ex.: pkg/.App$Admin): sem aspas o shell apagava o "$Admin"
        out = ap.sh(f"dpm remove-active-admin --user 0 {shlex.quote(comp)}", erro=True)
        if "Success" not in out:
            avisos.append(f"não consegui tirar o administrador {comp} pelo cabo")
    return avisos


def remover(ap: Aparelho, r: dict) -> tuple[bool, str]:
    """Remove o app. O id da quarentena fica em r["quarentena_id"] (para desfazer).

    - App de loja (WhatsApp, banco...): remove só para o usuário mantendo APK e dados (`pm uninstall -k
      --user 0`). Se foi engano, o desfazer devolve tudo, inclusive as conversas.
    - App de fora da loja: desinstala de vez, mas SÓ se a cópia na quarentena foi conferida; sem cópia
      completa, usa a remoção reversível para nunca perder o app sem volta.
    """
    pkg = exigir_pacote(r["pacote"])
    if essencial(pkg) or r.get("essencial"):
        return False, ("não removido: é um app essencial do Android (sem ele o celular pode travar, ficar sem "
                       "tela inicial ou sem teclado)")
    pasta = quarentena.criar(ap, pkg, r, copiar_apk=True)
    r["quarentena_id"] = pasta.name
    avisos = neutralizar(ap, pkg, pasta, r.get("admins") or [])
    tentativas = []

    def fim(ok: bool, acao: str | None, msg: str) -> tuple[bool, str]:
        if acao:
            quarentena.registrar(pasta, acao)
        elif quarentena.tem_ajustes(pasta):
            quarentena.registrar(pasta, "parcial")  # o que já foi tirado (acessibilidade...) pode ser desfeito
            r["parcial"] = True
        else:
            r["quarentena_id"] = None
            quarentena.descartar(pasta)
        return ok, msg

    if not r.get("loja") and quarentena.copia_completa(pasta):
        out = ap.adb("uninstall", pkg, erro=True, timeout=180)
        tentativas.append(out)
        if "Success" in out:
            return fim(True, "removido", "removido (cópia conferida na quarentena)")
    manter = "-k " if r.get("loja") else ""
    out2 = ap.sh(f"pm uninstall {manter}--user 0 {pkg}", erro=True)
    tentativas.append(out2)
    if "Success" in out2:
        texto = ("removido para o usuário, com os dados guardados (o desfazer devolve tudo)" if manter
                 else "removido para o usuário (reversível)")
        return fim(True, "removido_usuario0", texto)
    juntos = " ".join(tentativas)
    if "DEVICE_POLICY" in juntos or "device admin" in juntos.lower():
        ap.sh("am start -a android.settings.SECURITY_SETTINGS")
        return fim(False, None, "bloqueado por ser administrador. Abri as Configurações de Segurança no celular: "
                                "desative o app em 'Apps de administrador' e rode de novo."
                                + (f" ({'; '.join(avisos)})" if avisos else ""))
    out3 = ap.sh(f"pm disable-user --user 0 {pkg}", erro=True)
    if "disabled" in out3:
        return fim(True, "desativado", "desativado (não foi possível desinstalar)")
    return fim(False, None, f"falhou: {(juntos or out3).strip()[:300]}")
