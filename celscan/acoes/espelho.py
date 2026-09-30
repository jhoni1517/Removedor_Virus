"""Espelhamento e controle da tela pelo PC com o scrcpy (embutido no instalador).

Modos:
- "controlar": vê a tela e usa mouse/teclado do PC no celular (precisa da depuração USB autorizada);
- "ver": só vê a tela, sem mexer (bom para mostrar ao cliente);
- "otg": o PC vira mouse e teclado USB do celular, SEM depuração USB e SEM imagem. Serve para quem
  tem o toque quebrado mas ainda enxerga a tela: dá para desbloquear, ligar a depuração e tocar em
  "Permitir" usando o mouse do computador.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from celscan.config import recursos
from celscan.core import adb
from celscan.core.adb import SEM_JANELA
from celscan.core.log import LOGGER

MODOS = ("controlar", "ver", "otg")


class EspelhoErro(Exception):
    pass


def localizar() -> str | None:
    """scrcpy: CELSCAN_SCRCPY, embutido no programa ou no PATH."""
    nome = "scrcpy.exe" if os.name == "nt" else "scrcpy"
    for c in (os.getenv("CELSCAN_SCRCPY"), str(recursos() / "scrcpy" / nome), shutil.which("scrcpy")):
        if c and os.path.isfile(c):
            return c
    return None


@dataclass
class OpcoesEspelho:
    modo: str = "controlar"
    tela_desligada: bool = False  # desliga a tela do celular enquanto espelha (economiza bateria, tela queimada)
    acordado: bool = True  # não deixa o celular dormir com o cabo ligado
    gravar: str | None = None  # caminho .mp4 para gravar a tela
    tamanho_max: int = 0  # 0 = resolução do celular; ex.: 1280 para PCs mais fracos


@dataclass
class Sessao:
    serial: str | None
    modo: str
    processo: subprocess.Popen = field(repr=False)
    comando: list[str] = field(default_factory=list)

    @property
    def ativa(self) -> bool:
        return self.processo.poll() is None


def montar_comando(scrcpy: str, serial: str | None, o: OpcoesEspelho) -> list[str]:
    if o.modo not in MODOS:
        raise ValueError(f"modo inválido: {o.modo}")
    cmd = [scrcpy, "--window-title", "CelScan - tela do celular"]
    if o.modo == "otg":
        cmd.append("--otg")  # mouse/teclado USB (HID) sem depuração; não tem imagem
        if serial:
            cmd += ["--serial", serial]
        return cmd
    if serial:
        cmd += ["--serial", serial]
    if o.modo == "ver":
        cmd.append("--no-control")
    else:
        if o.tela_desligada:
            cmd.append("--turn-screen-off")
        if o.acordado:
            cmd.append("--stay-awake")
    if o.gravar:
        cmd += ["--record", o.gravar]
    if o.tamanho_max:
        cmd += ["--max-size", str(o.tamanho_max)]
    return cmd


class Espelhos:
    """Uma sessão de espelhamento por aparelho."""

    def __init__(self) -> None:
        self._sessoes: dict[str, Sessao] = {}
        self._trava = threading.Lock()

    def abrir(self, serial: str | None, opcoes: OpcoesEspelho) -> Sessao:
        scrcpy = localizar()
        if not scrcpy:
            raise EspelhoErro("O scrcpy não foi encontrado. Ele vem no instalador do CelScan para Windows; "
                              "em outro sistema, instale o scrcpy.")
        chave = serial or "otg"
        with self._trava:
            atual = self._sessoes.get(chave)
            if atual and atual.ativa:
                raise EspelhoErro("A tela deste celular já está aberta em outra janela.")
            if opcoes.gravar:
                Path(opcoes.gravar).parent.mkdir(parents=True, exist_ok=True)
            cmd = montar_comando(scrcpy, serial, opcoes)
            if scrcpy.endswith(".py"):  # scrcpy simulado dos testes
                cmd = [sys.executable, *cmd]
            env = dict(os.environ)
            caminho_adb = adb.localizar()
            if caminho_adb and not caminho_adb.endswith(".py"):
                env["ADB"] = caminho_adb  # o scrcpy usa o mesmo adb do CelScan
            LOGGER.info("scrcpy: %s", " ".join(cmd))
            try:
                p = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     creationflags=SEM_JANELA)
            except OSError as e:
                raise EspelhoErro(f"Não foi possível abrir o scrcpy: {e}") from e
            sessao = Sessao(serial, opcoes.modo, p, cmd)
            self._sessoes[chave] = sessao
        return sessao

    def erro_inicial(self, sessao: Sessao, espera: float = 2.0) -> str | None:
        """Se o scrcpy fechar logo ao abrir, devolve a mensagem de erro dele."""
        try:
            sessao.processo.wait(timeout=espera)
        except subprocess.TimeoutExpired:
            return None
        saida = (sessao.processo.stderr.read() if sessao.processo.stderr else b"") or b""
        texto = saida.decode("utf-8", "replace").strip().splitlines()
        erros = [linha for linha in texto if "ERROR" in linha or "error" in linha] or texto[-3:]
        return " / ".join(erros)[-500:] or f"o scrcpy fechou (código {sessao.processo.returncode})"

    def parar(self, serial: str | None) -> bool:
        with self._trava:
            s = self._sessoes.pop(serial or "otg", None)
        if s and s.ativa:
            s.processo.terminate()
            return True
        return False

    def ativas(self) -> list[dict[str, str | None]]:
        with self._trava:
            return [{"serial": s.serial, "modo": s.modo} for s in self._sessoes.values() if s.ativa]

    def parar_todas(self) -> None:
        for chave in list(self._sessoes):
            self.parar(None if chave == "otg" else chave)
