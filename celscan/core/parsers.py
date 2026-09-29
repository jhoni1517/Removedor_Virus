"""Leitores das saídas do Android (getprop, pm, dumpsys, settings...).

Só transformam texto em dados; não decidem nada sobre risco.
"""

from __future__ import annotations

import re
from datetime import datetime


def secoes(texto: str) -> dict[str, str]:
    """Divide a saída de um script em seções marcadas com '@@SEC nome'."""
    sec: dict[str, str] = {}
    nome: str | None = None
    buf: list[str] = []
    for linha in texto.replace("\r\n", "\n").split("\n"):
        if linha.startswith("@@SEC "):
            if nome:
                sec[nome] = "\n".join(buf).strip()
            nome, buf = linha[6:].strip(), []
        else:
            buf.append(linha)
    if nome:
        sec[nome] = "\n".join(buf).strip()
    return sec


def data(txt: str | None) -> datetime | None:
    try:
        return datetime.strptime((txt or "").strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def props(txt: str) -> dict[str, str]:
    return dict(re.findall(r"^\[(.+?)\]: \[(.*)\]$", txt, re.M))


def pacotes(txt: str) -> dict[str, tuple[str, str | None]]:
    """`pm list packages -f -i` -> {pacote: (caminho_apk, instalador)}."""
    rx = re.compile(r"^package:(.+\.apk)=([\w.]+)(?:\s+installer=(\S+))?")
    res: dict[str, tuple[str, str | None]] = {}
    for linha in txt.splitlines():
        m = rx.match(linha.strip())
        if m:
            caminho, pkg, inst = m.groups()
            res[pkg] = (caminho, None if inst in (None, "null") else inst)
    return res


def pkgdump(txt: str) -> dict[str, dict]:
    """`dumpsys package packages` -> {pacote: {perms, versao, instalado}}."""
    pkgs: dict[str, dict] = {}
    cur: dict | None = None
    for linha in txt.splitlines():
        m = re.match(r"^\s{2}Package \[([\w.]+)\] \(", linha)
        if m:
            cur = pkgs.setdefault(m.group(1), {"perms": set(), "versao": None, "instalado": None})
            continue
        if cur is None:
            continue
        s = linha.strip()
        if s.startswith("versionName="):
            cur["versao"] = s.split("=", 1)[1]
        elif s.startswith("firstInstallTime="):
            cur["instalado"] = data(s.split("=", 1)[1])
        else:
            m = re.match(r"(android\.permission\.[A-Z0-9_]+): granted=true", s)
            if m:
                cur["perms"].add(m.group(1))
    return pkgs


def admins(txt: str) -> dict[str, list[str]]:
    """`dumpsys device_policy` -> {pacote: [componentes de administrador]}."""
    res: dict[str, list[str]] = {}

    def add(pkg: str, classe: str) -> None:
        comp = f"{pkg}/{classe}"
        if comp not in res.setdefault(pkg, []):
            res[pkg].append(comp)

    for pkg, classe in re.findall(r"ComponentInfo\{([\w.]+)/([\w.$]+)\}", txt):
        add(pkg, classe)
    dentro = False
    for linha in txt.splitlines():  # formato Android 10+
        if "Enabled Device Admins" in linha:
            dentro = True
            continue
        if dentro:
            m = re.match(r"^\s{4}([\w.]+)/([\w.$]+):\s*$", linha)
            if m:
                add(m.group(1), m.group(2))
            elif linha.strip() and not linha.startswith("      "):
                dentro = False
    return res


def componentes(valor: str | None) -> set[str]:
    """'pkg/Classe:pkg2/Classe2' (settings) -> {pkg, pkg2}."""
    if not valor or valor.strip() == "null":
        return set()
    return {c.split("/")[0] for c in valor.strip().split(":") if "/" in c}


def owners(txt: str) -> set[str]:
    return set(re.findall(r"admin=([\w.]+)/", txt))


def launcher(txt: str) -> set[str] | None:
    """Apps com ícone na tela inicial; None se a consulta não funcionou."""
    return set(re.findall(r"^\s*([\w.]+)/", txt, re.M)) or None


def sempre_ativo(txt: str) -> set[str]:
    return set(re.findall(r"^user,([\w.]+),", txt, re.M))


def desativados(txt: str) -> set[str]:
    return set(re.findall(r"^package:([\w.]+)", txt, re.M))


def appops(txt: str, interesse: set[str]) -> dict[str, set[str]]:
    """Blocos '@@PKG pacote' + saída de `cmd appops get` -> {pacote: {ops liberadas}}."""
    res: dict[str, set[str]] = {}
    atual: set[str] | None = None
    for linha in txt.splitlines():
        if linha.startswith("@@PKG "):
            atual = res.setdefault(linha[6:].strip(), set())
        elif atual is not None:
            m = re.match(r"^\s*(\w+): allow", linha)
            if m and m.group(1) in interesse:
                atual.add(m.group(1))
    return res


def linhas_nao_vazias(txt: str) -> list[str]:
    return [linha.strip() for linha in txt.splitlines() if linha.strip()]


def chave_valor(txt: str) -> dict[str, str]:
    return {k.strip().lower(): v.strip() for k, v in re.findall(r"^\s*([^:\n]+):\s*(.+)$", txt, re.M)}
