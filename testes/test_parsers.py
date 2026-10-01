from celscan.core import parsers
from conftest import ler_fixture


def test_secoes():
    s = parsers.secoes("@@SEC a\n1\n2\n@@SEC b\n\n@@SEC fim\n")
    assert s == {"a": "1\n2", "b": "", "fim": ""}


def test_pacotes_formato_padrao_com_igual_no_caminho():
    s = parsers.secoes(ler_fixture("sintetico/coleta.txt"))
    p = parsers.pacotes(s["pkgs"])
    assert p["com.whatsapp"] == ("/data/app/~~X==/com.whatsapp-Y==/base.apk", "com.android.vending")
    assert len(p) == 4


def test_pacotes_android14_com_uid():
    p = parsers.pacotes(ler_fixture("sintetico/variantes/pkgs_android14_uid.txt"))
    assert p["com.nu.production"][1] == "com.android.vending"
    assert p["com.falso.banco"][0].endswith("base.apk")


def test_pacotes_sem_caminho_e_instalador_nulo():
    p = parsers.pacotes(ler_fixture("sintetico/variantes/pkgs_android8_sem_f.txt"))
    assert p["com.whatsapp"] == ("", "com.android.vending")
    assert p["com.exemplo.sem.instalador"] == ("", None)
    assert p["com.exemplo.antigo"] == ("", None)


def test_pkgdump_primeira_ocorrencia_vale():
    d = parsers.pkgdump(ler_fixture("sintetico/variantes/pkgdump_hidden.txt"))
    assert d["com.exemplo"]["versao"] == "2.0"
    assert d["com.exemplo"]["perms"] == {"android.permission.READ_SMS"}  # CAMERA está negada
    assert d["com.exemplo"]["instalado"].year == 2025


def test_admins_formatos_android9_e_14():
    s = parsers.secoes(ler_fixture("sintetico/coleta.txt"))
    assert parsers.admins(s["admins"]) == {"com.systemservice": ["com.systemservice/com.systemservice.AdminRcv"]}
    a9 = parsers.admins(ler_fixture("sintetico/variantes/device_policy_android9.txt"))
    assert "com.google.android.gms" in a9 and "com.empresa.mdm" in a9


def test_owners_pelo_device_policy():
    assert parsers.owners(ler_fixture("sintetico/variantes/device_policy_android9.txt")) == {"com.empresa.mdm"}
    assert parsers.owners("User 0: admin=com.mdm/.Rcv,DeviceOwner") == {"com.mdm"}


def test_launcher_brief_completo_e_erro():
    s = parsers.secoes(ler_fixture("sintetico/coleta.txt"))
    assert parsers.launcher(s["launcher"]) == {"com.whatsapp", "com.x8bit.bitwarden", "com.exemplo.jogo"}
    assert parsers.launcher(ler_fixture("sintetico/variantes/launcher_completo.txt")) == {
        "com.whatsapp", "com.nu.production"}
    assert parsers.launcher(ler_fixture("sintetico/variantes/launcher_erro.txt")) is None


def test_appops_formatos_e_erro():
    ops = parsers.appops(ler_fixture("sintetico/variantes/appops_uid_mode.txt"),
                         {"SYSTEM_ALERT_WINDOW", "REQUEST_INSTALL_PACKAGES"})
    assert ops == {"com.samsung.exemplo": {"SYSTEM_ALERT_WINDOW"},
                   "com.xiaomi.exemplo": {"SYSTEM_ALERT_WINDOW"}, "com.limpo": set()}
    assert not parsers.appops_indisponivel(ler_fixture("sintetico/variantes/appops_uid_mode.txt"))
    assert parsers.appops_indisponivel(ler_fixture("sintetico/variantes/appops_erro.txt"))


def test_componentes_e_sempre_ativo():
    assert parsers.componentes("a.b/.C:d.e/f.G") == {"a.b", "d.e"}
    assert parsers.componentes("null") == set()
    assert parsers.sempre_ativo("system-excidle,com.android.phone,1001\nuser,com.x,10250") == {"com.x"}


def test_indisponivel():
    assert parsers.indisponivel("")
    assert parsers.indisponivel("Error: unknown command 'x'\n")
    assert parsers.indisponivel("/system/bin/sh: dpm: not found")
    assert not parsers.indisponivel("no owners")


def test_diagnostico_bateria_df_mem():
    s = parsers.secoes(ler_fixture("sintetico/diag.txt"))
    b = parsers.bateria(s["bateria"])
    assert b["nivel"] == "78" and b["saude"] == "boa" and b["temperatura"] == "31.2 °C"
    assert round(parsers.df(s["df"])["livre_gb"], 1) == 24.2
    assert round(parsers.meminfo(s["mem"])["disponivel_gb"], 1) == 2.5
    assert round(parsers.uptime_dias(s["uptime"])) == 10
    assert parsers.tamanhos_pastas(s["pastas"])["/sdcard/DCIM"] == 8388608


def test_diagnostico_variantes():
    b = parsers.bateria(ler_fixture("sintetico/variantes/battery_samsung.txt"))
    assert b["ciclos"] == "312"
    assert round(parsers.df(ler_fixture("sintetico/variantes/df_quebrado.txt"))["livre_gb"], 1) == 11.7
    assert parsers.bateria("Error: can't find service") is None
    assert parsers.df("") is None and parsers.meminfo("") is None


def test_identificacao_usa_nomes_curtos():
    # A tela, a CLI e o laudo leem "model", "release"... — não o nome cru da propriedade.
    txt = ("ro.product.manufacturer=Xiaomi\nro.product.model=24090RA29G\nro.product.marketname=Redmi Note 14\n"
           "ro.serialno=ABC123\nro.build.version.release=16\nro.build.version.security_patch=2026-07-01\n"
           "ro.vazio=\n")
    assert parsers.identificacao(txt) == {
        "manufacturer": "Xiaomi", "model": "24090RA29G", "marketname": "Redmi Note 14",
        "serial": "ABC123", "release": "16", "security_patch": "2026-07-01"}
