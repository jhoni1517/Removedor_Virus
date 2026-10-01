"""Operações completas (varrer, remover, desfazer) usadas pela CLI e pela interface.

Cada operação informa o progresso por eventos e pode ser cancelada entre um passo e outro.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

from celscan.acoes import quarentena
from celscan.analise import iocs as iocs_mod
from celscan.analise.pontuacao import nota
from celscan.analise.virustotal import VirusTotal
from celscan.core import adb, bases, db, log, preferencias
from celscan.core import agente as agente_mod
from celscan.core.adb import AdbErro, Aparelho
from celscan.varredura import Varredura

Evento = dict[str, Any]
Progresso = Callable[[Evento], None]

MODOS = {
    "rapido": "Rápido: apps, permissões, assinaturas e ameaças conhecidas (1–2 min)",
    "completo": "Completo: tudo do rápido + VirusTotal nos apps suspeitos",
    "profundo": "Profundo: coleta forense AndroidQF + MVT (chega na Etapa B)",
}

# etapa -> (texto para o usuário, segundos estimados para ~150 apps)
ETAPAS = {
    "coleta": ("Lendo apps e configurações do aparelho", 25),
    "iocs": ("Carregando a lista de ameaças conhecidas", 5),
    "hashes": ("Calculando a impressão digital de cada app", 40),
    "assinaturas": ("Conferindo a assinatura dos apps suspeitos", 15),
    "rotulos": ("Lendo o nome e o ícone dos apps", 12),
    "virustotal": ("Consultando o VirusTotal", 0),
    "analise": ("Analisando e montando o resultado", 2),
}


class Cancelado(Exception):
    """O usuário cancelou a operação."""


class AparelhoDesconectado(AdbErro):
    """O cabo saiu (ou a depuração foi revogada) no meio da operação."""


class ModoIndisponivel(Exception):
    pass


@dataclass
class OpcoesVarredura:
    modo: str = "rapido"
    sistema: bool = False
    usar_iocs: bool = True
    vt_todos: bool = False
    cliente_id: int | None = None


@dataclass
class ResultadoVarredura:
    varredura_id: int
    modo: str
    info: dict[str, str]
    nota: int
    veredito: str
    achados: list[dict]
    resultados: list[dict]
    avisos: list[str] = field(default_factory=list)
    duracao_s: float = 0.0

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


def _nada(_: Evento) -> None:
    pass


def verificar_conexao(serial: str, erro: Exception) -> Exception:
    """Troca um erro de adb por AparelhoDesconectado quando o aparelho sumiu."""
    try:
        prontos = [s for s, estado in adb.dispositivos() if estado == "device"]
    except AdbErro:
        prontos = []
    if serial not in prontos:
        return AparelhoDesconectado(
            "O celular foi desconectado ou bloqueou a depuração USB. Reconecte o cabo, desbloqueie a tela "
            "e tente de novo. Nada foi alterado no aparelho.")
    return erro


class _Passos:
    """Emite eventos de progresso e confere o cancelamento."""

    def __init__(self, progresso: Progresso, cancelar: threading.Event | None):
        self.progresso, self.cancelar = progresso, cancelar

    def checar(self) -> None:
        if self.cancelar is not None and self.cancelar.is_set():
            raise Cancelado("Operação cancelada. Nada foi alterado no aparelho.")

    def etapa(self, nome: str, atual: int | None = None, total: int | None = None, detalhe: str = "") -> None:
        self.checar()
        texto, estimativa = ETAPAS.get(nome, (nome, 0))
        self.progresso({"etapa": nome, "descricao": texto, "detalhe": detalhe, "atual": atual, "total": total,
                        "estimativa_s": estimativa})


TRABALHADORES = int(os.getenv("CELSCAN_PARALELO", "4"))


def _em_paralelo(pacotes: list[str], tarefa: Callable[[str], Any], avancar: Callable[[int, str], None]) -> None:
    """Roda `tarefa(pacote)` em paralelo (cada leitura é uma conexão separada com o adb).

    O progresso e o cancelamento continuam no fio principal: `avancar` é chamado a cada app concluído.
    """
    if TRABALHADORES <= 1 or len(pacotes) < 2:
        for i, pkg in enumerate(pacotes, 1):
            avancar(i, pkg)
            tarefa(pkg)
        return
    with ThreadPoolExecutor(max_workers=TRABALHADORES, thread_name_prefix="celscan-leitura") as ex:
        futuros = {ex.submit(tarefa, pkg): pkg for pkg in pacotes}
        try:
            for i, f in enumerate(as_completed(futuros), 1):
                avancar(i, futuros[f])
                f.result()
        except BaseException:
            for f in futuros:
                f.cancel()
            raise


def executar_varredura(ap: Aparelho, opcoes: OpcoesVarredura | None = None, progresso: Progresso = _nada,
                       cancelar: threading.Event | None = None, conexao=None) -> ResultadoVarredura:
    opcoes = opcoes or OpcoesVarredura()
    if opcoes.modo not in MODOS:
        raise ValueError(f"modo desconhecido: {opcoes.modo}")
    if opcoes.modo == "profundo":
        raise ModoIndisponivel("O modo Profundo (AndroidQF + MVT) chega na Etapa B. Use o Completo por enquanto.")
    passos = _Passos(progresso, cancelar)
    inicio = time.perf_counter()
    chave_vt = preferencias.chave_virustotal() if opcoes.modo == "completo" else None
    vt = VirusTotal(chave_vt) if chave_vt else None
    atualizacao = bases.atualizar_em_segundo_plano(["iocs"]) if opcoes.usar_iocs else None
    sc = Varredura(ap, vt, None, sistema=opcoes.sistema)
    try:
        passos.etapa("coleta")
        with log.etapa("coleta"):
            sc.coletar()
        avisos = list(sc.avisos)
        if opcoes.modo == "completo" and not vt:
            avisos.append("VirusTotal não consultado: cadastre sua chave gratuita em Configurações.")

        if atualizacao is not None:
            passos.etapa("iocs")
            atualizacao.join(timeout=120)
            sc.iocs = iocs_mod.carregar(avisar=lambda m: None)
            if not sc.iocs:
                avisos.append("Lista de ameaças conhecidas indisponível (sem internet e sem cópia local).")

        total = len(sc.apps)
        with log.etapa("hashes"):
            for i, pkg in enumerate(sc.calcular_hashes(), 1):
                passos.etapa("hashes", i, total, pkg)

        cands = sc.candidatos()
        with log.etapa("assinaturas"):
            _em_paralelo(cands, sc.ler_certificado, lambda i, pkg: passos.etapa("assinaturas", i, len(cands), pkg))
        sem_nome = cands
        if preferencias.ler().get("usar_agente") and agente_mod.disponivel():
            passos.etapa("rotulos", 0, len(cands), "CelScan Agente")
            try:
                with log.etapa("agente"), agente_mod.Agente(ap) as ag:
                    for pkg, dados in ag.apps(icones=True).items():
                        if pkg in sc.apps:
                            sc.apps[pkg].nome, sc.apps[pkg].icone = dados["nome"], dados["icone"]
                sem_nome = [p for p in cands if not sc.apps[p].nome]
            except AdbErro as e:  # inclui AgenteIndisponivel: cai para a leitura do APK
                avisos.append(f"CelScan Agente indisponível ({e}); nomes lidos direto dos APKs.")
        with log.etapa("rotulos"):
            _em_paralelo(sem_nome, sc.ler_rotulo, lambda i, pkg: passos.etapa("rotulos", i, len(sem_nome), pkg))

        if vt:
            alvo = sc.candidatos(todos=opcoes.vt_todos)
            with log.etapa("virustotal"):
                for i, pkg in enumerate(alvo, 1):
                    passos.etapa("virustotal", i, len(alvo), pkg)
                    sc.consultar_vt(pkg)
    except AdbErro as e:
        raise verificar_conexao(ap.serial, e) from e

    passos.etapa("analise")
    achados, resultados = sc.pontuar()
    n, veredito = nota(achados, resultados)
    duracao = time.perf_counter() - inicio
    info = sc.info()
    con = conexao or db.conectar()
    vid = db.salvar_varredura(con, info, n, veredito, achados, resultados, avisos, duracao, modo=opcoes.modo,
                              cliente_id=opcoes.cliente_id)
    log.LOGGER.info("varredura %d (%s): %d apps em %.1fs, nota %d", vid, opcoes.modo, len(resultados), duracao, n)
    return ResultadoVarredura(vid, opcoes.modo, info, n, veredito, achados, resultados, avisos, duracao)


def remover_apps(ap: Aparelho, alvos: list[dict], progresso: Progresso = _nada,
                 cancelar: threading.Event | None = None, conexao=None) -> list[dict[str, Any]]:
    """Remove cada app (com cópia na quarentena). `alvos` são resultados da varredura."""
    from celscan.acoes import remocao

    passos = _Passos(progresso, cancelar)
    con = conexao or db.conectar()
    feitos = []
    for i, r in enumerate(alvos, 1):
        passos.checar()
        progresso({"etapa": "remocao", "descricao": "Removendo apps", "detalhe": r["pacote"], "atual": i,
                   "total": len(alvos), "estimativa_s": 10})
        try:
            ok, msg = remocao.remover(ap, r)
        except AdbErro as e:
            raise verificar_conexao(ap.serial, e) from e
        qid = r.get("quarentena_id")
        if ok:
            db.registrar_acao(con, ap.serial, "remocao", r["pacote"], msg, qid)
        feitos.append({"pacote": r["pacote"], "ok": ok, "mensagem": msg, "quarentena_id": qid})
    return feitos


def desfazer(ap: Aparelho, quarentena_id: str, conexao=None) -> dict[str, Any]:
    try:
        ok, msg = quarentena.restaurar(ap, quarentena_id)
    except AdbErro as e:
        raise verificar_conexao(ap.serial, e) from e
    if ok:
        db.marcar_desfeita(conexao or db.conectar(), quarentena_id)
    return {"quarentena_id": quarentena_id, "ok": ok, "mensagem": msg}
