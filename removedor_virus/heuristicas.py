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
}

# permissão -> (peso, explicação)
PERMISSOES_RISCO = {
    "android.permission.SYSTEM_ALERT_WINDOW": (10, "pede para desenhar sobre outros apps"),
    "android.permission.REQUEST_INSTALL_PACKAGES": (10, "pode instalar outros apps"),
    "android.permission.USE_FULL_SCREEN_INTENT": (5, "pode abrir telas cheias sozinho"),
    "android.permission.WRITE_SETTINGS": (5, "altera configurações do sistema"),
    "android.permission.PACKAGE_USAGE_STATS": (5, "monitora uso de outros apps"),
    "android.permission.READ_SMS": (8, "lê SMS (golpes de assinatura)"),
    "android.permission.RECEIVE_SMS": (8, "intercepta SMS (golpes de assinatura)"),
    "android.permission.QUERY_ALL_PACKAGES": (3, "lista todos os apps instalados"),
    "android.permission.RECEIVE_BOOT_COMPLETED": (3, "inicia sozinho ao ligar o celular"),
}

PESO_MALICIOSO_CONHECIDO = 100
PESO_ADMIN = 40
PESO_ACESSIBILIDADE = 30
PESO_ICONE_OCULTO = 30
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
    permissoes: set[str] = field(default_factory=set)
    admins: list[str] = field(default_factory=list)  # componentes de administrador ativos
    acessibilidade: list[str] = field(default_factory=list)  # serviços de acessibilidade ativos
    sobreposicao: bool = False  # permissão "sobrepor a outros apps" concedida
    icone_oculto: bool = False
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
            "sobreposicao": self.sobreposicao,
            "icone_oculto": self.icone_oculto,
            "permissoes": sorted(self.permissoes),
        }


def avaliar(app: App, assinaturas: Assinaturas, agora: datetime | None = None) -> App:
    """Calcula pontuação e motivos do app (altera e devolve o próprio objeto)."""
    pontos = 0
    motivos: list[str] = []

    def somar(peso: int, motivo: str) -> None:
        nonlocal pontos
        pontos += peso
        motivos.append(motivo)

    if app.pacote in assinaturas.pacotes_maliciosos:
        somar(PESO_MALICIOSO_CONHECIDO, "malware conhecido (lista de assinaturas)")
    elif app.da_loja_oficial and app.pacote.startswith(assinaturas.confiaveis_prefixos):
        app.pontuacao, app.motivos = 0, ["app confiável da loja oficial"]
        return app

    if app.admins:
        somar(PESO_ADMIN, "é administrador do dispositivo (bloqueia desinstalação)")
    if app.acessibilidade:
        somar(PESO_ACESSIBILIDADE, "serviço de acessibilidade ativo (controla a tela)")
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

    for permissao, (peso, explicacao) in PERMISSOES_RISCO.items():
        if permissao not in app.permissoes:
            continue
        if permissao == "android.permission.SYSTEM_ALERT_WINDOW" and app.sobreposicao:
            continue  # já contado como permissão concedida
        somar(peso, explicacao)

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
