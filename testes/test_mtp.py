"""Resgate sem depuração (MTP): leitura da saída do Windows, progresso, cancelamento e a API.

O PowerShell/Shell do Windows só existe no Windows; aqui testamos tudo o que o Python faz com a saída.
"""

import threading

import pytest
from test_api import H, cliente  # noqa: F401

from celscan.acoes import mtp

LISTA = (
    "@@VAZIO\tGalaxy A10\n"
    "@@DEV\tRedmi Note 15 Pro 5G\n"
    "@@ARM\tRedmi Note 15 Pro 5G\tArmazenamento interno compartilhado\n"
    "@@PASTA\tRedmi Note 15 Pro 5G\tArmazenamento interno compartilhado\tDCIM\n"
    "@@PASTA\tRedmi Note 15 Pro 5G\tArmazenamento interno compartilhado\tAndroid/media/com.whatsapp/WhatsApp/Media\n"
    "@@PASTA\tRedmi Note 15 Pro 5G\tArmazenamento interno compartilhado\t../../Windows\n"  # nunca vem do nosso script
)


def test_analisa_lista():
    r = mtp.analisar_lista(LISTA)
    assert r["so_carregando"] == ["Galaxy A10"]
    (ap,) = r["aparelhos"]
    (arm,) = ap["armazenamentos"]
    assert [p["caminho"] for p in arm["pastas"]] == ["DCIM", "Android/media/com.whatsapp/WhatsApp/Media"]
    assert arm["pastas"][1]["nome"] == "Mídia do WhatsApp"


def test_processa_copia_e_progresso():
    linhas = ["@@TOTAL\t3\n", "@@OK\tDCIM/Camera/a.jpg\t2048\n", "@@PULOU\tDCIM/Camera/b.jpg\n",
              "@@FALHOU\tDCIM/Camera/c.mp4\n", "@@FIM\n"]
    passos = []
    r = mtp.processar_copia(linhas, passos.append)
    assert r == {"total": 3, "copiados": 1, "pulados": 1, "falhas": ["DCIM/Camera/c.mp4"], "bytes": 2048,
                 "cancelado": False}
    assert [p["atual"] for p in passos] == [1, 2, 3] and passos[-1]["total"] == 3


def test_erro_do_windows_vira_mensagem():
    with pytest.raises(mtp.MtpErro, match="não aparece"):
        mtp.processar_copia(["@@ERRO\tO celular não aparece mais no Windows.\n"])


def test_cancelar_para_o_processo():
    parado = []
    ev = threading.Event()
    ev.set()
    r = mtp.processar_copia(["@@TOTAL\t9\n", "@@OK\tx\t1\n"], cancelar=ev, parar=lambda: parado.append(1))
    assert r["cancelado"] and parado == [1] and r["copiados"] == 0


def test_fora_do_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(mtp, "disponivel", lambda: False)
    assert mtp.listar() == {"windows": False, "aparelhos": [], "so_carregando": []}
    with pytest.raises(mtp.MtpErro):
        mtp.copiar("x", "y", ["DCIM"], tmp_path)


def test_pasta_fora_da_lista_e_recusada(monkeypatch, tmp_path):
    monkeypatch.setattr(mtp, "disponivel", lambda: True)
    with pytest.raises(mtp.MtpErro):
        mtp.copiar("x", "y", ["../../Windows"], tmp_path)


def test_api(cliente, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mtp, "listar", lambda: {"windows": True, **mtp.analisar_lista(LISTA)})
    r = cliente.get("/api/mtp/aparelhos", headers=H).json()
    assert r["aparelhos"][0]["nome"] == "Redmi Note 15 Pro 5G"

    monkeypatch.setattr(mtp, "disponivel", lambda: True)
    corpo = {"aparelho": "Redmi", "armazenamento": "Interno", "pastas": ["../../Windows"]}
    assert cliente.post("/api/mtp/copiar", json=corpo, headers=H).status_code == 422


@pytest.mark.skipif(not mtp.disponivel(), reason="só no Windows (o CI do instalador roda lá)")
@pytest.mark.parametrize("nome", ["LISTAR", "COPIAR"])
def test_scripts_powershell_sem_erro_de_sintaxe(nome, tmp_path):
    import subprocess

    arq = tmp_path / "s.ps1"
    arq.write_text(getattr(mtp, nome), encoding="utf-8-sig")
    verifica = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
                f"'{arq}', [ref]$null, [ref]$e); $e.Count")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", verifica], capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "0", r.stdout + r.stderr


@pytest.mark.skipif(not mtp.disponivel(), reason="só no Windows")
def test_listar_de_verdade_sem_celular():
    r = mtp.listar()
    assert r["windows"] is True and isinstance(r["aparelhos"], list)
