"""Atualização automática pelo GitHub Releases (canal estável ou beta).

- Consulta a página de Releases do projeto (HTTPS, host fixo) e compara as versões.
- Baixa o instalador e confere o SHA-256 que o próprio GitHub publica para o arquivo ("digest");
  se não bater, não instala.
- No Windows, roda o instalador em modo silencioso e o CelScan fecha para ele trocar os arquivos.
- Respeita o modo offline. Sem assinatura de código, o Windows pode mostrar "editor desconhecido".
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from celscan import __version__, config
from celscan.core.log import LOGGER

REPO = "jhoni1517/Removedor_Virus"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
HOSTS_OK = ("api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
_ESTAGIO = {"a": 0, "b": 1, "rc": 2, "": 3}


class ErroAtualizacao(Exception):
    pass


def chave_versao(v: str) -> tuple[int, int, int, int, int]:
    """'3.0.0b6' -> (3,0,0,1,6); '3.1.0' -> (3,1,0,3,0). Versão final vem depois das betas."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?", v.strip())
    if not m:
        return (0, 0, 0, 0, 0)
    return (int(m[1]), int(m[2]), int(m[3]), _ESTAGIO[m[4] or ""], int(m[5] or 0))


def _host_ok(url: str) -> bool:
    h = urlparse(url).hostname or ""
    return urlparse(url).scheme == "https" and any(h == x or h.endswith("." + x) for x in HOSTS_OK)


def verificar(canal: str = "beta", atual: str = __version__, releases: list[dict] | None = None) -> dict[str, Any]:
    """Devolve {disponivel, versao, url, sha256, notas, pagina}. Não baixa nada."""
    if config.OFFLINE:
        return {"disponivel": False, "motivo": "modo offline"}
    if releases is None:
        import requests

        r = requests.get(API, timeout=15, headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        releases = r.json()
    melhor = None
    for rel in releases:
        if rel.get("draft") or (canal == "estavel" and rel.get("prerelease")):
            continue
        v = (rel.get("tag_name") or "").lstrip("v")
        inst = next((a for a in rel.get("assets", [])
                     if re.fullmatch(r"CelScan-Setup-.+\.exe", a.get("name", ""))), None)
        if not inst:
            continue
        if melhor is None or chave_versao(v) > chave_versao(melhor[0]):
            melhor = (v, rel, inst)
    if not melhor or chave_versao(melhor[0]) <= chave_versao(atual):
        return {"disponivel": False, "atual": atual}
    v, rel, inst = melhor
    digest = (inst.get("digest") or "")
    return {"disponivel": True, "atual": atual, "versao": v, "url": inst["browser_download_url"],
            "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None,
            "tamanho_mb": round(inst.get("size", 0) / 1048576), "notas": (rel.get("body") or "")[:2000],
            "pagina": rel.get("html_url"), "beta": bool(rel.get("prerelease"))}


def baixar(info: dict[str, Any], destino: Path | None = None) -> Path:
    """Baixa o instalador e confere o SHA-256. Recusa se faltar hash ou não bater."""
    import requests

    url = info["url"]
    if not _host_ok(url):
        raise ErroAtualizacao(f"Endereço de download não confiável: {url}")
    if not info.get("sha256"):
        raise ErroAtualizacao("O GitHub não informou o SHA-256 deste arquivo; atualize manualmente pela página.")
    destino = destino or Path(tempfile.gettempdir()) / f"CelScan-Setup-{info['versao']}.exe"
    h = hashlib.sha256()
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        if not _host_ok(r.url):
            raise ErroAtualizacao(f"Download redirecionado para host inesperado: {r.url}")
        with open(destino, "wb") as f:
            for bloco in r.iter_content(1 << 20):
                h.update(bloco)
                f.write(bloco)
    if h.hexdigest() != info["sha256"].lower():
        destino.unlink(missing_ok=True)
        raise ErroAtualizacao("O arquivo baixado não confere com o SHA-256 publicado. Nada foi instalado.")
    return destino


def instalar(instalador: Path) -> None:
    """Windows: roda o instalador em modo silencioso, desligado deste processo. O CelScan deve fechar em seguida."""
    if os.name != "nt":
        raise ErroAtualizacao("A atualização automática é só para Windows; baixe pela página de Releases.")
    LOGGER.info("iniciando instalador %s", instalador)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(instalador), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], creationflags=flags,
                     close_fds=True)
