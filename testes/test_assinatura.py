"""Assinatura Ed25519 dos laudos (QR verificável) — o mesmo vetor é conferido pela página (site/v/teste.mjs)."""

from pathlib import Path

from celscan.core import assinatura as a

VETOR = Path(__file__).parent / "fixtures" / "laudo_assinado.txt"


def test_assina_e_confere():
    d = a.assinar_laudo(7, "2026-10-01T10:00:00", "Xiaomi Redmi Note 14", 88, "Bom", "ab" * 32)
    url = a.url_verificacao(d)
    assert url.startswith(a.PAGINA + "#") and len(url) < 450  # cabe num QR legível
    assert a.verificar(a.ler_url(url))


def test_adulterar_invalida():
    d = a.assinar_laudo(7, "2026-10-01T10:00:00", "X", 40, "Crítico", "cd" * 32)
    for campo, valor in (("n", 95), ("v", "Excelente"), ("m", "Outro"), ("d", "2027-01-01T00:00")):
        assert not a.verificar({**d, campo: valor})


def test_mesma_chave_entre_laudos():
    k1 = a.assinar_laudo(1, "2026-10-01", "A", 1, "x", "0" * 32)["k"]
    k2 = a.assinar_laudo(2, "2026-10-02", "B", 2, "y", "1" * 32)["k"]
    assert k1 == k2 and len(a.impressao_digital()) == 19


def test_vetor_fixo_compartilhado_com_a_pagina():
    frag, digital = VETOR.read_text(encoding="utf-8").strip().splitlines()
    d = a.ler_url("#" + frag)
    assert a.verificar(d)
    assert a.impressao_digital(a._de_b64(d["k"])) == digital
