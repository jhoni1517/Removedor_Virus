"""Saúde da bateria, ciclos restantes e indícios de peça trocada (nível de aparelho, honesto)."""

from celscan.acoes import saude


def test_veredito_por_faixa():
    assert saude.veredito_bateria(95) == "Ótima"
    assert saude.veredito_bateria(85) == "Boa"
    assert saude.veredito_bateria(75).startswith("Desgastada")
    assert saude.veredito_bateria(60).startswith("Muito desgastada")
    assert saude.veredito_bateria(None) is None


def test_ciclos_restantes_medido():
    # 90% de saúde com 100 ciclos -> 0,1% por ciclo -> faltam ~100 ciclos até 80%.
    r = saude.ciclos_restantes(90, 100)
    assert r["base"] == "medido" and r["restantes"] == 100 and r["ate_pct"] == 80


def test_ciclos_restantes_referencia_sem_saude():
    r = saude.ciclos_restantes(None, 200)
    assert r["base"] == "referencia" and r["restantes"] == saude.CICLOS_REFERENCIA - 200


def test_ciclos_restantes_sem_dados():
    assert saude.ciclos_restantes(90, None) is None


def test_indicio_bateria_sem_capacidade_de_fabrica():
    ind = saude.indicios_pecas({"saude_pct": 88})  # sem capacidade_projeto_mah
    bat = next(i for i in ind if i["peca"] == "Bateria")
    assert bat["nivel"] == "medio"


def test_indicio_saude_impossivel_indica_paralela():
    ind = saude.indicios_pecas({"saude_pct": 118, "capacidade_projeto_mah": 4000})
    bat = next(i for i in ind if i["peca"] == "Bateria")
    assert bat["nivel"] == "alto"


def test_indicio_bateria_normal_nao_prova_originalidade():
    ind = saude.indicios_pecas({"saude_pct": 92, "capacidade_projeto_mah": 4000})
    bat = next(i for i in ind if i["peca"] == "Bateria")
    assert bat["nivel"] == "baixo"
    # Sempre deixa claro que tela/câmera não dá para verificar por USB.
    assert any("Tela" in i["peca"] for i in ind)


def test_avaliar_enriquece_bateria():
    r = saude.avaliar({"saude_pct": 90, "ciclos": 100, "capacidade_projeto_mah": 4000})
    assert r["bateria_extra"]["veredito"] == "Ótima"
    assert r["bateria_extra"]["ciclos_restantes"]["restantes"] == 100
    assert r["pecas"]
