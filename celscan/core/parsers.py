"""Leitores das saídas do Android (getprop, pm, dumpsys, settings...).

Só transformam texto em dados; não decidem nada sobre risco. São tolerantes às diferenças
entre Android 8-15 e entre fabricantes: quando não reconhecem nada, devolvem vazio/None e
quem chama (core/coleta.py) registra um aviso visível com `indisponivel()`.
"""

from __future__ import annotations

import re
from datetime import datetime

# Mensagens que indicam que o comando não existe ou foi bloqueado neste aparelho.
_ERROS = re.compile(
    r"^\s*(Error:|Exception|java\.lang\.|Unknown command|.*: not found|.*inaccessible or not found|"
    r"Permission Denial|Security exception|Can't find service|cmd: Can't find|/system/bin/sh: )",
    re.I | re.M,
)


def indisponivel(txt: str | None) -> bool:
    """True se a saída está vazia ou é só mensagem de erro."""
    texto = (txt or "").strip()
    if not texto:
        return True
    linhas = [linha for linha in texto.splitlines() if linha.strip()]
    return all(_ERROS.match(linha) for linha in linhas)


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
    """`pm list packages [-f] [-i] [-U]` -> {pacote: (caminho_apk ou "", instalador)}.

    Aceita caminho com '=' (Android 11+: /data/app/~~abc==/pkg-xyz==/base.apk=pkg),
    linhas sem -f e campos extras como uid:.
    """
    res: dict[str, tuple[str, str | None]] = {}
    for linha in txt.splitlines():
        linha = linha.strip()
        if not linha.startswith("package:"):
            continue
        corpo = linha[len("package:"):]
        inst = None
        m = re.search(r"\s+installer=(\S+)", corpo)
        if m:
            inst = m.group(1)
            corpo = corpo[:m.start()] + corpo[m.end():]
        corpo = re.sub(r"\s+uid:\S+", "", corpo).strip()
        caminho, _, pkg = corpo.rpartition("=")
        if not re.fullmatch(r"[\w.]+", pkg):
            continue
        res[pkg] = (caminho, None if inst in (None, "null") else inst)
    return res


def pkgdump(txt: str) -> dict[str, dict]:
    """`dumpsys package packages` -> {pacote: {perms, versao, instalado}}."""
    pkgs: dict[str, dict] = {}
    cur: dict | None = None
    for linha in txt.splitlines():
        m = re.match(r"^\s{1,4}Package \[([\w.]+)\] \(", linha)
        if m:
            # A primeira ocorrência vale (a seção "Hidden system packages" repete nomes).
            cur = pkgs.setdefault(m.group(1), {"perms": set(), "versao": None, "instalado": None})
            continue
        if re.match(r"^\S", linha):  # nova seção de primeiro nível (ex.: "Hidden system packages:")
            cur = None
            continue
        if cur is None:
            continue
        s = linha.strip()
        if s.startswith("versionName=") and not cur["versao"]:
            cur["versao"] = s.split("=", 1)[1]
        elif s.startswith("firstInstallTime=") and not cur["instalado"]:
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
    """`dpm list-owners` ("admin=pkg/.Classe,DeviceOwner") ou trecho "Device Owner" do device_policy."""
    res = set(re.findall(r"admin=([\w.]+)/", txt))
    res |= set(re.findall(r"admin=ComponentInfo\{([\w.]+)/", txt))
    return res


def launcher(txt: str) -> set[str] | None:
    """Apps com ícone na tela inicial; None se a consulta não funcionou.

    Aceita --brief ("  pkg/.Classe") e o formato completo ("packageName=pkg").
    """
    if indisponivel(txt):
        return None
    res = set(re.findall(r"^\s*([\w.]+)/[\w.$]+\s*$", txt, re.M))
    res |= set(re.findall(r"packageName=([\w.]+)", txt))
    return res or None


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
            # "OP: allow; time=..." (8-15), "Uid mode: OP: allow" (alguns Samsung/Xiaomi)
            m = re.match(r"^\s*(?:Uid mode:\s*)?(\w+):\s*(\w+)(.*)$", linha)
            if not m or m.group(1) not in interesse:
                continue
            # liberada ("allow") ou usada recentemente ("time=..."), como a captura de tela
            if m.group(2) == "allow" or (m.group(1) == "PROJECT_MEDIA" and "time=" in m.group(3)):
                atual.add(m.group(1))
    return res


def appops_indisponivel(txt: str) -> bool:
    """True se nenhum app devolveu saída reconhecível de appops."""
    corpos: list[str] = []
    for linha in txt.splitlines():
        if linha.startswith("@@PKG "):
            corpos.append("")
        elif corpos:
            corpos[-1] += linha + "\n"
    if not corpos:
        return True
    reconhecido = re.compile(r"^\s*((?:Uid mode:\s*)?[A-Z_]+:\s*(allow|ignore|deny|default|foreground|errored)\b"
                             r"|No operations\.)", re.M)
    return not any(reconhecido.search(c) for c in corpos)


def linhas_nao_vazias(txt: str) -> list[str]:
    return [linha.strip() for linha in txt.splitlines() if linha.strip()]


def chave_valor(txt: str) -> dict[str, str]:
    return {k.strip().lower(): v.strip() for k, v in re.findall(r"^\s*([^:\n]+):\s*(.+)$", txt, re.M)}


# ---------------------------------------------------------------- diagnóstico (otimização)

SAUDE_BATERIA = {"1": "desconhecida", "2": "boa", "3": "superaquecida", "4": "morta",
                 "5": "sobretensão", "6": "falha", "7": "fria"}
STATUS_BATERIA = {"1": "desconhecido", "2": "carregando", "3": "descarregando",
                  "4": "sem carregar", "5": "cheia"}


def bateria(txt: str) -> dict[str, str | None] | None:
    """`dumpsys battery` -> nível, saúde, temperatura, tensão, ciclos (quando o fabricante informa)."""
    b = chave_valor(txt)
    if "level" not in b:
        return None
    temp, volt = b.get("temperature", ""), b.get("voltage", "")
    return {
        "nivel": b.get("level"),
        "saude": SAUDE_BATERIA.get(b.get("health", ""), b.get("health")),
        "situacao": STATUS_BATERIA.get(b.get("status", ""), b.get("status")),
        "temperatura": f"{int(temp) / 10:.1f} °C" if temp.lstrip("-").isdigit() else None,
        "tensao": f"{int(volt) / 1000:.2f} V" if volt.isdigit() else None,
        "ciclos": b.get("cycle count") or b.get("battery cycle count") or b.get("mbatterycyclecount"),
    }


def saude_bateria(txt: str) -> dict[str, int] | None:
    """Lê charge_full/charge_full_design/cycle_count do /sys: capacidade real e desgaste da bateria."""
    v: dict[str, int] = {}
    for k, val in re.findall(r"^(\w+)=(-?\d+)\s*$", txt, re.M):
        v[k] = int(val)
    full, design = v.get("charge_full"), v.get("charge_full_design")
    res: dict[str, int] = {}
    if full and design and design > 0:
        res["saude_pct"] = round(full / design * 100)
        res["capacidade_mah"] = round(full / 1000)
        res["capacidade_projeto_mah"] = round(design / 1000)
    if "cycle_count" in v and v["cycle_count"] >= 0:
        res["ciclos"] = v["cycle_count"]
    return res or None


# Nome curto que a interface, a CLI e o laudo usam para cada propriedade do Android.
_IDENT_CURTO = {
    "ro.product.manufacturer": "manufacturer", "ro.product.model": "model",
    "ro.product.marketname": "marketname", "ro.serialno": "serial",
    "ro.build.version.release": "release", "ro.build.version.security_patch": "security_patch",
}


def identificacao(txt: str) -> dict[str, str]:
    """Pares chave=valor da seção 'ident' (getprop rotulado), com nomes curtos (model, release...)."""
    return {_IDENT_CURTO.get(k, k): val.strip() for k, val in re.findall(r"^([\w.]+)=(.*)$", txt, re.M)
            if val.strip()}


def imei(txt: str) -> str | None:
    """Extrai os dígitos do IMEI da saída de `service call iphonesubinfo` (parcel em hex com texto UTF-16)."""
    chars = "".join(re.findall(r"'([^']*)'", txt))
    digitos = re.sub(r"\D", "", chars)
    return digitos if 14 <= len(digitos) <= 17 else None


def df(txt: str) -> dict[str, float] | None:
    """`df -k /data` -> total/livre em GB (aceita linha quebrada em duas)."""
    numeros = re.findall(r"(\d+)\s+(\d+)\s+(\d+)\s+\d+%", txt)
    if not numeros:
        return None
    total, _usado, livre = (int(x) for x in numeros[-1])
    return {"total_gb": total / 1048576, "livre_gb": livre / 1048576}


def livre_kb(txt: str) -> int | None:
    numeros = re.findall(r"(\d+)\s+(\d+)\s+(\d+)\s+\d+%", txt)
    return int(numeros[-1][2]) if numeros else None


def meminfo(txt: str) -> dict[str, float] | None:
    m = chave_valor(txt)
    try:
        total = int(m["memtotal"].split()[0])
        disp = int((m.get("memavailable") or m["memfree"]).split()[0])
    except (KeyError, ValueError, IndexError):
        return None
    return {"total_gb": total / 1048576, "disponivel_gb": disp / 1048576}


def uptime_dias(txt: str) -> float | None:
    try:
        return float(txt.split()[0]) / 86400
    except (ValueError, IndexError):
        return None


def tamanhos_pastas(txt: str) -> dict[str, int]:
    """Saída de `du -sk` -> {pasta: kB}."""
    res = {}
    for linha in txt.splitlines():
        m = re.match(r"^(\d+)\s+(.+)$", linha.strip())
        if m:
            res[m.group(2)] = int(m.group(1))
    return res
