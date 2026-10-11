"""Quarentena: guarda o APK antes de remover e permite desfazer qualquer ação.

Os APKs ficam num zip cifrado com a senha padrão da área ("infected"). Isso impede o
antivírus do Windows de escanear e apagar a amostra (o que fazia a prova sumir), e é o
mesmo formato usado para compartilhar malware entre analistas.
"""
import hashlib
import json
import shlex
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pyzipper

from celscan.config import DIR

DIRQ = DIR / "quarentena"
ZIP_APKS = "apks_infected.zip"
SENHA_APKS = b"infected"  # convenção da área para amostras de malware


def _guardar_apks(pasta, arquivos_locais):
    """Grava os APKs (caminho_local, nome_no_zip) num zip AES com senha 'infected'. Devolve os nomes."""
    nomes = []
    with pyzipper.AESZipFile(pasta / ZIP_APKS, "w", compression=pyzipper.ZIP_DEFLATED,
                            encryption=pyzipper.WZ_AES) as z:
        z.setpassword(SENHA_APKS)
        for caminho, nome in arquivos_locais:
            z.write(caminho, nome)
            nomes.append(nome)
    return nomes


def _extrair_apks(pasta, meta, destino):
    """Extrai os APKs da quarentena para 'destino'. Cobre o zip cifrado (novo) e os arquivos soltos (antigo)."""
    apks = []
    if meta.get("protegido") and (pasta / ZIP_APKS).exists():
        with pyzipper.AESZipFile(pasta / ZIP_APKS) as z:
            z.setpassword(SENHA_APKS)
            for nome in meta["arquivos"]:
                z.extract(nome, destino)
                alvo = Path(destino) / nome
                esperado = (meta.get("hashes") or {}).get(nome)
                if esperado and _sha256(alvo) != esperado:  # cópia estragada no disco do PC
                    raise ValueError(f"a cópia de {nome} na quarentena está corrompida (hash diferente)")
                apks.append(str(alvo))
    else:  # quarentenas antigas: arquivos .quarentena soltos
        for a in meta["arquivos"]:
            alvo = Path(destino) / a.replace(".quarentena", "")
            shutil.copy(pasta / a, alvo)
            apks.append(str(alvo))
    return apks


def _ler(pasta):
    return json.loads((pasta / "meta.json").read_text(encoding="utf-8"))


def _gravar(pasta, meta):
    (pasta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _nova_pasta(nome: str) -> Path:
    """Pasta nova e exclusiva. Antes, duas ações no mesmo segundo (ex.: permissões de dois apps) caíam na
    mesma pasta e a segunda apagava o "desfazer" da primeira."""
    DIRQ.mkdir(parents=True, exist_ok=True)
    base = f"{datetime.now():%Y%m%d_%H%M%S}_{nome}"
    for i in range(1000):
        pasta = DIRQ / (base if i == 0 else f"{base}_{i}")
        try:
            pasta.mkdir()
            return pasta
        except FileExistsError:
            continue
    raise OSError("não consegui criar a pasta da quarentena")


def _sha256(caminho) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def _tamanho_remoto(ap, caminho: str) -> int | None:
    saida = ap.sh(f"stat -c %s {shlex.quote(caminho)}").strip()
    return int(saida) if saida.isdecimal() else None


def criar(ap, pacote, dados=None, copiar_apk=True):
    pasta = _nova_pasta(pacote)
    arquivos, protegido, hashes, completa = [], False, {}, False
    if copiar_apk:
        caminhos = [linha[8:] for linha in ap.sh(f"pm path {pacote}").splitlines() if linha.startswith("package:")]
        with tempfile.TemporaryDirectory() as tmp:
            locais = []
            for i, c in enumerate(caminhos):
                bruto = Path(tmp) / f"{i:02d}_{Path(c).name}"
                ap.adb("pull", c, str(bruto), timeout=900)
                esperado = _tamanho_remoto(ap, c)
                # cópia cortada (cabo caiu no meio) não serve para desfazer: descarta
                if bruto.exists() and (esperado is None or bruto.stat().st_size == esperado):
                    locais.append((str(bruto), bruto.name))
                    hashes[bruto.name] = _sha256(bruto)
            if locais:
                arquivos = _guardar_apks(pasta, locais)
                protegido = True
            completa = bool(caminhos) and len(locais) == len(caminhos)
    d = dados or {}
    _gravar(pasta, {
        "id": pasta.name, "pacote": pacote, "nome": d.get("nome") or pacote, "serial": ap.serial,
        "data": datetime.now().isoformat(timespec="seconds"), "acao": None,
        "arquivos": arquivos, "protegido": protegido, "hashes": hashes, "copia_completa": completa,
        "motivos": d.get("motivos", []), "sha256": d.get("sha256"),
        "ajustes": [],
    })
    return pasta


def copia_completa(pasta) -> bool:
    """True se todos os APKs do app foram copiados e conferidos (dá para reinstalar no desfazer)."""
    return bool(_ler(pasta).get("copia_completa"))


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
        elif a["tipo"] == "permissao":
            out = ap.sh(f"pm grant {a['pacote']} {a['permissao']}", erro=True)
            certo = "error" not in out.lower() and "exception" not in out.lower()
            msgs.append(f"{a['permissao']} de {a['pacote']}: {'devolvida' if certo else 'não confirmou'}")
            ok &= certo
        elif a["tipo"] == "wm":  # densidade ou resolução da tela (wm density / wm size)
            valor = a.get("anterior")
            ap.sh(f"wm {a['chave']} {shlex.quote(valor) if valor else 'reset'}")
            msgs.append(f"tela ({a['chave']}): {valor or 'padrão de fábrica'}")
        elif a["tipo"] == "cmd":  # comando de volta gravado pelo próprio CelScan (ex.: Não perturbe)
            ap.sh(a["desfazer"])
            msgs.append(a.get("descricao") or a["desfazer"])
    return ok, msgs


def tem_ajustes(pasta) -> bool:
    return bool(_ler(pasta).get("ajustes"))


def descartar(pasta) -> None:
    """Apaga uma pasta da quarentena que não guardou nada (nem APK nem ajuste)."""
    if Path(pasta).resolve().parent == DIRQ.resolve():
        shutil.rmtree(pasta, ignore_errors=True)


def registrar(pasta, acao):
    meta = _ler(pasta)
    meta["acao"] = acao
    _gravar(pasta, meta)


def listar():
    if not DIRQ.exists():
        return []
    return [_ler(p) for p in sorted(DIRQ.iterdir(), reverse=True) if (p / "meta.json").exists()]


def restaurar(ap, ident):
    from celscan.core.seguranca import id_quarentena_valido

    if not id_quarentena_valido(ident):
        return False, "ID da quarentena inválido"
    pasta = DIRQ / ident
    if pasta.resolve().parent != DIRQ.resolve() or not (pasta / "meta.json").exists():
        return False, "ID não encontrado na quarentena"
    meta = _ler(pasta)
    pkg, acao = meta["pacote"], meta["acao"]
    if meta.get("restaurado"):
        return False, f"já desfeito em {meta['restaurado'].replace('T', ' ')}"
    if acao == "desativado":
        out = ap.sh(f"pm enable {pkg}", erro=True)
        ok = "enabled" in out
    elif acao == "removido_usuario0":
        out = ap.sh(f"cmd package install-existing {pkg}", erro=True)
        ok = "installed" in out.lower()
    elif acao == "removido" and meta["arquivos"]:
        tmp = Path(tempfile.mkdtemp())
        try:
            try:
                apks = _extrair_apks(pasta, meta, tmp)
            except ValueError as e:
                return False, str(e)
            cmd = "install-multiple" if len(apks) > 1 else "install"
            out = ap.adb(cmd, "-r", *apks, timeout=600, erro=True)
            ok = "Success" in out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif acao == "arquivos_apagados" and meta.get("caminhos"):  # instaladores .apk tirados do armazenamento
        tmp = Path(tempfile.mkdtemp())
        try:
            try:
                locais = _extrair_apks(pasta, meta, tmp)
            except ValueError as e:
                return False, str(e)
            msgs, ok = [], True
            for local in locais:
                original = meta["caminhos"].get(Path(local).name)
                if not original:
                    continue
                r = ap.adb("push", local, original, timeout=600, erro=True)
                certo = any(x in r for x in ("pushed", "bytes in"))
                ok &= certo
                msgs.append(f"{original}: {'devolvido' if certo else 'não confirmou'}")
            out = "; ".join(msgs)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif acao in ("ajuste", "parcial") or (acao is None and meta.get("ajustes")):
        # "parcial": a remoção falhou depois de já ter tirado acessibilidade/sobreposição; isso se desfaz aqui
        ok, msgs = _reverter_ajustes(ap, meta)
        out = "; ".join(msgs) or "nada a desfazer"
    else:
        return False, f"nada a restaurar (ação: {acao})"
    if ok and acao not in ("ajuste", "parcial", "arquivos_apagados", None) and meta.get("ajustes"):
        _, msgs = _reverter_ajustes(ap, meta)
        out = f"{out}\n" + "; ".join(msgs)
    if ok:
        meta["restaurado"] = datetime.now().isoformat(timespec="seconds")
        _gravar(pasta, meta)
    return ok, out
