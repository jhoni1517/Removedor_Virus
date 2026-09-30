"""Percorre a interface no navegador com o celular simulado e tira fotos de cada tela.

Uso (precisa de `pip install playwright` e da interface compilada em celscan/web/dist):
    CELSCAN_ADB=testes/fake_adb.py APK_TESTE=<um .apk> CELSCAN_OFFLINE=1 python testes/e2e_interface.py fotos/
Opcional: CELSCAN_CHROME=<caminho do Chromium>.
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright

from celscan.api import servidor

SAIDA = sys.argv[1] if len(sys.argv) > 1 else "."
CHROME = os.getenv("CELSCAN_CHROME")
servidor_, url = servidor.subir()
erros = []
with sync_playwright() as p:
    nav = p.chromium.launch(executable_path=CHROME) if CHROME else p.chromium.launch()
    pg = nav.new_page(viewport={"width": 1360, "height": 880})
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pg.goto(url)
    pg.get_by_text("motorola moto g54 5G").first.wait_for(timeout=15000)
    time.sleep(0.5)
    pg.screenshot(path=f"{SAIDA}/1_conectar.png", full_page=True)
    pg.get_by_role("button", name="Usar este aparelho").click()
    pg.get_by_role("button", name="Iniciar varredura").wait_for()
    pg.get_by_role("radio", name=re.compile("^Completo")).click()
    pg.screenshot(path=f"{SAIDA}/2_modo.png")
    pg.get_by_role("radio", name=re.compile("^Rápido")).click()
    pg.get_by_role("button", name="Iniciar varredura").click()
    pg.get_by_text("Verificando o celular").wait_for()
    time.sleep(0.3)
    pg.screenshot(path=f"{SAIDA}/3_varrendo.png")
    pg.get_by_text("Laudo técnico").wait_for(timeout=60000)
    time.sleep(1.2)
    pg.screenshot(path=f"{SAIDA}/4_resultado.png", full_page=True)
    pg.get_by_role("button", name="Remover").first.click()
    pg.get_by_role("dialog").wait_for()
    pg.screenshot(path=f"{SAIDA}/5_confirmar.png")
    pg.get_by_role("dialog").get_by_role("button", name="Remover").click()
    pg.get_by_role("button", name="Desfazer").wait_for(timeout=30000)
    pg.screenshot(path=f"{SAIDA}/6_removido_toast.png")
    pg.get_by_role("button", name="Desfazer").click()
    pg.get_by_text("restaurado").wait_for(timeout=30000)
    pg.keyboard.press("Alt+3")
    pg.get_by_text("Quarentena e alterações").wait_for()
    time.sleep(0.5)
    pg.screenshot(path=f"{SAIDA}/7_historico.png", full_page=True)
    pg.keyboard.press("Alt+4")
    pg.get_by_role("radio", name="Escuro").click()
    pg.keyboard.press("Alt+1")
    time.sleep(0.8)
    pg.screenshot(path=f"{SAIDA}/8_resultado_escuro.png")
    # Tela quebrada: espelhar e copiar os dados
    pg.keyboard.press("Alt+2")
    pg.get_by_role("button", name="Abrir a tela").click()
    pg.get_by_text("abriu numa janela nova").wait_for(timeout=15000)
    pg.get_by_role("button", name="Calcular tamanho").click()
    pg.get_by_text("no total").wait_for(timeout=20000)
    pg.get_by_role("button", name="Copiar para o PC").click()
    pg.get_by_text("copiado(s) agora").wait_for(timeout=30000)
    time.sleep(0.5)
    pg.screenshot(path=f"{SAIDA}/10_tela_quebrada.png", full_page=True)
    pg.get_by_role("radio", name=re.compile("toque não funciona")).click()
    time.sleep(0.4)
    pg.screenshot(path=f"{SAIDA}/11_toque_quebrado.png", full_page=True)
    pg.keyboard.press("Alt+1")
    # Wi-Fi: abre o modal e confere o QR
    pg.get_by_role("button", name="Nova varredura").click()
    pg.get_by_role("button", name="Conectar pelo Wi-Fi").click()
    pg.locator(".qr svg").wait_for(timeout=10000)
    time.sleep(0.6)
    pg.screenshot(path=f"{SAIDA}/9_wifi_escuro.png")
    pg.keyboard.press("Escape")
    nav.close()
servidor_.should_exit = True
print("erros no console:", erros or "nenhum")
