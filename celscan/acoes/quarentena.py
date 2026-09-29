"""Quarentena: guarda o APK antes de remover e permite desfazer qualquer ação."""
import json
import shlex
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from celscan.config import DIR

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
        "ajustes": [],
    })
    return pasta


def criar_ajuste(ap, ident, descricao, ajustes):
    """Registra mudanças de configuração (sem APK) para poder desfazer depois.

    ident: nome curto sem espaços (vira parte do ID); descricao: texto para o usuário.
    """
    pasta = criar(ap, ident, {"motivos": [descricao]}, copiar_apk=False)
    for a in ajustes:
        adicionar_ajuste(pasta, a)
    registrar(pasta, "ajuste")
    return pasta


def adicionar_ajuste(pasta, ajuste):
    """ajuste: {"tipo": "settings", "ns", "chave", "anterior"} ou {"tipo": "appops", "pacote", "op", "anterior"}."""
    meta = _ler(pasta)
    meta.setdefault("ajustes", []).append(ajuste)
    _gravar(pasta, meta)


def ler_setting(ap, ns, chave):
    valor = ap.sh(f"settings get {ns} {chave}").strip()
    return None if valor in ("", "null") else valor


def _reverter_ajustes(ap, meta):
    """Desfaz os ajustes na ordem inversa. Devolve (tudo_ok, mensagens)."""
    ok, msgs = True, []
    for a in reversed(meta.get("ajustes") or []):
        if a["tipo"] == "settings":
            if a.get("anterior") is None:
                ap.sh(f"settings delete {a['ns']} {a['chave']}")
            else:
                ap.sh(f"settings put {a['ns']} {a['chave']} {shlex.quote(a['anterior'])}")
            atual = ler_setting(ap, a["ns"], a["chave"])
            certo = atual == a.get("anterior")
            msgs.append(f"{a['chave']}: {'restaurado' if certo else 'não confirmou'}")
            ok &= certo
        elif a["tipo"] == "appops":
            ap.sh(f"appops set {a['pacote']} {a['op']} {a.get('anterior') or 'default'}")
            msgs.append(f"{a['op']} de {a['pacote']}: {a.get('anterior') or 'default'}")
    return ok, msgs


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
    elif acao == "ajuste":
        ok, msgs = _reverter_ajustes(ap, meta)
        out = "; ".join(msgs) or "nada a desfazer"
    else:
        return False, f"nada a restaurar (ação: {acao})"
    if ok and acao != "ajuste" and meta.get("ajustes"):
        _, msgs = _reverter_ajustes(ap, meta)
        out = f"{out}\n" + "; ".join(msgs)
    if ok:
        meta["restaurado"] = datetime.now().isoformat(timespec="seconds")
        _gravar(pasta, meta)
    return ok, out
