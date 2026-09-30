"""Recuperação honesta de arquivos "apagados" sem root.

Limite importante (dito em linguagem simples na tela): SEM ROOT, o Android não deixa ler a
memória crua, então NÃO existe "undelete"/carving de verdade por USB, e mensagens do WhatsApp
apagadas (banco criptografado dentro do app) não voltam.

O que DÁ para recuperar é o que ainda está no aparelho, só escondido do usuário:
- Lixeira da galeria (Android 11+ marca como .trashed-*; MIUI/Samsung têm pastas próprias) —
  fotos e vídeos apagados nos últimos ~30 dias.
- Miniaturas (.thumbnails): versões em baixa resolução de fotos que já sumiram.
- Mídia que ficou nos apps mesmo depois de apagada da conversa (ex.: status do WhatsApp vistos).
"""

from __future__ import annotations

import shlex
from pathlib import Path

from celscan.acoes.backup import Arquivo, nome_seguro, parse_lista
from celscan.core.adb import Aparelho

RAIZES = ("/sdcard/DCIM", "/sdcard/Pictures", "/sdcard/Movies", "/sdcard/Download", "/sdcard/MIUI")

# categoria -> (nome amigável, expressão do find dentro de cada raiz)
FONTES: dict[str, tuple[str, str]] = {
    "lixeira": (
        "Lixeira da galeria (apagados recentemente)",
        r"\( -name '.trashed-*' -o -ipath '*/.trash*/*' -o -ipath '*/recyclebin/*' "
        r"-o -ipath '*/trashbin/*' \)",
    ),
    "miniaturas": (
        "Miniaturas de fotos que já sumiram (baixa resolução)",
        r"-ipath '*/.thumbnails/*'",
    ),
}
# Pastas específicas varridas por inteiro (mídia que sobra dentro de apps).
PASTAS_APP: dict[str, tuple[str, tuple[str, ...]]] = {
    "status_whatsapp": (
        "Status do WhatsApp já vistos (some sozinho em 24h)",
        ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/.Statuses",
         "/sdcard/WhatsApp/Media/.Statuses"),
    ),
    "cache_telegram": (
        "Cache de fotos/vídeos do Telegram",
        ("/sdcard/Android/data/org.telegram.messenger/cache",),
    ),
}
PADRAO = ("lixeira", "miniaturas", "status_whatsapp")


def procurar(ap: Aparelho, categorias: list[str] | None = None) -> list[Arquivo]:
    """Lista as sobras recuperáveis. Só lê; nada é alterado no celular."""
    cats = list(categorias or PADRAO)
    arquivos: list[Arquivo] = []
    vistos: set[str] = set()

    def juntar(cat: str, saida: str) -> None:
        for tamanho, mtime, caminho in parse_lista(saida):
            if caminho not in vistos and tamanho > 0:
                vistos.add(caminho)
                arquivos.append(Arquivo(cat, caminho, tamanho, mtime))

    for cat in cats:
        if cat in FONTES:
            expr = FONTES[cat][1]
            for raiz in RAIZES:
                cmd = (f"[ -d {shlex.quote(raiz)} ] && find {shlex.quote(raiz)} -type f {expr} "
                       f"-exec stat -c '%s|%Y|%n' {{}} + 2>/dev/null")
                juntar(cat, ap.sh(cmd, timeout=600))
        elif cat in PASTAS_APP:
            for pasta in PASTAS_APP[cat][1]:
                cmd = (f"[ -d {shlex.quote(pasta)} ] && find {shlex.quote(pasta)} -type f "
                       f"-exec stat -c '%s|%Y|%n' {{}} + 2>/dev/null")
                juntar(cat, ap.sh(cmd, timeout=600))
        else:
            raise ValueError(f"categoria desconhecida: {cat}")
    return arquivos


def destino_recuperado(raiz: Path, a: Arquivo) -> Path:
    """Tudo vai para 'Recuperados/<categoria>/', achatando o caminho e evitando repetir nome."""
    nome = nome_seguro(Path(a.caminho).name)
    return raiz / "Recuperados" / nome_seguro(nome_categoria(a.categoria)) / f"{a.mtime}_{nome}"


def nome_categoria(cat: str) -> str:
    if cat in FONTES:
        return FONTES[cat][0]
    if cat in PASTAS_APP:
        return PASTAS_APP[cat][0]
    return cat


def resumo(arquivos: list[Arquivo]) -> dict[str, dict[str, object]]:
    res: dict[str, dict[str, object]] = {}
    for a in arquivos:
        r = res.setdefault(a.categoria, {"nome": nome_categoria(a.categoria), "arquivos": 0, "bytes": 0})
        r["arquivos"] = int(r["arquivos"]) + 1  # type: ignore[arg-type]
        r["bytes"] = int(r["bytes"]) + a.tamanho  # type: ignore[arg-type]
    return res
