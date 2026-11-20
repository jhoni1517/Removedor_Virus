"""Resgate de fotos e arquivos SEM depuração USB, pelo modo "Transferência de arquivos" (MTP).

Quando a depuração não pode ser ligada (tela quebrada que ainda desbloqueia, cliente sem saber
ligar, aparelho de terceiros), o celular desbloqueado com "Transferência de arquivos" aparece no
Windows como um dispositivo portátil. O CelScan usa o próprio Windows (Shell do Explorer) para
copiar as pastas escolhidas para o computador.

Limites honestos:
- Só o armazenamento compartilhado: fotos, vídeos, downloads, documentos e mídia do WhatsApp.
  Conversas, dados de apps e senhas NÃO aparecem por MTP.
- O celular precisa estar DESBLOQUEADO e com "Transferência de arquivos" escolhido no aviso do USB.
- Só no Windows (no Linux/macOS use o gerenciador de arquivos do sistema).

Nada é apagado no celular: é só leitura. Arquivos já copiados são pulados (dá para continuar).
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Pastas conhecidas, relativas à raiz do armazenamento (os nomes são iguais em qualquer marca).
PASTAS: dict[str, str] = {
    "DCIM": "Fotos e vídeos da câmera",
    "Pictures": "Imagens e prints",
    "Movies": "Vídeos",
    "Download": "Downloads",
    "Documents": "Documentos",
    "Android/media/com.whatsapp/WhatsApp/Media": "Mídia do WhatsApp",
    "WhatsApp/Media": "Mídia do WhatsApp (antigo)",
    "Android/media/org.telegram.messenger": "Mídia do Telegram",
}

_COMUM = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$sh = New-Object -ComObject Shell.Application
$pc = $sh.Namespace(17)
$alvos = @($env:CELSCAN_MTP_PASTAS -split '\|' | Where-Object { $_ })
function Filho($f, $nome) { foreach ($i in $f.Items()) { if ($i.Name -eq $nome) { return $i } }; return $null }
function Ir($f, $rel) {
  foreach ($p in ($rel -split '/')) {
    $i = Filho $f $p
    if (-not $i -or -not $i.IsFolder) { return $null }
    $f = $i.GetFolder
  }
  return $f
}
function NomeReal($i) { $n = $i.ExtendedProperty('System.FileName'); if ($n) { return $n }; return $i.Name }
"""

# Lista aparelhos portáteis, armazenamentos e quais pastas conhecidas existem em cada um.
LISTAR = _COMUM + r"""
foreach ($d in $pc.Items()) {
  if ($d.IsFileSystem -or -not $d.IsFolder) { continue }
  $arms = @($d.GetFolder.Items() | Where-Object { $_.IsFolder })
  if ($arms.Count -eq 0) { "@@VAZIO`t$($d.Name)"; continue }
  "@@DEV`t$($d.Name)"
  foreach ($a in $arms) {
    "@@ARM`t$($d.Name)`t$($a.Name)"
    foreach ($r in $alvos) { if (Ir $a.GetFolder $r) { "@@PASTA`t$($d.Name)`t$($a.Name)`t$r" } }
  }
}
"""

# Copia arquivo por arquivo (pula o que já existe) e espera cada um terminar de gravar.
COPIAR = _COMUM + r"""
$dev = Filho $pc $env:CELSCAN_MTP_APARELHO
if (-not $dev) {
  "@@ERRO`tO celular não aparece mais no Windows. Desbloqueie e confira o modo Transferência de arquivos."
  exit 2
}
$arm = Filho $dev.GetFolder $env:CELSCAN_MTP_ARMAZENAMENTO
if (-not $arm) { "@@ERRO`tArmazenamento não encontrado no celular."; exit 2 }
$lista = New-Object System.Collections.ArrayList
function Coletar($f, $rel) {
  foreach ($i in $f.Items()) {
    if ($i.IsFolder) { Coletar $i.GetFolder "$rel/$($i.Name)" } else { [void]$lista.Add(@($i, $rel)) }
  }
}
foreach ($r in $alvos) { $f = Ir $arm.GetFolder $r; if ($f) { Coletar $f $r } }
"@@TOTAL`t$($lista.Count)"
foreach ($par in $lista) {
  $i = $par[0]; $rel = $par[1]; $nome = NomeReal $i
  $dir = Join-Path $env:CELSCAN_MTP_DESTINO ($rel -replace '/', '\')
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $alvo = Join-Path $dir $nome
  $esperado = [int64]($i.ExtendedProperty('System.Size'))
  if (Test-Path -LiteralPath $alvo) {
    # só pula o que está inteiro: um arquivo cortado (cabo caiu no meio) era pulado para sempre
    if ($esperado -le 0 -or (Get-Item -LiteralPath $alvo).Length -eq $esperado) { "@@PULOU`t$rel/$nome"; continue }
    Remove-Item -LiteralPath $alvo -Force
  }
  $sh.Namespace($dir).CopyHere($i, 1556)
  $ant = -1; $parado = 0
  while ($parado -lt 300) {
    Start-Sleep -Milliseconds 200
    if (Test-Path -LiteralPath $alvo) {
      $tam = (Get-Item -LiteralPath $alvo).Length
      if ($esperado -gt 0 -and $tam -eq $esperado) { break }
      if ($tam -eq $ant) { $parado++ } else { $parado = 0; $ant = $tam }
      if ($esperado -le 0 -and $parado -ge 10) { break }
    } else { $parado++ }
  }
  $final = if (Test-Path -LiteralPath $alvo) { (Get-Item -LiteralPath $alvo).Length } else { -1 }
  if ($final -ge 0 -and ($esperado -le 0 -or $final -eq $esperado)) {
    "@@OK`t$rel/$nome`t$final"
  } else {
    # travou no meio: apaga o pedaço para a próxima tentativa copiar de novo
    if ($final -ge 0) { Remove-Item -LiteralPath $alvo -Force }
    "@@FALHOU`t$rel/$nome"
  }
}
"@@FIM"
"""


class MtpErro(Exception):
    pass


def disponivel() -> bool:
    return os.name == "nt"


def _processo(script: str, env_extra: dict[str, str]) -> subprocess.Popen:
    env = {**os.environ, **env_extra}
    return subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                            encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def analisar_lista(saida: str) -> dict[str, Any]:
    """Saída do LISTAR -> {aparelhos: [{nome, armazenamentos: [{nome, pastas: [{caminho, nome}]}]}], so_carregando}."""
    aparelhos: dict[str, dict[str, Any]] = {}
    so_carregando: list[str] = []
    for linha in saida.splitlines():
        partes = linha.rstrip("\r").split("\t")
        tipo = partes[0]
        if tipo == "@@VAZIO" and len(partes) >= 2:
            so_carregando.append(partes[1])
        elif tipo == "@@DEV" and len(partes) >= 2:
            aparelhos.setdefault(partes[1], {"nome": partes[1], "armazenamentos": []})
        elif tipo == "@@ARM" and len(partes) >= 3:
            ap = aparelhos.setdefault(partes[1], {"nome": partes[1], "armazenamentos": []})
            ap["armazenamentos"].append({"nome": partes[2], "pastas": []})
        elif tipo == "@@PASTA" and len(partes) >= 4 and partes[3] in PASTAS:
            arms = aparelhos.get(partes[1], {}).get("armazenamentos", [])
            arm = next((a for a in arms if a["nome"] == partes[2]), None)
            if arm is not None:
                arm["pastas"].append({"caminho": partes[3], "nome": PASTAS[partes[3]]})
    return {"aparelhos": list(aparelhos.values()), "so_carregando": so_carregando}


def listar() -> dict[str, Any]:
    if not disponivel():
        return {"windows": False, "aparelhos": [], "so_carregando": []}
    p = _processo(LISTAR, {"CELSCAN_MTP_PASTAS": "|".join(PASTAS)})
    try:
        saida, _ = p.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        p.kill()
        raise MtpErro("O Windows demorou demais para listar o celular. Desconecte e conecte o cabo.") from None
    return {"windows": True, **analisar_lista(saida or "")}


def copiar(aparelho: str, armazenamento: str, pastas: list[str], destino: Path,
           progresso: Callable[[dict[str, Any]], None] | None = None,
           cancelar: threading.Event | None = None) -> dict[str, Any]:
    """Copia as pastas escolhidas para `destino`, arquivo por arquivo. Só leitura no celular."""
    if not disponivel():
        raise MtpErro("A cópia por Transferência de arquivos só funciona no Windows.")
    invalidas = [p for p in pastas if p not in PASTAS]
    if invalidas or not pastas:
        raise MtpErro(f"Pasta não permitida: {', '.join(invalidas) or 'nenhuma escolhida'}")
    destino.mkdir(parents=True, exist_ok=True)
    p = _processo(COPIAR, {"CELSCAN_MTP_APARELHO": aparelho, "CELSCAN_MTP_ARMAZENAMENTO": armazenamento,
                           "CELSCAN_MTP_PASTAS": "|".join(pastas), "CELSCAN_MTP_DESTINO": str(destino)})
    try:
        res = processar_copia(p.stdout or [], progresso, cancelar, parar=p.kill)
    finally:
        if p.poll() is None and (cancelar is None or cancelar.is_set()):
            p.kill()
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
    return {**res, "pasta": str(destino)}


def processar_copia(linhas, progresso=None, cancelar: threading.Event | None = None,
                    parar: Callable[[], None] | None = None) -> dict[str, Any]:
    """Lê a saída do COPIAR linha a linha, informa o progresso e monta o resumo."""
    res: dict[str, Any] = {"total": 0, "copiados": 0, "pulados": 0, "falhas": [], "bytes": 0, "cancelado": False}
    feitos = 0
    for linha in linhas:
        if cancelar is not None and cancelar.is_set():
            if parar:
                parar()
            res["cancelado"] = True
            break
        partes = linha.rstrip("\r\n").split("\t")
        tipo = partes[0]
        if tipo == "@@ERRO":
            raise MtpErro(partes[1] if len(partes) > 1 else "Falha na cópia.")
        if tipo == "@@TOTAL":
            res["total"] = int(partes[1]) if len(partes) > 1 and partes[1].isdecimal() else 0
        elif tipo in ("@@OK", "@@PULOU", "@@FALHOU"):
            feitos += 1
            if tipo == "@@OK":
                res["copiados"] += 1
                res["bytes"] += int(partes[2]) if len(partes) > 2 and partes[2].isdigit() else 0
            elif tipo == "@@PULOU":
                res["pulados"] += 1
            else:
                res["falhas"].append(partes[1] if len(partes) > 1 else "?")
            if progresso:
                progresso({"etapa": "mtp", "descricao": "Copiando pelo modo Transferência de arquivos",
                           "detalhe": partes[1] if len(partes) > 1 else "", "atual": feitos,
                           "total": res["total"] or None, "estimativa_s": None})
    return res
