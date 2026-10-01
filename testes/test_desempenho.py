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


def test_parse_cpu_nucleos_e_clock():
    cpuinfo = "processor\t: 0\nprocessor\t: 1\nprocessor\t: 2\nprocessor\t: 3\n"
    freqs = "1800000\n1800000\n2400000\n3000000\n"
    r = desempenho._parse_cpu(cpuinfo, freqs)
    assert r == {"nucleos": 4, "ghz_max": 3.0}


def test_parse_cpu_vazio_nao_inventa():
    assert desempenho._parse_cpu("", "") == {"nucleos": None, "ghz_max": None}


def test_parse_cameras_separa_traseiras_e_frontais():
    saida = ("Camera 0 information:\n  Facing: BACK\n  Resolution: 4000x3000\n"
             "Camera 1 information:\n  Facing: FRONT\n  Resolution: 1920x1080\n"
             "Camera 2 information:\n  Facing: BACK\n  Resolution: 1280x720\n")
    r = desempenho._parse_cameras(saida)
    assert r["total"] == 3 and r["traseiras"] == 2 and r["frontais"] == 1 and r["megapixels_max"] == 12.0


def test_parse_cameras_facing_numerico():
    saida = "Camera 0 information:\n  facing=0\nCamera 1 information:\n  facing=1\n"
    r = desempenho._parse_cameras(saida)
    assert r["traseiras"] == 1 and r["frontais"] == 1


def test_parse_cameras_sem_dados():
    r = desempenho._parse_cameras("")
    assert r["total"] is None and r["megapixels_max"] is None


def test_pontuar_topo_de_linha_chega_perto_de_1000():
    hw = {"nucleos": 8, "ghz_max": 3.0, "ram_gb": 12}
    arm = {"leitura_mb_s": 1000, "gravacao_mb_s": 500}
    r = desempenho.pontuar(hw, arm, 300)
    assert r["total"] == 1000
    assert r["categorias"] == {"hardware": 100, "armazenamento": 100, "fluidez": 100}


def test_pontuar_ignora_categoria_sem_dado():
    # Só armazenamento medido: o total usa só ele (não zera por falta de hardware).
    r = desempenho.pontuar({}, {"leitura_mb_s": 500, "gravacao_mb_s": 250}, None)
    assert r["categorias"]["hardware"] is None and r["categorias"]["fluidez"] is None
    assert r["total"] == 500


def test_pontuar_sem_nada_devolve_none():
    assert desempenho.pontuar({}, {}, None)["total"] is None
