"""Driver USB do celular no Windows — a causa nº 1 de "o aparelho não aparece".

No Windows, lista os dispositivos USB, reconhece os de fabricantes de celular pelo VID e avisa
quando um está com problema de driver (status diferente de OK). Também entrega o link do driver
certo. Fora do Windows, não faz nada (Linux/macOS usam regras udev/nativo).
"""

from __future__ import annotations

import os
import re
import subprocess

# VID (fabricante) -> (nome, link do driver). 18D1 = Google (driver genérico serve para quase tudo).
FABRICANTES: dict[str, tuple[str, str]] = {
    "18D1": ("Google", "https://developer.android.com/studio/run/win-usb"),
    "04E8": ("Samsung", "https://developer.samsung.com/mobile/android-usb-driver.html"),
    "22B8": ("Motorola", "https://www.motorola.com/us/device-software-and-drivers"),
    "2717": ("Xiaomi", "https://developer.android.com/studio/run/win-usb"),
    "2A70": ("OnePlus/Oppo/Realme", "https://developer.android.com/studio/run/win-usb"),
    "22D9": ("Oppo", "https://developer.android.com/studio/run/win-usb"),
    "12D1": ("Huawei", "https://consumer.huawei.com/en/support/hisuite/"),
    "2A45": ("Meizu", "https://developer.android.com/studio/run/win-usb"),
    "0FCE": ("Sony", "https://developer.sony.com/develop/drivers/"),
    "1004": ("LG", "https://developer.android.com/studio/run/win-usb"),
    "0BB4": ("HTC", "https://developer.android.com/studio/run/win-usb"),
    "2916": ("Asus", "https://www.asus.com/support/"),
    "GENERICO": ("driver genérico do Android (Google)", "https://developer.android.com/studio/run/win-usb"),
}

# Powershell devolve linhas "InstanceId; Status" separadas por ";" (ver montar_comando).
_PS = ("Get-PnpDevice -Class USB,AndroidUsbDeviceClass,WPD -ErrorAction SilentlyContinue | "
       "ForEach-Object { \"$($_.InstanceId);$($_.Status)\" }")


def _saida_windows() -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", _PS],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def analisar(saida: str) -> list[dict[str, object]]:
    """Parser da saída (InstanceId;Status). Devolve os dispositivos de celular com problema de driver."""
    problemas = []
    for linha in saida.splitlines():
        if ";" not in linha:
            continue
        inst, _, status = linha.partition(";")
        m = re.search(r"VID_([0-9A-Fa-f]{4})", inst)
        if not m:
            continue
        vid = m.group(1).upper()
        if vid not in FABRICANTES:
            continue
        if status.strip().upper() not in ("OK", ""):  # Error, Unknown, Degraded... = driver ruim
            nome, link = FABRICANTES[vid]
            problemas.append({"fabricante": nome, "vid": vid, "status": status.strip(), "link": link})
    return problemas


def diagnosticar() -> dict[str, object]:
    """No Windows, procura celular com driver com problema. Devolve {windows, problemas, link_generico}."""
    if os.name != "nt":
        return {"windows": False, "problemas": [], "link_generico": FABRICANTES["GENERICO"][1]}
    return {"windows": True, "problemas": analisar(_saida_windows()),
            "link_generico": FABRICANTES["GENERICO"][1]}
