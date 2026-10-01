"""Correções automáticas: acha configurações que causam "bugs" comuns e corrige com um clique.

Vale para qualquer marca, porque só usa configurações do próprio Android (sem root, sem app extra).
São os casos que mais aparecem no balcão: opções de desenvolvedor ligadas por engano, data/hora
manual, animações lentas, "Não perturbe" esquecido, zoom da tela alterado.

Regras:
- Só aponta o que está DIFERENTE do normal, com o sintoma em linguagem simples.
- Antes de mudar qualquer coisa, grava o valor atual: tudo pode ser desfeito (Quarentena/Desfazer).
- Nada é apagado e nenhum app é removido. Itens "opcionais" podem ter sido escolha do dono
  (ex.: letra grande por acessibilidade) e vêm desmarcados.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from celscan.acoes import quarentena

ANIM = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")
# zen_mode -> argumento do 'cmd notification set_dnd' para voltar ao estado anterior
ZEN = {"1": "priority", "2": "none", "3": "alarms"}


def _num(v: str | None, padrao: float) -> float:
    try:
        return float(v) if v is not None else padrao
    except ValueError:
        return padrao


@dataclass(frozen=True)
class Checagem:
    id: str
    titulo: str
    sintoma: str
    ajustes: tuple[tuple[str, str, str], ...]  # (namespace, chave, valor correto)
    ruim: Callable[[dict[str, str | None]], bool]
    opcional: bool = False


CHECAGENS: tuple[Checagem, ...] = (
    Checagem("nao_manter_atividades", "Apps fecham ou recomeçam ao trocar de app",
             "A opção de desenvolvedor \"Não manter atividades\" está ligada: o Android fecha cada app "
             "assim que você sai dele (perde o que estava digitando, o jogo recomeça).",
             (("global", "always_finish_activities", "0"),),
             lambda v: v["always_finish_activities"] == "1"),
    Checagem("mostrar_toques", "Aparecem bolinhas onde você toca",
             "A opção de desenvolvedor \"Mostrar toques\" está ligada.",
             (("system", "show_touches", "0"),), lambda v: v["show_touches"] == "1"),
    Checagem("local_ponteiro", "Linhas e números no topo da tela",
             "A opção de desenvolvedor \"Local do ponteiro\" está ligada (desenha linhas e coordenadas).",
             (("system", "pointer_location", "0"),), lambda v: v["pointer_location"] == "1"),
    Checagem("animacoes_lentas", "Celular parece lento ao abrir e fechar telas",
             "As animações estão configuradas mais lentas que o normal.",
             tuple(("global", k, "1") for k in ANIM), lambda v: any(_num(v[k], 1) > 1 for k in ANIM)),
    Checagem("hora_automatica", "Data ou hora erradas (WhatsApp e banco dão erro de conexão)",
             "A data/hora ou o fuso automáticos estão desligados. Hora errada quebra a conexão segura "
             "de vários apps.",
             (("global", "auto_time", "1"), ("global", "auto_time_zone", "1")),
             lambda v: v["auto_time"] == "0" or v["auto_time_zone"] == "0"),
    Checagem("notificacao_flutuante", "Notificações não aparecem no topo da tela",
             "As notificações flutuantes (que descem no topo) estão desligadas.",
             (("global", "heads_up_notifications_enabled", "1"),),
             lambda v: v["heads_up_notifications_enabled"] == "0"),
    Checagem("tela_sempre_ligada", "A tela não apaga enquanto carrega",
             "A opção \"Permanecer ativo\" está ligada: gasta bateria e pode marcar a tela com o tempo.",
             (("global", "stay_on_while_plugged_in", "0"),),
             lambda v: _num(v["stay_on_while_plugged_in"], 0) != 0, opcional=True),
    Checagem("letras_gigantes", "Letras muito grandes",
             "O tamanho da fonte está bem acima do normal. Pode ter sido escolhido de propósito "
             "(acessibilidade) — só corrija se o dono pedir.",
             (("system", "font_scale", "1.0"),), lambda v: _num(v["font_scale"], 1) > 1.3, opcional=True),
)
POR_ID = {c.id: c for c in CHECAGENS}
ESPECIAIS = ("nao_perturbe", "zoom_tela", "resolucao_tela")
IDS = set(POR_ID) | set(ESPECIAIS)


def _wm(saida: str) -> tuple[str | None, str | None]:
    """'wm density'/'wm size' -> (valor físico, valor forçado ou None)."""
    fis = re.search(r"Physical \w+:\s*(\S+)", saida)
    forc = re.search(r"Override \w+:\s*(\S+)", saida)
    return (fis.group(1) if fis else None, forc.group(1) if forc else None)


def _item(ident: str, titulo: str, sintoma: str, opcional: bool = False, detalhe: str = "") -> dict[str, Any]:
    return {"id": ident, "titulo": titulo, "sintoma": sintoma, "opcional": opcional, "detalhe": detalhe}


def verificar(ap) -> dict[str, Any]:
    """Lê as configurações e devolve só o que está fora do normal."""
    valores: dict[str, str | None] = {}
    for c in CHECAGENS:
        for ns, chave, _ in c.ajustes:
            if chave not in valores:
                valores[chave] = quarentena.ler_setting(ap, ns, chave)
    problemas = []
    for c in CHECAGENS:
        if c.ruim(valores):
            atuais = ", ".join(f"{ch}={valores[ch] if valores[ch] is not None else 'padrão'}"
                               for _, ch, _ in c.ajustes)
            problemas.append(_item(c.id, c.titulo, c.sintoma, c.opcional, atuais))

    zen = quarentena.ler_setting(ap, "global", "zen_mode")
    if zen in ZEN:
        problemas.append(_item("nao_perturbe", "Notificações e ligações chegam sem som",
                               "O \"Não perturbe\" está ligado e esquecido.", detalhe=f"modo {ZEN[zen]}"))
    fis, forc = _wm(ap.sh("wm density"))
    if forc and forc != fis:
        problemas.append(_item("zoom_tela", "Tudo na tela ficou pequeno demais ou grande demais",
                               "O tamanho de exibição (densidade) foi alterado.",
                               detalhe=f"de fábrica {fis}, atual {forc}"))
    fis, forc = _wm(ap.sh("wm size"))
    if forc and forc != fis:
        problemas.append(_item("resolucao_tela", "Imagem cortada, borrada ou com faixa preta",
                               "A resolução da tela foi alterada.", detalhe=f"de fábrica {fis}, atual {forc}"))
    return {"problemas": problemas, "verificados": len(CHECAGENS) + len(ESPECIAIS)}


def _igual(a: str | None, b: str) -> bool:
    if a == b:
        return True
    try:
        return a is not None and float(a) == float(b)
    except ValueError:
        return False


def corrigir(ap, ids: list[str]) -> dict[str, Any]:
    """Grava os valores atuais (para Desfazer) e depois corrige. Devolve o resultado de cada item."""
    desconhecidos = set(ids) - IDS
    if desconhecidos:
        raise ValueError(f"correção desconhecida: {', '.join(sorted(desconhecidos))}")
    ids = list(dict.fromkeys(ids))  # sem repetição, na ordem pedida

    # 1) guarda o estado de agora, ANTES de mexer
    desfazer: list[dict[str, Any]] = []
    zen = dens = tam = None
    for ident in ids:
        if ident in POR_ID:
            for ns, chave, _ in POR_ID[ident].ajustes:
                desfazer.append({"tipo": "settings", "ns": ns, "chave": chave,
                                 "anterior": quarentena.ler_setting(ap, ns, chave)})
        elif ident == "nao_perturbe":
            zen = quarentena.ler_setting(ap, "global", "zen_mode")
            if zen in ZEN:
                desfazer.append({"tipo": "cmd", "desfazer": f"cmd notification set_dnd {ZEN[zen]}",
                                 "descricao": "Não perturbe ligado de novo"})
        elif ident == "zoom_tela":
            dens = _wm(ap.sh("wm density"))[1]
            desfazer.append({"tipo": "wm", "chave": "density", "anterior": dens})
        elif ident == "resolucao_tela":
            tam = _wm(ap.sh("wm size"))[1]
            desfazer.append({"tipo": "wm", "chave": "size", "anterior": tam})
    pasta = quarentena.criar_ajuste(ap, "correcoes", f"Correções automáticas ({len(ids)})", desfazer)

    # 2) corrige e confere cada um
    resultado = []
    for ident in ids:
        if ident in POR_ID:
            c = POR_ID[ident]
            for ns, chave, correto in c.ajustes:
                ap.sh(f"settings put {ns} {chave} {correto}")
            ok = all(_igual(quarentena.ler_setting(ap, ns, ch), correto) for ns, ch, correto in c.ajustes)
            titulo = c.titulo
        elif ident == "nao_perturbe":
            ap.sh("cmd notification set_dnd off")
            ok = quarentena.ler_setting(ap, "global", "zen_mode") in (None, "0")
            titulo = "Não perturbe desligado"
        else:
            chave = "density" if ident == "zoom_tela" else "size"
            ap.sh(f"wm {chave} reset")
            ok = _wm(ap.sh(f"wm {chave}"))[1] is None
            titulo = "Tamanho de exibição de fábrica" if chave == "density" else "Resolução de fábrica"
        resultado.append({"id": ident, "titulo": titulo, "ok": ok})
    return {"resultado": resultado, "desfazer_id": pasta.name}
