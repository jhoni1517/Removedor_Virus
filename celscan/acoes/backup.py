"""Cópia dos dados do celular para o PC (fotos, vídeos, documentos, WhatsApp...).

- Só lê do celular: nada é apagado ou alterado nele.
- Retomada: se o cabo cair, rodar de novo pula o que já foi copiado (mesmo tamanho).
- Conferência: tamanho de cada arquivo sempre; SHA-256 opcional (mais lento).
- Precisa da depuração USB autorizada (sem ela o Android não entrega os arquivos).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from celscan.core.adb import AdbErro, Aparelho
from celscan.core.log import LOGGER

# categoria -> (nome para o usuário, pastas no celular)
CATEGORIAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "fotos": ("Fotos e vídeos da câmera", ("/sdcard/DCIM",)),
    "imagens": ("Imagens, capturas de tela e downloads de imagem", ("/sdcard/Pictures",)),
    "videos": ("Vídeos", ("/sdcard/Movies",)),
    "whatsapp_midia": ("Mídia do WhatsApp (fotos, vídeos, áudios, documentos)", (
        "/sdcard/Android/media/com.whatsapp/WhatsApp/Media", "/sdcard/WhatsApp/Media",
        "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Media")),
    "whatsapp_backup": ("Backup local das conversas do WhatsApp", (
        "/sdcard/Android/media/com.whatsapp/WhatsApp/Databases", "/sdcard/WhatsApp/Databases",
        "/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Databases")),
    "documentos": ("Documentos", ("/sdcard/Documents",)),
    "downloads": ("Downloads", ("/sdcard/Download",)),
    "audio": ("Músicas, gravações e toques", ("/sdcard/Music", "/sdcard/Recordings", "/sdcard/Ringtones")),
    "telegram": ("Arquivos do Telegram", ("/sdcard/Android/media/org.telegram.messenger", "/sdcard/Telegram")),
}
PADRAO = ("fotos", "imagens", "videos", "whatsapp_midia", "whatsapp_backup", "documentos", "downloads", "audio")

Progresso = Callable[[dict[str, Any]], None]


@dataclass
class Arquivo:
    categoria: str
    caminho: str  # no celular
    tamanho: int
    mtime: int


@dataclass
class ResumoBackup:
    destino: str
    copiados: int = 0
    pulados: int = 0  # já estavam no PC (retomada)
    falhas: list[dict[str, str]] = field(default_factory=list)
    bytes_copiados: int = 0
    por_categoria: dict[str, dict[str, int]] = field(default_factory=dict)
    verificado_hash: bool = False
    duracao_s: float = 0.0


def pasta_padrao() -> Path:
    return Path.home() / "Documents" / "CelScan Backups"


def nome_seguro(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto).strip(" .") or "celular"


def parse_lista(saida: str) -> list[tuple[int, int, str]]:
    """Linhas 'tamanho|mtime|caminho' (stat -c) -> [(tamanho, mtime, caminho)]."""
    res = []
    for linha in saida.splitlines():
        partes = linha.rstrip("\r").split("|", 2)
        if len(partes) == 3 and partes[0].isdigit():
            res.append((int(partes[0]), int(partes[1]) if partes[1].isdigit() else 0, partes[2]))
    return res


def listar(ap: Aparelho, categorias: list[str]) -> list[Arquivo]:
    arquivos: list[Arquivo] = []
    vistos: set[str] = set()
    for cat in categorias:
        if cat not in CATEGORIAS:
            raise ValueError(f"categoria desconhecida: {cat}")
        for pasta in CATEGORIAS[cat][1]:
            cmd = (f"[ -d {shlex.quote(pasta)} ] && find {shlex.quote(pasta)} -type f "
                   f"! -name '.nomedia' ! -path '*/.thumbnails/*' ! -path '*/.trashed*' "
                   f"-exec stat -c '%s|%Y|%n' {{}} + 2>/dev/null")
            for tamanho, mtime, caminho in parse_lista(ap.sh(cmd, timeout=600)):
                if caminho not in vistos:
                    vistos.add(caminho)
                    arquivos.append(Arquivo(cat, caminho, tamanho, mtime))
    return arquivos


def resumo_listagem(arquivos: list[Arquivo]) -> dict[str, dict[str, Any]]:
    res: dict[str, dict[str, Any]] = {c: {"nome": CATEGORIAS[c][0], "arquivos": 0, "bytes": 0} for c in CATEGORIAS}
    for a in arquivos:
        res[a.categoria]["arquivos"] += 1
        res[a.categoria]["bytes"] += a.tamanho
    return res


def destino_local(raiz: Path, a: Arquivo) -> Path:
    """Mantém a estrutura de pastas do celular dentro da pasta da categoria."""
    relativo = a.caminho[len("/sdcard/"):] if a.caminho.startswith("/sdcard/") else a.caminho.lstrip("/")
    partes = [nome_seguro(p) for p in relativo.split("/") if p]
    return raiz.joinpath(nome_seguro(CATEGORIAS[a.categoria][0].split(" (")[0]), *partes)


def _sha256_local(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def copiar(ap: Aparelho, arquivos: list[Arquivo], raiz: Path, progresso: Progresso | None = None,
           cancelar: threading.Event | None = None, verificar_hash: bool = False,
           info: dict[str, str] | None = None) -> ResumoBackup:
    from celscan.servicos import Cancelado, verificar_conexao

    raiz.mkdir(parents=True, exist_ok=True)
    resumo = ResumoBackup(destino=str(raiz), verificado_hash=verificar_hash)
    total_bytes = sum(a.tamanho for a in arquivos) or 1
    feitos_bytes = 0
    inicio = time.perf_counter()
    for i, a in enumerate(arquivos, 1):
        if cancelar is not None and cancelar.is_set():
            _gravar_relatorio(raiz, resumo, arquivos, info)
            raise Cancelado(f"Cópia interrompida. {resumo.copiados + resumo.pulados} de {len(arquivos)} arquivos "
                            f"já estão no PC; rode de novo para continuar de onde parou.")
        cat = resumo.por_categoria.setdefault(a.categoria, {"arquivos": 0, "bytes": 0})
        local = destino_local(raiz, a)
        decorrido = time.perf_counter() - inicio
        velocidade = resumo.bytes_copiados / decorrido if decorrido > 1 else 0
        if progresso:
            progresso({"etapa": "backup", "descricao": "Copiando arquivos para o PC", "detalhe": a.caminho,
                       "atual": i, "total": len(arquivos), "bytes": feitos_bytes, "bytes_total": total_bytes,
                       "velocidade": velocidade,
                       "estimativa_s": (total_bytes - feitos_bytes) / velocidade if velocidade else 0})
        feitos_bytes += a.tamanho
        if local.exists() and local.stat().st_size == a.tamanho:
            resumo.pulados += 1
            cat["arquivos"] += 1
            cat["bytes"] += a.tamanho
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        parcial = local.with_name(local.name + ".parcial")
        try:
            saida = ap.adb("pull", "-a", a.caminho, str(parcial), timeout=max(120, a.tamanho // 2_000_000),
                           erro=True)
        except AdbErro as e:
            parcial.unlink(missing_ok=True)
            _gravar_relatorio(raiz, resumo, arquivos, info)
            erro = verificar_conexao(ap.serial, e)
            if erro is not e:
                raise type(erro)(f"{erro} Os {resumo.copiados + resumo.pulados} arquivos já copiados ficam no PC; "
                                 "rode de novo para continuar.") from e
            resumo.falhas.append({"arquivo": a.caminho, "erro": str(e)})
            continue
        if not parcial.exists() or parcial.stat().st_size != a.tamanho:
            parcial.unlink(missing_ok=True)
            resumo.falhas.append({"arquivo": a.caminho, "erro": f"tamanho diferente ({saida[-120:]})"})
            continue
        if verificar_hash:
            remoto = ap.sh(f"sha256sum {shlex.quote(a.caminho)}", timeout=600).split()
            if not remoto or remoto[0] != _sha256_local(parcial):
                parcial.unlink(missing_ok=True)
                resumo.falhas.append({"arquivo": a.caminho, "erro": "o conteúdo não bateu (SHA-256)"})
                continue
        os.replace(parcial, local)
        if a.mtime:
            os.utime(local, (a.mtime, a.mtime))
        resumo.copiados += 1
        resumo.bytes_copiados += a.tamanho
        cat["arquivos"] += 1
        cat["bytes"] += a.tamanho
    resumo.duracao_s = time.perf_counter() - inicio
    _gravar_relatorio(raiz, resumo, arquivos, info)
    LOGGER.info("backup em %s: %d copiados, %d pulados, %d falhas, %.0fs", raiz, resumo.copiados, resumo.pulados,
                len(resumo.falhas), resumo.duracao_s)
    return resumo


def lista_de_apps(ap: Aparelho) -> str:
    """Apps instalados pelo usuário (para reinstalar no aparelho novo)."""
    saida = ap.sh("pm list packages -3", timeout=60)
    return "\n".join(sorted(linha[8:] for linha in saida.splitlines() if linha.startswith("package:")))


def _gravar_relatorio(raiz: Path, resumo: ResumoBackup, arquivos: list[Arquivo], info: dict[str, str] | None) -> None:
    dados = {"data": datetime.now().isoformat(timespec="seconds"), "aparelho": info or {}, **asdict(resumo),
             "total_arquivos": len(arquivos)}
    (raiz / "relatorio_backup.json").write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    linhas = [f"Backup feito pelo CelScan em {dados['data']}",
              f"Aparelho: {(info or {}).get('fabricante', '')} {(info or {}).get('modelo', '')}".rstrip(),
              f"Arquivos copiados agora: {resumo.copiados} | já estavam no PC: {resumo.pulados} | "
              f"falhas: {len(resumo.falhas)}",
              "Conferência: " + ("tamanho e SHA-256 de cada arquivo" if resumo.verificado_hash else
                                  "tamanho de cada arquivo"), ""]
    for c, v in resumo.por_categoria.items():
        linhas.append(f"- {CATEGORIAS[c][0]}: {v['arquivos']} arquivos, {v['bytes'] / 1048576:.1f} MB")
    if resumo.falhas:
        linhas += ["", "Arquivos que não foram copiados:"] + [f"- {f['arquivo']}: {f['erro']}" for f in resumo.falhas]
    linhas += ["", "Contatos, agenda e conversas do WhatsApp na nuvem ficam na conta Google/WhatsApp do dono.",
               "Estes arquivos são dados pessoais do cliente: entregue e apague do computador depois (LGPD)."]
    (raiz / "LEIA-ME.txt").write_text("\n".join(linhas), encoding="utf-8")
