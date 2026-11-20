"""Por que o celular trava: diagnóstico com prova (números medidos) e o conserto de cada causa.

Feito pensando no Xiaomi/HyperOS, que trava por motivos que o usuário não vê:
- depois de cada atualização do sistema os apps rodam SEM compilar (o Android só compila de madrugada, com o
  celular parado e carregando, e o gerenciador de bateria da Xiaomi quase nunca deixa);
- o gerenciador de memória da marca fecha apps cedo demais (o app "reseta" ao voltar);
- armazenamento quase cheio deixa tudo lento (a memória interna grava devagar perto do limite);
- modo economia, calor e dias sem reiniciar seguram o processador;
- dezenas de apps da marca rodando escondidos.

E "Destravar este app" (Netflix, câmera, YouTube...): compila o app por completo, tira ele da economia de bateria
e do balde de apps "raros", limpa o cache e reabre do zero. Tudo vai para o Histórico e pode ser desfeito.
"""

from __future__ import annotations

import re
from typing import Any

from celscan.acoes import quarentena
from celscan.core.seguranca import exigir_pacote

VIDEO = {
    "com.netflix.mediaclient": "Netflix", "com.google.android.youtube": "YouTube",
    "com.amazon.avod.thirdpartyclient": "Prime Video", "com.disney.disneyplus": "Disney+",
    "com.globo.globotv": "Globoplay", "com.wbd.stream": "Max", "com.hbo.hbonow": "HBO Max",
    "com.zhiliaoapp.musically": "TikTok", "com.instagram.android": "Instagram",
    "com.crunchyroll.crunchyroid": "Crunchyroll", "com.spotify.music": "Spotify",
}
CAMERA = {
    "com.android.camera": "Câmera (Xiaomi)", "com.miui.gallery": "Galeria (Xiaomi)",
    "com.sec.android.app.camera": "Câmera (Samsung)", "com.motorola.camera3": "Câmera (Motorola)",
    "com.motorola.camera2": "Câmera (Motorola)", "com.google.android.GoogleCamera": "Câmera do Google",
}
BONS = {"speed-profile", "speed", "everything", "everything-profile", "space-profile"}
RUINS = {"verify", "quicken", "extract", "run-from-apk", "run-from-vdex-fallback", "interpret-only",
         "assume-verified", "error", "unknown"}

DIAG = r"""
sec(){ echo "@@SEC $1"; }
sec df; df /data 2>/dev/null | tail -n 1
sec lowpower; settings get global low_power
sec anim; for k in window_animation_scale transition_animation_scale animator_duration_scale; do
  settings get global $k; done
sec dexopt; dumpsys package dexopt 2>/dev/null | grep -E '^ *\[[A-Za-z0-9_.]+\] *$|status='
sec ativos; pm list packages -e
sec idle; dumpsys deviceidle whitelist 2>/dev/null
sec escrita; settings put global celscan_teste 7 2>&1; settings get global celscan_teste
settings delete global celscan_teste >/dev/null 2>&1
sec fim
"""


def ler_dexopt(texto: str) -> dict[str, str]:
    """pacote -> estado da compilação (o primeiro 'status=' de cada app)."""
    res: dict[str, str] = {}
    atual = None
    for linha in texto.splitlines():
        m = re.match(r"^\s*\[([\w.]+)\]\s*$", linha)
        if m:
            atual = m.group(1)
            continue
        s = re.search(r"\[?status=([\w-]+)", linha)
        if s and atual and atual not in res:
            res[atual] = s.group(1)
    return res


def _livre_pct(df: str) -> tuple[float | None, float | None]:
    p = df.split()
    if len(p) >= 4 and p[1].isdigit() and p[3].isdigit() and int(p[1]):
        return round(100 * int(p[3]) / int(p[1]), 1), round(int(p[3]) / 1048576, 1)
    return None, None


COMPLETOS = {"speed", "everything"}


def escrita_liberada(texto: str) -> bool | None:
    """O teste 'grava e lê de volta' passou? None = não deu para testar."""
    linhas = [x.strip() for x in (texto or "").splitlines() if x.strip()]
    if not linhas:
        return None
    return linhas[-1] == "7"


def montar(f: dict[str, Any], s: dict[str, str], marca_apps: list[dict[str, Any]],
           ajustes: dict[str, bool] | None = None) -> dict[str, Any]:
    """Junta o que foi medido e devolve os problemas (do mais grave ao mais leve) e o que já está bom.

    Tudo é conferido no ESTADO atual: o que já foi consertado não volta a aparecer como problema."""
    ajustes = ajustes or {}
    probs: list[dict[str, Any]] = []
    bons: list[str] = []

    def prob(ident: str, gravidade: str, titulo: str, prova: str, conserto: str, etapas: list[str],
             marcar: bool = True) -> None:
        probs.append({"id": ident, "gravidade": gravidade, "titulo": titulo, "prova": prova, "conserto": conserto,
                      "etapas": [e for e in etapas if not ajustes.get(e)], "marcar": marcar})

    xiaomi = any(m in (f.get("fabricante") or "").lower() for m in ("xiaomi", "redmi", "poco"))
    escrita = escrita_liberada(s.get("escrita", ""))
    if escrita is False:
        prob("bloqueado", "critica", "O celular está recusando os ajustes",
             "Teste de gravação: o Android não deixou o CelScan mudar uma configuração.",
             ("No Xiaomi: Configurações > Opções do desenvolvedor > ative 'Depuração USB (Configurações de "
              "segurança)' (pede o login da conta Mi e chip no celular). Depois clique em Analisar de novo. Sem "
              "isso, otimizações parecem feitas mas não ficam.") if xiaomi else
             "Desconecte e conecte o cabo, aceite a depuração USB no celular e analise de novo.", [])
    dex = ler_dexopt(s.get("dexopt", ""))
    ativos = set(re.findall(r"^package:([\w.]+)", s.get("ativos", ""), re.M))
    ruins = [p for p, st in dex.items() if st in RUINS]
    pct_ruim = round(100 * len(ruins) / len(dex)) if dex else None
    if pct_ruim is not None and pct_ruim >= 30:
        prob("sem_compilar", "alta", "Apps rodando sem compilar",
             f"{len(ruins)} de {len(dex)} apps ({pct_ruim}%) estão sem a otimização do Android.",
             "Compila agora o sistema e os apps mais usados (o Android só faria de madrugada, parado e carregando"
             + (", e a Xiaomi quase nunca deixa" if xiaomi else "") + "). É a causa nº 1 de travar depois de "
             "atualização.",
             ["dexopt", "sistema_leve", "compilar_mais_usados"])
    elif pct_ruim is not None:
        bons.append(f"Apps compilados ({100 - pct_ruim}% otimizados)")
    livre_pct, livre_gb = _livre_pct(s.get("df", ""))
    if livre_pct is not None and livre_pct < 20:
        prob("armazenamento", "alta" if livre_pct < 10 else "media", "Armazenamento quase cheio",
             f"Só {livre_gb} GB livres ({livre_pct}%).",
             "Com pouco espaço, a memória interna grava devagar e a câmera trava ao salvar. Libere espaço na aba "
             "Bateria e espaço (com cópia no PC) e rode a manutenção do armazenamento.",
             ["armazenamento"])
    elif livre_gb is not None:
        bons.append(f"Espaço livre ({livre_gb} GB)")
    if (s.get("lowpower") or "").strip() == "1":
        prob("economia", "alta", "Modo economia de bateria ligado", "O modo economia está ligado agora.",
             "Ele segura o processador e a tela: vídeo e jogo engasgam. Desliga (volta pelo Histórico).",
             ["economia_off"])
    else:
        bons.append("Modo economia desligado")
    status = (f.get("termico") or {}).get("status") or 0
    if status >= 2 or (f.get("bateria_c") or 0) >= 41:
        prob("calor", "alta", "Celular quente", f"Bateria a {f.get('bateria_c')} °C, nível térmico {status}.",
             "Quente, o próprio celular corta a velocidade. Tire da capa e do carregador enquanto usa vídeo/jogo; "
             "se esquenta parado, rode 'Pegar no flagra' para achar o app que trabalha escondido.", [])
    elif f.get("bateria_c"):
        bons.append(f"Temperatura normal ({f['bateria_c']} °C)")
    ram, livre = f.get("ram_gb"), f.get("ram_livre_gb")
    mem = ["fantasmas"] + (["mais_processos"] if ram and ram >= 7 else ["menos_processos"])
    if not all(ajustes.get(e) for e in mem):
        if ram and livre is not None and livre / ram < 0.2:
            prob("memoria", "media", "Memória apertada (apps reiniciando)", f"{livre} GB livres de {ram} GB.",
                 "Para de matar apps em segundo plano sem motivo e faz os apps esquecidos dormirem. Os apps voltam "
                 "de onde pararam em vez de recomeçar.", mem + ["esquecidos"])
        elif xiaomi and ram and ram >= 7:
            prob("memoria_xiaomi", "media", "Xiaomi fechando apps cedo",
                 f"{ram} GB de RAM, mas o limite de apps em segundo plano está no padrão da Xiaomi.",
                 "Libera o Android para guardar mais apps abertos (eles param de 'resetar').", mem)
    elif ram:
        bons.append("Apps em segundo plano liberados (não resetam)")
    if (f.get("ligado_h") or 0) >= 72:
        prob("reiniciar", "media", "Muitos dias sem reiniciar", f"Ligado há {round(f['ligado_h'] / 24)} dias.",
             "Só some reiniciando: o botão aparece depois de otimizar. Vários ajustes só valem depois disso.", [])
    bloat = [a for a in marca_apps if a["ativo"] and a["marcado"]]
    if bloat:
        prob("bloat", "media", "Apps inúteis da marca rodando",
             f"{len(bloat)} apps de propaganda/duplicados ativos ({', '.join(a['nome'] for a in bloat[:3])}...).",
             "Tira os apps de anúncio e duplicados (detalhes na aba Apps do sistema).", ["faxina_marca"])
    elif marca_apps:
        bons.append("Sem apps de propaganda da marca ativos")
    if xiaomi and ajustes.get("xiaomi_interface_leve") is False:
        prob("interface", "media", "Interface pesada (Xiaomi)", "Desfoque e animações no nível máximo.",
             "Usa os efeitos de aparelho básico: menos desfoque na barra e nas pastas, interface mais leve "
             "(vale após reiniciar).", ["xiaomi_interface_leve"])
    elif xiaomi and ajustes.get("xiaomi_interface_leve"):
        bons.append("Interface leve ligada")
    if xiaomi and "com.xiaomi.joyose" in ativos:
        prob("joyose", "baixa", "Limitador de desempenho Joyose ligado", "O Joyose (da Xiaomi) está ativo.",
             "Ele segura CPU/GPU em jogos e apps pesados. Desativar libera desempenho, mas o celular pode esquentar "
             "mais: só marque se quiser.", ["joyose"], marcar=False)
    escalas = [x.strip() for x in s.get("anim", "").splitlines() if x.strip() and x.strip() != "null"]
    if any(_float(x) > 1 for x in escalas):
        prob("animacoes", "baixa", "Animações lentas", f"Escalas de animação: {', '.join(escalas)}.",
             "Volta as animações para metade do tempo.", ["animacoes_rapidas"])
    video = [p for p in VIDEO if p in ativos]
    pendentes = [p for p in video if dex.get(p) not in COMPLETOS]
    if pendentes:
        estados = ", ".join(f"{VIDEO[p]} ({_estado(dex.get(p))})" for p in pendentes[:5])
        prob("video", "alta" if any(dex.get(p) in RUINS for p in pendentes) else "media",
             "Apps de vídeo sem a otimização completa", f"{estados}.",
             "Destrava cada app de vídeo: compilação completa, fora da economia de bateria e com o cache limpo.",
             ["destravar_video"])
    elif video:
        bons.append(f"Apps de vídeo destravados ({', '.join(VIDEO[p] for p in video[:3])})")
    cam = [p for p in CAMERA if p in ativos]
    cam_ruim = [p for p in cam if dex.get(p) in RUINS]
    if cam_ruim:
        prob("camera", "media", "Câmera sem compilar",
             f"{', '.join(f'{CAMERA[p]} ({_estado(dex.get(p))})' for p in cam_ruim)}.",
             "Compila câmera e galeria por completo, limpa o cache e reabre a câmera.", ["camera"])
    elif cam:
        bons.append("Câmera e galeria compiladas")
    ordem = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
    probs.sort(key=lambda p: ordem[p["gravidade"]])
    return {"problemas": probs, "bons": bons, "escrita": escrita,
            "compilacao": {"total": len(dex), "sem_compilar": len(ruins), "pct": pct_ruim},
            "livre_gb": livre_gb, "livre_pct": livre_pct, "video": video, "camera": cam}


ESTADOS = {"verify": "sem compilar", "quicken": "sem compilar", "run-from-apk": "sem compilar",
           "speed-profile": "parcial", "speed": "completa", "everything": "completa", "error": "com erro",
           None: "desconhecido"}


def _estado(st: str | None) -> str:
    return ESTADOS.get(st, st or "desconhecido")


def _float(x: str) -> float:
    try:
        return float(x)
    except ValueError:
        return 0.0


def diagnostico(ap, f: dict[str, Any] | None = None, progresso=None) -> dict[str, Any]:
    from celscan.acoes import faxina, turbo

    f = f or turbo.ficha(ap)
    if progresso:
        progresso(1, "estado de otimização de cada app (pode levar até 1 min)")
    s = ap.script(DIAG, timeout=180)
    if progresso:
        progresso(2, "espaço livre, modo economia e animações")
        progresso(3, "propaganda e apps de fábrica")
    try:
        marca = faxina.apps_da_marca(ap)["apps"]
    except Exception:  # noqa: BLE001 - diagnóstico nunca para por causa da lista
        marca = []
    try:
        ajustes = {a["id"]: bool(a.get("ligado")) for a in turbo.listar_ajustes(ap)["ajustes"]}
    except Exception:  # noqa: BLE001
        ajustes = {}
    return montar(f, s, marca, ajustes)


def destravar_app(ap, pkg: str, compilar: bool = True) -> dict[str, Any]:
    """Netflix/câmera/etc. travando: compila tudo, tira da economia de bateria, limpa o cache e reabre."""
    from celscan.acoes import turbo

    exigir_pacote(pkg)
    if f"package:{pkg}" not in ap.sh(f"pm list packages {pkg}").split():
        raise ValueError(f"{pkg} não está instalado")
    desfazer: list[dict[str, Any]] = []
    feitos: list[str] = []
    anterior = turbo.balde(ap, pkg)
    if anterior and anterior not in ("active", "exempted"):
        ap.sh(f"am set-standby-bucket {pkg} active")
        desfazer.append({"tipo": "cmd", "desfazer": f"am set-standby-bucket {pkg} {anterior}",
                         "descricao": f"{pkg} de volta ao balde '{anterior}'"})
        feitos.append(f"saiu do balde '{anterior}' (o Android segurava o app)")
    if pkg not in ap.sh("dumpsys deviceidle whitelist"):
        out = ap.sh(f"cmd deviceidle whitelist +{pkg}", erro=True)
        if "Added" in out or pkg in ap.sh("dumpsys deviceidle whitelist"):
            desfazer.append({"tipo": "cmd", "desfazer": f"cmd deviceidle whitelist -{pkg}",
                             "descricao": f"{pkg} de volta à economia de bateria"})
            feitos.append("fora da economia de bateria")
    if "ignore" in ap.sh(f"appops get {pkg} RUN_ANY_IN_BACKGROUND"):
        ap.sh(f"appops set {pkg} RUN_ANY_IN_BACKGROUND allow")
        desfazer.append({"tipo": "appops", "pacote": pkg, "op": "RUN_ANY_IN_BACKGROUND", "anterior": "ignore"})
        feitos.append("liberado para rodar em segundo plano")
    pasta = quarentena.criar_ajuste(ap, f"destravar-{pkg}", f"Destravar {pkg}", desfazer) if desfazer else None
    ap.sh(f"am force-stop {pkg}")
    limpo = ap.sh(f"pm clear --cache-only {pkg}", erro=True)
    if "Success" in limpo:
        feitos.append("cache limpo")
    if compilar:
        out = ap.sh(f"cmd package compile -m speed -f {pkg}", timeout=900, erro=True)
        feitos.append("compilado por completo" if "Success" in out else "compilação recusada pelo Android")
    feitos.append("reaberto do zero")
    return {"pacote": pkg, "feitos": feitos, "desfazer_id": pasta.name if pasta else None}


def reiniciar(ap) -> None:
    ap.adb("reboot", timeout=30)
