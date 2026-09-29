"""Remoção de apps maliciosos, quarentena (backup do APK) e restauração."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .adb import ADB, ErroADB, nome_seguro
from .caminhos import pasta_quarentena
from .heuristicas import App
from .scanner import parse_acessibilidade

DNS_ANTIANUNCIOS = "dns.adguard-dns.com"


@dataclass
class Resultado:
    pacote: str
    sucesso: bool = False
    metodo: str = ""  # desinstalado / removido_do_usuario / desativado
    quarentena: str = ""
    etapas: list[str] = field(default_factory=list)


def _falhou(saida: str) -> bool:
    texto = saida.lower()
    return "error" in texto or "exception" in texto or "failure" in texto


class Removedor:
    def __init__(self, adb: ADB, pasta: Path | None = None):
        self.adb = adb
        self.pasta_quarentena = Path(pasta) if pasta else pasta_quarentena()

    # --- neutralização (tira os "poderes" do app antes de remover) ---

    def remover_acessibilidade(self, pacote: str) -> bool:
        atuais = parse_acessibilidade(
            self.adb.shell("settings", "get", "secure", "enabled_accessibility_services")
        )
        restantes = [c for c in atuais if not c.startswith(pacote + "/")]
        if len(restantes) == len(atuais):
            return False
        if restantes:
            self.adb.shell("settings", "put", "secure", "enabled_accessibility_services", ":".join(restantes))
        else:
            self.adb.shell("settings", "delete", "secure", "enabled_accessibility_services")
            self.adb.shell("settings", "put", "secure", "accessibility_enabled", "0")
        return True

    def remover_admin(self, componente: str) -> bool:
        saida = self.adb.shell("dpm", "remove-active-admin", "--user", "0", componente)
        return not _falhou(saida)

    def neutralizar(self, app: App, resultado: Resultado) -> None:
        self.adb.shell("am", "force-stop", app.pacote)
        resultado.etapas.append("app parado")
        self.adb.shell("appops", "set", app.pacote, "SYSTEM_ALERT_WINDOW", "deny")
        resultado.etapas.append("sobreposição (anúncios em tela) bloqueada")
        if self.remover_acessibilidade(app.pacote):
            resultado.etapas.append("acessibilidade desativada")
        for componente in app.admins:
            if self.remover_admin(componente):
                resultado.etapas.append(f"administrador removido: {componente}")
            else:
                resultado.etapas.append(
                    f"não foi possível remover o administrador {componente} "
                    "(remova manualmente em Configurações > Segurança > Apps de administração)"
                )

    # --- quarentena ---

    def quarentena(self, app: App) -> Path:
        """Copia os APKs do app para o computador antes de remover (permite restaurar)."""
        caminhos = [
            linha.strip()[len("package:"):]
            for linha in self.adb.shell("pm", "path", app.pacote).splitlines()
            if linha.strip().startswith("package:")
        ]
        if not caminhos:
            raise ErroADB(f"APK de {app.pacote} não encontrado no celular")
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = self.pasta_quarentena / nome_seguro(self.adb.serial or "") / f"{app.pacote}__{carimbo}"
        destino.mkdir(parents=True, exist_ok=True)
        for caminho in caminhos:
            self.adb.executar("pull", caminho, str(destino / Path(caminho).name), timeout=600)
        info = app.como_dict() | {"data_quarentena": carimbo, "apks": [Path(c).name for c in caminhos]}
        (destino / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
        return destino

    # --- remoção ---

    def desinstalar(self, pacote: str) -> str:
        """Tenta desinstalar; se não der, remove só do usuário; por fim desativa."""
        if "success" in self.adb.shell("pm", "uninstall", pacote).lower():
            return "desinstalado"
        if "success" in self.adb.shell("pm", "uninstall", "-k", "--user", "0", pacote).lower():
            return "removido_do_usuario"
        saida = self.adb.shell("pm", "disable-user", "--user", "0", pacote).lower()
        if "disabled" in saida and not _falhou(saida):
            return "desativado"
        return ""

    def remover(self, app: App, backup: bool = True) -> Resultado:
        resultado = Resultado(app.pacote)
        if backup:
            try:
                resultado.quarentena = str(self.quarentena(app))
                resultado.etapas.append(f"backup salvo em {resultado.quarentena}")
            except (ErroADB, OSError) as erro:
                resultado.etapas.append(f"falha no backup ({erro}); remoção cancelada")
                return resultado
        self.neutralizar(app, resultado)
        resultado.metodo = self.desinstalar(app.pacote)
        resultado.sucesso = bool(resultado.metodo)
        if resultado.sucesso:
            resultado.etapas.append(resultado.metodo.replace("_", " "))
        else:
            resultado.etapas.append("falha ao remover")
            if app.admins:
                # Abre a tela de segurança para o usuário remover o administrador na mão.
                self.adb.shell("am", "start", "-a", "android.settings.SECURITY_SETTINGS")
        return resultado

    # --- restauração ---

    def listar_quarentena(self) -> list[Path]:
        if not self.pasta_quarentena.is_dir():
            return []
        return sorted(p.parent for p in self.pasta_quarentena.glob("*/*/info.json"))

    def restaurar(self, pasta: Path) -> tuple[bool, str]:
        apks = sorted(str(p) for p in Path(pasta).glob("*.apk"))
        if not apks:
            return False, "nenhum APK na pasta"
        comando = "install" if len(apks) == 1 else "install-multiple"
        try:
            saida = self.adb.executar(comando, "-r", *apks, timeout=600)
        except ErroADB as erro:
            return False, str(erro)
        return "success" in saida.lower(), saida.strip()


def dns_antianuncios(adb: ADB, ativar: bool, servidor: str = DNS_ANTIANUNCIOS) -> str:
    """Ativa/desativa o DNS Privado que bloqueia anúncios em todo o celular (Android 9+)."""
    if ativar:
        adb.shell("settings", "put", "global", "private_dns_mode", "hostname")
        adb.shell("settings", "put", "global", "private_dns_specifier", servidor)
    else:
        adb.shell("settings", "put", "global", "private_dns_mode", "opportunistic")
    return adb.shell("settings", "get", "global", "private_dns_mode").strip()
