"""Quarentena: guarda o APK antes de remover e permite desfazer qualquer ação."""
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from config import DIR

DIRQ = DIR / "quarentena"


def _ler(pasta):
    return json.loads((pasta / "meta.json").read_text(encoding="utf-8"))


def _gravar(pasta, meta):
    (pasta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def criar(ap, pacote, dados=None, copiar_apk=True):
    pasta = DIRQ / f"{datetime.now():%Y%m%d_%H%M%S}_{pacote}"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    if copiar_apk:
        caminhos = [l[8:] for l in ap.sh(f"pm path {pacote}").splitlines() if l.startswith("package:")]
        for i, c in enumerate(caminhos):
            destino = pasta / f"{i:02d}_{Path(c).name}.quarentena"
            ap.adb("pull", c, str(destino), timeout=900)
            if destino.exists():
                arquivos.append(destino.name)
    d = dados or {}
    _gravar(pasta, {
        "id": pasta.name, "pacote": pacote, "serial": ap.serial,
        "data": datetime.now().isoformat(timespec="seconds"), "acao": None,
        "arquivos": arquivos, "motivos": d.get("motivos", []), "sha256": d.get("sha256"),
    })
    return pasta


def registrar(pasta, acao):
    meta = _ler(pasta)
    meta["acao"] = acao
    _gravar(pasta, meta)


def listar():
    if not DIRQ.exists():
        return []
    return [_ler(p) for p in sorted(DIRQ.iterdir(), reverse=True) if (p / "meta.json").exists()]


def restaurar(ap, ident):
    pasta = DIRQ / ident
    if not (pasta / "meta.json").exists():
        return False, "ID não encontrado na quarentena"
    meta = _ler(pasta)
    pkg, acao = meta["pacote"], meta["acao"]
    if acao == "desativado":
        out = ap.sh(f"pm enable {pkg}", erro=True)
        ok = "enabled" in out
    elif acao == "removido_usuario0":
        out = ap.sh(f"cmd package install-existing {pkg}", erro=True)
        ok = "installed" in out.lower()
    elif acao == "removido" and meta["arquivos"]:
        tmp = Path(tempfile.mkdtemp())
        apks = []
        for a in meta["arquivos"]:
            destino = tmp / a.replace(".quarentena", "")
            shutil.copy(pasta / a, destino)
            apks.append(str(destino))
        cmd = "install-multiple" if len(apks) > 1 else "install"
        out = ap.adb(cmd, "-r", *apks, timeout=600, erro=True)
        ok = "Success" in out
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        return False, f"nada a restaurar (ação: {acao})"
    if ok:
        meta["restaurado"] = datetime.now().isoformat(timespec="seconds")
        _gravar(pasta, meta)
    return ok, out
