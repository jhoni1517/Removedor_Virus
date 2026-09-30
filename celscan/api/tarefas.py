"""Tarefas longas (varredura, remoção...) em segundo plano, com progresso para o WebSocket."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from celscan.core.log import LOGGER

Ouvinte = Callable[[dict[str, Any]], None]


@dataclass
class Tarefa:
    id: str
    tipo: str
    serial: str | None
    estado: str = "executando"  # executando | concluida | erro | cancelada
    progresso: dict[str, Any] = field(default_factory=dict)
    resultado: Any = None
    erro: str | None = None
    criada: float = field(default_factory=time.time)
    terminada: float | None = None
    cancelar: threading.Event = field(default_factory=threading.Event, repr=False)

    def publico(self) -> dict[str, Any]:
        return {"id": self.id, "tipo": self.tipo, "serial": self.serial, "estado": self.estado,
                "progresso": self.progresso, "resultado": self.resultado, "erro": self.erro,
                "criada": self.criada, "terminada": self.terminada}


class Gerenciador:
    def __init__(self) -> None:
        self._tarefas: dict[str, Tarefa] = {}
        self._ouvintes: list[Ouvinte] = []
        self._trava = threading.Lock()

    # ---- ouvintes (WebSocket)
    def ouvir(self, ouvinte: Ouvinte) -> None:
        with self._trava:
            self._ouvintes.append(ouvinte)

    def parar_de_ouvir(self, ouvinte: Ouvinte) -> None:
        with self._trava:
            if ouvinte in self._ouvintes:
                self._ouvintes.remove(ouvinte)

    def publicar(self, mensagem: dict[str, Any]) -> None:
        with self._trava:
            ouvintes = list(self._ouvintes)
        for o in ouvintes:
            try:
                o(mensagem)
            except Exception:  # um ouvinte com problema não derruba os outros
                LOGGER.exception("falha ao avisar ouvinte")

    # ---- tarefas
    def ocupado(self, serial: str | None) -> Tarefa | None:
        """Uma tarefa por aparelho de cada vez (evita dois comandos brigando pelo mesmo celular)."""
        with self._trava:
            return next((t for t in self._tarefas.values() if t.serial == serial and t.estado == "executando"),
                        None)

    def criar(self, tipo: str, serial: str | None,
              funcao: Callable[[Callable[[dict[str, Any]], None], threading.Event], Any],
              erros_esperados: tuple[type[BaseException], ...] = ()) -> Tarefa:
        tarefa = Tarefa(id=uuid.uuid4().hex[:12], tipo=tipo, serial=serial)
        with self._trava:
            self._tarefas[tarefa.id] = tarefa

        def progresso(evento: dict[str, Any]) -> None:
            tarefa.progresso = evento
            self.publicar({"tipo": "progresso", "tarefa": tarefa.id, "evento": evento})

        def rodar() -> None:
            from celscan.servicos import Cancelado

            try:
                tarefa.resultado = funcao(progresso, tarefa.cancelar)
                tarefa.estado = "concluida"
            except Cancelado as e:
                tarefa.estado, tarefa.erro = "cancelada", str(e)
            except erros_esperados as e:
                tarefa.estado, tarefa.erro = "erro", str(e)
            except Exception as e:
                LOGGER.error("tarefa %s (%s) falhou: %s\n%s", tarefa.id, tipo, e, traceback.format_exc())
                tarefa.estado, tarefa.erro = "erro", f"Erro inesperado: {e}. Detalhes no log."
            tarefa.terminada = time.time()
            self.publicar({"tipo": "tarefa", "tarefa": tarefa.publico()})

        self.publicar({"tipo": "tarefa", "tarefa": tarefa.publico()})
        threading.Thread(target=rodar, name=f"tarefa-{tipo}", daemon=True).start()
        return tarefa

    def obter(self, ident: str) -> Tarefa | None:
        return self._tarefas.get(ident)

    def listar(self) -> list[Tarefa]:
        return sorted(self._tarefas.values(), key=lambda t: t.criada, reverse=True)

    def cancelar(self, ident: str) -> bool:
        t = self._tarefas.get(ident)
        if not t or t.estado != "executando":
            return False
        t.cancelar.set()
        return True
