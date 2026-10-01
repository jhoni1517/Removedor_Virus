"""Balcão: ordem de serviço, preços configuráveis, mensagem de WhatsApp, painel e CSV."""

from datetime import datetime

from fastapi.testclient import TestClient

from celscan.api.app import criar_app
from celscan.core import balcao, db

H = {"X-CelScan-Token": "t"}


def test_fluxo_da_ordem_e_painel():
    con = db.conectar()
    oid = balcao.criar_ordem(con, ["checkup", "limpeza"], aparelho="Redmi Note 14", imei="864210357912345")
    o = balcao.ordem(con, oid)
    assert o["status"] == "aguardando" and o["valor"] == 139.80
    for st in ("analisando", "pronto", "entregue"):
        assert balcao.mudar_status(con, oid, st)
    o = balcao.ordem(con, oid)
    assert o["entregue_em"]
    p = balcao.painel(con, datetime.now())
    assert p["dia"]["entregues"] >= 1 and p["dia"]["faturamento"] >= 139.80
    assert {x["nome"] for x in p["mes"]["por_servico"]} >= {"Check-up básico", "Limpeza completa"}
    assert "Redmi Note 14" in balcao.csv_ordens(con)


def test_servico_desconhecido_e_status_invalido():
    con = db.conectar()
    import pytest
    with pytest.raises(ValueError):
        balcao.criar_ordem(con, ["inexistente"])
    oid = balcao.criar_ordem(con, ["checkup"])
    with pytest.raises(ValueError):
        balcao.mudar_status(con, oid, "voando")


def test_mensagem_whatsapp():
    o = {"id": 7, "cliente": "Maria Souza", "telefone": "(11) 98888-7777", "aparelho": "Moto G",
         "servicos": ["checkup"], "valor": 49.9, "status": "pronto"}
    m = balcao.mensagem_whatsapp(o, "Loja X")
    assert "Maria" in m["texto"] and "R$ 49,90" in m["texto"] and "pronto" in m["texto"]
    assert m["link"].startswith("https://wa.me/5511988887777?text=")


def test_api_balcao_e_precos():
    with TestClient(criar_app("t", observar=False)) as c:
        assert "checkup" in c.get("/api/servicos", headers=H).json()
        precos = c.post("/api/servicos/precos", json={"precos": {"checkup": 60}}, headers=H).json()
        assert precos["checkup"]["preco"] == 60
        sem = c.post("/api/ordens", json={"servicos": ["checkup"], "cliente_nome": "Ana"}, headers=H)
        assert sem.status_code == 422  # sem consentimento, não guarda cliente
        o = c.post("/api/ordens", json={"servicos": ["checkup"], "cliente_nome": "Ana",
                                        "cliente_telefone": "11999990000", "consentimento": True}, headers=H).json()
        assert o["valor"] == 60 and o["cliente"] == "Ana"
        r = c.post(f"/api/ordens/{o['id']}/status", json={"status": "pronto"}, headers=H).json()
        assert r["status"] == "pronto"
        assert "wa.me" in c.get(f"/api/ordens/{o['id']}/mensagem", headers=H).json()["link"]
        assert c.get("/api/painel", headers=H).json()["por_status"]["pronto"] >= 1
        assert c.get("/api/painel/ordens.csv", headers=H).text.lstrip("﻿").startswith("OS;")
