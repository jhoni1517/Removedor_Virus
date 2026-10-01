"""Reiniciar o celular (normal/recovery/fastboot): manda o comando certo e não quebra se a conexão cai."""

import pytest

from celscan.acoes import energia
from celscan.core.adb import AdbErro


class Ap:
    def __init__(self, cair=False):
        self.chamadas, self.cair = [], cair

    def adb(self, *args, timeout=120, erro=False):
        self.chamadas.append(args)
        if self.cair:
            raise AdbErro("conexão caiu ao reiniciar")
        return ""


def test_reiniciar_normal():
    ap = Ap()
    r = energia.reiniciar(ap, "normal")
    assert ap.chamadas == [("reboot",)] and r["enviado"] and r["modo"] == "normal"


def test_reiniciar_recovery_e_bootloader():
    ap = Ap()
    energia.reiniciar(ap, "recovery")
    energia.reiniciar(ap, "bootloader")
    assert ap.chamadas == [("reboot", "recovery"), ("reboot", "bootloader")]


def test_conexao_cair_e_esperado_nao_quebra():
    ap = Ap(cair=True)
    assert energia.reiniciar(ap, "normal")["enviado"] is True


def test_modo_invalido():
    with pytest.raises(ValueError):
        energia.reiniciar(Ap(), "desbloquear")


def test_modos_tem_os_tres_com_aviso():
    m = {x["chave"]: x for x in energia.modos()}
    assert set(m) == {"normal", "recovery", "bootloader"}
    assert all(x["aviso"] and x["descricao"] for x in m.values())
