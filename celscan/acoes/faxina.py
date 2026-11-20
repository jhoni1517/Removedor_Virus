"""Faxina geral: apps inúteis da marca, anúncios do sistema e bloqueio de anúncios por DNS.

- Apps da marca: lista curada por fabricante (Xiaomi/Redmi/POCO, Samsung, Motorola e os "parceiros"
  pré-instalados). Cada app vem com o que faz e o que se perde. Nada é apagado do aparelho: o app é
  desativado/removido só para o usuário (volta pelo Histórico ou num reset de fábrica).
- Anúncios: na Xiaomi, as propagandas dentro de Configurações, Segurança, Arquivos e Temas vêm do serviço
  MSA + Analytics. Tirando os dois, elas param. Nas outras marcas, o bloqueio por DNS cobre apps e sites.
- DNS privado (o "VPN" de anúncios sem app nenhum): o próprio Android manda as consultas para um servidor
  que bloqueia propaganda e rastreadores. Não gasta bateria, vale no Wi-Fi e nos dados e não precisa
  instalar nada. Não bloqueia anúncio do YouTube (vem do mesmo servidor do vídeo).
- Câmera mais rápida: compila a câmera e a galeria por completo, limpa o cache delas e reinicia a câmera.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any

from celscan.acoes import otimizacao, quarentena
from celscan.core.seguranca import essencial, exigir_pacote


@dataclass(frozen=True)
class AppMarca:
    pacote: str
    nome: str
    grupo: str  # anuncios | duplicado | inutil | avancado
    explicacao: str
    perde: str = ""


XIAOMI = ("xiaomi", "redmi", "poco")
GRUPOS = {
    "anuncios": "Anúncios e coleta de dados",
    "duplicado": "Duplicados (já existe um app do Google igual)",
    "inutil": "Inúteis no Brasil ou quase ninguém usa",
    "google": "Apps do Google pouco usados",
    "opcional": "Só tire se você não usa",
    "avancado": "Avançado (leia antes)",
}
MARCADOS = ("anuncios", "duplicado", "inutil")  # já vêm marcados: tirar não faz falta a ninguém

LISTAS: dict[str, tuple[AppMarca, ...]] = {
    "xiaomi": (
        AppMarca("com.miui.msa.global", "MSA (anúncios do sistema)", "anuncios",
                 "É o serviço que coloca propaganda em Configurações, Segurança, Limpeza, Arquivos e Temas."),
        AppMarca("com.miui.analytics", "Analytics da Xiaomi", "anuncios",
                 "Envia estatísticas de uso para a Xiaomi e alimenta os anúncios."),
        AppMarca("com.miui.daemon", "MiuiDaemon (coleta)", "anuncios", "Coleta de dados de desempenho e uso."),
        AppMarca("com.mi.android.globalminusscreen", "App Vault (tela à esquerda)", "anuncios",
                 "Tela de atalhos com notícias e propaganda à esquerda da tela inicial.",
                 "A tela à esquerda da tela inicial."),
        AppMarca("com.mfashiongallery.emag", "Carrossel de papéis de parede", "anuncios",
                 "Troca o fundo da tela de bloqueio com imagens patrocinadas.", "O carrossel da tela de bloqueio."),
        AppMarca("com.miui.android.fashiongallery", "Carrossel de papéis de parede (antigo)", "anuncios",
                 "Versão antiga do carrossel com propaganda."),
        AppMarca("com.miui.hybrid", "Quick Apps", "anuncios",
                 "Mini-apps que abrem sozinhos com conteúdo patrocinado."),
        AppMarca("com.miui.hybrid.accessory", "Quick Apps (complemento)", "anuncios", "Complemento do Quick Apps."),
        AppMarca("com.mi.globalbrowser", "Navegador Mi", "duplicado",
                 "Navegador da Xiaomi, cheio de notícias patrocinadas. O Chrome continua.", "O navegador Mi."),
        AppMarca("com.android.browser", "Navegador Mi (nome antigo)", "duplicado", "Mesmo navegador, nome antigo."),
        AppMarca("com.miui.videoplayer", "Mi Vídeo", "duplicado", "Player de vídeo com propaganda. A Galeria toca "
                 "vídeos normalmente."),
        AppMarca("com.miui.player", "Mi Música", "duplicado", "Player de música com propaganda."),
        AppMarca("com.xiaomi.mipicks", "GetApps (loja da Xiaomi)", "duplicado",
                 "Loja paralela que empurra apps e notificações. A Play Store continua.",
                 "Atualizações de apps só da Xiaomi (raro)."),
        AppMarca("com.xiaomi.glgm", "Games (central de jogos)", "inutil", "Central de jogos com recomendações."),
        AppMarca("com.miui.bugreport", "Feedback", "inutil", "Envio de relatórios de erro para a Xiaomi."),
        AppMarca("com.miui.miservice", "Serviços e feedback", "inutil", "Atendimento e feedback da Xiaomi."),
        AppMarca("com.miui.yellowpage", "Páginas amarelas", "inutil", "Identificador de empresas (pouco usado no "
                 "Brasil)."),
        AppMarca("com.mi.globalminusscreen", "App Vault (tela à esquerda)", "anuncios",
                 "Tela de atalhos com notícias e propaganda à esquerda da tela inicial.",
                 "A tela à esquerda da tela inicial."),
        AppMarca("com.miui.personalassistant", "Assistente pessoal (tela à esquerda)", "anuncios",
                 "Versão chinesa da tela de notícias à esquerda."),
        AppMarca("com.miui.systemAdSolution", "Anúncios do sistema (ROM chinesa)", "anuncios",
                 "O serviço de propaganda das ROMs chinesas e de importação."),
        AppMarca("com.miui.cleaner", "Limpeza (Cleaner)", "duplicado",
                 "Limpador com propaganda e 'acelerador' que não acelera. O CelScan e o Segurança fazem isso.",
                 "O atalho 'Limpeza'."),
        AppMarca("com.miui.contentextension", "Taplus", "inutil",
                 "Lê o texto da tela para sugerir buscas (fica rodando escondido)."),
        AppMarca("com.miui.huanji", "Mi Mover", "inutil", "Só serve para passar dados de outro celular no "
                 "primeiro uso.", "Passar dados de outro celular pelo app da Xiaomi."),
        AppMarca("com.miui.touchassistant", "Bola rápida", "inutil", "Botão flutuante de atalhos (quase ninguém "
                 "liga)."),
        AppMarca("com.miui.virtualsim", "Mi SIM virtual", "inutil", "Chip virtual de viagem, não funciona no "
                 "Brasil."),
        AppMarca("com.miui.vsimcore", "Mi SIM virtual (serviço)", "inutil", "Serviço do chip virtual."),
        AppMarca("com.xiaomi.payment", "Mi Pay", "inutil", "Pagamento da Xiaomi, não funciona no Brasil."),
        AppMarca("com.mipay.wallet.in", "Mi Pay (Índia)", "inutil", "Carteira da Xiaomi para a Índia."),
        AppMarca("com.miui.voiceassist", "XiaoAi (assistente chinês)", "inutil", "Assistente de voz em chinês."),
        AppMarca("com.xiaomi.discover", "Atualizador de apps do sistema", "inutil",
                 "Fica oferecendo atualização de apps da Xiaomi e mandando notificação.",
                 "Atualizações dos apps da Xiaomi fora da Play Store (o sistema continua atualizando)."),
        AppMarca("com.mi.android.globalFileexplorer", "Gerenciador de arquivos Mi", "opcional",
                 "Tem propaganda. Antes, instale o Files do Google pela Play Store.", "O app Arquivos da Xiaomi."),
        AppMarca("com.xiaomi.midrop", "ShareMe", "opcional", "Envio de arquivos entre celulares (o Quick Share do "
                 "Android faz igual).", "O ShareMe."),
        AppMarca("com.miui.notes", "Notas", "opcional", "Bloco de notas da Xiaomi.", "Suas notas ficam "
                 "escondidas até devolver o app."),
        AppMarca("com.miui.weather2", "Clima", "opcional", "App de clima.", "O widget de clima da tela inicial."),
        AppMarca("com.miui.compass", "Bússola", "opcional", "Bússola e nível."),
        AppMarca("com.miui.fm", "Rádio FM", "opcional", "Rádio FM (precisa de fone com fio)."),
        AppMarca("com.duokan.phone.remotecontroller", "Mi Controle remoto", "opcional",
                 "Controle de TV pelo infravermelho.", "Usar o celular como controle remoto."),
        AppMarca("com.xiaomi.scanner", "Scanner", "opcional", "Leitor de QR code e documentos (a câmera já lê "
                 "QR code)."),
        AppMarca("com.miui.screenrecorder", "Gravador de tela", "opcional", "Grava a tela.",
                 "O botão de gravar a tela."),
        AppMarca("com.miui.backup", "Backup local", "opcional", "Backup da Xiaomi no próprio celular."),
        AppMarca("com.android.thememanager", "Temas", "avancado",
                 "Loja de temas com propaganda.", "Trocar tema, ícones e fontes; o celular fica no tema padrão."),
        AppMarca("com.xiaomi.mi_connect_service", "Mi Connect", "avancado",
                 "Conexão com outros aparelhos Xiaomi.", "Espelhar e compartilhar com TV/tablet/notebook Xiaomi."),
        AppMarca("com.miui.cloudbackup", "Backup na nuvem Xiaomi", "avancado",
                 "Backup automático na Xiaomi Cloud.", "O backup na nuvem da Xiaomi (o do Google continua)."),
        AppMarca("com.xiaomi.joyose", "Joyose (limitador de jogos)", "avancado",
                 "Controla perfis de jogo e segura a CPU/GPU para não esquentar. Desativar libera desempenho em "
                 "jogos.", "O celular pode esquentar mais em jogo pesado; vigie a temperatura no Turbo."),
    ),
    "samsung": (
        AppMarca("com.samsung.android.app.spage", "Samsung Free (tela à esquerda)", "anuncios",
                 "Notícias e propaganda à esquerda da tela inicial."),
        AppMarca("com.samsung.android.mdx.quickboard", "Sugestões rápidas", "inutil", "Painel de sugestões."),
        AppMarca("com.sec.android.app.sbrowser", "Samsung Internet", "duplicado",
                 "Navegador da Samsung; o Chrome continua.", "O navegador Samsung."),
        AppMarca("com.samsung.android.bixby.agent", "Bixby", "inutil", "Assistente de voz da Samsung.",
                 "O botão/comando do Bixby."),
        AppMarca("com.samsung.android.game.gametools", "Ferramentas de jogo", "inutil",
                 "Painel flutuante dentro dos jogos."),
        AppMarca("com.samsung.android.game.gamehome", "Game Launcher", "inutil", "Central de jogos com "
                 "recomendações."),
        AppMarca("com.samsung.android.app.tips", "Dicas", "inutil", "Notificações de dicas."),
        AppMarca("com.samsung.android.arzone", "AR Zone", "inutil", "Efeitos de realidade aumentada."),
        AppMarca("com.samsung.android.aremoji", "AR Emoji", "inutil", "Emoji 3D do rosto."),
        AppMarca("com.samsung.android.tvplus", "Samsung TV Plus", "inutil", "Canais de TV com propaganda."),
        AppMarca("com.samsung.android.kidsinstaller", "Samsung Kids", "inutil", "Modo criança."),
        AppMarca("com.samsung.android.bixby.wakeup", "Bixby (ouvir 'Oi Bixby')", "inutil", "Microfone esperando "
                 "o comando de voz do Bixby."),
        AppMarca("com.samsung.android.visionintelligence", "Bixby Vision", "inutil", "Busca pela câmera."),
        AppMarca("com.sec.android.easyMover", "Smart Switch", "opcional", "Passar dados de outro celular.",
                 "Passar dados de outro celular pelo app da Samsung."),
        AppMarca("com.microsoft.skydrive", "OneDrive", "opcional", "Nuvem da Microsoft."),
        AppMarca("com.linkedin.android", "LinkedIn", "opcional", "Pré-instalado de parceiro."),
    ),
    "motorola": (
        AppMarca("com.motorola.genie", "Ajuda Motorola", "inutil", "App de ajuda e dicas."),
        AppMarca("com.motorola.demo", "Modo demonstração", "inutil", "Usado só em loja."),
    ),
    "todas": (
        AppMarca("com.google.android.apps.youtube.music", "YouTube Music", "google", "Música do YouTube.",
                 "O YouTube Music (o YouTube continua)."),
        AppMarca("com.google.android.videos", "Google TV (filmes)", "google", "Loja de filmes do Google."),
        AppMarca("com.google.android.apps.tachyon", "Google Meet", "google", "Chamadas de vídeo do Google."),
        AppMarca("com.google.android.apps.podcasts", "Google Podcasts", "google", "App de podcasts."),
        AppMarca("com.google.android.apps.magazines", "Google Notícias", "google", "Notícias."),
        AppMarca("com.google.android.apps.subscriptions.red", "Google One", "google", "Assinatura de espaço do "
                 "Google.", "O app (o backup do Google continua funcionando)."),
        AppMarca("com.google.android.feedback", "Feedback do Google", "google", "Envio de relatórios ao Google."),
        AppMarca("com.facebook.katana", "Facebook (vem instalado)", "opcional",
                 "O app do Facebook que veio de fábrica.",
                 "O Facebook (dá para instalar de novo pela Play Store quando quiser)."),
        AppMarca("com.netflix.partner.activation", "Ativação Netflix (parceiro)", "inutil",
                 "Serviço de parceria da fábrica. NÃO é o app da Netflix, que continua funcionando."),
        AppMarca("com.facebook.appmanager", "Facebook App Manager", "anuncios",
                 "Serviço do Facebook pré-instalado que roda escondido (mesmo sem o app do Facebook)."),
        AppMarca("com.facebook.services", "Facebook Services", "anuncios", "Serviço de fundo do Facebook."),
        AppMarca("com.facebook.system", "Facebook Installer", "anuncios", "Instalador escondido do Facebook."),
        AppMarca("com.netflix.partner.activation", "Ativação Netflix (parceiro)", "inutil",
                 "Só serve para ativar promoção da Netflix."),
        AppMarca("com.amazon.appmanager", "Amazon App Manager", "anuncios", "Instalador de apps da Amazon."),
        AppMarca("com.ironsource.appcloud.oobe", "Instalador de apps de parceiros", "anuncios",
                 "Instala apps patrocinados na primeira configuração."),
        AppMarca("com.aura.oobe.deutsche", "Instalador de apps da operadora", "anuncios",
                 "Instala apps patrocinados da operadora."),
    ),
}


def _marca(ap) -> str:
    fab = ap.sh("getprop ro.product.manufacturer").strip().lower()
    if any(m in fab for m in XIAOMI):
        return "xiaomi"
    return fab if fab in LISTAS else "outra"


def apps_da_marca(ap) -> dict[str, Any]:
    marca = _marca(ap)
    todos = set(re.findall(r"^package:([\w.]+)", ap.sh("pm list packages -u"), re.M))
    ativos = set(re.findall(r"^package:([\w.]+)", ap.sh("pm list packages -e"), re.M))
    itens = []
    for a in (*LISTAS.get(marca, ()), *LISTAS["todas"]):
        if a.pacote not in todos or essencial(a.pacote):
            continue
        itens.append({"pacote": a.pacote, "nome": a.nome, "grupo": a.grupo, "explicacao": a.explicacao,
                      "perde": a.perde, "ativo": a.pacote in ativos, "marcado": a.grupo in MARCADOS})
    return {"marca": marca, "grupos": GRUPOS, "apps": itens}


def remover_apps(ap, pacotes: list[str], progresso=None, cancelar=None) -> dict[str, Any]:
    """Desativa (ou remove só para o usuário) apps da lista. Recusa qualquer pacote fora da lista curada."""
    conhecidos = {a.pacote for lista in LISTAS.values() for a in lista}
    feitos = []
    for i, pkg in enumerate(pacotes, 1):
        exigir_pacote(pkg)
        if pkg not in conhecidos:
            raise ValueError(f"{pkg} não está na lista de apps seguros de tirar")
        if cancelar is not None and cancelar.is_set():
            break
        if progresso:
            progresso({"etapa": "faxina", "descricao": "Tirando apps inúteis", "detalhe": pkg, "atual": i,
                       "total": len(pacotes), "estimativa_s": 2 * (len(pacotes) - i)})
        ok, motivo = otimizacao.desativar_detalhado(ap, pkg)
        feitos.append({"pacote": pkg, "ok": ok, "motivo": motivo})
    return {"apps": feitos, "removidos": sum(f["ok"] for f in feitos),
            "falhas": [f for f in feitos if not f["ok"]]}


def devolver(ap, pkg: str) -> dict[str, Any]:
    """Traz de volta um app de fábrica que foi desativado ou removido só para o usuário."""
    exigir_pacote(pkg)
    ap.sh(f"pm enable --user 0 {pkg}", erro=True)
    ap.sh(f"cmd package install-existing --user 0 {pkg}", erro=True)
    ok = pkg in set(re.findall(r"^package:([\w.]+)", ap.sh("pm list packages -e"), re.M))
    return {"pacote": pkg, "ok": ok}


# ---------------------------------------------------------------------------------------------- DNS

DNS = {
    "adguard": ("AdGuard", "dns.adguard-dns.com", "Bloqueia anúncios e rastreadores. O mais usado."),
    "adguard_familia": ("AdGuard Família", "family.adguard-dns.com",
                        "Anúncios + sites adultos + busca segura. Bom para celular de criança."),
    "mullvad": ("Mullvad (bloqueio)", "adblock.dns.mullvad.net", "Anúncios e rastreadores, sem guardar registros."),
    "cloudflare_seguro": ("Cloudflare (só golpes)", "security.cloudflare-dns.com",
                          "Só bloqueia golpes e malware (não tira propaganda), muito rápido."),
}
HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def dns_atual(ap) -> dict[str, Any]:
    modo = quarentena.ler_setting(ap, "global", "private_dns_mode")
    host = quarentena.ler_setting(ap, "global", "private_dns_specifier")
    provedor = next((k for k, v in DNS.items() if v[1] == host), None) if modo == "hostname" else None
    return {"modo": modo or "padrão", "servidor": host if modo == "hostname" else None, "provedor": provedor,
            "opcoes": [{"id": k, "nome": v[0], "servidor": v[1], "descricao": v[2]} for k, v in DNS.items()]}


def definir_dns(ap, provedor: str | None = None, servidor: str | None = None) -> dict[str, Any]:
    """Liga o DNS privado (provedor da lista ou servidor próprio, ex.: NextDNS) ou volta ao automático."""
    if provedor and provedor not in DNS:
        raise ValueError(f"provedor desconhecido: {provedor}")
    if servidor is not None:
        servidor = servidor.strip().lower()
        if not HOST.fullmatch(servidor):
            raise ValueError("servidor inválido: use um nome como abc123.dns.nextdns.io")
    alvo = DNS[provedor][1] if provedor else servidor
    desfazer = [{"tipo": "settings", "ns": "global", "chave": k, "anterior": quarentena.ler_setting(ap, "global", k)}
                for k in ("private_dns_specifier", "private_dns_mode")]
    pasta = quarentena.criar_ajuste(ap, "dns_privado", f"DNS privado: {alvo or 'automático'}", desfazer)
    if alvo:
        ap.sh(f"settings put global private_dns_specifier {shlex.quote(alvo)}")
        ap.sh("settings put global private_dns_mode hostname")
    else:
        ap.sh("settings put global private_dns_mode opportunistic")
    atual = dns_atual(ap)
    ok = atual["servidor"] == alvo if alvo else atual["modo"] == "opportunistic"
    return {"ok": ok, "servidor": alvo, "desfazer_id": pasta.name,
            "obs": "Se a internet parar, o servidor está fora: volte para 'Automático'. Anúncio do YouTube não é "
                   "bloqueado por DNS."}


# ---------------------------------------------------------------------------------------------- câmera

CAMERAS = ("com.android.camera", "com.sec.android.app.camera", "com.motorola.camera3", "com.motorola.camera2",
           "com.google.android.GoogleCamera", "com.oplus.camera", "com.oneplus.camera", "org.codeaurora.snapcam",
           "com.miui.gallery", "com.sec.android.gallery3d", "com.google.android.apps.photos",
           "com.xiaomi.cameratools", "com.android.camera2")


def camera_rapida(ap) -> dict[str, Any]:
    """Câmera e galeria compiladas por completo + cache limpo + câmera reiniciada."""
    instalados = set(re.findall(r"^package:([\w.]+)", ap.sh("pm list packages -e"), re.M))
    sdk = int(ap.sh("getprop ro.build.version.sdk").strip() or 0)
    res = []
    for pkg in CAMERAS:
        if pkg not in instalados:
            continue
        passos = {"compilado": "Success" in ap.sh(f"cmd package compile -m speed -f {pkg}", timeout=600, erro=True)}
        if sdk >= 34:  # 'pm clear --cache-only' só existe do Android 14 em diante
            saida = ap.sh(f"pm clear --cache-only {pkg}", erro=True)
            passos["cache_limpo"] = "success" in saida.lower()
        ap.sh(f"am force-stop {pkg}")
        res.append({"pacote": pkg, **passos})
    livre = otimizacao.livre_kb(ap)
    dica = None
    if livre is not None and livre < 8 * 1048576:
        dica = (f"Só {livre / 1048576:.1f} GB livres: com o armazenamento quase cheio a câmera demora a salvar e "
                "engasga. Libere espaço (backup das fotos) para ter o maior ganho.")
    return {"apps": res, "dica": dica,
            "obs": "A câmera abre mais rápido a partir da próxima abertura. Se travar ao trocar de lente, "
                   "reinicie o celular uma vez."}
