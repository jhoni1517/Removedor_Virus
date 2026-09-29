"""Coleta dados dos apps instalados no celular e avalia o risco de cada um."""

from __future__ import annotations

import re
from typing import Callable

from .adb import ADB
from .heuristicas import App, Assinaturas, avaliar, carregar_assinaturas
from .virustotal import ErroVirusTotal, consultar_hash

RE_COMPONENTE = re.compile(r"ComponentInfo\{([\w.]+)/([\w.$]+)\}")
RE_PACOTE = re.compile(r"^[A-Za-z][\w]*(\.[\w]+)+$")
RE_LAUNCHER = re.compile(r"packageName=([\w.]+)|^\s*([\w.]+)/[\w.$]+\s*$")
RE_PERMISSAO = re.compile(r"^([\w.]+\.[\w.]+)(:.*)?$")
RE_CONCEDIDA = re.compile(r"([\w.]+\.permission\.[\w]+): granted=true")
RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")

Progresso = Callable[[int, int, str], None]


def parse_lista_pacotes(saida: str) -> dict[str, tuple[str, str | None]]:
    """Lê `pm list packages -f -i` -> {pacote: (caminho_apk, instalador)}."""
    pacotes: dict[str, tuple[str, str | None]] = {}
    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha.startswith("package:"):
            continue
        corpo, _, instalador = linha[len("package:"):].partition(" installer=")
        caminho, _, pacote = corpo.strip().rpartition("=")
        instalador = instalador.strip()
        pacotes[pacote] = (caminho, None if instalador in ("", "null") else instalador)
    return pacotes


def parse_componentes(saida: str) -> list[str]:
    """Extrai componentes `pacote/classe` de saídas como `dumpsys device_policy`."""
    vistos: list[str] = []
    for pacote, classe in RE_COMPONENTE.findall(saida):
        componente = f"{pacote}/{classe}"
        if componente not in vistos:
            vistos.append(componente)
    return vistos


def parse_sha256(saida: str) -> str:
    partes = saida.split()
    return partes[0] if partes and RE_SHA256.match(partes[0]) else ""


def parse_acessibilidade(saida: str) -> list[str]:
    valor = saida.strip()
    if not valor or valor == "null":
        return []
    return [c for c in valor.split(":") if "/" in c]


def parse_lista_simples(saida: str) -> set[str]:
    """Uma linha por pacote (ex.: `appops query-op`); ignora mensagens de erro."""
    return {linha.strip() for linha in saida.splitlines() if RE_PACOTE.match(linha.strip())}


def parse_launchers(saida: str) -> set[str]:
    pacotes = set()
    for linha in saida.splitlines():
        achado = RE_LAUNCHER.search(linha)
        if achado:
            pacotes.add(achado.group(1) or achado.group(2))
    return pacotes


def parse_dumpsys_pacote(saida: str) -> dict:
    """Extrai versão, data de instalação e permissões de `dumpsys package <pacote>`."""
    info = {"versao": "", "instalado_em": "", "permissoes": set(), "concedidas": set(RE_CONCEDIDA.findall(saida))}
    na_secao = False
    for linha in saida.splitlines():
        texto = linha.strip()
        if texto.startswith("versionName=") and not info["versao"]:
            info["versao"] = texto.split("=", 1)[1]
        elif texto.startswith("firstInstallTime=") and not info["instalado_em"]:
            info["instalado_em"] = texto.split("=", 1)[1]
        elif texto == "requested permissions:":
            na_secao = True
        elif na_secao:
            achado = RE_PERMISSAO.match(texto)
            if achado:
                info["permissoes"].add(achado.group(1))
            else:
                na_secao = False
    return info


class Scanner:
    def __init__(self, adb: ADB, assinaturas: Assinaturas | None = None):
        self.adb = adb
        self.assinaturas = assinaturas or carregar_assinaturas()

    def escanear(
        self,
        progresso: Progresso | None = None,
        somente: set[str] | None = None,
        chave_vt: str | None = None,
        vt_todos: bool = False,
    ) -> list[App]:
        """Analisa os apps instalados pelo usuário (apps do sistema não são tocados).

        Com `chave_vt`, consulta no VirusTotal os apps suspeitos (ou todos, se `vt_todos`).
        """
        adb = self.adb
        pacotes = parse_lista_pacotes(adb.shell("pm", "list", "packages", "-3", "-f", "-i"))
        if somente is not None:
            pacotes = {p: v for p, v in pacotes.items() if p in somente}
        admins = parse_componentes(adb.shell("dumpsys", "device_policy"))
        acessibilidade = parse_acessibilidade(
            adb.shell("settings", "get", "secure", "enabled_accessibility_services")
        )
        notificacoes = parse_acessibilidade(
            adb.shell("settings", "get", "secure", "enabled_notification_listeners")
        )
        sobreposicao = parse_lista_simples(
            adb.shell("appops", "query-op", "--user", "0", "SYSTEM_ALERT_WINDOW", "allow")
        )
        launchers = parse_launchers(
            adb.shell(
                "cmd", "package", "query-activities", "--brief",
                "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
            )
        )

        def do_pacote(componentes: list[str], pacote: str) -> list[str]:
            return [c for c in componentes if c.startswith(pacote + "/")]

        apps = []
        for indice, (pacote, (caminho, instalador)) in enumerate(sorted(pacotes.items()), 1):
            if progresso:
                progresso(indice, len(pacotes), f"Analisando {pacote}")
            detalhes = parse_dumpsys_pacote(adb.shell("dumpsys", "package", pacote))
            app = App(
                pacote=pacote,
                caminho_apk=caminho,
                instalador=instalador,
                versao=detalhes["versao"],
                instalado_em=detalhes["instalado_em"],
                permissoes=detalhes["permissoes"],
                concedidas=detalhes["concedidas"],
                admins=do_pacote(admins, pacote),
                acessibilidade=do_pacote(acessibilidade, pacote),
                notificacoes=do_pacote(notificacoes, pacote),
                sobreposicao=pacote in sobreposicao,
                # Se a consulta de launchers falhou (lista vazia), não acusa ninguém.
                icone_oculto=bool(launchers) and pacote not in launchers,
            )
            apps.append(avaliar(app, self.assinaturas))

        if chave_vt:
            self.consultar_virustotal(apps, chave_vt, vt_todos, progresso)

        apps.sort(key=lambda a: a.pontuacao, reverse=True)
        return apps

    def consultar_virustotal(
        self, apps: list[App], chave: str, todos: bool = False, progresso: Progresso | None = None
    ) -> None:
        alvos = [a for a in apps if todos or a.pontuacao > 0]
        for indice, app in enumerate(alvos, 1):
            if progresso:
                progresso(indice, len(alvos), f"VirusTotal: {app.pacote}")
            if not app.sha256 and app.caminho_apk:
                app.sha256 = parse_sha256(self.adb.shell("sha256sum", app.caminho_apk))
            if not app.sha256:
                continue
            try:
                app.virustotal = consultar_hash(app.sha256, chave)
            except ErroVirusTotal as erro:
                app.virustotal = {"erro": str(erro)}
                if "inválida" in str(erro):
                    break
            avaliar(app, self.assinaturas)
