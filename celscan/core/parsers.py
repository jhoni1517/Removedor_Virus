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
            cur = pkgs.setdefault(m.group(1), {"perms": set(), "versao": None, "instalado": None,
                                               "atualizado": None, "origem": None, "iniciador": None})
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
        elif s.startswith("lastUpdateTime=") and not cur["atualizado"]:
            cur["atualizado"] = data(s.split("=", 1)[1])
        elif s.startswith(("installOriginatingPackageName=", "installInitiatingPackageName=")):
            if s.startswith("installInitiatingPackageName="):
                ini = s.split("=", 1)[1].strip()
                cur["iniciador"] = None if ini in ("", "null") else ini
            # quem abriu o instalador: Chrome, WhatsApp, gerenciador de arquivos... (Android 11+)
            v = s.split("=", 1)[1].strip()
            if v and v != "null" and "packageinstaller" not in v and (not cur["origem"] or "Originating" in s):
                cur["origem"] = v
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
        "temperatura": f"{int(temp) / 10:.1f} °C" if temp.lstrip("-").isdecimal() else None,
        "tensao": f"{int(volt) / 1000:.2f} V" if volt.isdecimal() else None,
        "ciclos": b.get("cycle count") or b.get("battery cycle count") or b.get("mbatterycyclecount"),
    }


def saude_bateria(txt: str) -> dict[str, int] | None:
    """Capacidade real e desgaste da bateria a partir de vários medidores do /sys.

    Aceita 'medidor.campo=valor' (ex.: bms.charge_full_design=5000000) e também o formato antigo
    'campo=valor'. Para a saúde, usa o primeiro medidor que informa a capacidade real E a de fábrica;
    para os ciclos, o maior valor plausível encontrado (cada fabricante guarda num medidor diferente).
    """
    medidores: dict[str, dict[str, int]] = {}
    for nome, campo, val in re.findall(r"^(?:(\w+)\.)?(\w+)=(-?\d+)\s*$", txt, re.M):
        medidores.setdefault(nome or "battery", {})[campo] = int(val)
    res: dict[str, int] = {}
    for v in medidores.values():
        full, design = v.get("charge_full"), v.get("charge_full_design")
        if full and design and design > 0:
            res["saude_pct"] = round(full / design * 100)
            res["capacidade_mah"] = round(full / 1000)
            res["capacidade_projeto_mah"] = round(design / 1000)
            break
    ciclos = [v[c] for v in medidores.values() for c in ("cycle_count", "battery_cycle") if v.get(c, -1) >= 0]
    if ciclos:
        res["ciclos"] = max(ciclos)
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


# ---------------------------------------------------------------- uso, anúncios, sensores e rede

def duracao(txt: str | None) -> float:
    """'1d2h3m4s500ms' -> segundos."""
    mult = {"d": 86400, "h": 3600, "m": 60, "s": 1, "ms": 0.001}
    return sum(int(n) * mult[u] for n, u in re.findall(r"(\d+)(ms|d|h|m|s)", txt or ""))


def appops_tempos(txt: str, interesse: set[str]) -> dict[str, dict[str, float]]:
    """Blocos '@@PKG' + `cmd appops get` -> {pacote: {OP: segundos desde o último uso}}.

    Aceita o formato antigo ("OP: allow; time=+1h2m ago") e o do Android 11+
    (bloco com "Access: [fg-s] 2026-10-10 09:00:00.000 (-3h2m10s)")."""
    res: dict[str, dict[str, float]] = {}
    pkg_atual: dict[str, float] | None = None
    op: str | None = None
    for linha in txt.splitlines():
        if linha.startswith("@@PKG "):
            pkg_atual, op = res.setdefault(linha[6:].strip(), {}), None
            continue
        if pkg_atual is None:
            continue
        m = re.match(r"^\s*(?:Uid mode:\s*)?([A-Z_]{3,}):\s*(\w+)(.*)$", linha)
        if m:
            op = m.group(1) if m.group(1) in interesse else None
            t = re.search(r"\btime=\+(\S+?) ago", m.group(3))
            if op and t:
                pkg_atual[op] = min(pkg_atual.get(op, 1e12), duracao(t.group(1)))
            continue
        if op and "Access:" in linha:
            t = re.search(r"\(-([0-9dhms]+)\)", linha)
            if t:
                pkg_atual[op] = min(pkg_atual.get(op, 1e12), duracao(t.group(1)))
    return {p: v for p, v in res.items() if v}


EVENTO = re.compile(r'time="([^"]+)"\s+type=(ACTIVITY_RESUMED|MOVE_TO_FOREGROUND|NOTIFICATION_INTERRUPTION)'
                    r'\s+package=(\S+)(?:\s+class=(\S+))?')


def uso(txt: str) -> tuple[list[tuple[datetime, str, str]], dict[str, datetime], dict[str, int]]:
    """Trecho de `dumpsys usagestats` -> (telas abertas em ordem, último uso por app, notificações por app)."""
    telas, notif, ultimo = set(), {}, {}
    vistas_notif = set()
    for linha in txt.splitlines():
        m = EVENTO.search(linha)
        if m:
            t = data(m.group(1)[:19])
            if not t:
                continue
            if m.group(2) == "NOTIFICATION_INTERRUPTION":
                if (t, m.group(3)) not in vistas_notif:  # o dump repete eventos em intervalos diferentes
                    vistas_notif.add((t, m.group(3)))
                    notif[m.group(3)] = notif.get(m.group(3), 0) + 1
            else:
                telas.add((t, m.group(3), m.group(4) or ""))
            continue
        m = re.search(r'package=(\S+).*?lastTimeUsed="([^"]+)"', linha)
        if m:
            t = data(m.group(2)[:19])
            if t and t.year > 2000 and (m.group(1) not in ultimo or t > ultimo[m.group(1)]):
                ultimo[m.group(1)] = t
    return sorted(telas), ultimo, notif


def periodo_eventos(txt: str) -> tuple[datetime, datetime] | None:
    """Primeiro e último evento do usagestats (telas E notificações): base para 'por dia'.

    Antes o período vinha só das telas; num aparelho com poucas telas registradas e muitas notificações
    o período virava 1 dia e qualquer app comum parecia mandar notificação em excesso.
    """
    ts = [t for m in EVENTO.finditer(txt) if (t := data(m.group(1)[:19]))]
    return (min(ts), max(ts)) if ts else None


def anuncios(telas: list[tuple[datetime, str, str]], sdk_de, janela_s: int = 120) -> dict[str, dict]:
    """Conta anúncios em tela cheia por app e os que surgiram por cima de outro app (pop-up).

    Pop-up = a tela de anúncio apareceu vindo de OUTRO app (tela inicial, outro app) e a pessoa NÃO entrou no
    app em seguida. O anúncio de abertura ("app open"), que aparece quando a própria pessoa toca no ícone do
    jogo e logo depois cai na tela do jogo, não conta: antes isso marcava jogos comuns como adware."""
    res: dict[str, dict] = {}
    for i, (t, pkg, classe) in enumerate(telas):
        sdk = sdk_de(classe) if classe else None
        if not sdk:
            continue
        r = res.setdefault(pkg, {"tela_cheia": 0, "fora_do_app": 0, "ultimo": None, "sdks": set(),
                                 "abertura": 0})
        r["tela_cheia"] += 1
        r["sdks"].add(sdk)
        r["ultimo"] = max(r["ultimo"], t) if r["ultimo"] else t
        anterior = telas[i - 1][1] if i > 0 else None
        if not anterior or anterior == pkg:
            continue
        seguinte = next(((t2, p2, c2) for t2, p2, c2 in telas[i + 1:] if not (p2 == pkg and sdk_de(c2 or ""))), None)
        entrou_no_app = (seguinte is not None and seguinte[1] == pkg
                         and (seguinte[0] - t).total_seconds() <= janela_s)
        if entrou_no_app:
            r["abertura"] += 1  # anúncio de abertura: a pessoa abriu o app
        else:
            r["fora_do_app"] += 1
    return res


def rede(txt: str) -> dict[str, object]:
    """Seção 'rede' do script: DNS privado, VPN sempre ativa e VPN conectada."""
    linhas = [linha.strip() for linha in txt.splitlines()] + ["", "", "", ""]
    limpo = [("" if v in ("null", "") else v) for v in linhas[:4]]
    return {"dns_modo": limpo[0], "dns_servidor": limpo[1], "vpn_sempre": limpo[2],
            "vpn_ativa": limpo[3].isdecimal() and int(limpo[3]) > 0}


def home(txt: str) -> str | None:
    achados = re.findall(r"^\s*([\w.]+)/[\w.$]+\s*$", txt, re.M)
    return achados[-1] if achados else None


def teclado(txt: str) -> str | None:
    """'com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME' -> pacote do teclado."""
    v = (txt or "").strip().splitlines()[0].strip() if (txt or "").strip() else ""
    pkg = v.split("/")[0]
    return pkg if pkg and pkg != "null" and re.fullmatch(r"[\w.]+", pkg) else None



# ---------------------------------------------------------------- 3.3: usuários, APKs guardados, uso e bateria

def usuarios(txt: str) -> list[dict[str, object]]:
    """`pm list users` -> [{id, nome, ativo}] ("UserInfo{10:Trabalho:1030} running")."""
    res = []
    for uid, nome, _flags, resto in re.findall(r"UserInfo\{(\d+):([^:}]*):?([0-9a-fA-F]*)\}(.*)", txt):
        res.append({"id": int(uid), "nome": nome.strip() or f"Usuário {uid}", "ativo": "running" in resto})
    return res


def pacotes_por_usuario(txt: str) -> dict[int, dict[str, str | None]]:
    """Blocos '@@USER n' + `pm list packages -3 -i --user n` -> {n: {pacote: instalador}}."""
    res: dict[int, dict[str, str | None]] = {}
    atual: dict[str, str | None] | None = None
    for linha in txt.splitlines():
        if linha.startswith("@@USER "):
            n = linha[7:].strip()
            atual = res.setdefault(int(n), {}) if n.isdecimal() else None
            continue
        m = re.match(r"^package:([\w.]+)(?:\s+installer=(\S+))?", linha.strip())
        if m and atual is not None:
            atual[m.group(1)] = None if m.group(2) in (None, "null") else m.group(2)
    return res


def apks_guardados(txt: str) -> list[dict[str, object]]:
    """Linhas 'tamanho<TAB>sha256<TAB>caminho' -> [{caminho, tamanho, sha256}]."""
    res = []
    for linha in txt.splitlines():
        partes = linha.split("\t", 2)
        if len(partes) == 3 and partes[2].startswith("/") and partes[2].lower().endswith(".apk"):
            sha = partes[1] if re.fullmatch(r"[0-9a-f]{64}", partes[1]) else None
            res.append({"caminho": re.sub(r"/{2,}", "/", partes[2]),
                        "tamanho": int(partes[0]) if partes[0].isdecimal() else None,
                        "sha256": sha})
    return res


def rodando(txt: str) -> set[str]:
    """`ps -A -o NAME` -> pacotes com processo vivo (processos 'pkg:servico' contam para o pacote)."""
    res = set()
    for linha in txt.splitlines():
        nome = linha.strip().split()[-1] if linha.strip() else ""
        nome = nome.split(":")[0]
        if "." in nome and re.fullmatch(r"[A-Za-z0-9_.]+", nome):
            res.add(nome)
    return res


def relogio(txt: str) -> int | None:
    """`date +%s` do aparelho (para corrigir 'há X minutos' quando o relógio do PC está diferente)."""
    v = (txt or "").strip().splitlines()
    return int(v[0]) if v and v[0].strip().isdecimal() else None


def _hms(txt: str) -> int:
    """'01:02:03', '02:03' ou '1d 02:03:04' -> segundos."""
    dias = 0
    m = re.match(r"^\s*(\d+)d\s+(.*)$", txt or "")
    if m:
        dias, txt = int(m.group(1)), m.group(2)
    partes = [int(x) for x in re.findall(r"\d+", txt or "")]
    seg = 0
    for x in partes[-3:]:
        seg = seg * 60 + x
    return dias * 86400 + seg


def tempo_de_uso(txt: str) -> dict[str, int]:
    """Tempo de tela por app (s) do intervalo semanal do `dumpsys usagestats` (diário se não houver)."""
    blocos: dict[str, dict[str, int]] = {}
    atual = "diario"
    for linha in txt.splitlines():
        m = re.search(r"In-memory (daily|weekly|monthly|yearly) stats", linha)
        if m:
            atual = {"daily": "diario", "weekly": "semanal", "monthly": "mensal", "yearly": "anual"}[m.group(1)]
            continue
        m = re.search(r'package=(\S+)\s+totalTimeUsed="([^"]+)"', linha)
        if m:
            b = blocos.setdefault(atual, {})
            b[m.group(1)] = max(b.get(m.group(1), 0), _hms(m.group(2)))
    return blocos.get("semanal") or blocos.get("diario") or {}


def bateria_por_app(txt: str) -> dict[str, float]:
    """`dumpsys batterystats --checkin`: linhas 'pwi' (uso de energia em mAh por uid) -> {pacote: mAh}."""
    pacotes: dict[str, list[str]] = {}
    gasto: dict[str, float] = {}
    for linha in txt.splitlines():
        p = linha.strip().split(",")
        if len(p) >= 6 and p[2] == "i" and p[3] == "uid":
            pacotes.setdefault(p[4], []).append(p[5])
        elif len(p) >= 6 and p[2] == "l" and p[3] == "pwi" and p[4] == "uid":
            try:
                gasto[p[1]] = gasto.get(p[1], 0.0) + float(p[5])
            except ValueError:
                continue
    res: dict[str, float] = {}
    for uid, mah in gasto.items():
        for pkg in pacotes.get(uid, []):
            res[pkg] = round(mah, 1)
    return res
