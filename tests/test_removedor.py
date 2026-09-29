import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from removedor_virus.acoes import Removedor, dns_antianuncios
from removedor_virus.adb import ADB, nome_seguro, parse_dispositivos
from removedor_virus.cli import parse_selecao
from removedor_virus.heuristicas import App, Assinaturas, avaliar, carregar_assinaturas
from removedor_virus.scanner import (
    Scanner,
    parse_acessibilidade,
    parse_componentes,
    parse_dumpsys_pacote,
    parse_launchers,
    parse_lista_pacotes,
    parse_lista_simples,
    parse_sha256,
)

LISTA_PACOTES = """package:/data/app/~~aB1==/com.limpa.booster-xY2==/base.apk=com.limpa.booster installer=null
package:/data/app/com.whatsapp-1/base.apk=com.whatsapp  installer=com.android.vending
package:/data/app/com.jogo.legal-2/base.apk=com.jogo.legal installer=com.android.vending
"""

DEVICE_POLICY = """Current Device Policy Manager state:
  Enabled Device Admins (User 0, provisioningState: 0):
    com.limpa.booster/.AdminReceiver:
      uid=10234
      policies:
    admin=ComponentInfo{com.limpa.booster/com.limpa.booster.AdminReceiver}
"""

LAUNCHERS = """2 activities found:
  Activity #0:
    priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false
    com.whatsapp/.Main
  Activity #1:
    com.jogo.legal/com.jogo.legal.MainActivity
"""

DUMPSYS_BOOSTER = """Packages:
  Package [com.limpa.booster] (abc):
    versionName=1.0.3
    firstInstallTime=2026-09-27 10:00:00
    requested permissions:
      android.permission.SYSTEM_ALERT_WINDOW
      android.permission.RECEIVE_BOOT_COMPLETED
      android.permission.REQUEST_INSTALL_PACKAGES: restricted=true
    install permissions:
      android.permission.INTERNET: granted=true
    runtime permissions:
      android.permission.READ_SMS: granted=true, flags=[ USER_SET ]
      android.permission.CAMERA: granted=false
"""


class FakeADB(ADB):
    """Simula o celular: responde por prefixo de comando e registra as chamadas."""

    def __init__(self, respostas: dict[str, str]):
        super().__init__(caminho="adb", serial="ABC123")
        self.respostas = respostas
        self.chamadas: list[str] = []

    def _responder(self, comando: str) -> str:
        self.chamadas.append(comando)
        for prefixo in sorted(self.respostas, key=len, reverse=True):
            if comando.startswith(prefixo):
                return self.respostas[prefixo]
        return ""

    def shell(self, *args, timeout=60):
        return self._responder(" ".join(args))

    def executar(self, *args, timeout=60, checar=True):
        if args[0] == "pull":
            Path(args[2]).write_bytes(b"apk")
        return self._responder(" ".join(args))


def celular_infectado() -> FakeADB:
    return FakeADB({
        "pm list packages": LISTA_PACOTES,
        "dumpsys device_policy": DEVICE_POLICY,
        "settings get secure enabled_accessibility_services":
            "com.limpa.booster/com.limpa.booster.Svc:com.outro/.Acess",
        "appops query-op": "com.limpa.booster\n",
        "cmd package query-activities": LAUNCHERS,
        "dumpsys package com.limpa.booster": DUMPSYS_BOOSTER,
        "dumpsys package com.whatsapp": "versionName=2.24\n",
        "dumpsys package com.jogo.legal": "versionName=5\nfirstInstallTime=2020-01-01 00:00:00\n",
        "pm path com.limpa.booster": "package:/data/app/x/base.apk\npackage:/data/app/x/split_config.arm64_v8a.apk\n",
        "dpm remove-active-admin": "Success: Admin removed",
        "pm uninstall com.limpa.booster": "Success",
    })


class TestParsers(unittest.TestCase):
    def test_lista_pacotes(self):
        pacotes = parse_lista_pacotes(LISTA_PACOTES)
        self.assertEqual(
            pacotes["com.limpa.booster"],
            ("/data/app/~~aB1==/com.limpa.booster-xY2==/base.apk", None),
        )
        self.assertEqual(pacotes["com.whatsapp"][1], "com.android.vending")

    def test_componentes_admin(self):
        self.assertEqual(parse_componentes(DEVICE_POLICY), ["com.limpa.booster/com.limpa.booster.AdminReceiver"])

    def test_acessibilidade(self):
        self.assertEqual(parse_acessibilidade("null\n"), [])
        self.assertEqual(parse_acessibilidade("a.b/.C:d.e/f.G"), ["a.b/.C", "d.e/f.G"])

    def test_lista_simples_ignora_erros(self):
        self.assertEqual(parse_lista_simples("Error: unknown op\ncom.x.y\n"), {"com.x.y"})

    def test_launchers(self):
        self.assertEqual(parse_launchers(LAUNCHERS), {"com.whatsapp", "com.jogo.legal"})
        self.assertEqual(parse_launchers("packageName=com.a.b\n"), {"com.a.b"})

    def test_dumpsys_pacote(self):
        info = parse_dumpsys_pacote(DUMPSYS_BOOSTER)
        self.assertEqual(info["versao"], "1.0.3")
        self.assertEqual(info["instalado_em"], "2026-09-27 10:00:00")
        self.assertEqual(len(info["permissoes"]), 3)
        self.assertNotIn("android.permission.INTERNET", info["permissoes"])
        self.assertIn("android.permission.READ_SMS", info["concedidas"])
        self.assertNotIn("android.permission.CAMERA", info["concedidas"])

    def test_sha256(self):
        h = "a" * 64
        self.assertEqual(parse_sha256(f"{h}  /data/app/x/base.apk"), h)
        self.assertEqual(parse_sha256("sha256sum: not found"), "")

    def test_dispositivos(self):
        saida = "List of devices attached\nR58M device usb:1 product:a10 model:SM_A105M transport_id:1\nXYZ unauthorized\n"
        dispositivos = parse_dispositivos(saida)
        self.assertEqual(dispositivos[0].modelo, "SM A105M")
        self.assertTrue(dispositivos[0].pronto)
        self.assertFalse(dispositivos[1].pronto)

    def test_selecao_e_nome_seguro(self):
        self.assertEqual(parse_selecao("1, 3-4,9,x,3", 5), [0, 2, 3])
        self.assertEqual(nome_seguro("192.168.0.2:5555"), "192.168.0.2_5555")


class TestHeuristicas(unittest.TestCase):
    def setUp(self):
        self.assinaturas = carregar_assinaturas()

    def test_confiavel_da_loja_fica_limpo(self):
        app = avaliar(App("com.whatsapp", instalador="com.android.vending", sobreposicao=True), self.assinaturas)
        self.assertEqual(app.nivel, "LIMPO")

    def test_confiavel_fora_da_loja_nao_e_ignorado(self):
        app = avaliar(App("com.whatsapp", instalador=None, icone_oculto=True, sobreposicao=True), self.assinaturas)
        self.assertEqual(app.nivel, "ALTO")

    def test_malware_conhecido(self):
        assinaturas = Assinaturas(pacotes_maliciosos={"com.mal.app"})
        app = avaliar(App("com.mal.app", instalador="com.android.vending"), assinaturas)
        self.assertEqual(app.nivel, "ALTO")

    def test_virustotal_confirmado_vence_lista_confiavel(self):
        app = App("com.whatsapp", instalador="com.android.vending",
                  virustotal={"conhecido": True, "malicioso": 12, "rotulo": "trojan.joker"})
        avaliar(app, self.assinaturas)
        self.assertEqual(app.nivel, "ALTO")
        self.assertIn("trojan.joker", app.motivos[0])

    def test_virustotal_poucas_deteccoes_e_desconhecido(self):
        poucos = avaliar(App("com.x.y", instalador="com.android.vending",
                             virustotal={"conhecido": True, "malicioso": 1}), self.assinaturas)
        self.assertEqual(poucos.pontuacao, 30)
        desconhecido = avaliar(App("com.x.y", virustotal={"conhecido": False}), self.assinaturas)
        self.assertIn("APK desconhecido no VirusTotal", desconhecido.motivos)

    def test_espionagem_so_conta_se_concedida(self):
        pedida = avaliar(App("com.x.y", instalador="com.android.vending",
                             permissoes={"android.permission.READ_SMS"}), self.assinaturas)
        concedida = avaliar(App("com.x.y", instalador="com.android.vending",
                                concedidas={"android.permission.READ_SMS"}), self.assinaturas)
        self.assertEqual(pedida.pontuacao, 0)
        self.assertEqual(concedida.pontuacao, 15)

    def test_leitor_de_notificacoes(self):
        app = avaliar(App("com.x.y", instalador="com.android.vending", notificacoes=["com.x.y/.N"]),
                      self.assinaturas)
        self.assertEqual(app.pontuacao, 20)

    def test_app_recente(self):
        app = App("com.x.y", instalador="com.android.vending", instalado_em="2026-09-27 10:00:00")
        avaliar(app, self.assinaturas, agora=datetime(2026, 9, 29))
        self.assertEqual(app.pontuacao, 5)


class TestScannerERemocao(unittest.TestCase):
    def test_escanear(self):
        apps = Scanner(celular_infectado()).escanear()
        por_pacote = {a.pacote: a for a in apps}
        booster = por_pacote["com.limpa.booster"]
        self.assertEqual(apps[0].pacote, "com.limpa.booster")
        self.assertEqual(booster.nivel, "ALTO")
        self.assertTrue(booster.icone_oculto and booster.sobreposicao)
        self.assertEqual(booster.admins, ["com.limpa.booster/com.limpa.booster.AdminReceiver"])
        self.assertEqual(por_pacote["com.whatsapp"].nivel, "LIMPO")
        self.assertEqual(por_pacote["com.jogo.legal"].nivel, "LIMPO")

    def test_escanear_somente(self):
        apps = Scanner(celular_infectado()).escanear(somente={"com.jogo.legal", "com.android.settings"})
        self.assertEqual([a.pacote for a in apps], ["com.jogo.legal"])

    def test_remover_com_quarentena(self):
        adb = celular_infectado()
        booster = next(a for a in Scanner(adb).escanear() if a.pacote == "com.limpa.booster")
        with tempfile.TemporaryDirectory() as pasta:
            removedor = Removedor(adb, Path(pasta))
            resultado = removedor.remover(booster)
            self.assertTrue(resultado.sucesso)
            self.assertEqual(resultado.metodo, "desinstalado")
            destino = Path(resultado.quarentena)
            self.assertTrue((destino / "base.apk").is_file())
            self.assertTrue((destino / "split_config.arm64_v8a.apk").is_file())
            self.assertTrue((destino / "info.json").is_file())
            self.assertEqual(removedor.listar_quarentena(), [destino])
        self.assertIn("settings put secure enabled_accessibility_services com.outro/.Acess", adb.chamadas)
        self.assertIn(
            "dpm remove-active-admin --user 0 com.limpa.booster/com.limpa.booster.AdminReceiver", adb.chamadas
        )
        self.assertIn("appops set com.limpa.booster SYSTEM_ALERT_WINDOW deny", adb.chamadas)

    def test_fallback_desativa_quando_nao_desinstala(self):
        adb = FakeADB({
            "pm uninstall": "Failure [DELETE_FAILED_INTERNAL_ERROR]",
            "pm disable-user": "Package com.a.b new state: disabled-user",
        })
        self.assertEqual(Removedor(adb).desinstalar("com.a.b"), "desativado")

    def test_sem_backup_nao_remove(self):
        adb = FakeADB({})  # `pm path` vazio -> backup falha
        resultado = Removedor(adb, Path(tempfile.gettempdir())).remover(App("com.a.b"))
        self.assertFalse(resultado.sucesso)
        self.assertFalse(any(c.startswith("pm uninstall") for c in adb.chamadas))

    def test_virustotal_consulta_apenas_suspeitos(self):
        import removedor_virus.scanner as scanner_mod

        consultados = []

        def falso_consultar(sha, chave):
            consultados.append(sha)
            return {"conhecido": True, "malicioso": 20, "rotulo": "adware.hiddad"}

        adb = celular_infectado()
        adb.respostas["sha256sum"] = "b" * 64 + "  /data/app/x/base.apk"
        original = scanner_mod.consultar_hash
        scanner_mod.consultar_hash = falso_consultar
        try:
            apps = Scanner(adb).escanear(chave_vt="chave")
        finally:
            scanner_mod.consultar_hash = original
        self.assertEqual(len(consultados), 1)  # só o booster tinha pontos
        self.assertIn("adware.hiddad", " ".join(apps[0].motivos))

    def test_dns(self):
        adb = FakeADB({"settings get global private_dns_mode": "hostname\n"})
        self.assertEqual(dns_antianuncios(adb, ativar=True), "hostname")
        self.assertIn("settings put global private_dns_specifier dns.adguard-dns.com", adb.chamadas)


if __name__ == "__main__":
    unittest.main()
