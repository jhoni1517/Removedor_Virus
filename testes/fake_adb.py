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
APKS = os.getenv("CELSCAN_APKS", "")  # opcional: pasta com <pacote>.apk para cada app ter nome/ícone próprios


def apk_de(pkg):
    alvo = os.path.join(APKS, f"{pkg}.apk") if APKS and pkg else ""
    return alvo if alvo and os.path.exists(alvo) else APK_REAL
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
    pk = re.search(r"/([\w.]+)-Y==/", m.group(1))
    with open(apk_de(pk.group(1) if pk else None), "rb") as f:
        f.seek(bs * sk)
        sys.stdout.buffer.write(f.read(bs * ct))
    sys.exit(0)
if a[0] == "shell":
    c = " ".join(a[1:])
    if c.startswith("sh /data/local/tmp"):
        with open(os.path.join(EST, "script.sh"), encoding="utf-8") as f:
            script = f.read()
        if "sec cpu1" in script:  # Turbo: nota
            fim("@@SEC cpu1\n320\n@@SEC cpun\n410\n@@SEC memoria\n1073741824 bytes (1.0 G) copied, 0.2 s\n"
                "@@SEC gfx\nTotal frames rendered: 900\nJanky frames: 9 (1.00%)\n@@SEC mem\n"
                "MemTotal: 7864320 kB\nMemAvailable: 3145728 kB\n@@SEC bateria\n  level: 80\n  temperature: 341\n"
                "@@SEC fim")
        if "sec features" in script:  # Turbo: ficha
            fim(fixture("turbo_ficha.txt"))
        if "sec dexopt" in script:  # Otimizar: por que trava
            fim("@@SEC df\n/dev/block/dm-50 115000000 106000000 9000000 93% /data\n@@SEC lowpower\n1\n"
                "@@SEC anim\n1.0\n1.0\n1.0\n@@SEC dexopt\n[com.netflix.mediaclient]\n  arm64: [status=verify]\n"
                "[com.android.systemui]\n  arm64: [status=verify]\n[com.whatsapp]\n  arm64: [status=speed-profile]\n"
                "@@SEC ativos\npackage:com.netflix.mediaclient\npackage:com.whatsapp\n@@SEC idle\n@@SEC fim")
        if "policy*" in script:  # Turbo: calor e lentidão
            fim(fixture("turbo_calor.txt"))
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
    if "@@S" in c:  # tamanho + data de modificação (cache incremental de hashes)
        for pkg in PACOTES:
            print(f"@@S\t{os.path.getsize(apk_de(pkg))} 1700000000\t/data/app/~~X==/{pkg}-Y==/base.apk")
        fim()
    if "sha256sum" in c:
        with open(os.path.join(EST, "hashes.log"), "a", encoding="utf-8") as hl:
            hl.write(c + "\n")
        for pkg, h in zip(PACOTES, "abcd", strict=True):
            tam = os.path.getsize(apk_de(pkg))
            # hash muda conforme o APK servido, para o cache de nomes/ícones não misturar apps
            print(f"@@H\t{tam}\t{(h * 56) + format(tam % 2**32, '08x')}\t/data/app/~~X==/{pkg}-Y==/base.apk")
        fim()
    if "dumpsys activity activities" in c:
        fim("  mResumedActivity: ActivityRecord{1 u0 com.exemplo.jogo/com.google.android.gms.ads.AdActivity t9}")
    if "batterystats --checkin" in c:
        fim("9,0,i,uid,10250,com.systemservice\n9,0,i,uid,10101,com.whatsapp\n"
            "9,10250,l,nt,0,0,52428800,157286400,1,2,3,4\n9,10101,l,nt,10485760,1048576,20971520,2097152,1,2\n")
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
    # ---- Turbo
    if c.startswith("device_config get"):
        fim("null")
    if c.startswith("device_config put"):
        fim("Successfully set")
    if c.startswith("dumpsys display"):
        fim("mActiveSfDisplayMode=DisplayMode{id=1, width=1080, height=2400, fps=120.0}\n"
            "supportedModes [{id=1, width=1080, height=2400, fps=120.0}, {id=2, width=1080, height=2400, fps=60.0}]")
    if c.startswith("dumpsys meminfo"):
        fim(fixture("turbo_meminfo.txt"))
    if c.startswith("dumpsys usagestats"):
        fim('In-memory weekly stats\n'
            '  package=com.whatsapp totalTimeUsed="05:10:00" lastTimeUsed="2026-11-17 10:00:00"\n'
            '  package=com.exemplo.jogo totalTimeUsed="01:00:00" lastTimeUsed="2026-11-16 10:00:00"')
    if c.startswith("dumpsys wifi"):
        fim("mWifiInfo SSID: \"Casa\", RSSI: -58, Link speed: 433Mbps, Frequency: 5180MHz, Wi-Fi standard: 11ac")
    if c.startswith("ping "):
        fim("10 packets transmitted, 10 received, 0% packet loss, time 2702ms\n"
            "rtt min/avg/max/mdev = 12.1/18.4/31.0/5.2 ms")
    if c.startswith("cmd package compile") or c.startswith("cmd package bg-dexopt-job") or c.startswith("pm art"):
        fim("Success")
    if c.startswith("am get-standby-bucket"):
        fim("10")
    if c.startswith("cmd game"):
        fim("")
    if c.startswith("settings list"):
        fim("window_animation_scale=1.0\ntransition_animation_scale=1.0\nadb_enabled=1\npeak_refresh_rate=120.0")
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
