# Gera dist/CelScan/ com CelScan.exe (janela) e celscan-cli.exe (linha de comando).
# Antes: npm run build em celscan/web e python instalador/baixar_dependencias.py
# Uso: pyinstaller --noconfirm instalador/CelScan.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

raiz = Path(SPECPATH).parent
icone = str(raiz / "assets" / "celscan.ico")
web = raiz / "celscan" / "web" / "dist"
if not (web / "index.html").exists():
    raise SystemExit("Compile a interface antes: cd celscan/web && npm ci && npm run build")

datas = [(str(raiz / "celscan" / "dados"), "celscan/dados"), (str(web), "celscan/web/dist")]
adb = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "NOTICE.txt"] if sys.platform == "win32" else ["adb", "NOTICE.txt"]
datas += [(str(raiz / "platform-tools" / n), "platform-tools") for n in adb if (raiz / "platform-tools" / n).exists()]
if (raiz / "scrcpy").is_dir():
    datas.append((str(raiz / "scrcpy"), "scrcpy"))

# uvicorn escolhe loop/protocolos em tempo de execução: lista explícita do que o CelScan usa.
ocultos = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.loops.asyncio", "uvicorn.lifespan.on",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.websockets_impl",
    "celscan.acoes.otimizacao", "celscan.analise.certificados",
]
# A lib websockets usa imports preguiçosos (__getattr__); sem coletar tudo, o WebSocket não sobe no exe
# e a interface fica presa em "Reconectando...". Coleta explícita resolve.
ocultos += collect_submodules("websockets")
excluir = ["tkinter", "unittest", "pydoc", "numpy", "pytest", "cryptography"]  # PIL fica: o reportlab usa

janela = Analysis([str(raiz / "instalador" / "celscan_app.py")], pathex=[str(raiz)], datas=datas,
                  hiddenimports=ocultos, excludes=excluir)
cli = Analysis([str(raiz / "instalador" / "celscan_cli.py")], pathex=[str(raiz)], datas=datas,
               hiddenimports=ocultos, excludes=excluir)

exe_janela = EXE(PYZ(janela.pure), janela.scripts, [], exclude_binaries=True, name="CelScan", console=False,
                 icon=icone, upx=False)
exe_cli = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="celscan-cli", console=True,
              icon=icone, upx=False)
COLLECT(exe_janela, janela.binaries, janela.datas, exe_cli, cli.binaries, cli.datas, name="CelScan", upx=False)
