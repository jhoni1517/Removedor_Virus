"""Autodiagnóstico da instalação e listagem de apps salvos."""

from celscan.core import autodiagnostico


def test_autodiagnostico_lista_itens_com_dica():
    itens = autodiagnostico.verificar()
    nomes = [i["item"] for i in itens]
    assert "ADB" in nomes and "Banco do histórico" in nomes and "Pasta de dados" in nomes
    assert all(set(i) == {"item", "ok", "detalhe", "dica"} for i in itens)
    assert all(i["dica"] for i in itens if i["ok"] is False)  # todo problema diz o que fazer
    assert autodiagnostico.resumo([{"ok": True}]) == "Tudo certo com o CelScan."
    assert autodiagnostico.resumo([{"ok": False}, {"ok": None}]) == "1 problema(s) na instalação."


def test_celula_csv_protege_formula_sem_estragar_vazio():
    from celscan.cli import _celula_csv
    assert _celula_csv("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _celula_csv("") == "" and _celula_csv(None) == ""
    assert _celula_csv("WhatsApp") == "WhatsApp" and _celula_csv(-3) == "'-3"
