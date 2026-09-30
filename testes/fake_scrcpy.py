"""scrcpy simulado: registra os argumentos e fica aberto até ser encerrado.

CELSCAN_FAKE_SCRCPY_ERRO=1 faz ele fechar na hora com erro (como quando o celular não autorizou).
"""

import os
import sys
import time

estado = os.getenv("CELSCAN_FAKE_ESTADO") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".estado")
os.makedirs(estado, exist_ok=True)
with open(os.path.join(estado, "scrcpy.log"), "a", encoding="utf-8") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
if os.getenv("CELSCAN_FAKE_SCRCPY_ERRO"):
    sys.stderr.write("ERROR: Device is unauthorized\n")
    sys.exit(1)
while True:
    time.sleep(0.2)
