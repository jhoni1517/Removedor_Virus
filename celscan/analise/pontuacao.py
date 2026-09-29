"""Pontuação de risco: aplica as regras aos dados coletados (não fala com o aparelho)."""

from __future__ import annotations

from datetime import datetime

from celscan.config import LOJAS, SMS_CONHECIDOS
from celscan.core.coleta import AppBruto, DadosAparelho

PERMISSOES = {
    "android.permission.READ_SMS": (20, "lê SMS"),
    "android.permission.RECEIVE_SMS": (15, "intercepta SMS"),
    "android.permission.SEND_SMS": (15, "envia SMS"),
    "android.permission.READ_CALL_LOG": (10, "lê registro de chamadas"),
    "android.permission.RECORD_AUDIO": (10, "grava áudio"),
    "android.permission.ACCESS_BACKGROUND_LOCATION": (10, "localização em 2º plano"),
    "android.permission.CAMERA": (5, "usa câmera"),
    "android.permission.READ_CONTACTS": (5, "lê contatos"),
    "android.permission.ACCESS_FINE_LOCATION": (5, "localização precisa"),
}
APPOPS = {
    "SYSTEM_ALERT_WINDOW": (15, "desenha sobre outros apps"),
    "REQUEST_INSTALL_PACKAGES": (15, "pode instalar outros apps"),
}


def nivel(score: int) -> str:
    if score >= 60:
        return "ALTO"
    if score >= 30:
        return "MÉDIO"
    return "BAIXO" if score > 0 else "OK"


def achados_aparelho(dados: DadosAparelho, agora: datetime | None = None) -> list[tuple[str, str]]:
    a: list[tuple[str, str]] = []
    agora = agora or datetime.now()
    i = dados.info()
    try:
        patch = datetime.strptime(i["patch_seguranca"], "%Y-%m-%d")
        meses = (agora - patch).days // 30
        if meses >= 24:
            a.append(("ALTO", f"Atualização de segurança de {meses} meses atrás"))
        elif meses >= 12:
            a.append(("MÉDIO", f"Atualização de segurança de {meses} meses atrás"))
    except ValueError:
        pass
    if dados.proxy and dados.proxy not in ("null", ":0"):
        a.append(("ALTO", f"Proxy global ativo ({dados.proxy}): o tráfego pode estar sendo interceptado"))
    if dados.su:
        a.append(("ALTO", "Root detectado (" + ", ".join(dados.su) + ")"))
    if dados.props.get("ro.boot.verifiedbootstate") == "orange" or dados.props.get("ro.boot.flash.locked") == "0":
        a.append(("MÉDIO", "Bootloader desbloqueado"))
    for o in sorted(dados.owners):
        a.append(("MÉDIO", f"Aparelho gerenciado por {o} (normal se for celular corporativo)"))
    if dados.sms and dados.sms not in SMS_CONHECIDOS:
        a.append(("MÉDIO", f"App de SMS padrão incomum: {dados.sms}"))
    return a


def pontuar_app(app: AppBruto, dados: DadosAparelho, iocs=None, permitidos: set[str] | None = None,
                agora: datetime | None = None) -> dict:
    agora = agora or datetime.now()
    pkg = app.pacote
    a: list[tuple[int, str]] = []
    ioc = iocs.checar(pkg, app.cert, app.sha256) if iocs else None
    if ioc:
        a.append((100, f"AMEAÇA CONHECIDA: {ioc}"))
    loja = LOJAS.get(app.instalador or "")
    if pkg in dados.acess:
        a.append((40, "serviço de acessibilidade ativo (pode ler e controlar a tela)"))
    if pkg in dados.admins:
        a.append((30, "administrador do dispositivo (dificulta a remoção)"))
    if pkg in dados.owners:
        a.append((30, "controla o aparelho (device owner)"))
    if pkg in dados.notif:
        a.append((20, "lê todas as notificações"))
    if not app.sistema:
        if dados.icones is not None and pkg not in dados.icones:
            a.append((20, "sem ícone na tela inicial"))
        if not loja:
            a.append((15, f"instalado fora da loja ({app.instalador or 'desconhecido'})"))
    if pkg == dados.sms and pkg not in SMS_CONHECIDOS:
        a.append((20, "definido como app de SMS padrão"))
    a += [PERMISSOES[p] for p in sorted(app.perms) if p in PERMISSOES]
    a += [APPOPS[o] for o in sorted(app.appops) if o in APPOPS]
    if app.cert and app.cert.get("debug"):
        a.append((25, "assinado com certificado de teste (debug)"))
    vt = app.vt or {}
    if vt.get("malicioso"):
        a.append((60, f"VirusTotal: {vt['malicioso']} antivírus detectaram ({vt.get('rotulo') or 'sem rótulo'})"))
    elif vt.get("conhecido") is False and not loja and not app.sistema:
        a.append((10, "APK nunca visto pelo VirusTotal"))
    if pkg in dados.sempre_ativo:
        a.append((5, "liberado da economia de bateria (roda sempre)"))
    if app.instalado and (agora - app.instalado).days < 7:
        a.append((5, f"instalado há {(agora - app.instalado).days} dia(s)"))

    score = min(100, sum(p for p, _ in a))
    permitido = pkg in (permitidos or set()) and bool(loja) and not ioc
    if permitido:
        score = min(score, 10)
    return {
        "pacote": pkg, "score": score, "nivel": "PERMITIDO" if permitido else nivel(score),
        "motivos": [m for _, m in sorted(a, reverse=True)], "ameaca": ioc,
        "instalador": app.instalador, "loja": loja, "sistema": app.sistema,
        "desativado": pkg in dados.desativados, "versao": app.versao,
        "instalado": app.instalado.isoformat() if app.instalado else None,
        "sha256": app.sha256, "cert": app.cert, "virustotal": app.vt,
        "admins": dados.admins.get(pkg, []),
    }


def pontuar(dados: DadosAparelho, iocs=None, permitidos: set[str] | None = None,
            agora: datetime | None = None) -> tuple[list[tuple[str, str]], list[dict]]:
    resultados = [pontuar_app(app, dados, iocs, permitidos, agora) for app in dados.apps.values()]
    resultados.sort(key=lambda r: r["score"], reverse=True)
    return achados_aparelho(dados, agora), resultados


def nota(achados: list[tuple[str, str]], resultados: list[dict]) -> tuple[int, str]:
    n = 100
    n -= sum(25 if nv == "ALTO" else 10 for nv, _ in achados)
    n -= sum(30 if r["nivel"] == "ALTO" else 8 if r["nivel"] == "MÉDIO" else 0 for r in resultados)
    n = max(0, n)
    if any(r.get("ameaca") for r in resultados):
        n = min(n, 20)  # ameaça conhecida = crítico, sempre
    rot = "Excelente" if n >= 90 else "Bom" if n >= 70 else "Atenção" if n >= 50 else "Crítico"
    return n, rot
