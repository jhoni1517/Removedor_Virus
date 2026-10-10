"""Pontuação de risco: aplica as regras (regras.yaml) aos dados coletados.

Não fala com o aparelho. Cada achado vem com título curto, "o que significa" e "o que fazer".
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from celscan.analise import certificados as certificados_mod
from celscan.analise import pix, rotulos
from celscan.analise import regras as regras_mod
from celscan.analise.regras import Regras
from celscan.config import LOJAS, LOJAS_ALTERNATIVAS, PROPRIOS, SMS_CONHECIDOS, TRANSFERENCIA
from celscan.core import seguranca
from celscan.core.coleta import AppBruto, DadosAparelho

Achado = dict[str, Any]

_padrao: Regras | None = None


def regras_padrao() -> Regras:
    global _padrao
    if _padrao is None:
        _padrao = regras_mod.carregar()
    return _padrao


def _oficiais() -> dict:
    global _certs
    if _certs is None:
        _certs = certificados_mod.carregar()
    return _certs


_certs: dict | None = None

# Quem abriu o instalador do APK, em linguagem de gente
ORIGEM = {
    "com.android.chrome": "arquivo baixado pelo Chrome", "org.mozilla.firefox": "arquivo baixado pelo Firefox",
    "com.sec.android.app.sbrowser": "arquivo baixado pelo navegador Samsung",
    "com.whatsapp": "arquivo recebido pelo WhatsApp", "com.whatsapp.w4b": "arquivo recebido pelo WhatsApp Business",
    "org.telegram.messenger": "arquivo recebido pelo Telegram", "com.google.android.gm": "anexo de e-mail",
    "com.android.bluetooth": "arquivo recebido por Bluetooth", "com.google.android.apps.nbu.files": "aberto no Files",
    "com.mi.android.globalFileexplorer": "aberto no gerenciador de arquivos",
    "com.sec.android.app.myfiles": "aberto no Meus Arquivos", "com.android.shell": "instalado por computador (adb)",
}
INSTALADORES = {
    "com.google.android.packageinstaller": "arquivo APK instalado à mão",
    "com.android.packageinstaller": "arquivo APK instalado à mão",
    "com.android.shell": "instalado por computador (adb)",
}
# Apps que naturalmente mandam muitas notificações (não contam como excesso)
MENSAGEIROS = {"com.whatsapp", "com.whatsapp.w4b", "org.telegram.messenger", "com.google.android.apps.messaging",
               "com.samsung.android.messaging", "com.google.android.gm", "com.microsoft.teams", "com.slack",
               "com.instagram.android", "com.facebook.orca", "com.discord", "org.thoughtcrime.securesms"}
SENSORES_SUSPEITOS = ("câmera", "microfone", "localização", "SMS")


def quando(seg: float | None) -> str:
    if seg is None:
        return "—"
    if seg < 120:
        return "agora há pouco"
    if seg < 3600:
        return f"há {int(seg // 60)} min"
    if seg < 86400:
        return f"há {int(seg // 3600)} h"
    return f"há {int(seg // 86400)} dia(s)"


def relacoes(dados: DadosAparelho) -> dict[str, Any]:
    """Quem instalou quem (droppers) e apps de fora da loja que chegaram em lote. Calculado uma vez."""
    cache = getattr(dados, "_relacoes", None)
    if cache is not None:
        return cache
    filhos: dict[str, list[str]] = {}
    for pkg, app in dados.apps.items():
        for pai in {app.instalador, app.origem} - {None, "", pkg}:
            p = dados.apps.get(pai)
            # Navegador, mensageiro ou gerenciador de arquivos que só ABRIU o APK a pedido do usuário não é dropper
            # (antes o WhatsApp da Play virava "instalou outros apps" quando alguém abria um APK recebido nele).
            # Dropper é app de FORA da loja que instala outros.
            if (p and not p.sistema and pai not in LOJAS and pai not in LOJAS_ALTERNATIVAS and pai not in ORIGEM
                    and pai not in TRANSFERENCIA and (p.instalador or "") not in LOJAS):
                filhos.setdefault(pai, []).append(pkg)
    fora = sorted(((a.instalado, p) for p, a in dados.apps.items()
                   if a.instalado and not a.sistema and p not in PROPRIOS
                   and (a.instalador or "") not in {*LOJAS, *LOJAS_ALTERNATIVAS, *TRANSFERENCIA, "com.android.shell"}),
                  key=lambda x: x[0])
    lote: dict[str, list[str]] = {}
    for t, pkg in fora:  # outros apps de fora da loja instalados até 10 min antes ou depois
        vizinhos = [q for t2, q in fora if q != pkg and abs((t2 - t).total_seconds()) <= 600]
        if len(vizinhos) >= 2:
            lote[pkg] = vizinhos
    rel = {"filhos": filhos, "lote": lote}
    try:
        dados._relacoes = rel  # type: ignore[attr-defined]
    except AttributeError:
        pass
    return rel


# Remover estes pode trancar a pessoa fora das contas (códigos de 2 etapas, senhas, carteiras, token do banco)
SENSIVEIS = {
    "com.google.android.apps.authenticator2", "com.azure.authenticator", "com.authy.authy", "com.twofasapp",
    "org.fedorahosted.freeotp", "com.beemdevelopment.aegis", "com.x8bit.bitwarden", "com.lastpass.lpandroid",
    "com.agilebits.onepassword", "com.dashlane", "keepass2android.keepass2android", "com.kunzisoft.keepass.free",
    "io.metamask", "com.wallet.crypto.trustapp", "com.binance.dev", "com.coinbase.android", "com.google.android.gm",
    "com.whatsapp", "com.whatsapp.w4b", "org.telegram.messenger", "org.thoughtcrime.securesms",
}


def poderes(app: AppBruto, dados: DadosAparelho) -> list[str]:
    """Poderes especiais que o app tem agora (o que ele CONSEGUE fazer além de um app comum)."""
    pkg, res = app.pacote, []
    if pkg in dados.admins:
        res.append("administrador")
    if pkg in dados.acess:
        res.append("controla a tela")
    if pkg in dados.notif:
        res.append("lê notificações")
    if "SYSTEM_ALERT_WINDOW" in app.appops:
        res.append("janela sobre outros apps")
    if "PROJECT_MEDIA" in app.appops:
        res.append("grava a tela")
    if "REQUEST_INSTALL_PACKAGES" in app.appops:
        res.append("instala apps")
    if dados.teclado == pkg:
        res.append("teclado")
    if dados.sms == pkg:
        res.append("SMS padrão")
    if {"android.permission.READ_SMS", "android.permission.RECEIVE_SMS"} & app.perms:
        res.append("lê SMS")
    return res


def sensivel(pkg: str) -> bool:
    """App cujo dado não volta só reinstalando: autenticador, senhas, carteira, banco, mensageiro."""
    return pkg in SENSIVEIS or pkg in pix.carregar().oficiais


def _proprio(app: AppBruto, dados: DadosAparelho) -> dict[str, Any]:
    return {"pacote": app.pacote, "score": 0, "nivel": "PERMITIDO", "motivos": [PROPRIOS[app.pacote]],
            "achados": [], "ameaca": None, "instalador": app.instalador, "loja": None, "sistema": False,
            "desativado": False, "versao": app.versao,
            "instalado": app.instalado.isoformat() if app.instalado else None,
            "sha256": app.sha256, "cert": app.cert, "virustotal": None, "admins": [], "nome": "CelScan Agente",
            "icone": app.icone, "atualizado": None, "ultimo_uso": None, "origem": PROPRIOS[app.pacote],
            "essencial": False, "tamanho": app.tamanho, "sem_icone": False, "disfarces": [], "sensores": {},
            "anuncios": {"tela_cheia": 0, "fora_do_app": 0, "ultimo": None, "sdks": [], "gatilhos": []},
            "notificacoes": 0, "notificacoes_dia": 0, "enviado_mb": None, "sobreposicao": False, "proprio": True,
            "tempo_uso_s": None, "bateria_mah": None, "rodando": app.rodando, "removido_antes": None,
            "vigilancia": False, "sensivel": False, "poderes": []}


def origem_legivel(app: AppBruto, dados: DadosAparelho | None = None) -> str:
    inst = app.instalador or ""
    if inst in LOJAS_ALTERNATIVAS:
        return f"{LOJAS_ALTERNATIVAS[inst]} (loja alternativa)"
    if inst in TRANSFERENCIA:
        return f"copiado de outro celular ({TRANSFERENCIA[inst]})"
    if app.origem:
        pai = dados.apps.get(app.origem) if dados else None
        return ORIGEM.get(app.origem, f"aberto pelo app {(pai.nome if pai and pai.nome else app.origem)}")
    return INSTALADORES.get(app.instalador or "", app.instalador or "origem desconhecida")


def nivel(score: int, regras: Regras | None = None) -> str:
    lim = (regras or regras_padrao()).limites
    if score >= lim.get("alto", 60):
        return "ALTO"
    if score >= lim.get("medio", 30):
        return "MÉDIO"
    return "BAIXO" if score > 0 else "OK"


def achados_aparelho(dados: DadosAparelho, regras: Regras | None = None,
                     agora: datetime | None = None, iocs: Any = None) -> list[Achado]:
    r = regras or regras_padrao()
    ra, par = r.aparelho, r.parametros
    a: list[Achado] = []
    agora = agora or datetime.now()
    try:
        patch = datetime.strptime(dados.info()["patch_seguranca"], "%Y-%m-%d")
        meses = (agora - patch).days // 30
        if meses >= par.get("patch_alto_meses", 24):
            a.append(ra["patch_muito_antigo"].achado(meses))
        elif meses >= par.get("patch_medio_meses", 12):
            a.append(ra["patch_antigo"].achado(meses))
    except ValueError:
        pass
    if dados.proxy and dados.proxy not in ("null", ":0"):
        a.append(ra["proxy_global"].achado(dados.proxy))
    if dados.su:
        a.append(ra["root"].achado(", ".join(dados.su)))
    if dados.props.get("ro.boot.verifiedbootstate") == "orange" or dados.props.get("ro.boot.flash.locked") == "0":
        a.append(ra["bootloader"].achado())
    for o in sorted(dados.owners):
        a.append(ra["gerenciado"].achado(o))
    if dados.sms and dados.sms not in SMS_CONHECIDOS:
        a.append(ra["sms_incomum"].achado(dados.sms))
    pop = sorted(p for p, an in dados.anuncios.items() if an["fora_do_app"] and p in dados.apps)
    if pop:
        a.append(ra["popups"].achado(f"{len(pop)} app(s)"))
    rede = dados.rede or {}
    if rede.get("vpn_sempre"):
        app_vpn = dados.apps.get(str(rede["vpn_sempre"]))
        a.append(ra["vpn_sempre"].achado(app_vpn.nome if app_vpn and app_vpn.nome else rede["vpn_sempre"]))
    elif rede.get("vpn_ativa"):
        a.append(ra["vpn_ativa"].achado())
    if rede.get("dns_modo") == "hostname" and rede.get("dns_servidor"):
        a.append(ra["dns_privado"].achado(rede["dns_servidor"]))
    extras = [u for u in dados.usuarios if u.get("id") != 0]
    if extras and "outros_usuarios" in ra:
        nomes = ", ".join(f"'{u['nome']}'" for u in extras[:3])
        a.append(ra["outros_usuarios"].achado(f"{len(extras)} perfil(is)/usuário(s) ({nomes})"))
    escondidos = sorted({p for pk in dados.outros_usuarios.values() for p in pk})
    if escondidos and "apps_em_outro_perfil" in ra:
        a.append(ra["apps_em_outro_perfil"].achado(", ".join(escondidos[:5]) + ("..." if len(escondidos) > 5 else "")))
    if dados.apks_guardados:
        perigosos = []
        for f in dados.apks_guardados:
            hit = iocs.checar("", None, f.get("sha256")) if (iocs and f.get("sha256")) else None
            if hit:
                f["ameaca"] = hit
                perigosos.append(f"{f['caminho'].rsplit('/', 1)[-1]} ({hit})")
        if perigosos and "apk_ameaca_guardado" in ra:
            a.append(ra["apk_ameaca_guardado"].achado("; ".join(perigosos[:3])))
        elif "apks_guardados" in ra:
            a.append(ra["apks_guardados"].achado(f"{len(dados.apks_guardados)} instalador(es) .apk"))
    bancos = pix.bancarios_instalados(dados.apps)
    suspeitos = sorted(p for p, app in dados.apps.items() if not app.sistema
                       and LOJAS.get(app.instalador or "") is None and pix.padrao_trojan(p, dados.acess, app.appops))
    if bancos and suspeitos:
        a.insert(0, ra["risco_pix"].achado(f"{', '.join(suspeitos)} junto com {', '.join(bancos)}"))
    return a


def pontuar_app(app: AppBruto, dados: DadosAparelho, iocs: Any = None, permitidos: set[str] | None = None,
                agora: datetime | None = None, regras: Regras | None = None) -> dict[str, Any]:
    r = regras or regras_padrao()
    ra, par, lim = r.apps, r.parametros, r.limites
    # hora do próprio celular: com o relógio do PC errado, "instalado há X dias" saía errado
    agora = agora or dados.relogio_aparelho or datetime.now()
    pkg = app.pacote
    if pkg in PROPRIOS:  # o próprio CelScan Agente (se ficou instalado) não é suspeito
        return _proprio(app, dados)
    a: list[Achado] = []
    ioc = iocs.checar(pkg, app.cert, app.sha256) if iocs else None
    if ioc:
        a.append(ra["ameaca_conhecida"].achado(ioc))
    loja = LOJAS.get(app.instalador or "")
    if pkg in dados.acess:
        a.append(ra["acessibilidade"].achado())
    if pkg in dados.admins:
        a.append(ra["administrador"].achado())
    if pkg in dados.owners:
        a.append(ra["device_owner"].achado())
    if pkg in dados.notif:
        a.append(ra["leitor_notificacoes"].achado())
    sem_icone = not app.sistema and dados.icones is not None and pkg not in dados.icones
    if not app.sistema:
        if sem_icone:
            a.append(ra["sem_icone"].achado())
        if not loja:
            inst = app.instalador or ""
            if inst in LOJAS_ALTERNATIVAS and "loja_alternativa" in ra:
                a.append(ra["loja_alternativa"].achado(LOJAS_ALTERNATIVAS[inst]))
            elif inst in TRANSFERENCIA and "transferido" in ra:
                a.append(ra["transferido"].achado(TRANSFERENCIA[inst]))
            else:
                a.append(ra["fora_da_loja"].achado(origem_legivel(app, dados)))
    imitado = pix.imitacao(pkg) if not app.sistema and not loja else None
    if imitado:
        a.append(ra["imita_app_conhecido"].achado(imitado))
    if not app.sistema and not loja and not imitado and (pelo_nome := pix.imitacao_por_nome(pkg, app.nome)):
        a.append(ra["imita_pelo_nome"].achado(pelo_nome))
    if not app.sistema and not loja and (finge := pix.finge_sistema(pkg, app.nome)):
        a.append(ra["finge_sistema"].achado(finge))
    if not app.sistema and app.nome_truque:
        a.append(ra["nome_com_truque"].achado())
    if not app.sistema and not loja and app.sem_rotulo:
        a.append(ra["sem_nome"].achado())
    rel = relacoes(dados)
    if pkg in rel["filhos"]:
        nomes = [dados.apps[f].nome or f for f in rel["filhos"][pkg]]
        a.append(ra["instalou_outros"].achado(", ".join(sorted(nomes)[:4]) + ("..." if len(nomes) > 4 else "")))
    if pkg in rel["lote"]:
        a.append(ra["lote_suspeito"].achado(f"{len(rel['lote'][pkg])} outros apps de fora da loja"))
    for disf in app.disfarces[:1]:
        a.append((ra["disfarce_escondido"] if sem_icone else ra["disfarce"]).achado(disf))
    # anúncios: pop-ups vistos no histórico do Android e apps preparados para isso
    an = dados.anuncios.get(pkg) or {}
    if an.get("fora_do_app"):
        ultimo = f", o último em {an['ultimo']:%d/%m às %H:%M}" if an.get("ultimo") else ""
        a.append(ra["anuncio_popup"].achado(f"{an['fora_do_app']} anúncio(s) fora do app{ultimo}"))
    elif an.get("tela_cheia"):
        a.append(ra["anuncio_tela_cheia"].achado(f"{an['tela_cheia']} anúncio(s) em tela cheia dentro do app"))
    gatilhos = [g for g in app.gatilhos if g in rotulos.GATILHOS_POPUP]
    if (not app.sistema and not an.get("fora_do_app") and app.sdks_anuncio and "SYSTEM_ALERT_WINDOW" in app.appops
            and (gatilhos or sem_icone)):
        a.append(ra["anuncio_gatilho"].achado("(" + ", ".join(gatilhos[:3] or ["sem ícone na tela inicial"]) + ")"))
    if app.anuncio_escondido and not app.sistema:
        a.append(ra["anuncio_escondido"].achado())
    if not app.sistema and (sem_icone or not loja):
        limite = par.get("sensor_dias", 7) * 86400
        for sensor in SENSORES_SUSPEITOS:
            seg = app.sensores.get(sensor)
            if seg is not None and seg < limite:
                a.append(ra["sensor_recente"].achado(f"{sensor} {quando(seg)}"))
    if (not app.sistema and (sem_icone or not loja) and app.enviado_mb
            and app.enviado_mb >= par.get("envio_mb", 50)):
        a.append(ra["envio_dados"].achado(f"{app.enviado_mb:.0f} MB"))
    n_notif = dados.notificacoes.get(pkg, 0)
    dias = dias_de_uso(dados)
    if n_notif and pkg not in MENSAGEIROS and not app.sistema:
        if n_notif / dias >= par.get("notificacoes_dia", 20):
            a.append(ra["notificacoes_excesso"].achado(f"{n_notif} notificações em {dias} dia(s)"))
    inst_atual = app.instalador or ""
    # "de fora" = instalado pelo navegador/arquivos/adb; loja alternativa e cópia de outro celular não contam
    fora = not app.sistema and not loja and inst_atual not in LOJAS_ALTERNATIVAS and inst_atual not in TRANSFERENCIA
    bancos_inst = bool(pix.bancarios_instalados(dados.apps))
    # instalador forjado: diz que veio da loja, mas quem iniciou foi o adb ou outro app comum (Android 11+)
    ini = app.iniciador
    if (loja and ini and ini != app.instalador and ini not in LOJAS and ini not in dados.sistema_pkgs
            and ini not in ("com.google.android.gms", "android") and ini not in TRANSFERENCIA
            and (ini == "com.android.shell" or ini in dados.apps)
            and "instalador_forjado" in ra):
        a.append(ra["instalador_forjado"].achado(loja))
    if app.removido_antes and not loja and "voltou" in ra:  # reinstalado da loja oficial pelo dono não é reinfecção
        a.append(ra["voltou"].achado(app.removido_antes))
    if fora and "REQUEST_INSTALL_PACKAGES" in app.appops and pkg in dados.acess and "dropper_ativo" in ra:
        a.append(ra["dropper_ativo"].achado())
    perms_sms = {"android.permission.READ_SMS", "android.permission.RECEIVE_SMS"}
    if (fora and bancos_inst and (pkg in dados.notif or app.perms & perms_sms) and pkg not in MENSAGEIROS
            and pkg != dados.sms and "intercepta_codigos" in ra):
        a.append(ra["intercepta_codigos"].achado())
    agenda = "android.permission.READ_CONTACTS" in app.perms and app.perms & {
        "android.permission.READ_SMS", "android.permission.READ_CALL_LOG"}
    if fora and agenda and pkg not in MENSAGEIROS and "golpe_emprestimo" in ra:
        a.append(ra["golpe_emprestimo"].achado())
    if fora and dados.teclado == pkg and "teclado_suspeito" in ra:
        a.append(ra["teclado_suspeito"].achado())
    escondido = sem_icone or bool(app.disfarces)
    espiona = pkg in dados.acess or pkg in dados.notif or pkg in dados.admins or any(
        (app.sensores.get(x) or 1e12) < par.get("sensor_dias", 7) * 86400 for x in SENSORES_SUSPEITOS) or (
        (app.enviado_mb or 0) >= par.get("envio_mb", 50))
    if fora and escondido and espiona and "padrao_espiao" in ra:
        a.append(ra["padrao_espiao"].achado())
    if pix.padrao_trojan(pkg, dados.acess, app.appops) and not (loja and pkg in (permitidos or set())):
        a.append(ra["trojan_bancario"].achado())
    cert_situacao = certificados_mod.conferir(pkg, app.cert, _oficiais())
    if cert_situacao == "falso":
        a.append(ra["certificado_falso"].achado(pix.carregar().oficiais.get(pkg, pix.AppConhecido(pkg, pkg, ())).nome))
    if pkg == dados.sms and pkg not in SMS_CONHECIDOS:
        a.append(ra["sms_padrao"].achado())
    a += [r.permissoes[p].achado() for p in sorted(app.perms) if p in r.permissoes]
    a += [r.appops[o].achado() for o in sorted(app.appops) if o in r.appops]
    if app.cert and app.cert.get("debug"):
        a.append(ra["certificado_debug"].achado())
    vt = app.vt or {}
    if vt.get("malicioso"):
        a.append(ra["virustotal_detectado"].achado(
            f"{vt['malicioso']} antivírus detectaram ({vt.get('rotulo') or 'sem rótulo'})"))
    elif vt.get("conhecido") is False and not loja and not app.sistema:
        a.append(ra["virustotal_desconhecido"].achado())
    if pkg in dados.sempre_ativo:
        a.append(ra["sempre_ativo"].achado())
    if app.instalado and (agora - app.instalado).days < par.get("recente_dias", 7):
        a.append(ra["instalado_recente"].achado((agora - app.instalado).days))

    a.sort(key=lambda x: x["peso"], reverse=True)
    score = min(lim.get("maximo", 100), sum(x["peso"] for x in a))
    permitido = pkg in (permitidos or set()) and bool(loja) and not ioc
    if permitido:
        score = min(score, lim.get("permitido_teto", 10))
    pod = poderes(app, dados)
    return {
        "pacote": pkg, "score": score, "nivel": "PERMITIDO" if permitido else nivel(score, r),
        "motivos": [x["titulo"] for x in a], "achados": a, "ameaca": ioc,
        "instalador": app.instalador, "loja": loja, "sistema": app.sistema,
        "desativado": pkg in dados.desativados, "versao": app.versao,
        "instalado": app.instalado.isoformat() if app.instalado else None,
        "sha256": app.sha256, "cert": app.cert, "virustotal": app.vt,
        "admins": dados.admins.get(pkg, []),
        "nome": app.nome, "icone": app.icone,
        "atualizado": app.atualizado.isoformat() if app.atualizado else None,
        "ultimo_uso": app.ultimo_uso.isoformat() if app.ultimo_uso else None,
        "origem": None if loja or app.sistema else origem_legivel(app, dados),
        "essencial": seguranca.essencial(pkg, {dados.home or "", dados.teclado or ""}),
        "tamanho": app.tamanho, "sem_icone": sem_icone, "disfarces": app.disfarces,
        "sensores": dict(sorted(app.sensores.items(), key=lambda x: x[1])),
        "anuncios": {"tela_cheia": an.get("tela_cheia", 0), "fora_do_app": an.get("fora_do_app", 0),
                     "ultimo": an["ultimo"].isoformat() if an.get("ultimo") else None,
                     "sdks": sorted(set(app.sdks_anuncio) | set(an.get("sdks") or ())), "gatilhos": app.gatilhos},
        "notificacoes": n_notif, "notificacoes_dia": round(n_notif / dias, 1) if n_notif else 0,
        "enviado_mb": app.enviado_mb,
        "sobreposicao": "SYSTEM_ALERT_WINDOW" in app.appops,
        "tempo_uso_s": app.tempo_uso_s, "bateria_mah": app.bateria_mah, "rodando": app.rodando,
        "removido_antes": app.removido_antes,
        "vigilancia": bool(ioc and any(p in ioc.lower() for p in ("stalkerware", "spyware", "pegasus", "predator")))
        or any(x["chave"] == "padrao_espiao" for x in a),
        "sensivel": sensivel(pkg),
        "poderes": pod,
        "seguro_porque": _por_que_seguro(app, loja, permitido, cert_situacao, iocs, pod),
    }


def _por_que_seguro(app: AppBruto, loja: str | None, permitido: bool, cert: str | None, iocs: Any,
                    poderes_app: list[str]) -> list[str]:
    """Os sinais bons que o técnico pode mostrar ao cliente ("por que esse eu deixei?")."""
    res = []
    if permitido:
        res.append("está na lista de apps permitidos desta loja")
    if app.sistema:
        res.append("veio de fábrica no celular")
    elif loja:
        res.append(f"instalado pela {loja}")
    if cert == "ok":
        res.append("assinatura digital igual à do app oficial")
    if iocs and app.sha256:
        res.append("não está na lista de ameaças conhecidas")
    if not poderes_app:
        res.append("não tem nenhum poder especial")
    return res


def pontuar(dados: DadosAparelho, iocs: Any = None, permitidos: set[str] | None = None,
            agora: datetime | None = None, regras: Regras | None = None) -> tuple[list[Achado], list[dict[str, Any]]]:
    r = regras or regras_padrao()
    resultados = [pontuar_app(app, dados, iocs, permitidos, agora, r) for app in dados.apps.values()]
    _mesmo_autor(resultados, r)
    # ordem estável: risco, depois nome (a lista não "pula" entre varreduras iguais)
    resultados.sort(key=lambda x: (-x["score"], (x.get("nome") or x["pacote"]).lower(), x["pacote"]))
    return achados_aparelho(dados, regras, agora, iocs), resultados


def _mesmo_autor(resultados: list[dict[str, Any]], regras: Regras) -> None:
    """App de fora da loja assinado pelo mesmo certificado de um app de risco alto: mesmo autor."""
    regra = regras.apps.get("mesmo_autor")
    if regra is None:
        return
    perigosos: dict[str, str] = {}
    for x in resultados:
        cert = (x.get("cert") or {}).get("sha256")
        if cert and x["nivel"] == "ALTO" and not x.get("loja") and not x.get("sistema"):
            perigosos.setdefault(cert, x.get("nome") or x["pacote"])
    lim = regras.limites
    for x in resultados:
        cert = (x.get("cert") or {}).get("sha256")
        dono = perigosos.get(cert) if cert else None
        if not dono or x["nivel"] in ("ALTO", "PERMITIDO") or x.get("loja") or x.get("sistema"):
            continue
        ach = regra.achado(dono)
        x["achados"].append(ach)
        x["achados"].sort(key=lambda a: a["peso"], reverse=True)
        x["motivos"] = [a["titulo"] for a in x["achados"]]
        x["score"] = min(lim.get("maximo", 100), sum(a["peso"] for a in x["achados"]))
        x["nivel"] = nivel(x["score"], regras)


def dias_de_uso(dados) -> int:
    """Dias cobertos pelo histórico de uso (mínimo 1; 36 h contam como 2 dias)."""
    if not dados.periodo_uso:
        return 1
    seg = (dados.periodo_uso[1] - dados.periodo_uso[0]).total_seconds()
    return max(1, math.ceil(seg / 86400))


def decompor(achados: list[Achado], resultados: list[dict[str, Any]], regras: Regras | None = None) -> list[dict]:
    """O que tirou pontos da nota, do maior para o menor (mostrado ao lado do medidor)."""
    cfg = (regras or regras_padrao()).nota
    itens = []
    for a in achados:
        p = cfg.get("aparelho_alto", 25) if a["nivel"] == "ALTO" else cfg.get("aparelho_outro", 10) \
            if a["nivel"] == "MÉDIO" else 0
        if p:
            itens.append({"texto": a["titulo"], "pontos": -p})
    for r in resultados:
        p = cfg.get("app_alto", 30) if r["nivel"] == "ALTO" else cfg.get("app_medio", 8) if r["nivel"] == "MÉDIO" else 0
        if p:
            itens.append({"texto": r.get("nome") or r["pacote"], "pontos": -p})
    itens.sort(key=lambda i: (i["pontos"], i["texto"]))
    # o teto por ameaça conhecida também tira pontos: sem esta linha a soma não batia com a nota
    soma = max(0, 100 + sum(i["pontos"] for i in itens))
    teto = cfg.get("teto_com_ameaca", 20)
    if any(r.get("ameaca") for r in resultados) and soma > teto:
        itens.insert(0, {"texto": "Ameaça conhecida: nota limitada", "pontos": teto - soma})
    return itens


def nota(achados: list[Achado], resultados: list[dict[str, Any]], regras: Regras | None = None) -> tuple[int, str]:
    cfg = (regras or regras_padrao()).nota
    n = 100
    # avisos BAIXO (DNS privado, VPN conectada) são informativos: não tiram pontos
    n -= sum(cfg.get("aparelho_alto", 25) if a["nivel"] == "ALTO" else cfg.get("aparelho_outro", 10)
             if a["nivel"] == "MÉDIO" else 0 for a in achados)
    n -= sum(cfg.get("app_alto", 30) if r["nivel"] == "ALTO" else cfg.get("app_medio", 8) if r["nivel"] == "MÉDIO"
             else 0 for r in resultados)
    n = max(0, n)
    if any(r.get("ameaca") for r in resultados):
        n = min(n, cfg.get("teto_com_ameaca", 20))  # ameaça conhecida = crítico, sempre
    rotulos = cfg.get("rotulos") or [[90, "Excelente"], [70, "Bom"], [50, "Atenção"], [0, "Crítico"]]
    rot = next(nome for minimo, nome in rotulos if n >= minimo)
    return n, rot
