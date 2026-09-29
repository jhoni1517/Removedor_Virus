"""Ponta a ponta: CLI contra o ADB simulado (sem celular)."""

import json
import subprocess
import sys
from pathlib import Path

from conftest import RAIZ


def rodar(env, *args):
    return subprocess.run([sys.executable, str(RAIZ / "celscan.py"), *args], env=env, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=120)


def test_android_sem_teclado_gera_laudo(ambiente_fake, tmp_path):
    r = rodar(ambiente_fake, "android", "--nao-abrir", "--sem-iocs", "--saida", str(tmp_path / "laudos"))
    assert r.returncode == 0, r.stdout + r.stderr
    laudos = list((tmp_path / "laudos").glob("*.json"))
    assert len(laudos) == 1
    dados = json.loads(laudos[0].read_text(encoding="utf-8"))
    assert dados["nota"] == 45 or dados["nota"] < 50  # depende da data de hoje (patch antigo)
    assert dados["apps"][0]["pacote"] == "com.systemservice"
    ss = dados["apps"][0]
    assert ss["cert"]["debug"] is True  # certificado lido pelo exec-out/dd do APK sintético
    assert Path(ambiente_fake["CELSCAN_HOME"], "logs", "celscan.log").exists()


def test_android_remover_tira_admin(ambiente_fake, tmp_path):
    r = rodar(ambiente_fake, "android", "--nao-abrir", "--sem-iocs", "--remover", "--saida", str(tmp_path / "l"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "removido" in r.stdout
    log = Path(ambiente_fake["CELSCAN_FAKE_ESTADO"], "comandos.log").read_text(encoding="utf-8")
    assert "dpm remove-active-admin --user 0 com.systemservice/com.systemservice.AdminRcv" in log
    assert "uninstall com.systemservice" in log


def test_otimizar_e_desfazer(ambiente_fake):
    r = rodar(ambiente_fake, "otimizar", "--animacoes", "0.5")
    assert r.returncode == 0, r.stdout + r.stderr
    ident = next(Path(ambiente_fake["CELSCAN_HOME"], "quarentena").iterdir()).name
    r = rodar(ambiente_fake, "quarentena", "restaurar", ident)
    assert "Restaurado" in r.stdout, r.stdout
