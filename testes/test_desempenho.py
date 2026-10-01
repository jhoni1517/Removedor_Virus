"""Teste de desempenho: parse de am start -W e dd; arquivo temporário sempre apagado."""

from celscan.acoes import desempenho


class Ap:
    def __init__(self, falhar_dd=False):
        self.cmds, self.falhar_dd = [], falhar_dd

    def sh(self, cmd, timeout=120, erro=False):
        self.cmds.append(cmd)
        if cmd.startswith("pm list packages"):
            return "package:com.android.settings\npackage:com.whatsapp\n"
        if cmd.startswith("cmd package resolve-activity"):
            pkg = cmd.split()[-1]
            return f"priority=0 preferredOrder=0\n{pkg}/.Principal"
        if cmd.startswith("am start -W"):
            return "Status: ok\nLaunchState: COLD\nTotalTime: 640\nWaitTime: 660\nComplete"
        if cmd.startswith("dd if=/dev/zero"):
            if self.falhar_dd:
                raise RuntimeError("cabo saiu")
            return "64+0 records in\n64+0 records out\n67108864 bytes (64 M) copied, 0.5 s, 128 M/s"
        if cmd.startswith("dd if="):
            return "67108864 bytes (64 M) copied, 0.25 s, 256 M/s"
        return ""


def test_testar_mede_abertura_e_disco():
    ap = Ap()
    r = desempenho.testar(ap)
    assert [a["pacote"] for a in r["apps"]] == ["com.android.settings", "com.whatsapp"]
    assert r["media_abertura_ms"] == 640
    assert r["armazenamento"]["gravacao_mb_s"] == 128.0 and r["armazenamento"]["leitura_mb_s"] == 256.0
    assert any(c.startswith("rm -f") for c in ap.cmds)  # arquivo temporário apagado


def test_apaga_arquivo_mesmo_com_erro():
    ap = Ap(falhar_dd=True)
    try:
        desempenho.armazenamento(ap)
    except RuntimeError:
        pass
    assert any(c.startswith("rm -f") for c in ap.cmds)


def test_parse_dd_sem_numero():
    assert desempenho._mb_s("dd: erro") is None
