"""Modo flagrante: observa o celular enquanto a pessoa usa normalmente e pega o app que age escondido.

A cada poucos segundos, numa única chamada ao celular, lê:
- qual app está na frente (mCurrentFocus);
- tela de anúncio aberta (AdActivity do AdMob, Unity, AppLovin, Meta...) e DE QUAL APP ela é;
- janelas por cima de outros apps (sobreposição, appop SYSTEM_ALERT_WINDOW);
- conexões de internet abertas por app (/proc/net/tcp e tcp6, pelo uid), separando as feitas em segundo plano.

O que entrega: "o anúncio que apareceu do nada era do app X", "o app Y ficou conectado à internet o tempo todo
sem estar aberto". É a prova que a análise parada não consegue: o adware só mostra a cara quando está rodando.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Any

# telas cheias de anúncio dos SDKs mais usados (o pacote da janela é o app que carrega o SDK)
ANUNCIOS = re.compile(
    r"(com\.google\.android\.gms\.ads\.AdActivity|com\.unity3d\.(?:services\.ads|ads)\.|com\.applovin\.(?:adview|"
    r"mediation|sdk)|com\.facebook\.ads\.(?:AudienceNetworkActivity|internal)|com\.ironsource\.sdk|"
    r"com\.mbridge\.msdk|com\.vungle\.|com\.bytedance\.sdk\.openadsdk|com\.inmobi\.|com\.chartboost\.|"
    r"com\.adcolony\.|com\.startapp\.|com\.my\.target\.|com\.yandex\.mobile\.ads|com\.pangle\.)", re.I)
RX_FOCO = re.compile(r"mCurrentFocus=Window\{\S+ u\d+ ([\w.]+)(?:/([\w.$]+))?\}")
RX_OVERLAY = re.compile(r"package=([\w.]+) appop=SYSTEM_ALERT_WINDOW")
RX_UID = re.compile(r"^package:([\w.]+) uid:(\d+)", re.M)
AMOSTRA = ("echo @@foco; dumpsys window | grep -E 'mCurrentFocus'; echo @@ov; dumpsys window windows | "
           "grep -E 'appop=SYSTEM_ALERT_WINDOW'; echo @@tcp; cat /proc/net/tcp /proc/net/tcp6 2>/dev/null")
# janelas do próprio sistema que aparecem como foco (não contam como "app aberto")
SISTEMA_FOCO = ("com.android.systemui", "android", "com.miui.home", "com.sec.android.app.launcher",
                "com.google.android.apps.nexuslauncher", "com.android.launcher3", "com.motorola.launcher3")
LOOPBACK = ("0100007F", "00000000000000000000000001000000", "0000000000000000FFFF00000100007F")


def _secoes(texto: str) -> dict[str, str]:
    res, atual = {}, None
    for linha in texto.splitlines():
        if linha.startswith("@@"):
            atual = linha[2:].strip()
            res[atual] = ""
        elif atual:
            res[atual] += linha + "\n"
    return res


def conexoes(tcp: str) -> dict[int, int]:
    """uid -> conexões ESTABELECIDAS com endereço de fora (sem loopback)."""
    res: dict[int, int] = defaultdict(int)
    for linha in tcp.splitlines():
        p = linha.split()
        if len(p) < 8 or not p[0].endswith(":") or p[3] != "01":
            continue
        remoto = p[2].split(":")[0].upper()
        if set(remoto) == {"0"} or remoto in LOOPBACK:
            continue
        try:
            res[int(p[7])] += 1
        except ValueError:
            continue
    return dict(res)


def amostrar(texto: str) -> dict[str, Any]:
    s = _secoes(texto)
    m = RX_FOCO.search(s.get("foco", ""))
    foco, atividade = (m.group(1), m.group(2) or "") if m else (None, "")
    return {"foco": foco, "atividade": atividade, "anuncio": bool(foco and ANUNCIOS.search(atividade)),
            "sobreposicao": sorted(set(RX_OVERLAY.findall(s.get("ov", "")))), "conexoes": conexoes(s.get("tcp", "")),
            "tcp_legivel": bool(s.get("tcp", "").strip())}


def observar(ap, duracao_s: int = 120, progresso=None, cancelar=None, intervalo: float = 3.0,
             dormir=time.sleep) -> dict[str, Any]:
    uid_pkg: dict[int, list[str]] = defaultdict(list)
    for p, u in RX_UID.findall(ap.sh("pm list packages -U -3")):
        uid_pkg[int(u)].append(p)
    st: dict[str, dict[str, Any]] = defaultdict(lambda: {"frente": 0, "anuncios": 0, "anuncio_fora": 0,
                                                         "sobreposicao": 0, "rede_fundo": 0, "rede_frente": 0})
    eventos: list[dict[str, Any]] = []
    inicio, n, anterior, tcp_ok = time.monotonic(), 0, None, False
    total = max(1, int(duracao_s / intervalo))
    while n < total:
        if cancelar is not None and cancelar.is_set():
            break
        a = amostrar(ap.sh(AMOSTRA, timeout=30))
        n += 1
        tcp_ok = tcp_ok or a["tcp_legivel"]
        foco = a["foco"] if a["foco"] not in SISTEMA_FOCO else None
        t = round(time.monotonic() - inicio)
        if foco:
            st[foco]["frente"] += 1
        if a["anuncio"] and foco:
            st[foco]["anuncios"] += 1
            if anterior and anterior != foco:  # o anúncio abriu por cima de OUTRO app: adware
                st[foco]["anuncio_fora"] += 1
                eventos.append({"t": t, "pacote": foco,
                                "texto": f"anúncio de tela cheia aberto por cima de {anterior}"})
        for p in a["sobreposicao"]:
            if p not in SISTEMA_FOCO:
                st[p]["sobreposicao"] += 1
        for uid, qtd in a["conexoes"].items():
            for p in uid_pkg.get(uid, []):
                st[p]["rede_frente" if p == foco else "rede_fundo"] += 1 if qtd else 0
        if not a["anuncio"]:
            anterior = foco or anterior
        if progresso:
            progresso({"etapa": "flagrante", "descricao": "Observando o celular", "detalhe":
                       f"use o celular normalmente ({t}s de {duracao_s}s)", "atual": n, "total": total,
                       "estimativa_s": max(0, int(duracao_s - t))})
        if n < total:
            dormir(intervalo)
    return {"amostras": n, "intervalo_s": intervalo, "rede_disponivel": tcp_ok, "eventos": eventos[:50],
            "apps": ranking(st, n)}


def ranking(st: dict[str, dict[str, Any]], n: int) -> list[dict[str, Any]]:
    res = []
    for p, x in st.items():
        motivos = []
        if x["anuncio_fora"]:
            motivos.append(f"abriu {x['anuncio_fora']} anúncio(s) por cima de outro app")
        elif x["anuncios"]:
            motivos.append("mostrou anúncio de tela cheia dentro dele")
        if x["sobreposicao"]:
            motivos.append("desenhou por cima de outros apps")
        fundo_pct = round(100 * x["rede_fundo"] / n) if n else 0
        if fundo_pct >= 50 and not x["frente"]:
            motivos.append(f"usou a internet escondido em {fundo_pct}% do tempo")
        if not motivos:
            continue
        grave = bool(x["anuncio_fora"] or (x["sobreposicao"] and not x["frente"]))
        res.append({"pacote": p, **x, "rede_fundo_pct": fundo_pct, "motivos": motivos,
                    "nivel": "ALTO" if grave else "MÉDIO" if x["sobreposicao"] or fundo_pct >= 80 else "BAIXO"})
    ordem = {"ALTO": 0, "MÉDIO": 1, "BAIXO": 2}
    return sorted(res, key=lambda r: (ordem[r["nivel"]], -r["anuncio_fora"], -r["rede_fundo"]))
