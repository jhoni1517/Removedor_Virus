"""Motor CelScan (antivírus local) e a redução de falsos positivos em apps oficiais."""

from __future__ import annotations

import io
import os
import struct
import zipfile
from datetime import datetime

from celscan.analise import motor, pix, pontuacao
from celscan.core import agente
from celscan.core.coleta import AppBruto, DadosAparelho


def dex(*strings: str) -> bytes:
    """classes.dex mínimo com uma tabela de strings (o que o motor lê)."""
    dados = b""
    offs = []
    base = 0x70 + 4 * len(strings)
    for st in strings:
        b = st.encode()
        offs.append(base + len(dados))
        dados += bytes([len(b)]) + b + b"\x00"
    cab = bytearray(0x70)
    cab[0:8] = b"dex\n035\x00"
    struct.pack_into("<II", cab, 0x38, len(strings), 0x70)
    return bytes(cab) + b"".join(struct.pack("<I", o) for o in offs) + dados


class Zip:
    def __init__(self, arquivos: dict[str, bytes]):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n, b in arquivos.items():
                z.writestr(n, b)
        self.z = zipfile.ZipFile(buf)

    def nomes(self):
        return self.z.namelist()

    def __contains__(self, n):
        return n in self.z.namelist()

    def tamanho_de(self, n):
        return self.z.getinfo(n).compress_size

    def ler_arquivo(self, n, limite=0):
        return self.z.read(n)


BANCOS = list(pix.carregar().oficiais)[:5]


def test_le_strings_do_dex():
    assert motor.strings_dex(dex("abc", "Landroid/x;")) == [b"abc", b"Landroid/x;"]
    assert motor.strings_dex(b"lixo") == []


def test_trojan_bancario_pelo_codigo():
    codigo = dex(*BANCOS, "Landroid/accessibilityservice/AccessibilityService;", "dispatchGesture",
                 "chave pix", "https://api.telegram.org/bot123:abc/sendMessage")
    r = motor.analisar_zip(Zip({"classes.dex": codigo}), "com.leitor.pdf.pro")
    chaves = {a["chave"] for a in r["achados"]}
    assert {"motor_bancos_alvo", "motor_pix", "motor_canal_envio"} <= chaves
    assert len(r["bancos_alvo"]) >= 3


def test_dropper_com_apk_escondido():
    r = motor.analisar_zip(Zip({"classes.dex": dex("Ldalvik/system/DexClassLoader;"),
                                "assets/update.dat": b"PK\x03\x04" + os.urandom(80000)}), "com.x")
    assert any(a["chave"] == "motor_payload" for a in r["achados"])


def test_app_limpo_nao_tem_achado():
    r = motor.analisar_zip(Zip({"classes.dex": dex("Landroid/app/Activity;", "Olá"),
                                "assets/fonte.ttf": os.urandom(90000)}), "com.limpo")
    assert r["achados"] == []


# ---------------------------------------------------------------------------------------------- falsos positivos
AGORA = datetime(2026, 11, 18)


def _dados(**apps) -> DadosAparelho:
    return DadosAparelho(serial="X", props={}, apps=apps, icones=set(apps))


def test_app_oficial_da_loja_nao_vira_risco_por_permissao():
    w = AppBruto("com.whatsapp", "/data/app/w/base.apk", "com.android.vending", False, nome="WhatsApp",
                 perms={"android.permission.RECORD_AUDIO", "android.permission.CAMERA",
                        "android.permission.READ_CONTACTS", "android.permission.ACCESS_FINE_LOCATION",
                        "android.permission.READ_CALL_LOG", "android.permission.ACCESS_BACKGROUND_LOCATION"},
                 appops={"SYSTEM_ALERT_WINDOW"}, instalado=datetime(2025, 1, 1))
    d = _dados(**{"com.whatsapp": w})
    d.sempre_ativo = {"com.whatsapp"}
    r = pontuacao.pontuar_app(w, d, agora=AGORA)
    assert r["nivel"] in ("OK", "BAIXO") and r["score"] < 30


def test_mesmas_permissoes_fora_da_loja_continuam_pesando():
    x = AppBruto("com.x.app", "/data/app/x/base.apk", "com.google.android.packageinstaller", False, nome="App X",
                 perms={"android.permission.READ_SMS", "android.permission.RECEIVE_SMS"},
                 appops={"SYSTEM_ALERT_WINDOW"}, instalado=datetime(2025, 1, 1))
    r = pontuacao.pontuar_app(x, _dados(**{"com.x.app": x}), agora=AGORA)
    assert r["score"] >= 60


def test_leitor_de_pdf_da_play_com_poder_de_virus_e_pego():
    p = AppBruto("com.pdf.reader.docs", "/data/app/p/base.apk", "com.android.vending", False,
                 nome="PDF Reader - Document Manager", appops={"REQUEST_INSTALL_PACKAGES"},
                 instalado=datetime(2025, 1, 1))
    d = _dados(**{"com.pdf.reader.docs": p})
    d.acess = {"com.pdf.reader.docs"}
    r = pontuacao.pontuar_app(p, d, agora=AGORA)
    assert r["nivel"] == "ALTO"
    assert any(a["chave"] == "utilitario_poderoso" for a in r["achados"])


def test_achado_do_motor_pesa_menos_em_app_da_loja():
    m = {"achados": [{"chave": "motor_payload", "detalhe": "assets/a.dat", "peso_loja": 10}]}
    loja = AppBruto("com.a", "/x", "com.android.vending", False, nome="A", motor=m, instalado=datetime(2025, 1, 1))
    fora = AppBruto("com.b", "/y", None, False, nome="B", motor=m, instalado=datetime(2025, 1, 1))
    d = _dados(**{"com.a": loja, "com.b": fora})
    ra = pontuacao.pontuar_app(loja, d, agora=AGORA)
    rb = pontuacao.pontuar_app(fora, d, agora=AGORA)
    assert ra["score"] == 10 and rb["score"] > 45


def test_explica_bloqueio_do_agente_na_xiaomi():
    assert "Instalar via USB" in agente.explicar_falha("Failure [INSTALL_FAILED_USER_RESTRICTED]", "Xiaomi")


def test_rapida_mostra_apps_de_fabrica_com_icone():
    from celscan.core import coleta, parsers
    from conftest import ler_fixture
    s = parsers.secoes(ler_fixture("sintetico/coleta.txt"))
    s["sisvis"] = ("package:/system/app/Browser/Browser.apk=com.mi.globalbrowser  installer=null\n"
                   "package:/system/app/Svc/Svc.apk=com.android.servico  installer=null\n")
    s["launcher"] = s["launcher"] + "\ncom.mi.globalbrowser/.Main\n"
    d = coleta.montar("ABC123", s)
    assert d.apps["com.mi.globalbrowser"].so_lista and d.apps["com.mi.globalbrowser"].sistema
    assert "com.android.servico" not in d.apps  # sem ícone: continua fora da varredura rápida


def test_ler_pedacos_do_app():
    from celscan.analise import rotulos

    class Ap:
        def sh(self, cmd, timeout=120, erro=False):
            return ("120000 /data/app/x/base.apk\n9000 /data/app/x/split_config.xxhdpi.apk\n"
                    "800 /data/app/x/split_config.pt.apk")
    assert rotulos.pedacos(Ap(), "com.x") == [("/data/app/x/split_config.xxhdpi.apk", 9000),
                                               ("/data/app/x/split_config.pt.apk", 800)]


def test_zip_de_varios_pedacos_acha_o_arquivo_no_pedaco():
    from celscan.analise import rotulos
    base, pedaco = Zip({"AndroidManifest.xml": b"x"}), Zip({"res/mipmap-xxhdpi/ic.png": b"PNG"})
    z = rotulos._ZipVarios([base, pedaco])
    assert "res/mipmap-xxhdpi/ic.png" in z and z.ler_arquivo("res/mipmap-xxhdpi/ic.png") == b"PNG"
