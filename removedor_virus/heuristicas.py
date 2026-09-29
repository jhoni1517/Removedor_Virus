"""Regras que dão uma pontuação de risco para cada app instalado."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

ARQUIVO_ASSINATURAS = Path(__file__).resolve().parent / "dados" / "assinaturas.json"

LOJAS_OFICIAIS = {
    "com.android.vending",  # Google Play
    "com.google.android.feedback",  # Google Play (Android antigo)
    "com.sec.android.app.samsungapps",  # Galaxy Store
    "com.huawei.appmarket",  # AppGallery
    "com.xiaomi.market",  # GetApps
    "com.xiaomi.mipicks",  # GetApps
    "com.amazon.venezia",  # Amazon Appstore
}

# Permissões que contam só por serem pedidas: permissão -> (peso, explicação)
PERMISSOES_PEDIDAS = {
    "android.permission.SYSTEM_ALERT_WINDOW": (10, "pede para desenhar sobre outros apps"),
    "android.permission.REQUEST_INSTALL_PACKAGES": (10, "pode instalar outros apps"),
    "android.permission.USE_FULL_SCREEN_INTENT": (5, "pode abrir telas cheias sozinho"),
    "android.permission.WRITE_SETTINGS": (5, "altera configurações do sistema"),
    "android.permission.PACKAGE_USAGE_STATS": (5, "monitora uso de outros apps"),
    "android.permission.QUERY_ALL_PACKAGES": (3, "lista todos os apps instalados"),
    "android.permission.RECEIVE_BOOT_COMPLETED": (3, "inicia sozinho ao ligar o celular"),
}

# Permissões de espionagem: só contam se o usuário concedeu.
PERMISSOES_CONCEDIDAS = {
    "android.permission.READ_SMS": (15, "lê SMS"),
    "android.permission.RECEIVE_SMS": (10, "intercepta SMS"),
    "android.permission.SEND_SMS": (10, "envia SMS (golpes de assinatura)"),
    "android.permission.READ_CALL_LOG": (8, "lê registro de chamadas"),
    "android.permission.ACCESS_BACKGROUND_LOCATION": (8, "localização em segundo plano"),
    "android.permission.RECORD_AUDIO": (5, "grava áudio"),
    "android.permission.READ_CONTACTS": (3, "lê contatos"),
}

PESO_MALICIOSO_CONHECIDO = 100
PESO_ADMIN = 40
PESO_ACESSIBILIDADE = 30
PESO_ICONE_OCULTO = 30
PESO_LEITOR_NOTIFICACOES = 20
PESO_VT_DETECTADO = 100  # 3+ antivírus no VirusTotal
PESO_VT_POUCOS = 30  # 1-2 antivírus (pode ser falso positivo)
PESO_VT_DESCONHECIDO = 10
MINIMO_VT_CONFIRMADO = 3
PESO_SOBREPOSICAO = 25
PESO_FORA_DA_LOJA = 15
PESO_NOME_SUSPEITO = 10
PESO_RECENTE = 5
DIAS_RECENTE = 7

LIMITE_ALTO = 60
LIMITE_MEDIO = 30


@dataclass
class Assinaturas:
    pacotes_maliciosos: set[str] = field(default_factory=set)
    palavras_suspeitas: list[str] = field(default_factory=list)
    confiaveis_prefixos: tuple[str, ...] = ()


def carregar_assinaturas(caminho: Path | str | None = None) -> Assinaturas:
    dados = json.loads(Path(caminho or ARQUIVO_ASSINATURAS).read_text(encoding="utf-8"))
    return Assinaturas(
        pacotes_maliciosos=set(dados.get("pacotes_maliciosos", [])),
        palavras_suspeitas=[p.lower() for p in dados.get("palavras_suspeitas", [])],
        confiaveis_prefixos=tuple(dados.get("confiaveis_prefixos", [])),
    )


@dataclass
class App:
    pacote: str
    caminho_apk: str = ""
    instalador: str | None = None
    versao: str = ""
    instalado_em: str = ""
    permissoes: set[str] = field(default_factory=set)  # pedidas
    concedidas: set[str] = field(default_factory=set)
    admins: list[str] = field(default_factory=list)  # componentes de administrador ativos
    acessibilidade: list[str] = field(default_factory=list)  # serviços de acessibilidade ativos
    notificacoes: list[str] = field(default_factory=list)  # leitores de notificação ativos
    sobreposicao: bool = False  # permissão "sobrepor a outros apps" concedida
    icone_oculto: bool = False
    sha256: str = ""
    virustotal: dict | None = None
    pontuacao: int = 0
    motivos: list[str] = field(default_factory=list)

    @property
    def nivel(self) -> str:
        if self.pontuacao >= LIMITE_ALTO:
            return "ALTO"
        if self.pontuacao >= LIMITE_MEDIO:
            return "MEDIO"
        if self.pontuacao > 0:
            return "BAIXO"
        return "LIMPO"

    @property
    def da_loja_oficial(self) -> bool:
        return self.instalador in LOJAS_OFICIAIS

    def como_dict(self) -> dict:
        return {
            "pacote": self.pacote,
            "nivel": self.nivel,
            "pontuacao": self.pontuacao,
            "motivos": self.motivos,
            "instalador": self.instalador,
            "versao": self.versao,
            "instalado_em": self.instalado_em,
            "caminho_apk": self.caminho_apk,
            "admins": self.admins,
            "acessibilidade": self.acessibilidade,
            "notificacoes": self.notificacoes,
            "sobreposicao": self.sobreposicao,
            "icone_oculto": self.icone_oculto,
            "sha256": self.sha256,
            "virustotal": self.virustotal,
            "permissoes": sorted(self.permissoes),
            "concedidas": sorted(self.concedidas),
        }


def avaliar(app: App, assinaturas: Assinaturas, agora: datetime | None = None) -> App:
    """Calcula pontuação e motivos do app (altera e devolve o próprio objeto)."""
    pontos = 0
    motivos: list[str] = []

    def somar(peso: int, motivo: str) -> None:
        nonlocal pontos
        pontos += peso
        motivos.append(motivo)

    vt = app.virustotal or {}
    deteccoes = vt.get("malicioso", 0)
    if app.pacote in assinaturas.pacotes_maliciosos:
        somar(PESO_MALICIOSO_CONHECIDO, "malware conhecido (lista de assinaturas)")
    if deteccoes:
        rotulo = vt.get("rotulo") or "sem rótulo"
        peso = PESO_VT_DETECTADO if deteccoes >= MINIMO_VT_CONFIRMADO else PESO_VT_POUCOS
        somar(peso, f"VirusTotal: {deteccoes} antivírus detectaram ({rotulo})")
    if not pontos and app.da_loja_oficial and app.pacote.startswith(assinaturas.confiaveis_prefixos):
        app.pontuacao, app.motivos = 0, ["app confiável da loja oficial"]
        return app

    if app.admins:
        somar(PESO_ADMIN, "é administrador do dispositivo (bloqueia desinstalação)")
    if app.acessibilidade:
        somar(PESO_ACESSIBILIDADE, "serviço de acessibilidade ativo (controla a tela)")
    if app.notificacoes:
        somar(PESO_LEITOR_NOTIFICACOES, "lê todas as notificações")
    if app.icone_oculto:
        somar(PESO_ICONE_OCULTO, "sem ícone na tela inicial (app escondido)")
    if app.sobreposicao:
        somar(PESO_SOBREPOSICAO, "pode exibir janelas sobre outros apps (anúncios)")
    if not app.da_loja_oficial:
        origem = app.instalador or "desconhecida"
        somar(PESO_FORA_DA_LOJA, f"instalado fora da loja oficial (origem: {origem})")

    nome = app.pacote.lower()
    palavra = next((p for p in assinaturas.palavras_suspeitas if p in nome), None)
    if palavra:
        somar(PESO_NOME_SUSPEITO, f"nome típico de adware ('{palavra}')")

    for permissao, (peso, explicacao) in PERMISSOES_PEDIDAS.items():
        if permissao not in app.permissoes:
            continue
        if permissao == "android.permission.SYSTEM_ALERT_WINDOW" and app.sobreposicao:
            continue  # já contado como permissão concedida
        somar(peso, explicacao)
    for permissao, (peso, explicacao) in PERMISSOES_CONCEDIDAS.items():
        if permissao in app.concedidas:
            somar(peso, explicacao)
    if vt.get("conhecido") is False and not app.da_loja_oficial:
        somar(PESO_VT_DESCONHECIDO, "APK desconhecido no VirusTotal")

    instalado = _data(app.instalado_em)
    if instalado and (agora or datetime.now()) - instalado <= timedelta(days=DIAS_RECENTE):
        somar(PESO_RECENTE, f"instalado recentemente ({app.instalado_em})")

    app.pontuacao, app.motivos = pontos, motivos
    return app


def _data(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
