"""Interface de linha de comando e menu interativo."""

from __future__ import annotations

import argparse
import re

from . import __version__
from .acoes import Removedor, dns_antianuncios
from .adb import ADB, ErroADB, baixar_adb, localizar_adb
from .heuristicas import App, Assinaturas, carregar_assinaturas
from .relatorio import cor, imprimir_apps, resumo, salvar_relatorio
from .scanner import Scanner

INSTRUCOES_CONEXAO = """Nenhum celular pronto foi encontrado. No celular:
  1. Configurações > Sobre o telefone > toque 7 vezes em "Número da versão"
     (Xiaomi: "Versão MIUI/HyperOS") para liberar as Opções do desenvolvedor.
  2. Configurações > Sistema > Opções do desenvolvedor > ative "Depuração USB".
  3. Conecte um cabo USB de DADOS e escolha "Transferência de arquivos".
  4. Aceite o aviso "Permitir depuração USB?" na tela do celular."""

INSTRUCAO_AUTORIZAR = (
    "O celular está conectado, mas não autorizou este computador.\n"
    "Desbloqueie a tela e toque em PERMITIR no aviso de depuração USB."
)

BANNER = f"""
==============================================
  REMOVEDOR DE VÍRUS ANDROID (USB)  v{__version__}
=============================================="""


def confirmar(pergunta: str) -> bool:
    return input(f"{pergunta} [s/N]: ").strip().lower() in ("s", "sim", "y")


def parse_selecao(texto: str, total: int) -> list[int]:
    """'1,3-5' -> [0, 2, 3, 4] (índices válidos, sem repetição)."""
    indices: list[int] = []
    for parte in re.split(r"[,\s]+", texto.strip()):
        if not parte:
            continue
        inicio, _, fim = parte.partition("-")
        if not inicio.isdigit() or (fim and not fim.isdigit()):
            continue
        for n in range(int(inicio), int(fim or inicio) + 1):
            if 1 <= n <= total and n - 1 not in indices:
                indices.append(n - 1)
    return indices


# --- conexão ---

def obter_adb(interativo: bool) -> ADB:
    if not localizar_adb():
        print(cor("ADB não encontrado neste computador.", "93"))
        if not (interativo and confirmar("Baixar agora o ADB oficial do Google (~10 MB)?")):
            raise ErroADB("Instale o ADB com o comando: python -m removedor_virus baixar-adb")
        print("Baixando platform-tools...")
        print("ADB instalado em", baixar_adb())
    return ADB()


def conectar(serial: str | None, interativo: bool) -> tuple[ADB, dict]:
    adb = obter_adb(interativo)
    dispositivos = adb.dispositivos()
    if serial:
        dispositivos = [d for d in dispositivos if d.serial == serial]
    prontos = [d for d in dispositivos if d.pronto]
    if not prontos:
        if any(d.estado == "unauthorized" for d in dispositivos):
            raise ErroADB(INSTRUCAO_AUTORIZAR)
        raise ErroADB(INSTRUCOES_CONEXAO)
    escolhido = prontos[0]
    if len(prontos) > 1:
        if not interativo:
            raise ErroADB("Mais de um celular conectado. Use -s SERIAL.")
        for n, d in enumerate(prontos, 1):
            print(f"  {n}. {d.modelo or 'Android'} ({d.serial})")
        indices = parse_selecao(input("Escolha o celular: "), len(prontos))
        escolhido = prontos[indices[0]] if indices else prontos[0]
    adb.serial = escolhido.serial
    info = adb.info_dispositivo()
    print(cor(f"Conectado: {info['fabricante']} {info['modelo']} - Android {info['android']} ({adb.serial})", "92"))
    return adb, info


def conectar_interativo(serial: str | None) -> tuple[ADB, dict]:
    while True:
        try:
            return conectar(serial, interativo=True)
        except ErroADB as erro:
            print(cor(str(erro), "93"))
            if input("\nEnter para tentar de novo, 0 para sair: ").strip() == "0":
                raise SystemExit(0)


# --- operações ---

def _progresso(atual: int, total: int, pacote: str) -> None:
    print(f"\rAnalisando {atual}/{total}: {pacote[:45]:<45}", end="", flush=True)


def escanear(adb: ADB, info: dict, assinaturas: Assinaturas, mostrar_limpos: bool = False) -> tuple[list[App], list[App]]:
    print("Coletando informações do celular...")
    apps = Scanner(adb, assinaturas).escanear(progresso=_progresso)
    print("\r" + " " * 70 + "\r", end="")
    visiveis = imprimir_apps(apps, mostrar_limpos)
    print("\n" + resumo(apps))
    print("Relatório salvo em", salvar_relatorio(apps, info))
    return apps, visiveis


def remover_apps(adb: ADB, apps: list[App], backup: bool = True) -> int:
    removedor = Removedor(adb)
    falhas = 0
    for app in apps:
        print(f"\nRemovendo {cor(app.pacote, '1')}...")
        resultado = removedor.remover(app, backup=backup)
        for etapa in resultado.etapas:
            print("  -", etapa)
        if resultado.sucesso:
            print(cor("  OK", "92"))
        else:
            falhas += 1
            print(cor("  FALHOU", "91"))
    return falhas


def alvos_por_nivel(apps: list[App], nivel: str) -> list[App]:
    niveis = {"alto": ("ALTO",), "medio": ("ALTO", "MEDIO")}[nivel]
    return [a for a in apps if a.nivel in niveis]


def restaurar_interativo(adb: ADB) -> None:
    removedor = Removedor(adb)
    pastas = removedor.listar_quarentena()
    if not pastas:
        print("A quarentena está vazia.")
        return
    for n, pasta in enumerate(pastas, 1):
        print(f"  {n}. {pasta.parent.name} / {pasta.name}")
    for i in parse_selecao(input("Números para restaurar (Enter = nenhum): "), len(pastas)):
        ok, mensagem = removedor.restaurar(pastas[i])
        print(cor("  OK" if ok else "  FALHOU", "92" if ok else "91"), mensagem)


def menu(args: argparse.Namespace, assinaturas: Assinaturas) -> int:
    print(BANNER)
    adb, info = conectar_interativo(args.serial)
    opcoes = """
  1. Escanear celular e escolher o que remover
  2. Limpeza rápida (remove todos os apps de risco ALTO)
  3. Remover um app pelo nome do pacote
  4. Restaurar app da quarentena
  5. Ativar DNS bloqueador de anúncios
  6. Desativar DNS bloqueador de anúncios
  7. Reconectar / trocar de celular
  0. Sair"""
    while True:
        print(opcoes)
        opcao = input("Opção: ").strip()
        try:
            if opcao == "0":
                return 0
            if opcao == "1":
                _, visiveis = escanear(adb, info, assinaturas)
                if visiveis:
                    texto = input("\nNúmeros para remover (ex: 1,3-5 | a = todos ALTO | Enter = nenhum): ")
                    alvos = (
                        alvos_por_nivel(visiveis, "alto") if texto.strip().lower() == "a"
                        else [visiveis[i] for i in parse_selecao(texto, len(visiveis))]
                    )
                    if alvos and confirmar(f"Remover {len(alvos)} app(s)? (backup vai para a quarentena)"):
                        remover_apps(adb, alvos)
            elif opcao == "2":
                apps, _ = escanear(adb, info, assinaturas)
                alvos = alvos_por_nivel(apps, "alto")
                if not alvos:
                    print(cor("Nenhum app de risco ALTO. Celular limpo!", "92"))
                elif confirmar(f"Remover {len(alvos)} app(s) de risco ALTO?"):
                    remover_apps(adb, alvos)
            elif opcao == "3":
                pacotes = input("Pacote(s) separados por espaço: ").split()
                comando_remover(adb, assinaturas, pacotes, backup=True, sim=False)
            elif opcao == "4":
                restaurar_interativo(adb)
            elif opcao in ("5", "6"):
                print("Modo DNS:", dns_antianuncios(adb, ativar=opcao == "5"))
            elif opcao == "7":
                adb, info = conectar_interativo(None)
        except ErroADB as erro:
            print(cor(f"Erro: {erro}", "91"))


def comando_remover(adb: ADB, assinaturas: Assinaturas, pacotes: list[str], backup: bool, sim: bool) -> int:
    apps = Scanner(adb, assinaturas).escanear(somente=set(pacotes))
    faltando = set(pacotes) - {a.pacote for a in apps}
    for pacote in sorted(faltando):
        print(cor(f"{pacote}: não encontrado entre os apps instalados pelo usuário.", "93"))
    if not apps:
        return 1
    imprimir_apps(apps, mostrar_limpos=True)
    if not sim and not confirmar(f"Remover {len(apps)} app(s)?"):
        return 0
    return 1 if remover_apps(adb, apps, backup=backup) else 0


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="removedor_virus",
        description="Detecta e remove vírus e adware de celulares Android via USB. "
        "Sem comando, abre o menu interativo.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-s", "--serial", help="serial do celular (quando houver mais de um)")
    parser.add_argument("--assinaturas", help="arquivo JSON de assinaturas alternativo")
    sub = parser.add_subparsers(dest="comando")

    sub.add_parser("dispositivos", help="lista celulares conectados")
    p = sub.add_parser("escanear", help="analisa os apps e gera relatório")
    p.add_argument("--todos", action="store_true", help="mostra também os apps limpos")
    p = sub.add_parser("limpar", help="remove apps suspeitos automaticamente")
    p.add_argument("--nivel", choices=["alto", "medio"], default="alto", help="nível mínimo (padrão: alto)")
    p.add_argument("--sim", action="store_true", help="não pede confirmação")
    p.add_argument("--sem-backup", action="store_true", help="não copia o APK para a quarentena")
    p = sub.add_parser("remover", help="remove apps específicos")
    p.add_argument("pacotes", nargs="+")
    p.add_argument("--sim", action="store_true")
    p.add_argument("--sem-backup", action="store_true")
    sub.add_parser("restaurar", help="reinstala apps da quarentena")
    p = sub.add_parser("dns", help="DNS privado que bloqueia anúncios (Android 9+)")
    p.add_argument("acao", choices=["ativar", "desativar"])
    sub.add_parser("baixar-adb", help="baixa o ADB oficial do Google")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)
    try:
        assinaturas = carregar_assinaturas(args.assinaturas)
        if args.comando is None:
            return menu(args, assinaturas)
        if args.comando == "baixar-adb":
            print("ADB instalado em", baixar_adb())
            return 0
        if args.comando == "dispositivos":
            dispositivos = obter_adb(False).dispositivos()
            for d in dispositivos:
                print(f"{d.serial}\t{d.estado}\t{d.modelo}")
            if not dispositivos:
                print(INSTRUCOES_CONEXAO)
            return 0

        adb, info = conectar(args.serial, interativo=False)
        if args.comando == "escanear":
            escanear(adb, info, assinaturas, mostrar_limpos=args.todos)
        elif args.comando == "limpar":
            apps, _ = escanear(adb, info, assinaturas)
            alvos = alvos_por_nivel(apps, args.nivel)
            if not alvos:
                print(cor("Nada para remover.", "92"))
            elif args.sim or confirmar(f"Remover {len(alvos)} app(s)?"):
                return 1 if remover_apps(adb, alvos, backup=not args.sem_backup) else 0
        elif args.comando == "remover":
            return comando_remover(adb, assinaturas, args.pacotes, not args.sem_backup, args.sim)
        elif args.comando == "restaurar":
            restaurar_interativo(adb)
        elif args.comando == "dns":
            print("Modo DNS:", dns_antianuncios(adb, ativar=args.acao == "ativar"))
        return 0
    except ErroADB as erro:
        print(cor(f"Erro: {erro}", "91"))
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        return 130
