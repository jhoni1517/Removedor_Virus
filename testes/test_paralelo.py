"""Leituras por app em paralelo: progresso no fio principal, erro propaga."""

import threading
import time

import pytest

from celscan import servicos


def test_roda_todos_e_conta_progresso():
    feitos, fios, passos = set(), set(), []

    def tarefa(p):
        time.sleep(0.02)
        fios.add(threading.current_thread().name)
        feitos.add(p)

    servicos._em_paralelo([f"app{i}" for i in range(12)], tarefa, lambda i, p: passos.append(i))
    assert len(feitos) == 12 and passos == list(range(1, 13))
    assert len(fios) > 1  # usou mais de um fio


def test_erro_propaga():
    def tarefa(p):
        if p == "ruim":
            raise RuntimeError("cabo saiu")

    with pytest.raises(RuntimeError):
        servicos._em_paralelo(["a", "ruim", "b"], tarefa, lambda i, p: None)


def test_cancelamento_no_progresso_para(monkeypatch):
    class Cancelado(Exception):
        pass

    def avancar(i, p):
        if i == 2:
            raise Cancelado

    with pytest.raises(Cancelado):
        servicos._em_paralelo([f"x{i}" for i in range(20)], lambda p: time.sleep(0.01), avancar)
