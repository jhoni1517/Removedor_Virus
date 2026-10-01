#!/usr/bin/env python3
"""ADB simulado para testar sem celular.

Uso: CELSCAN_ADB=testes/fake_adb.py  APK_TESTE=<um .apk>  [CELSCAN_FIXTURE=sintetico]
Responde com as fixtures de testes/fixtures/<CELSCAN_FIXTURE>/ e registra cada comando
em <CELSCAN_FAKE_ESTADO>/comandos.log (padrão: testes/.estado).
"""

import os
import re
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(AQUI, "fixtures", os.getenv("CELSCAN_FIXTURE", "sintetico"))
EST = os.getenv("CELSCAN_FAKE_ESTADO") or os.path.join(AQUI, ".estado")
os.makedirs(EST, exist_ok=True)
APK_REAL = os.getenv("APK_TESTE", "/tmp/fdroid.apk")  # qualquer APK real
PACOTES = ["com.whatsapp", "com.systemservice", "com.x8bit.bitwarden", "com.exemplo.jogo"]


def arquivos_fixture():
    res = {}
    caminho = os.path.join(FIXTURES, "arquivos.txt")
    if os.path.exists(caminho):
        for linha in open(caminho, encoding="utf-8").read().splitlines():
            tam, mtime, arq = linha.split("|", 2)
            res[arq] = (int(tam), mtime)
    return res


def conteudo(arq, tamanho):
    """Conteúdo determinístico de cada arquivo simulado (para conferir hash e tamanho)."""
    base = arq.encode("utf-8") or b"x"
    return (base * (tamanho // len(base) + 1))[:tamanho]


def fixture(nome):
    with open(os.path.join(FIXTURES, nome), encoding="utf-8") as f:
        return f.read()


def fim(texto=""):
    if texto:
        print(texto)
    sys.exit(0)


a = sys.argv[1:]
with open(os.path.join(EST, "comandos.log"), "a", encoding="utf-8") as log:
    log.write(" ".join(a) + "\n")

if a == ["start-server"]:
    fim()
if a == ["track-devices"]:
    lista = os.getenv("CELSCAN_FAKE_DISPOSITIVOS", "ABC123\tdevice\n")
    sys.stdout.write(f"{len(lista):04x}{lista}")
    sys.stdout.flush()
    fim()
if a == ["devices"]:
    lista = os.getenv("CELSCAN_FAKE_DISPOSITIVOS", "ABC123\tdevice\nXYZ\tunauthorized\n")
    fim("* daemon not running; starting now at tcp:5037\nList of devices attached\n" + lista)
if a[0] == "-s":
    a = a[2:]
if a[0] == "push":
    shutil.copy(a[1], os.path.join(EST, "script.sh"))
    fim("1 file pushed")
if a[0] == "pull":
    if a[1] == "-a":
        a = a[1:]
    arquivos = arquivos_fixture()
    with open(a[2], "wb") as f:
        f.write(conteudo(a[1], arquivos[a[1]][0]) if a[1] in arquivos else b"APKFAKE")
    fim(f"{a[1]}: 1 file pulled")
if a[0] in ("install", "install-multiple", "uninstall"):
    fim("Success")
if a[0] == "reboot":
    fim()  # o aparelho reiniciaria e a conexão cairia; aqui só confirmamos que o comando saiu
if a[0] == "exec-out" and "screencap" in a[1]:
    print_real = os.getenv("CELSCAN_FAKE_PRINT")  # PNG de verdade para ver a prévia na interface
    if print_real and os.path.isfile(print_real):
        with open(print_real, "rb") as f:
            sys.stdout.buffer.write(f.read())
    else:
        sys.stdout.buffer.write(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    sys.exit(0)
if a[0] == "exec-out":
    m = re.search(r"dd if=(\S+) bs=(\d+) skip=(\d+) count=(\d+)", a[1])
    bs, sk, ct = int(m.group(2)), int(m.group(3)), int(m.group(4))
    with open(APK_REAL, "rb") as f:
        f.seek(bs * sk)
        sys.stdout.buffer.write(f.read(bs * ct))
    sys.exit(0)
if a[0] == "shell":
    c = " ".join(a[1:])
    if c.startswith("sh /data/local/tmp"):
        with open(os.path.join(EST, "script.sh"), encoding="utf-8") as f:
            script = f.read()
        fim(fixture("coleta.txt" if "pkgdump" in script else "diag.txt"))
    if "-exec stat" in c:
        m = re.search(r"find ('([^']*)'|(\S+)) -type f", c)
        pasta = (m.group(2) or m.group(3)).rstrip("/") + "/"

        def manter(arq):
            a = arq.lower()
            lixo = ".trashed" in a or "/.trash" in a or "recyclebin" in a or "trashbin" in a
            mini = "/.thumbnails/" in a
            if "! -path '*/.thumbnails/*'" in c and mini:  # exclusão do backup
                return False
            if "! -path '*/.trashed*'" in c and lixo:
                return False
            if "! -path '*/.Statuses/*'" in c and "/.statuses/" in a:
                return False
            if "-ipath '*/.thumbnails/*'" in c:  # recuperação: só miniaturas
                return mini
            if ".trashed-*" in c or "recyclebin" in c.lower():  # recuperação: só lixeira
                return lixo
            return True
        for arq, (tam, mtime) in arquivos_fixture().items():
            if arq.startswith(pasta) and manter(arq):
                print(f"{tam}|{mtime}|{arq}")
        fim()
    if "du -sk" in c:
        import shlex as _sh
        m = re.search(r"du -sk (\S+|'[^']*')", c)
        alvo = _sh.split(m.group(1))[0].rstrip("/") + "/" if m else ""
        kb = sum(tam for arq, (tam, _mt) in arquivos_fixture().items() if arq.startswith(alvo)) // 1024
        if kb > 0:
            print(f"{kb}\t{alvo.rstrip('/')}")
        fim()
    if c.startswith("content query --uri"):
        if "/versao" in c:
            fim("Row: 0 versao=1")
        if "/apps" in c:
            fim(fixture("agente_apps.txt"))
        if "/uso" in c:
            fim(fixture("agente_uso.txt"))
        fim("No result found.")
    if c.startswith("pm trim-caches") or c.startswith("rm -rf") or "rm -rf" in c:
        fim()
    if c.startswith("sha256sum "):
        import hashlib
        import shlex
        arq = shlex.split(c)[1]
        arquivos = arquivos_fixture()
        if arq in arquivos:
            fim(f"{hashlib.sha256(conteudo(arq, arquivos[arq][0])).hexdigest()}  {arq}")
        fim(f"sha256sum: {arq}: No such file or directory")
    if c.startswith("pm list packages -3") and "-f" not in c:
        fim("\n".join(f"package:{p}" for p in PACOTES))
    if c.startswith("getprop "):
        chave = c.split()[1]
        m = re.search(r"^\[" + re.escape(chave) + r"\]: \[(.*)\]$", fixture("coleta.txt"), re.M)
        fim(m.group(1) if m else "")
    if "sha256sum" in c:
        tam = os.path.getsize(APK_REAL)
        for pkg, h in zip(PACOTES, "abcd", strict=True):
            print(f"@@H\t{tam}\t{h * 64}\t/data/app/~~X==/{pkg}-Y==/base.apk")
        fim()
    if c.startswith("pm path"):
        fim("package:/data/app/~~X==/" + c.split()[-1] + "-Y==/base.apk")
    # CELSCAN_FAKE_SETTINGS="always_finish_activities=1,zen_mode=2": configurações bagunçadas para a demo
    bagunca = dict(x.split("=", 1) for x in os.getenv("CELSCAN_FAKE_SETTINGS", "").split(",") if "=" in x)
    if c.startswith("settings get ") and c.split()[-1] in bagunca:
        fim(bagunca[c.split()[-1]])
    if c in ("wm density", "wm size") and os.getenv("CELSCAN_FAKE_WM_" + c.split()[1].upper()):
        tipo = c.split()[1]
        fis = "440" if tipo == "density" else "1080x2400"
        fim(f"Physical {tipo}: {fis}\nOverride {tipo}: {os.getenv('CELSCAN_FAKE_WM_' + tipo.upper())}")
    if c.startswith("settings get secure enabled_accessibility"):
        fim("com.systemservice/com.systemservice.Acc:com.x8bit.bitwarden/com.x8bit.bitwarden.Acc")
    if c.startswith("settings get global") and c.endswith("_scale"):
        fim("1.0")
    if c.startswith("df -k"):
        fim("Filesystem 1K-blocks Used Available Use% Mounted on\n"
            "/dev/block/dm-5 115343360 90000000 25343360 78% /data")
    if c.startswith("pm list packages -e"):
        fim("package:com.facebook.appmanager\npackage:com.whatsapp\npackage:com.miui.analytics")
    if c.startswith("appops set") or c.startswith("pm revoke") or c.startswith("pm grant"):
        fim()
    if c.startswith("appops get"):
        fim("SYSTEM_ALERT_WINDOW: allow")
    if c.startswith("am force-stop"):
        fim()
    if "disable-user" in c:
        fim(f"Package {c.split()[-1]} new state: disabled-user")
    if c.startswith("pm enable"):
        fim("Package x new state: enabled")
    if c.startswith("dpm remove-active-admin"):
        fim("Success: Admin removed ComponentInfo{" + c.split()[-1] + "}")
    # ---- teste de desempenho (pontuação): apps, disco, CPU, RAM e câmeras
    if c == "pm list packages":
        fim("\n".join(f"package:{p}" for p in ["com.android.settings", *PACOTES]))
    if c.startswith("cmd package resolve-activity"):
        fim(f"priority=0 preferredOrder=0\n{c.split()[-1]}/.Principal")
    if c.startswith("am start -W"):
        fim("Status: ok\nLaunchState: COLD\nTotalTime: 720\nWaitTime: 740\nComplete")
    if c.startswith("dd if=/dev/zero"):
        fim("67108864 bytes (64 M) copied, 0.6 s, 106 M/s")
    if c.startswith("dd if="):
        fim("67108864 bytes (64 M) copied, 0.2 s, 320 M/s")
    if c == "cat /proc/cpuinfo":
        fim("\n".join(f"processor\t: {i}" for i in range(8)))
    if c.startswith("cat /sys/devices/system/cpu/"):
        fim("1800000\n1800000\n2400000\n2400000\n2400000\n2400000\n2800000\n2800000")
    if c == "head -3 /proc/meminfo":
        fim("MemTotal:        7864320 kB\nMemFree:          512000 kB\nMemAvailable:    3145728 kB")
    if c.startswith("dumpsys media.camera"):
        fim("Camera 0 information:\n  Facing: BACK\n  Resolution: 8000x6000\n"
            "Camera 1 information:\n  Facing: FRONT\n  Resolution: 4000x3000\n"
            "Camera 2 information:\n  Facing: BACK\n  Resolution: 1920x1080")
    fim()
fim()
