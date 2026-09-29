"""Varredura de iPhone: backup via USB + MVT, sem falso 'limpo' quando algo falha."""
import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path


class IOSErro(Exception):
    pass


def _exigir(*bins):
    dicas = {"idevice_id": "libimobiledevice", "idevicebackup2": "libimobiledevice",
             "mvt-ios": "pip install mvt"}
    faltando = [f"{b} ({dicas.get(b, '')})" for b in bins if not shutil.which(b)]
    if faltando:
        raise IOSErro("Ferramentas faltando: " + ", ".join(faltando))


def _run(cmd, env=None):
    r = subprocess.run(cmd, env=env, capture_output=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def pastas_backup():
    home = Path.home()
    cands = [home / "Library/Application Support/MobileSync/Backup",
             Path(os.getenv("APPDATA", "")) / "Apple Computer/MobileSync/Backup",
             home / "Apple/MobileSync/Backup"]
    res = []
    for c in cands:
        if c.is_dir():
            for b in c.iterdir():
                info = b / "Info.plist"
                if info.exists():
                    try:
                        p = plistlib.loads(info.read_bytes())
                    except Exception:
                        p = {}
                    res.append({"pasta": str(b), "aparelho": p.get("Device Name", "?"),
                                "ios": p.get("Product Version", "?"), "data": str(p.get("Last Backup Date", "?"))})
    return res


def criptografado(pasta):
    m = Path(pasta) / "Manifest.plist"
    if not m.exists():
        raise IOSErro(f"{pasta} não parece um backup de iPhone (sem Manifest.plist)")
    return bool(plistlib.loads(m.read_bytes()).get("IsEncrypted"))


def aparelhos():
    _exigir("idevice_id")
    return _run(["idevice_id", "-l"])[1].split()


def bateria(udid):
    if not shutil.which("idevicediagnostics"):
        return None
    cod, out = _run(["idevicediagnostics", "-u", udid, "ioregentry", "AppleSmartBattery"])
    try:
        d = plistlib.loads(out[out.index("<?xml"):].encode()).get("IORegistry", {})
    except Exception:
        return None
    ciclos, projeto = d.get("CycleCount"), d.get("DesignCapacity")
    atual = d.get("AppleRawMaxCapacity") or d.get("NominalChargeCapacity")
    saude = round(atual / projeto * 100) if atual and projeto else None
    return {"ciclos": ciclos, "saude_pct": saude}


def fazer_backup(udid, destino, log=print):
    _exigir("idevicebackup2")
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    log("Mantenha o iPhone desbloqueado. O backup pode levar vários minutos.")
    cod, out = _run(["idevicebackup2", "-u", udid, "backup", "--full", str(destino)])
    if cod != 0:
        raise IOSErro("Backup falhou:\n" + out[-800:])
    return destino / udid


def analisar(backup, saida, senha=None, log=print):
    _exigir("mvt-ios")
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    alvo = Path(backup)
    env = dict(os.environ)
    if criptografado(alvo):
        if not senha:
            raise IOSErro("Backup criptografado: informe a senha.")
        env["MVT_IOS_BACKUP_PASSWORD"] = senha  # não aparece na lista de processos
        dec = saida / "backup_decifrado"
        cod, out = _run(["mvt-ios", "decrypt-backup", "-d", str(dec), str(alvo)], env)
        if cod != 0 or not (dec / "Manifest.db").exists():
            raise IOSErro("Não consegui decifrar o backup (senha errada?).\n" + out[-500:])
        alvo = dec
    cod, out = _run(["mvt-ios", "download-iocs"], env)
    if cod != 0:
        log("Aviso: não baixei indicadores novos; usando os já instalados.")
    res = saida / "mvt"
    cod, out = _run(["mvt-ios", "check-backup", "--output", str(res), str(alvo)], env)
    if cod != 0:
        raise IOSErro("A análise do MVT falhou — o resultado NÃO é confiável.\n" + out[-800:])
    det = {}
    for f in res.glob("*_detected.json"):
        try:
            dados = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        n = len(dados) if isinstance(dados, list) else 1
        if n:
            det[f.stem.replace("_detected", "")] = n
    return det
