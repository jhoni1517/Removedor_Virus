"""Domínios dos indicadores do MVT: normalização, domínio-pai e busca em texto."""

from celscan.analise import iocs


def _base():
    return iocs.IOCs({"pacotes": {}, "certs": {}, "hashes": {}, "atualizado": 0,
                      "dominios": {"evil-c2.com": "Predator", "spy.example.net": "Pegasus"}})


def test_normalizar():
    assert iocs.normalizar_dominio("https://X.Evil-C2.com:443/painel") == "x.evil-c2.com"
    assert iocs.normalizar_dominio("evil-c2.com.") == "evil-c2.com"
    assert iocs.normalizar_dominio("localhost") is None


def test_checar_dominio_e_pai():
    b = _base()
    assert b.checar_dominio("evil-c2.com") == "Predator"
    assert b.checar_dominio("api.cdn.evil-c2.com") == "Predator"  # subdomínio
    assert b.checar_dominio("notevil-c2.com") is None              # não confunde sufixo de texto
    assert b.checar_dominio("example.net") is None                 # pai não listado


def test_dominios_em_texto():
    texto = 'url="https://api.evil-c2.com/upload" outro=spy.example.net/x google.com'
    achados = _base().dominios_em(texto)
    assert ("api.evil-c2.com", "Predator") in achados
    assert ("spy.example.net", "Pegasus") in achados
    assert len(achados) == 2


def test_cache_antigo_sem_dominios():
    b = iocs.IOCs({"pacotes": {"a": "x"}, "certs": {}, "hashes": {}, "atualizado": 0})
    assert b.dominios == {} and b.checar_dominio("evil-c2.com") is None


def test_parser_stix_captura_dominio_e_url():
    pats = ("[domain-name:value = 'c2.badguy.org']", "[url:value = 'https://drop.badguy.io/a']",
            "[app:id = 'com.spy']")
    tipos = [t for p in pats for t, _ in iocs.RX.findall(p)]
    assert tipos == ["domain-name:value", "url:value", "app:id"]
