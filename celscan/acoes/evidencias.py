"""Documentar antes de remover (modo proteção à vítima).

Gera, no computador, um relatório de evidências sobre apps suspeitos de vigilância, SEM alterar
nada no celular: dados do app (versão, instalação, instalador, permissões), hash do APK,
certificado, um print da tela e um manifesto com o SHA-256 de cada arquivo (para provar depois
que nada foi mexido). Serve de apoio a um boletim de ocorrência.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from celscan.acoes.backup import nome_seguro
from celscan.config import DADOS
from celscan.core.adb import AdbErro, Aparelho

APOIO: dict[str, Any] = yaml.safe_load((DADOS / "apoio.yaml").read_text(encoding="utf-8"))


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _dump_pacote(ap: Aparelho, pacote: str) -> str:
    """Trecho do dumpsys só deste pacote (datas, instalador, permissões concedidas)."""
    try:
        return ap.sh(f"dumpsys package {shlex.quote(pacote)}", timeout=60)
    except AdbErro as e:
        return f"(não foi possível ler: {e})"


def documentar(ap: Aparelho, achados: list[dict[str, Any]], destino: Path, info: dict[str, str] | None = None,
               print_tela: bool = True) -> dict[str, Any]:
    """achados: itens do resultado da varredura (pacote, ameaca, versao, instalado, instalador, sha256, cert, motivos).

    Devolve {pasta, arquivos, manifesto_sha256}.
    """
    agora = datetime.now()
    pasta = destino / f"Evidencias_{agora:%Y%m%d_%H%M%S}"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos: list[Path] = []

    resumo = {
        "gerado_em": agora.isoformat(timespec="seconds"),
        "aparelho": info or {},
        "serial": ap.serial,
        "apps": [{k: a.get(k) for k in ("pacote", "nome", "ameaca", "versao", "instalado", "instalador",
                                        "sha256", "cert", "motivos")} for a in achados],
        "observacao": "Gerado pelo CelScan sem alterar o celular. Os hashes no MANIFESTO provam a integridade.",
    }
    r = pasta / "resumo.json"
    r.write_text(json.dumps(resumo, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    arquivos.append(r)

    for a in achados:
        pkg = a.get("pacote") or ""
        if not pkg:
            continue
        d = pasta / f"dumpsys_{nome_seguro(pkg)}.txt"
        d.write_text(_dump_pacote(ap, pkg), encoding="utf-8")
        arquivos.append(d)

    if print_tela:
        try:
            png = ap.bytes("screencap -p", timeout=30)
            if png.startswith(b"\x89PNG"):
                t = pasta / f"tela_{agora:%H%M%S}.png"
                t.write_bytes(png)
                arquivos.append(t)
        except AdbErro:
            pass  # sem print: o resto do relatório continua válido

    leia = pasta / "LEIA-ME.txt"
    linhas = [
        "RELATÓRIO DE EVIDÊNCIAS — CelScan",
        f"Gerado em {agora:%d/%m/%Y %H:%M:%S}. Nada foi alterado no celular para gerar este relatório.",
        "",
        "Apps encontrados:",
        *[f"- {a.get('nome') or a.get('pacote')} ({a.get('pacote')}): {a.get('ameaca') or 'suspeito'}; "
          f"instalado em {a.get('instalado') or '?'}; SHA-256 do APK {a.get('sha256') or '?'}" for a in achados],
        "",
        "Onde buscar ajuda:",
        *[f"- {c['nome']}: {c['contato']} — {c['descricao']}" for c in APOIO["contatos"]],
        "",
        "O arquivo MANIFESTO.sha256 lista o hash de cada arquivo desta pasta. Se algum arquivo for",
        "alterado, o hash deixa de bater — isso ajuda a mostrar que as provas estão íntegras.",
        "",
        APOIO["lgpd"],
    ]
    leia.write_text("\n".join(linhas), encoding="utf-8")
    arquivos.append(leia)

    manifesto = pasta / "MANIFESTO.sha256"
    manifesto.write_text("".join(f"{_sha256(f)}  {f.name}\n" for f in arquivos), encoding="utf-8")
    return {"pasta": str(pasta), "arquivos": [f.name for f in arquivos], "manifesto_sha256": _sha256(manifesto)}


def eh_vigilancia(resultado: dict[str, Any]) -> bool:
    """True para apps que acionam o modo vítima: indicador de stalkerware/spyware conhecido."""
    ameaca = (resultado.get("ameaca") or "").lower()
    return bool(ameaca) and any(p in ameaca for p in ("stalkerware", "spyware", "pegasus", "predator", "espião"))
