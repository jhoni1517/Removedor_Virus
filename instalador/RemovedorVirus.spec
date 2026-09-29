# Gera dist/RemovedorVirus/ com o executável. Uso: pyinstaller instalador/RemovedorVirus.spec
import sys
from pathlib import Path

raiz = Path(SPECPATH).parent
platform_tools = raiz / "platform-tools"
arquivos_adb = (
    ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "NOTICE.txt"]
    if sys.platform == "win32" else ["adb", "NOTICE.txt"]
)

datas = [
    (str(raiz / "removedor_virus" / "dados" / "assinaturas.json"), "removedor_virus/dados"),
    (str(raiz / "assets" / "icone.ico"), "assets"),
]
# ADB oficial embutido (baixe antes com: python -m removedor_virus baixar-adb --destino .)
datas += [(str(platform_tools / nome), "platform-tools") for nome in arquivos_adb if (platform_tools / nome).exists()]

a = Analysis(
    [str(raiz / "instalador" / "iniciar_app.py")],
    pathex=[str(raiz)],
    datas=datas,
    excludes=["unittest", "pydoc", "PIL", "numpy"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RemovedorVirus",
    console=False,
    icon=str(raiz / "assets" / "icone.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RemovedorVirus", upx=False)
