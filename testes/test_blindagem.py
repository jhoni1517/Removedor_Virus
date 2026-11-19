"""Blindagem pós-limpeza: Play Protect, instaladores fora da loja e DNS, tudo reversível."""
import re

import pytest

from celscan.acoes import blindagem, quarentena


@pytest.fixture(autouse=True)
def quarentena_temporaria(tmp_path, monkeypatch):
    monkeypatch.setattr(quarentena, "DIRQ", tmp_path / "q")


class Celular:
    serial = "ABC"

    def __init__(self):
        self.settings = {("global", "package_verifier_enable"): "0"}
        self.ops = {"com.baixador": "allow", "com.play": "allow", "com.fdroid.app": "default",
                    "org.fdroid.fdroid": "allow"}
        self.pacotes = {"com.baixador": "null", "com.play": "com.android.vending",
                        "com.fdroid.app": "org.fdroid.fdroid", "org.fdroid.fdroid": "null"}

    def sh(self, cmd, timeout=120, erro=False):
        if cmd == "pm list packages -3 -i":
            return "\n".join(f"package:{p}  installer={i}" for p, i in self.pacotes.items())
        m = re.fullmatch(r"settings get (\w+) (\S+)", cmd)
        if m:
            return self.settings.get((m[1], m[2]), "null")
        m = re.fullmatch(r"settings put (\w+) (\S+) '?([^']*)'?", cmd)
        if m:
            self.settings[(m[1], m[2])] = m[3]
            return ""
        m = re.fullmatch(r"settings delete (\w+) (\S+)", cmd)
        if m:
            self.settings.pop((m[1], m[2]), None)
            return ""
        m = re.fullmatch(r"(?:cmd )?appops get (\S+) REQUEST_INSTALL_PACKAGES", cmd)
        if m:
            return f"REQUEST_INSTALL_PACKAGES: {self.ops.get(m[1], 'default')}"
        m = re.fullmatch(r"(?:cmd )?appops set '?([\w.]+)'? REQUEST_INSTALL_PACKAGES (\w+)", cmd)
        if m:
            self.ops[m[1]] = m[2]
            return ""
        return ""


def test_so_aponta_instalador_fora_da_loja():
    assert blindagem.instaladores(Celular()) == ["com.baixador"]


def test_estado_e_aplicar_com_desfazer():
    c = Celular()
    e = blindagem.estado(c)
    assert e["play_protect"] is False and e["instaladores"] == ["com.baixador"] and e["nota"] == 0
    assert len(e["checklist"]) >= 4
    r = blindagem.aplicar(c, ["play_protect", "instaladores", "dns"])
    assert all(f["ok"] for f in r["feitos"])
    assert c.ops["com.baixador"] == "deny" and c.ops["com.play"] == "allow"
    assert c.settings[("global", "private_dns_specifier")] == "security.cloudflare-dns.com"
    assert r["estado"]["nota"] == 3
    ok, _ = quarentena.restaurar(c, r["desfazer_id"])
    assert ok and c.ops["com.baixador"] == "allow" and c.settings[("global", "package_verifier_enable")] == "0"


def test_item_desconhecido():
    with pytest.raises(ValueError):
        blindagem.aplicar(Celular(), ["apagar_tudo"])
