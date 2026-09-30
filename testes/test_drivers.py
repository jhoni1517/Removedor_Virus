"""Parser do diagnóstico de driver USB no Windows (a chamada real só roda no Windows)."""

from celscan.core import drivers

SAIDA = (
    "USB\\VID_18D1&PID_4EE7\\0123;OK\n"                 # Google, ok -> ignora
    "USB\\VID_04E8&PID_6860\\ABCD;Error\n"              # Samsung com problema
    "USB\\VID_2717&PID_FF48\\XYZ;Unknown\n"             # Xiaomi com problema
    "USB\\VID_8087&PID_0026\\INTEL;OK\n"                # não é celular -> ignora
    "linha sem ponto e vírgula\n"
)


def test_detecta_celular_com_driver_ruim():
    p = drivers.analisar(SAIDA)
    fabs = {x["fabricante"] for x in p}
    assert fabs == {"Samsung", "Xiaomi"}
    assert all(x["link"].startswith("http") for x in p)


def test_ignora_ok_e_nao_celular():
    p = drivers.analisar("USB\\VID_18D1&PID_1;OK\nUSB\\VID_8087&PID_2;Error\n")
    assert p == []


def test_diagnosticar_fora_do_windows():
    d = drivers.diagnosticar()
    assert d["windows"] is False and d["problemas"] == []
    assert d["link_generico"].startswith("http")
