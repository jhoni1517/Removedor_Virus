"""Coleta de dados brutos do Android numa única chamada ao aparelho (sem análise)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

from celscan.analise import apksig
from celscan.config import PASTAS_SISTEMA
from celscan.core import log, parsers
from celscan.core.adb import AdbErro, Aparelho

# PROJECT_MEDIA = captura/transmissão da tela (usada por trojans bancários como o PixRevolution)
APPOPS_COLETADOS = ("SYSTEM_ALERT_WINDOW", "REQUEST_INSTALL_PACKAGES", "PROJECT_MEDIA")
# Operações com horário do último uso (painel "quem usou câmera/microfone")
SENSORES = {"CAMERA": "câmera", "RECORD_AUDIO": "microfone", "FINE_LOCATION": "localização",
            "COARSE_LOCATION": "localização", "READ_SMS": "SMS", "READ_CONTACTS": "contatos",
            "READ_CALL_LOG": "chamadas"}

SCRIPT = r"""
sec(){ echo "@@SEC $1"; }
sec props; getprop
sec pkgs; pm list packages -f -i {F}
sec syspkgs; pm list packages -s
sec desativados; pm list packages -d
sec acess; settings get secure enabled_accessibility_services
sec notif; settings get secure enabled_notification_listeners
sec sms; settings get secure sms_default_application
sec proxy; settings get global http_proxy
sec owners; dpm list-owners 2>&1
sec admins; dumpsys device_policy 2>&1
sec launcher; cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER 2>&1
sec idle; dumpsys deviceidle whitelist 2>&1
sec su; for f in /system/bin/su /system/xbin/su /sbin/su /su/bin/su /debug_ramdisk/su; do [ -e "$f" ] && echo "$f"; done
sec pkgdump; dumpsys package packages 2>&1
sec teclado; settings get secure default_input_method
sec home; cmd package resolve-activity --brief -c android.intent.category.HOME -a android.intent.action.MAIN 2>&1
sec rede; settings get global private_dns_mode; settings get global private_dns_specifier; settings get secure always_on_vpn_app; dumpsys connectivity 2>/dev/null | grep -ciE 'Transports: [A-Z|]*VPN|VPN CONNECTED'
sec uso; dumpsys usagestats 2>/dev/null | grep -E 'type=(ACTIVITY_RESUMED|MOVE_TO_FOREGROUND|NOTIFICATION_INTERRUPTION)|lastTimeUsed=|In-memory (daily|weekly) stats'
sec consumo; dumpsys batterystats --checkin 2>/dev/null | grep -E '^9,[0-9]+,(i,uid|l,nt|l,pwi),'
sec relogio; date +%s
sec rodando; ps -A -o NAME 2>/dev/null || ps 2>/dev/null
sec usuarios; pm list users 2>&1
sec outros; for u in $(pm list users 2>/dev/null | sed -n 's/.*UserInfo{\([0-9]*\):.*/\1/p'); do [ "$u" != "0" ] && { echo "@@USER $u"; pm list packages -3 -i --user $u 2>/dev/null; }; done
sec apks; find /sdcard -maxdepth 5 -type f -iname '*.apk' -size -100M 2>/dev/null | head -20 | while read f; do printf '%s\t%s\t%s\n' "$(stat -c %s "$f" 2>/dev/null)" "$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1)" "$f"; done
sec appops
for p in $(pm list packages {F} | sed 's/^package://'); do
  echo "@@PKG $p"
  cmd appops get $p 2>/dev/null || appops get $p 2>/dev/null
done
sec fim
"""

# Seção do script -> o que o usuário deixa de ver se ela falhar.
VERIFICACOES = {
    "props": "informações do aparelho",
    "launcher": "apps escondidos (sem ícone)",
    "admins": "administradores do aparelho",
    "owners": "gerenciamento do aparelho (device owner)",
    "pkgdump": "permissões e data de instalação dos apps",
    "idle": "apps liberados da economia de bateria",
    "acess": "acessibilidade",
    "notif": "leitores de notificação",
    "sms": "app de SMS padrão",
    "proxy": "proxy global",
    "uso": "pop-ups de anúncio, notificações em excesso e apps esquecidos (histórico de uso)",
}

# Seções em que vazio/"null" significa "nenhum configurado" (não é erro).
OPCIONAIS = {"acess", "notif", "sms", "proxy"}


def avisos_da_coleta(s: dict[str, str], dados: DadosAparelho, dump: dict) -> list[str]:
    """Lista, em linguagem simples, as verificações que não funcionaram neste aparelho."""
    falhas: list[str] = []
    for secao, nome in VERIFICACOES.items():
        txt = s.get(secao)
        if txt is None:
            falhou = True
        elif secao in OPCIONAIS:
            valor = txt.strip()
            falhou = valor not in ("", "null") and parsers.indisponivel(valor)
        else:
            falhou = parsers.indisponivel(txt)
        if secao == "launcher" and dados.icones is None:
            falhou = True
        if secao == "pkgdump" and not falhou and not any(dump.get(p) for p in dados.apps):
            falhou = True
        if falhou:
            falhas.append(nome)
    if parsers.appops_indisponivel(s.get("appops", "")):
        falhas.append("sobreposição de tela e instalação de apps")
    return [f"Verificação de {nome} não disponível neste aparelho." for nome in falhas]


HASHES = ("pm list packages -f {F} | sed 's/^package://; s/=[^=]*$//' | while read f; do "
          "printf '@@H\\t%s\\t%s\\t%s\\n' \"$(stat -c %s \"$f\" 2>/dev/null)\" "
          "\"$(sha256sum \"$f\" 2>/dev/null | cut -d' ' -f1)\" \"$f\"; done")


@dataclass
class AppBruto:
    pacote: str
    apk: str
    instalador: str | None
    sistema: bool
    perms: set[str] = field(default_factory=set)  # permissões concedidas
    versao: str | None = None
    instalado: datetime | None = None
    appops: set[str] = field(default_factory=set)  # operações liberadas
    sha256: str | None = None
    tamanho: int | None = None
    cert: dict | None = None
    vt: dict | None = None
    nome: str | None = None
    icone: str | None = None  # data URI do ícone (PNG, WebP ou SVG)
    atualizado: datetime | None = None
    origem: str | None = None  # app que abriu o instalador (Chrome, WhatsApp...)
    sdks_anuncio: list[str] = field(default_factory=list)
    gatilhos: list[str] = field(default_factory=list)
    disfarces: list[str] = field(default_factory=list)
    anuncio_escondido: bool = False
    sensores: dict[str, float] = field(default_factory=dict)  # câmera/microfone/... -> segundos desde o uso
    ultimo_uso: datetime | None = None
    enviado_mb: float | None = None  # dados enviados pela internet desde a última carga completa
    nome_truque: bool = False  # nome com caracteres invisíveis/de inversão de texto
    sem_rotulo: bool = False  # APK lido, mas sem nome para mostrar
    iniciador: str | None = None  # quem realmente iniciou a instalação (Android 11+)
    tempo_uso_s: int | None = None  # tempo de tela na última semana
    bateria_mah: float | None = None  # energia gasta desde a última carga completa
    rodando: bool = False  # tinha processo vivo no momento da análise
    removido_antes: str | None = None  # data em que o CelScan já tinha removido este app (voltou?)


@dataclass
class DadosAparelho:
    serial: str
    props: dict[str, str]
    apps: dict[str, AppBruto]
    desativados: set[str] = field(default_factory=set)
    acess: set[str] = field(default_factory=set)
    notif: set[str] = field(default_factory=set)
    admins: dict[str, list[str]] = field(default_factory=dict)  # pacote -> componentes
    owners: set[str] = field(default_factory=set)
    sms: str = ""
    proxy: str = ""
    su: list[str] = field(default_factory=list)
    sempre_ativo: set[str] = field(default_factory=set)
    icones: set[str] | None = None
    avisos: list[str] = field(default_factory=list)
    anuncios: dict[str, dict] = field(default_factory=dict)  # pacote -> pop-ups/tela cheia
    notificacoes: dict[str, int] = field(default_factory=dict)  # pacote -> notificações que tocaram
    rede: dict[str, object] = field(default_factory=dict)
    home: str | None = None
    teclado: str | None = None
    periodo_uso: tuple[datetime, datetime] | None = None
    sistema_pkgs: set[str] = field(default_factory=set)
    usuarios: list[dict] = field(default_factory=list)  # perfis/usuários do aparelho (0 = dono)
    outros_usuarios: dict[int, dict[str, str | None]] = field(default_factory=dict)  # usuário -> apps só lá
    apks_guardados: list[dict] = field(default_factory=list)  # instaladores .apk soltos no armazenamento
    relogio_aparelho: datetime | None = None

    def info(self) -> dict[str, str]:
        g = self.props.get
        return {
            "fabricante": g("ro.product.manufacturer", "?"), "modelo": g("ro.product.model", "?"),
            "android": g("ro.build.version.release", "?"), "sdk": g("ro.build.version.sdk", "?"),
            "patch_seguranca": g("ro.build.version.security_patch", "?"), "serial": self.serial,
        }


def _limpo(valor: str | None) -> str:
    """Normaliza saídas do settings: 'null' e vazio viram '' (nada configurado)."""
    v = (valor or "").strip()
    return "" if v == "null" else v


def filtro(sistema: bool) -> str:
    return "-e" if sistema else "-3"


def montar(serial: str, s: dict[str, str]) -> DadosAparelho:
    """Transforma as seções brutas do script em DadosAparelho."""
    if "fim" not in s:
        raise AdbErro("Coleta interrompida — resultado incompleto. Reconecte o cabo e tente de novo.")
    dump = parsers.pkgdump(s.get("pkgdump", ""))
    ops = parsers.appops(s.get("appops", ""), set(APPOPS_COLETADOS))
    tempos = parsers.appops_tempos(s.get("appops", ""), set(SENSORES))
    telas, ultimo_uso, notificacoes = parsers.uso(s.get("uso", ""))
    from celscan.acoes.consumo import parse as parse_consumo
    rede_apps = parse_consumo(s.get("consumo", ""))
    # Apps de sistema atualizados pela loja migram para /data/app e perdem o caminho de sistema; por isso
    # perguntamos ao próprio Android quais são de sistema (pm list packages -s), além de olhar o caminho.
    syspkgs = parsers.desativados(s.get("syspkgs", ""))
    tempo_uso = parsers.tempo_de_uso(s.get("uso", ""))
    bateria = parsers.bateria_por_app(s.get("consumo", ""))
    vivos = parsers.rodando(s.get("rodando", ""))
    apps: dict[str, AppBruto] = {}
    for pkg, (caminho, inst) in parsers.pacotes(s.get("pkgs", "")).items():
        d = dump.get(pkg, {})
        apps[pkg] = AppBruto(
            pacote=pkg, apk=caminho, instalador=inst,
            sistema=caminho.startswith(PASTAS_SISTEMA) or pkg in syspkgs,
            perms=d.get("perms", set()), versao=d.get("versao"), instalado=d.get("instalado"),
            appops=ops.get(pkg, set()), atualizado=d.get("atualizado"), origem=d.get("origem"),
            ultimo_uso=ultimo_uso.get(pkg), enviado_mb=(rede_apps.get(pkg) or {}).get("enviado_mb"),
            iniciador=d.get("iniciador"), tempo_uso_s=tempo_uso.get(pkg), bateria_mah=bateria.get(pkg),
            rodando=pkg in vivos,
        )
        for op, seg in tempos.get(pkg, {}).items():  # sensores: guarda o uso mais recente por tipo
            nome = SENSORES[op]
            if seg < apps[pkg].sensores.get(nome, 1e12):
                apps[pkg].sensores[nome] = seg
    if not apps:
        raise AdbErro("Nenhum app listado — o 'pm list packages' falhou.")
    dados = DadosAparelho(
        serial=serial,
        props=parsers.props(s.get("props", "")),
        apps=apps,
        desativados=parsers.desativados(s.get("desativados", "")),
        acess=parsers.componentes(s.get("acess")),
        notif=parsers.componentes(s.get("notif")),
        admins=parsers.admins(s.get("admins", "")),
        owners=parsers.owners(s.get("owners", "")),
        sms=_limpo(s.get("sms")),
        proxy=(s.get("proxy") or "").strip(),
        su=parsers.linhas_nao_vazias(s.get("su", "")),
        sempre_ativo=parsers.sempre_ativo(s.get("idle", "")),
        icones=parsers.launcher(s.get("launcher", "")),
        notificacoes=notificacoes,
        rede=parsers.rede(s.get("rede", "")),
        home=parsers.home(s.get("home", "")),
        teclado=parsers.teclado(s.get("teclado", "")),
        periodo_uso=parsers.periodo_eventos(s.get("uso", "")),
        sistema_pkgs=syspkgs,
        usuarios=parsers.usuarios(s.get("usuarios", "")),
        apks_guardados=parsers.apks_guardados(s.get("apks", "")),
    )
    epoch = parsers.relogio(s.get("relogio", ""))
    # relógio zerado (bateria removida, 1970) não serve de referência: aí vale a hora do PC
    dados.relogio_aparelho = datetime.fromtimestamp(epoch) if epoch and epoch > 1_420_070_400 else None
    # apps que existem SÓ em outro usuário/perfil (o resto da análise vê só o dono, usuário 0)
    dados.outros_usuarios = {u: {p: i for p, i in pk.items() if p not in apps}
                             for u, pk in parsers.pacotes_por_usuario(s.get("outros", "")).items()}
    dados.outros_usuarios = {u: pk for u, pk in dados.outros_usuarios.items() if pk}
    from celscan.analise.rotulos import sdk_de
    dados.anuncios = parsers.anuncios(telas, sdk_de)
    dados.avisos = avisos_da_coleta(s, dados, dump)
    return dados


def coletar(ap: Aparelho, sistema: bool = False) -> DadosAparelho:
    return montar(ap.serial, ap.script(SCRIPT.replace("{F}", filtro(sistema)), timeout=900))


# 3.3: tamanho + data de modificação de cada APK (rápido). Só os APKs novos ou trocados passam pelo sha256sum;
# os demais vêm do cache deste PC. Na 2ª varredura do mesmo celular a etapa cai de ~40 s para ~2 s.
STATS = ("pm list packages -f {F} | sed 's/^package://; s/=[^=]*$//' | while read f; do "
         "printf '@@S\\t%s\\t%s\\n' \"$(stat -c '%s %Y' \"$f\" 2>/dev/null)\" \"$f\"; done")
HASH_LISTA = ("for f in {L}; do printf '@@H\\t%s\\t%s\\t%s\\n' \"$(stat -c %s \"$f\" 2>/dev/null)\" "
              "\"$(sha256sum \"$f\" 2>/dev/null | cut -d' ' -f1)\" \"$f\"; done")
LIMITE_LISTA = 3000  # aparelhos antigos aceitam comandos de no máximo ~4 KB pelo adb


def _arquivo_cache_hash(serial: str):
    from celscan.config import DIR
    return DIR / "cache" / f"hashes_{re.sub(r'[^A-Za-z0-9_.-]', '_', serial)}.json"


def _ler_cache_hash(serial: str) -> dict[str, list]:
    import json
    try:
        dados = json.loads(_arquivo_cache_hash(serial).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_cache_hash(serial: str, cache: dict[str, list]) -> None:
    import json
    import os
    alvo = _arquivo_cache_hash(serial)
    try:
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        os.replace(tmp, alvo)
    except OSError as e:
        log.LOGGER.info("cache de hashes não gravado: %s", e)


def _ler_linha_hash(linha: str, por_caminho: dict[str, AppBruto]) -> AppBruto | None:
    partes = linha.split("\t")
    if len(partes) != 4 or partes[0] != "@@H":
        return None
    app = por_caminho.get(partes[3])
    if not app:
        return None
    app.tamanho = int(partes[1]) if partes[1].isdigit() else None
    app.sha256 = partes[2] if re.fullmatch(r"[0-9a-f]{64}", partes[2]) else None
    return app


def calcular_hashes(ap: Aparelho, dados: DadosAparelho, sistema: bool = False) -> Iterator[str]:
    """Gerador: devolve cada pacote conforme o hash sai do aparelho (ou do cache, se o APK não mudou)."""
    import shlex

    por_caminho = {a.apk: a for a in dados.apps.values()}
    cache = _ler_cache_hash(ap.serial)
    estado: dict[str, tuple[int, int]] = {}  # caminho -> (tamanho, modificado)
    try:
        for linha in ap.linhas(STATS.replace("{F}", filtro(sistema))):
            partes = linha.split("\t")
            if len(partes) == 3 and partes[0] == "@@S":
                num = partes[1].split()
                if len(num) == 2 and num[0].isdigit() and num[1].isdigit():
                    estado[partes[2]] = (int(num[0]), int(num[1]))
    except AdbErro as e:
        log.LOGGER.info("stat dos APKs falhou (%s); calculando todos os hashes", e)
    faltam: list[str] = []
    novo_cache: dict[str, list] = {}
    entregues: set[str] = set()
    for caminho, (tam, mod) in estado.items():
        app = por_caminho.get(caminho)
        if not app:
            continue
        c = cache.get(caminho)
        if isinstance(c, list) and len(c) == 3 and c[0] == tam and c[1] == mod and c[2]:
            app.tamanho, app.sha256 = tam, c[2]
            novo_cache[caminho] = c
            entregues.add(app.pacote)
            yield app.pacote
        else:
            faltam.append(caminho)
    sem_estado = [a.apk for a in dados.apps.values() if a.apk and a.apk not in estado]
    lista = " ".join(shlex.quote(c) for c in faltam)
    if not estado or sem_estado or len(lista) > LIMITE_LISTA:
        comando = HASHES.replace("{F}", filtro(sistema))  # sem stat (ou lista grande demais): tudo, como antes
    else:
        comando = HASH_LISTA.replace("{L}", lista) if faltam else ""
    if comando:
        for linha in ap.linhas(comando):
            app = _ler_linha_hash(linha, por_caminho)
            if not app:
                continue
            if app.sha256 and app.apk in estado:
                novo_cache[app.apk] = [*estado[app.apk], app.sha256]
            if app.pacote not in entregues:
                entregues.add(app.pacote)
                yield app.pacote
    _gravar_cache_hash(ap.serial, novo_cache)


def ler_certificado(ap: Aparelho, app: AppBruto) -> None:
    if app.tamanho:
        try:
            app.cert = apksig.ler_remoto(ap, app.apk, app.tamanho)
        except Exception:
            app.cert = None


def ler_rotulo(ap: Aparelho, app: AppBruto) -> None:
    """Nome e ícone reais do app (só faz sentido com o tamanho do APK já conhecido)."""
    from celscan.analise import rotulos

    if not app.tamanho:
        return
    try:
        r = rotulos.obter(ap, app.pacote, app.apk, app.tamanho, app.sha256)
        # nome/ícone vindos do CelScan Agente têm prioridade; o manifesto sempre é lido (anúncios, disfarces...)
        if not app.nome or app.nome == app.pacote:
            app.nome = r.nome
        app.icone = app.icone or rotulos.icone_data_uri(r)
        app.sdks_anuncio, app.gatilhos, app.disfarces = r.sdks_anuncio, r.gatilhos, r.disfarces
        app.anuncio_escondido, app.nome_truque, app.sem_rotulo = r.anuncio_escondido, r.nome_truque, r.sem_rotulo
        if app.cert is None and r.cert:
            app.cert = r.cert
    except Exception as e:  # noqa: BLE001
        log.LOGGER.info("leitura do APK de %s falhou: %s", app.pacote, e)
