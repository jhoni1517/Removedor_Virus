import pypdfium2 as pdfium

from celscan.core import db
from celscan.relatorio import pdf

META = {"id": 7, "serial": "ABC123", "data": "2026-09-30T10:00:00", "modo": "rapido", "nota": 45,
        "veredito": "Crítico", "duracao_s": 12.0}
RETRATO = {
    "aparelho": {"serial": "ABC123", "fabricante": "motorola", "modelo": "moto g54", "android": "14",
                 "patch_seguranca": "2024-03-01"},
    "achados_aparelho": [{"chave": "root", "nivel": "ALTO", "titulo": "Celular com root → x", "significa": "S",
                          "fazer": "F"}],
    "apps": [{"pacote": "com.mal", "score": 100, "nivel": "ALTO", "ameaca": "stalkerware X", "loja": None,
              "instalador": None, "achados": [{"chave": "acessibilidade", "titulo": "Controla a tela",
                                               "significa": "Lê a tela <b>&", "fazer": "Remova"}]},
             {"pacote": "com.ok", "score": 0, "nivel": "OK", "achados": [], "loja": "Google Play"}],
    "avisos": ["Verificação de X não disponível neste aparelho."],
}


def texto_do_pdf(conteudo):
    doc = pdfium.PdfDocument(conteudo)
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def test_cliente_e_tecnico():
    c, h = pdf.gerar_pdf(META, RETRATO, "cliente", "Loja Teste", [{"pacote": "com.mal", "detalhe": "removido"}])
    t, h2 = pdf.gerar_pdf(META, RETRATO, "tecnico")
    assert c.startswith(b"%PDF") and h == h2  # mesmo código nas duas versões
    tc, tt = texto_do_pdf(c), texto_do_pdf(t)
    codigo = pdf.codigo_curto(h)
    assert codigo in tc and "Loja Teste" in tc and "stalkerware X" in tc and "O que fazer" in tc
    assert "Lê a tela <b>&" in tc  # texto escapado, não interpretado
    assert "→" not in tc  # símbolo sem glifo na fonte padrão foi trocado
    assert "com.ok" not in tc and "com.ok" in tt  # só o técnico lista todos os apps
    assert "Verificação de X" in tc


def test_hash_muda_se_os_dados_mudam():
    _, h1 = pdf.gerar_pdf(META, RETRATO)
    _, h2 = pdf.gerar_pdf({**META, "nota": 90}, RETRATO)
    assert h1 != h2


def test_verificar_laudo(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    vid = db.salvar_varredura(con, RETRATO["aparelho"], 45, "Crítico", [], RETRATO["apps"])
    meta = db.meta_varredura(con, vid)
    _, h = pdf.gerar_pdf(meta, db.retrato(con, vid))
    db.registrar_laudo(con, vid, h)
    for codigo in (pdf.codigo_curto(h), h, f"CELSCAN-LAUDO|{vid}|{h}", pdf.codigo_curto(h).lower()):
        assert db.verificar_laudo(con, codigo)["varredura_id"] == vid
    assert db.verificar_laudo(con, "0000-0000-0000-0000") is None
    assert db.verificar_laudo(con, "abc") is None
