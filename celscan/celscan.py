#!/usr/bin/env python3
"""CelScan 2.0 — segurança e otimização de celulares via USB."""
import argparse
import getpass
import os
import sys
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Confirm, InvalidResponse, Prompt
from rich.table import Table

import adb
from config import VERSAO

con = Console()


class Confirm(Confirm):  # noqa: F811 — aceita s/n em português
    choices = ["s", "n"]
    validate_error_message = "[prompt.invalid]Responda s ou n"

    def process_response(self, value):
        v = value.strip().lower()
        if v in ("s", "sim", "y", "yes"):
            return True
        if v in ("n", "nao", "não", "no"):
            return False
        raise InvalidResponse(self.validate_error_message)

    def render_default(self, default):
        return f"({'s' if default else 'n'})"
COR = {"ALTO": "bold red", "MÉDIO": "yellow", "BAIXO": "grey62", "OK": "green", "PERMITIDO": "green"}


def barra():
    return Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                    MofNCompleteColumn(), TimeRemainingColumn(), console=con, transient=True)


def escolher_aparelho(serial=None):
    try:
        devs = adb.dispositivos()
    except adb.AdbAusente:
        if not Confirm.ask("[yellow]ADB não encontrado.[/] Baixar o Android Platform Tools oficial agora?", default=True):
            sys.exit(1)
        with con.status("Baixando platform-tools..."):
            adb.instalar_platform_tools()
        devs = adb.dispositivos()
    for s, st in devs:
        if st != "device":
            con.print(f"[yellow]![/] {s}: {st} — desbloqueie o celular e aceite a depuração USB.")
    prontos = [s for s, st in devs if st == "device"]
    if serial:
        if serial not in prontos:
            sys.exit(f"Aparelho {serial} não está pronto.")
        return adb.Aparelho(serial)
    if not prontos:
        con.print(Panel("Ative: Configurações > Sobre o telefone > toque 7x em 'Número da versão'.\n"
                        "Depois: Opções do desenvolvedor > Depuração USB. Conecte o cabo e aceite no celular.\n"
                        "Sem cabo? Use: celscan parear IP:PORTA CÓDIGO (Depuração por Wi-Fi, Android 11+)",
                        title="Nenhum Android conectado", border_style="yellow"))
        sys.exit(1)
    if len(prontos) == 1:
        return adb.Aparelho(prontos[0])
    return adb.Aparelho(Prompt.ask("Vários aparelhos. Qual serial?", choices=prontos))


def mostrar_info(info):
    con.print(Panel(f"[bold]{info['fabricante']} {info['modelo']}[/]  ·  Android {info['android']}  ·  "
                    f"patch {info['patch_seguranca']}  ·  [dim]{info['serial']}[/]", border_style="cyan"))


def tabela_apps(resultados, todos=False):
    t = Table(show_lines=False, header_style="bold")
    t.add_column("Risco", justify="right")
    t.add_column("Nível")
    t.add_column("App")
    t.add_column("Motivos", overflow="fold")
    for r in resultados:
        if not todos and r["nivel"] not in ("ALTO", "MÉDIO"):
            continue
        t.add_row(str(r["score"]), f"[{COR[r['nivel']]}]{r['nivel']}[/]", r["pacote"],
                  "\n".join(r["motivos"][:5]))
    return t


# ---------------------------------------------------------------- android
def cmd_android(a):
    from android import AndroidScanner, nota
    import iocs as iocmod
    import relatorio
    from virustotal import VirusTotal

    ap = escolher_aparelho(a.serial)
    iocs = None
    if not a.sem_iocs:
        with con.status("Carregando indicadores de ameaças (Amnesty/MVT + Echap)..."):
            iocs = iocmod.carregar(avisar=lambda m: con.print(f"[yellow]{m}[/]"))
        if iocs:
            con.print(f"[dim]{len(iocs)} indicadores carregados.[/]")
    chave = os.getenv("VT_API_KEY")
    vt = VirusTotal(chave) if chave else None

    sc = AndroidScanner(ap, vt, iocs, sistema=a.sistema)
    with con.status("Coletando dados do aparelho (uma única leitura)..."):
        sc.coletar()
    info = sc.info()
    mostrar_info(info)
    for av in sc.avisos:
        con.print(f"[yellow]Aviso:[/] {av}")

    with barra() as p:
        t = p.add_task("Calculando hashes dos apps", total=len(sc.apps))
        for pkg in sc.calcular_hashes():
            p.update(t, advance=1, description=f"Hash: {pkg[:40]}")

    cands = sc.candidatos()
    with barra() as p:
        t = p.add_task("Verificando assinaturas", total=len(cands))
        for pkg in cands:
            sc.ler_certificado(pkg)
            p.advance(t)

    if vt:
        alvo = sc.candidatos(todos=a.vt_todos)
        sem_cache = sum(1 for x in alvo if sc.apps[x]["sha256"] and vt.em_cache(sc.apps[x]["sha256"]) is None)
        if sem_cache:
            con.print(f"[dim]VirusTotal: {sem_cache} consulta(s) novas (~{sem_cache * 16 // 60 + 1} min no plano grátis).[/]")
        with barra() as p:
            t = p.add_task("Consultando VirusTotal", total=len(alvo))
            for pkg in alvo:
                sc.consultar_vt(pkg)
                p.advance(t)
    else:
        con.print("[dim]Sem VT_API_KEY: VirusTotal desativado.[/]")

    achados, res = sc.pontuar()
    n, rot = nota(achados, res)

    if achados:
        con.print("\n[bold]Configurações do aparelho[/]")
        for nv, txt in achados:
            con.print(f"  [{COR[nv]}]{nv:<6}[/] {txt}")
    con.print()
    risco = [r for r in res if r["nivel"] in ("ALTO", "MÉDIO")]
    if risco or a.todos:
        con.print(tabela_apps(res, a.todos))
    cor = "green" if n >= 70 else "yellow" if n >= 50 else "red"
    con.print(Panel(f"[bold {cor}]{n}/100 — {rot}[/]\n{len(res)} apps analisados · {len(risco)} com risco médio/alto",
                    title="Resultado", border_style=cor))

    acoes = []
    alvos = [r for r in res if r["score"] >= a.limite and r["nivel"] != "PERMITIDO"]
    if alvos and (a.remover or Confirm.ask(f"Revisar a remoção de {len(alvos)} app(s) de risco agora?", default=False)):
        for r in alvos:
            con.print(Panel("\n".join(f"• {m}" for m in r["motivos"]), title=f"{r['pacote']} (risco {r['score']})",
                            border_style="red" if r["score"] >= 60 else "yellow"))
            if Confirm.ask("Remover? (fica cópia na quarentena)", default=r["score"] >= 60):
                with con.status("Removendo..."):
                    ok, msg = sc.remover(r)
                con.print(f"  {'[green]✔' if ok else '[red]✘'}[/] {msg}")
                if ok:
                    acoes.append(f"{r['pacote']}: {msg}")

    arq = relatorio.gerar(a.saida, info, n, rot, achados, res, loja=a.loja, acoes=acoes)
    con.print(f"Laudo salvo em [bold]{arq}[/] (+ .json)")
    if not a.nao_abrir:
        webbrowser.open(arq.resolve().as_uri())
    con.print("[dim]Terminou? Desative a Depuração USB no celular (Opções do desenvolvedor).[/]")


# ---------------------------------------------------------------- otimizar
def cmd_otimizar(a):
    import otimizar as ot

    ap = escolher_aparelho(a.serial)
    with con.status("Lendo bateria, armazenamento e memória..."):
        d = ot.diagnostico(ap)
    b, arm, ram = d["bateria"], d["armazenamento"], d["ram"]
    t = Table.grid(padding=(0, 2))
    t.add_row("Bateria", f"{b['nivel']}% · saúde {b['saude']} · {b['temperatura'] or '?'}"
              + (f" · {b['ciclos']} ciclos" if b.get("ciclos") else ""))
    if arm:
        pct = arm["livre_gb"] / arm["total_gb"] * 100
        t.add_row("Armazenamento", f"[{'red' if pct < 10 else 'green'}]{arm['livre_gb']:.1f} GB livres[/] de {arm['total_gb']:.0f} GB")
    if ram:
        t.add_row("RAM", f"{ram['disponivel_gb']:.1f} GB disponíveis de {ram['total_gb']:.1f} GB")
    if d["ligado_dias"] is not None:
        t.add_row("Ligado há", f"{d['ligado_dias']:.1f} dias" + (" [yellow](reiniciar ajuda)[/]" if d["ligado_dias"] > 7 else ""))
    for p in d["pastas"][:5]:
        t.add_row(f"  {p['pasta']}", f"{p['gb']:.1f} GB")
    con.print(Panel(t, title="Diagnóstico", border_style="cyan"))

    tudo = a.tudo
    feitos = []
    if tudo or a.cache or Confirm.ask("Limpar o cache de todos os apps?", default=True):
        with con.status("Limpando cache..."):
            mb = ot.limpar_cache(ap)
        feitos.append(f"Cache limpo: {mb:.0f} MB liberados" if mb is not None else "Cache limpo")
        con.print(f"[green]✔[/] {feitos[-1]}")
    if tudo or a.compilar or Confirm.ask("Otimizar apps (compilação — pode levar vários minutos)?", default=False):
        with con.status("Compilando apps... não desconecte"):
            ot.compilar(ap)
        feitos.append("Apps recompilados")
        con.print("[green]✔[/] Apps recompilados")
    if a.animacoes is not None or tudo or Confirm.ask("Deixar animações mais rápidas (0.5x)?", default=False):
        v = a.animacoes if a.animacoes is not None else 0.5
        ot.animacoes(ap, v)
        feitos.append(f"Animações em {v}x")
        con.print(f"[green]✔[/] Animações em {v}x")
    if a.debloat or Confirm.ask("Procurar apps pré-instalados desnecessários (bloatware)?", default=False):
        with con.status("Consultando lista da comunidade (UAD)..."):
            sug = ot.sugestoes_debloat(ap)
        if not sug:
            con.print("Nada recomendado para remover.")
        else:
            tb = Table(header_style="bold")
            tb.add_column("#", justify="right")
            tb.add_column("Pacote")
            tb.add_column("O que é", overflow="fold")
            for i, s in enumerate(sug, 1):
                tb.add_row(str(i), s["pacote"], s["descricao"])
            con.print(tb)
            esc = Prompt.ask("Desativar quais? (ex: 1,3,5 · 'todos' · Enter = nenhum)", default="")
            if esc.strip():
                idx = range(len(sug)) if esc.strip().lower() == "todos" else \
                    [int(x) - 1 for x in esc.replace(" ", "").split(",") if x.isdigit() and 0 < int(x) <= len(sug)]
                ok = sum(ot.desativar(ap, sug[i]["pacote"]) for i in idx)
                feitos.append(f"{ok} app(s) pré-instalados desativados")
                con.print(f"[green]✔[/] {feitos[-1]} (desfaça com: celscan quarentena restaurar ID)")
    if feitos:
        con.print(Panel("\n".join(f"• {f}" for f in feitos), title="Feito", border_style="green"))


# ---------------------------------------------------------------- quarentena
def cmd_quarentena(a):
    import quarentena
    if a.acao == "listar":
        itens = quarentena.listar()
        if not itens:
            return con.print("Quarentena vazia.")
        t = Table(header_style="bold")
        for c in ("ID", "Pacote", "Ação", "Data", "Restaurado"):
            t.add_column(c, overflow="fold")
        for m in itens:
            t.add_row(m["id"], m["pacote"], str(m["acao"]), m["data"], m.get("restaurado", ""))
        con.print(t)
    else:
        if not a.id:
            sys.exit("Informe o ID (veja: celscan quarentena listar)")
        ap = escolher_aparelho(a.serial)
        ok, out = quarentena.restaurar(ap, a.id)
        con.print(("[green]✔ Restaurado[/]" if ok else "[red]✘ Falhou[/]") + f"  {out[-300:]}")


# ---------------------------------------------------------------- ios
def cmd_ios(a):
    import ios
    if a.listar_backups:
        bs = ios.pastas_backup()
        if not bs:
            return con.print("Nenhum backup do iTunes/Finder encontrado.")
        t = Table(header_style="bold")
        for c in ("Aparelho", "iOS", "Data", "Pasta"):
            t.add_column(c, overflow="fold")
        for b in bs:
            t.add_row(b["aparelho"], b["ios"], b["data"], b["pasta"])
        return con.print(t)
    try:
        saida = Path(a.saida)
        if a.backup:
            backup = Path(a.backup)
        else:
            udids = ios.aparelhos()
            if not udids:
                sys.exit("Nenhum iPhone conectado. Desbloqueie e toque em 'Confiar'.")
            udid = a.udid or (udids[0] if len(udids) == 1 else Prompt.ask("Qual UDID?", choices=udids))
            bat = ios.bateria(udid)
            if bat:
                con.print(f"Bateria: saúde ~{bat['saude_pct']}% · {bat['ciclos']} ciclos")
            with con.status("Fazendo backup do iPhone..."):
                backup = ios.fazer_backup(udid, saida / "backup", log=con.print)
        senha = a.senha or os.getenv("CELSCAN_IOS_SENHA")
        if ios.criptografado(backup) and not senha:
            senha = getpass.getpass("Senha do backup criptografado: ")
        with con.status("Analisando com o MVT..."):
            det = ios.analisar(backup, saida, senha, log=con.print)
    except ios.IOSErro as e:
        con.print(Panel(str(e), title="Erro", border_style="red"))
        sys.exit(1)
    if det:
        con.print(Panel("\n".join(f"{k}: {v}" for k, v in det.items()) +
                        "\n\nSalve fotos/arquivos, atualize o iOS, restaure de fábrica SEM restaurar o backup "
                        "e ative o Modo de Isolamento.", title="POSSÍVEL SPYWARE", border_style="red"))
    else:
        con.print(Panel("Nenhum indicador conhecido encontrado (não garante 100%).", border_style="green"))
    con.print(f"[dim]Detalhes em {saida / 'mvt'}[/]")


# ---------------------------------------------------------------- utilidades
def cmd_parear(a):
    if a.codigo:
        con.print(adb.parear(a.endereco, a.codigo))
        con.print("[dim]Agora use o IP:PORTA mostrado em 'Depuração por Wi-Fi' (não o de pareamento):[/]")
        con.print("  celscan conectar IP:PORTA")
    else:
        con.print(adb.conectar(a.endereco))


def cmd_iocs(a):
    import iocs as iocmod
    with con.status("Baixando indicadores..."):
        i = iocmod.carregar(forcar=True, avisar=con.print)
    con.print(f"{len(i) if i else 0} indicadores ({len(i.pacotes)} pacotes, {len(i.certs)} certificados, "
              f"{len(i.hashes)} hashes)." if i else "Falhou.")


def main():
    p = argparse.ArgumentParser(prog="celscan", description=f"CelScan {VERSAO} — segurança e otimização via USB")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("android", help="Varredura de segurança do Android")
    s.add_argument("--serial")
    s.add_argument("--sistema", action="store_true", help="Inclui apps do sistema (pré-instalados)")
    s.add_argument("--vt-todos", action="store_true", help="Consulta todos os apps no VirusTotal")
    s.add_argument("--remover", action="store_true", help="Vai direto para a remoção")
    s.add_argument("--limite", type=int, default=60, help="Risco mínimo para sugerir remoção (padrão 60)")
    s.add_argument("--todos", action="store_true", help="Mostra todos os apps na tabela")
    s.add_argument("--sem-iocs", action="store_true", help="Não usa indicadores públicos")
    s.add_argument("--loja", help="Nome da loja/assistência no laudo")
    s.add_argument("--saida", default="laudos")
    s.add_argument("--nao-abrir", action="store_true", help="Não abre o laudo no navegador")
    s.set_defaults(func=cmd_android)

    s = sub.add_parser("otimizar", help="Diagnóstico e otimização do Android")
    s.add_argument("--serial")
    s.add_argument("--tudo", action="store_true", help="Cache + compilação + animações sem perguntar")
    s.add_argument("--cache", action="store_true")
    s.add_argument("--compilar", action="store_true")
    s.add_argument("--animacoes", type=float, help="Escala das animações (ex: 0.5; 1 = padrão)")
    s.add_argument("--debloat", action="store_true")
    s.set_defaults(func=cmd_otimizar)

    s = sub.add_parser("quarentena", help="Lista ou desfaz remoções")
    s.add_argument("acao", choices=["listar", "restaurar"])
    s.add_argument("id", nargs="?")
    s.add_argument("--serial")
    s.set_defaults(func=cmd_quarentena)

    s = sub.add_parser("ios", help="Varredura de iPhone (backup + MVT)")
    s.add_argument("--udid")
    s.add_argument("--senha", help="Senha do backup (prefira digitar quando pedir)")
    s.add_argument("--backup", help="Usar backup existente (pasta)")
    s.add_argument("--listar-backups", action="store_true")
    s.add_argument("--saida", default="saida_ios")
    s.set_defaults(func=cmd_ios)

    s = sub.add_parser("parear", help="Pareia via Wi-Fi (Android 11+)")
    s.add_argument("endereco", help="IP:PORTA de pareamento")
    s.add_argument("codigo", nargs="?", help="Código de 6 dígitos")
    s.set_defaults(func=cmd_parear)
    s = sub.add_parser("conectar", help="Conecta via Wi-Fi já pareado")
    s.add_argument("endereco")
    s.set_defaults(func=cmd_parear, codigo=None)

    s = sub.add_parser("iocs", help="Atualiza os indicadores de ameaças")
    s.set_defaults(func=cmd_iocs)

    a = p.parse_args()
    try:
        a.func(a)
    except adb.AdbErro as e:
        con.print(Panel(str(e), title="Erro de conexão", border_style="red"))
        sys.exit(1)
    except KeyboardInterrupt:
        con.print("\n[yellow]Interrompido.[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()
