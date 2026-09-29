#!/usr/bin/env python3
import sys, os, shutil, re
a = sys.argv[1:]
EST = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".estado"); os.makedirs(EST, exist_ok=True)
APK_REAL = os.getenv("APK_TESTE", "/tmp/fdroid.apk")  # qualquer APK real
if a == ["start-server"]: sys.exit(0)
if a == ["devices"]:
    print("* daemon not running; starting now at tcp:5037\nList of devices attached\nABC123\tdevice\nXYZ\tunauthorized\n"); sys.exit(0)
if a[0] == "-s": a = a[2:]
if a[0] == "push":
    shutil.copy(a[1], EST + "/script.sh"); print("1 file pushed"); sys.exit(0)
if a[0] == "pull":
    open(a[2], "wb").write(b"APKFAKE"); print("pulled"); sys.exit(0)
if a[0] in ("install", "install-multiple"):
    print("Success"); sys.exit(0)
if a[0] == "uninstall":
    print("Success"); sys.exit(0)
if a[0] == "exec-out":
    m = re.search(r"dd if=(\S+) bs=(\d+) skip=(\d+) count=(\d+)", a[1])
    bs, sk, ct = int(m.group(2)), int(m.group(3)), int(m.group(4))
    with open(APK_REAL, "rb") as f:
        f.seek(bs * sk); sys.stdout.buffer.write(f.read(bs * ct))
    sys.exit(0)
if a[0] == "shell":
    c = " ".join(a[1:])
    if c.startswith("sh /data/local/tmp"):
        s = open(EST + "/script.sh").read()
        print(open(os.path.dirname(__file__) + ("/coleta.txt" if "pkgdump" in s else "/diag.txt")).read()); sys.exit(0)
    if "sha256sum" in c:
        tam = os.path.getsize(APK_REAL)
        for pkg, h in [("com.whatsapp", "a"*64), ("com.systemservice", "b"*64), ("com.x8bit.bitwarden", "c"*64), ("com.exemplo.jogo", "d"*64)]:
            print(f"@@H\t{tam}\t{h}\t/data/app/~~X==/{pkg}-Y==/base.apk")
        sys.exit(0)
    if c.startswith("pm path"):
        print("package:/data/app/~~X==/" + c.split()[-1] + "-Y==/base.apk"); sys.exit(0)
    if c.startswith("settings get secure enabled_accessibility"):
        print("com.systemservice/com.systemservice.Acc:com.x8bit.bitwarden/com.x8bit.bitwarden.Acc"); sys.exit(0)
    if c.startswith("df -k"):
        print("Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-5 115343360 90000000 25343360 78% /data"); sys.exit(0)
    if c.startswith("pm list packages -e"):
        print("package:com.facebook.appmanager\npackage:com.whatsapp\npackage:com.miui.analytics"); sys.exit(0)
    if "disable-user" in c:
        print(f"Package {c.split()[-1]} new state: disabled-user"); sys.exit(0)
    if c.startswith("pm enable"):
        print("Package x new state: enabled"); sys.exit(0)
    sys.exit(0)
sys.exit(0)
