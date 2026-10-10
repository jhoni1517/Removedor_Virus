"""Validações centrais de segurança: tudo que vem de fora (API, arquivo, aparelho) e vai para o shell.

- Nome de pacote: só letras, números, "_" e ".", como o próprio Android exige. Bloqueia injeção de
  comandos em `am force-stop {pkg}`, `pm disable-user {pkg}` etc.
- Apps essenciais: nunca remover/desativar (o celular pode travar na tela inicial ou ficar sem teclado).
- Nomes de app com caracteres invisíveis ou de inversão de texto (truque para disfarçar o nome).
- IDs da quarentena: só um nome de pasta, sem "..", "/" ou "\\".
"""

from __future__ import annotations

import re
import unicodedata

PACOTE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
ID_QUARENTENA = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,150}$")

# Sem estes o aparelho não liga a interface, não telefona, não instala nem digita.
ESSENCIAIS = frozenset({
    "android", "com.android.systemui", "com.android.settings", "com.android.phone", "com.android.server.telecom",
    "com.android.providers.telephony", "com.android.providers.settings", "com.android.providers.contacts",
    "com.android.providers.media", "com.android.providers.media.module", "com.google.android.providers.media.module",
    "com.android.providers.downloads", "com.android.externalstorage", "com.android.packageinstaller",
    "com.google.android.packageinstaller", "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.shell", "com.android.keychain", "com.android.location.fused", "com.android.networkstack",
    "com.google.android.networkstack", "com.android.se", "com.android.bluetooth", "com.android.nfc",
    "com.android.inputmethod.latin", "com.google.android.inputmethod.latin", "com.android.launcher3",
    "com.google.android.apps.nexuslauncher", "com.sec.android.app.launcher", "com.miui.home",
    "com.mi.android.globallauncher",
    "com.motorola.launcher3", "com.google.android.gms", "com.google.android.gsf", "com.android.vending",
    "com.android.wifi.resources", "com.google.android.webview", "com.android.webview", "com.android.mms.service",
    "com.android.certinstaller", "com.android.emergency", "com.google.android.dialer", "com.samsung.android.dialer",
    "com.android.dialer", "com.android.incallui",
})

# Formatação invisível e inversão de direção do texto (ex.: U+202E faz "gpj.exe" parecer "exe.jpg")
INVISIVEIS = re.compile(r"[\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff]")


def pacote_valido(pkg: object) -> bool:
    return isinstance(pkg, str) and 0 < len(pkg) <= 255 and bool(PACOTE.fullmatch(pkg))


def exigir_pacote(pkg: object) -> str:
    """Devolve o pacote se for um nome válido do Android; senão levanta ValueError (nunca chega ao shell)."""
    if not pacote_valido(pkg):
        raise ValueError(f"nome de pacote inválido: {str(pkg)[:60]!r}")
    return pkg  # type: ignore[return-value]


def essencial(pkg: str, extras: set[str] | frozenset[str] | tuple = ()) -> bool:
    """True se remover/desativar este app pode deixar o celular inutilizável."""
    return pkg in ESSENCIAIS or pkg in set(extras)


def id_quarentena_valido(ident: object) -> bool:
    return isinstance(ident, str) and ".." not in ident and bool(ID_QUARENTENA.fullmatch(ident))


def limpar_nome(nome: str | None) -> tuple[str | None, bool]:
    """(nome sem caracteres invisíveis/de controle, True se havia algum truque)."""
    if not nome:
        return nome, False
    truque = bool(INVISIVEIS.search(nome))
    limpo = INVISIVEIS.sub("", nome)
    limpo = "".join(c for c in limpo if unicodedata.category(c)[0] != "C")  # controle (\n, \x00...)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return (limpo or None), truque
