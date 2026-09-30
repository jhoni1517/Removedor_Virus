from celscan.acoes import otimizacao, quarentena


class AparelhoFalso:
    """Guarda settings em memória e registra os comandos."""

    serial = "TESTE1"

    def __init__(self):
        self.settings = {("global", "window_animation_scale"): "1.0"}
        self.comandos = []

    def sh(self, cmd, timeout=120, erro=False):
        self.comandos.append(cmd)
        partes = cmd.split()
        if partes[:2] == ["settings", "get"]:
            return self.settings.get((partes[2], partes[3]), "null")
        if partes[:2] == ["settings", "put"]:
            self.settings[(partes[2], partes[3])] = partes[4].strip("'")
        if partes[:2] == ["settings", "delete"]:
            self.settings.pop((partes[2], partes[3]), None)
        return ""

    def adb(self, *args, **kw):
        return ""


def test_animacoes_registra_e_desfaz():
    ap = AparelhoFalso()
    ident = otimizacao.animacoes(ap, 0.5)
    assert ap.settings[("global", "window_animation_scale")] == "0.5"
    assert ap.settings[("global", "animator_duration_scale")] == "0.5"
    ok, msg = quarentena.restaurar(ap, ident)
    assert ok, msg
    assert ap.settings[("global", "window_animation_scale")] == "1.0"
    assert ("global", "animator_duration_scale") not in ap.settings  # antes não existia
    assert any(m["id"] == ident and m.get("restaurado") for m in quarentena.listar())


def test_restaurar_id_inexistente():
    assert quarentena.restaurar(AparelhoFalso(), "nao_existe") == (False, "ID não encontrado na quarentena")


class AparelhoComApk(AparelhoFalso):
    """Simula pm path + adb pull (grava um APK) + install."""

    def sh(self, cmd, timeout=120, erro=False):
        if cmd.startswith("pm path"):
            return "package:/data/app/com.mal-1/base.apk"
        return super().sh(cmd, timeout, erro)

    def adb(self, *args, **kw):
        if args[0] == "pull":
            open(args[2], "wb").write(b"APKFALSO" * 16)
        if args[0] in ("install", "install-multiple"):
            return "Success"
        return ""


def test_apk_vai_para_zip_cifrado_e_restaura(tmp_path, monkeypatch):
    import pyzipper

    monkeypatch.setattr(quarentena, "DIRQ", tmp_path / "q")
    ap = AparelhoComApk()
    pasta = quarentena.criar(ap, "com.mal", {"motivos": ["teste"]})
    quarentena.registrar(pasta, "removido")
    meta = quarentena._ler(pasta)
    assert meta["protegido"] and meta["arquivos"]
    # O APK cru não fica solto na pasta (o antivírus não o vê); só o zip cifrado.
    assert (pasta / quarentena.ZIP_APKS).exists()
    assert not list(pasta.glob("*.quarentena"))
    # Sem a senha, não abre.
    import pytest
    with pyzipper.AESZipFile(pasta / quarentena.ZIP_APKS) as z, pytest.raises(RuntimeError):
        z.read(meta["arquivos"][0])
    ok, _ = quarentena.restaurar(ap, pasta.name)
    assert ok
