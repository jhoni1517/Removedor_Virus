"""Sobe o backend numa porta local e abre a interface (janela própria ou navegador)."""

from __future__ import annotations

import secrets
import socket
import threading
import time
import webbrowser

import uvicorn

from celscan import config
from celscan.api.app import criar_app
from celscan.core import adb
from celscan.core.log import LOGGER


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def subir(porta: int = 0) -> tuple[uvicorn.Server, str]:
    """Inicia o servidor numa thread e devolve (servidor, url com token)."""
    token = secrets.token_urlsafe(24)
    porta = porta or porta_livre()
    # log_config=None: no programa com janela não existe console para o uvicorn escrever.
    servidor = uvicorn.Server(uvicorn.Config(criar_app(token), host="127.0.0.1", port=porta, log_level="warning",
                                             log_config=None))
    threading.Thread(target=servidor.run, name="celscan-servidor", daemon=True).start()
    for _ in range(200):
        if servidor.started:
            break
        time.sleep(0.05)
    return servidor, f"http://127.0.0.1:{porta}/?t={token}"


def abrir(modo: str = "janela", porta: int = 0) -> None:
    """modo: 'janela' (pywebview; cai para o navegador se não houver) ou 'navegador'."""
    servidor, url = subir(porta)
    LOGGER.info("interface em %s", url.split("?")[0])
    try:
        if modo == "janela":
            try:
                import webview
            except ImportError:
                modo = "navegador"
            else:
                try:
                    webview.create_window("CelScan", url, width=1280, height=820, min_size=(960, 640))
                    webview.start()
                    return
                except Exception:  # ex.: Windows sem o WebView2 -> usa o navegador
                    LOGGER.exception("janela própria indisponível; abrindo no navegador")
                    modo = "navegador"
        webbrowser.open(url)
        print(f"CelScan aberto no navegador: {url}\nFeche com Ctrl+C.")
        while not servidor.should_exit:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        servidor.should_exit = True
        encerrar_adb_embutido()


def encerrar_adb_embutido() -> None:
    """Fecha o servidor do adb que veio com o programa (libera os arquivos para atualizar/desinstalar)."""
    caminho = adb.localizar()
    if caminho and caminho.startswith((str(config.recursos() / "platform-tools"), str(config.DIR))):
        try:
            adb.run(["kill-server"], timeout=10)
        except adb.AdbErro:
            pass
