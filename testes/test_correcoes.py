"""Correções automáticas: detecta só o que está fora do normal, corrige, confere e desfaz."""

import re

import pytest

from celscan.acoes import correcoes, quarentena


class Ap:
    """Celular de mentira: configurações, 'wm' e 'Não perturbe' guardados em memória."""

    serial = "TESTE"

    def __init__(self, cfg=None, densidade=None, tamanho=None):
        self.cfg = dict(cfg or {})
        self.wm = {"density": ("440", densidade), "size": ("1080x2400", tamanho)}

    def sh(self, cmd, timeout=120, erro=False):
        if m := re.fullmatch(r"settings get (\w+) (\w+)", cmd):
            return self.cfg.get(m.group(2), "null")
        if m := re.fullmatch(r"settings put (\w+) (\w+) (\S+)", cmd):
            self.cfg[m.group(2)] = m.group(3).strip("'")
            return ""
        if m := re.fullmatch(r"settings delete (\w+) (\w+)", cmd):
            self.cfg.pop(m.group(2), None)
            return ""
        if m := re.fullmatch(r"wm (density|size)(?: (\S+))?", cmd):
            chave, valor = m.group(1), m.group(2)
            fis, forc = self.wm[chave]
            if valor == "reset":
                self.wm[chave] = (fis, None)
            elif valor:
                self.wm[chave] = (fis, valor.strip("'"))
            fis, forc = self.wm[chave]
            nome = "density" if chave == "density" else "size"
            return f"Physical {nome}: {fis}" + (f"\nOverride {nome}: {forc}" if forc else "")
        if m := re.fullmatch(r"cmd notification set_dnd (\w+)", cmd):
            self.cfg["zen_mode"] = {"off": "0", "priority": "1", "none": "2", "alarms": "3"}[m.group(1)]
            return ""
        return ""


def ids(r):
    return {p["id"] for p in r["problemas"]}


def test_celular_normal_nao_tem_problema():
    assert correcoes.verificar(Ap({"auto_time": "1", "window_animation_scale": "1.0"}))["problemas"] == []


def test_detecta_problemas_comuns():
    ap = Ap({"always_finish_activities": "1", "show_touches": "1", "auto_time": "0",
             "window_animation_scale": "5.0", "zen_mode": "2", "font_scale": "1.5"},
            densidade="300", tamanho="720x1600")
    achados = ids(correcoes.verificar(ap))
    assert achados == {"nao_manter_atividades", "mostrar_toques", "hora_automatica", "animacoes_lentas",
                       "nao_perturbe", "letras_gigantes", "zoom_tela", "resolucao_tela"}


def test_opcional_vem_marcado():
    r = correcoes.verificar(Ap({"font_scale": "1.6"}))
    assert r["problemas"][0]["opcional"] is True


def test_corrige_confere_e_desfaz():
    ap = Ap({"always_finish_activities": "1", "window_animation_scale": "10", "zen_mode": "1"}, densidade="300")
    r = correcoes.corrigir(ap, ["nao_manter_atividades", "animacoes_lentas", "nao_perturbe", "zoom_tela"])
    assert all(x["ok"] for x in r["resultado"]), r
    assert ap.cfg["always_finish_activities"] == "0" and ap.cfg["window_animation_scale"] == "1"
    assert ap.cfg["zen_mode"] == "0" and ap.wm["density"][1] is None
    assert correcoes.verificar(ap)["problemas"] == []

    ok, _msg = quarentena.restaurar(ap, r["desfazer_id"])
    assert ok
    assert ap.cfg["always_finish_activities"] == "1" and ap.cfg["window_animation_scale"] == "10"
    assert ap.cfg["zen_mode"] == "1" and ap.wm["density"][1] == "300"
    assert "transition_animation_scale" not in ap.cfg  # não existia antes: volta a não existir


def test_correcao_desconhecida_e_recusada():
    with pytest.raises(ValueError):
        correcoes.corrigir(Ap(), ["apagar_tudo"])
