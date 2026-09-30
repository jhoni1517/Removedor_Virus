"""CelScan — linha de comando (segurança e otimização de celulares via USB)."""
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

from celscan import config, servicos
from celscan.config import VERSAO
from celscan.core import adb, bases, db, log, preferencias

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

    def __call__(self, *args, **kwargs):
        try:
            return super().__call__(*args, **kwargs)
        except EOFError:  # sem teclado (script, teste, janela): usa a resposta padrão
            con.print(f"[dim](sem resposta: usando '{'s' if kwargs.get('default') else 'n'}')[/]")
            return kwargs.get("default", False)


def perguntar(texto, default=""):
    try:
        return Prompt.ask(texto, default=default)
    except EOFError:
        return default
COR = {"ALTO": "bold red", "MÉDIO": "yellow", "BAIXO": "grey62", "OK": "green", "PERMITIDO": "green"}


def barra():
    return Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                    MofNCompleteColumn(), TimeRemainingColumn(), console=con, transient=True)


def escolher_aparelho(serial=None):
    try:
        devs = adb.dispositivos()
    except adb.AdbAusente:
        if not Confirm.ask("[yellow]ADB não encontrado.[/] Baixar o Android Platform Tools oficial agora?",
                           default=True):
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
    from celscan import relatorio, servicos
    from celscan.core import preferencias

    ap = escolher_aparelho(a.serial)
    modo = a.modo or ("completo" if preferencias.chave_virustotal() else "rapido")
    opcoes = servicos.OpcoesVarredura(modo=modo, sistema=a.sistema, usar_iocs=not a.sem_iocs, vt_todos=a.vt_todos)
    con.print(f"[dim]Modo: {servicos.MODOS[modo]}[/]")

    with barra() as p:
        tarefas = {}

        def progresso(ev):
            nome = ev["etapa"]
            if nome not in tarefas:
                for t in tarefas.values():  # etapa anterior terminou
                    p.update(t, completed=p.tasks[t].total or 1)
                tarefas[nome] = p.add_task(ev["descricao"], total=ev["total"] or 1)
            if ev["atual"] is not None:
                p.update(tarefas[nome], completed=ev["atual"], total=ev["total"],
                         description=f"{ev['descricao']}: {ev['detalhe'][:30]}")

        res = servicos.executar_varredura(ap, opcoes, progresso)

    mostrar_info(res.info)
    for av in res.avisos:
        con.print(f"[yellow]Aviso:[/] {av}")
    if res.achados:
        con.print("\n[bold]Configurações do aparelho[/]")
        for ach in res.achados:
            nv = ach["nivel"]
            con.print(f"  [{COR[nv]}]{nv:<6}[/] [bold]{ach['titulo']}[/]")
            con.print(f"         [dim]{ach['significa']}[/]\n         → {ach['fazer']}")
    con.print()
    risco = [r for r in res.resultados if r["nivel"] in ("ALTO", "MÉDIO")]
    if risco or a.todos:
        con.print(tabela_apps(res.resultados, a.todos))
    n, rot = res.nota, res.veredito
    cor = "green" if n >= 70 else "yellow" if n >= 50 else "red"
    con.print(Panel(f"[bold {cor}]{n}/100 — {rot}[/]\n{len(res.resultados)} apps analisados · {len(risco)} com "
                    f"risco médio/alto · {res.duracao_s:.0f} s", title="Resultado", border_style=cor))

    acoes = []
    alvos = [r for r in res.resultados if r["score"] >= a.limite and r["nivel"] != "PERMITIDO"]
    if alvos and (a.remover or Confirm.ask(f"Revisar a remoção de {len(alvos)} app(s) de risco agora?", default=False)):
        for r in alvos:
            texto = "\n".join(f"• [bold]{x['titulo']}[/]\n  [dim]{x['significa']}[/]\n  → {x['fazer']}"
                              for x in r["achados"])
            con.print(Panel(texto, title=f"{r['pacote']} (risco {r['score']})",
                            border_style="red" if r["score"] >= 60 else "yellow"))
            if Confirm.ask("Remover? (fica cópia na quarentena)", default=r["score"] >= 60):
                with con.status("Removendo..."):
                    feito = servicos.remover_apps(ap, [r])[0]
                con.print(f"  {'[green]✔' if feito['ok'] else '[red]✘'}[/] {feito['mensagem']}")
                if feito["ok"]:
                    acoes.append(f"{r['pacote']}: {feito['mensagem']}")

    arq = relatorio.gerar(a.saida, res.info, n, rot, res.achados, res.resultados, loja=a.loja, acoes=acoes,
                          avisos=res.avisos)
    from celscan.relatorio import pdf

    con_db = db.conectar()
    vid = res.varredura_id
    conteudo, h = pdf.gerar_pdf(db.meta_varredura(con_db, vid), db.retrato(con_db, vid), "cliente", a.loja,
                                db.acoes_da_varredura(con_db, vid))
    db.registrar_laudo(con_db, vid, h)
    arq.with_suffix(".pdf").write_bytes(conteudo)
    con.print(f"Laudo salvo em [bold]{arq}[/] (+ .pdf e .json) · varredura nº {vid} · verificação "
              f"{pdf.codigo_curto(h)}")
    if not a.nao_abrir:
        webbrowser.open(arq.resolve().as_uri())
    con.print("[dim]Terminou? Desative a Depuração USB no celular (Opções do desenvolvedor).[/]")


# ---------------------------------------------------------------- otimizar
def cmd_otimizar(a):
    from celscan.acoes import otimizacao as ot

    ap = escolher_aparelho(a.serial)
    with con.status("Lendo bateria, armazenamento e memória..."):
        d = ot.diagnostico(ap)
    b, arm, ram = d["bateria"], d["armazenamento"], d["ram"]
    ident = d.get("identificacao", {})
    t = Table.grid(padding=(0, 2))
    if ident:
        nome = ident.get("marketname") or ident.get("model") or "?"
        t.add_row("Aparelho", f"{ident.get('manufacturer', '')} {nome}".strip())
        if ident.get("imei"):
            t.add_row("IMEI", ident["imei"])
        if ident.get("release"):
            t.add_row("Android", f"{ident['release']} · patch {ident.get('security_patch', '?')}")
    if b:
        linha = f"{b['nivel']}% · saúde {b['saude']} · {b['temperatura'] or '?'}"
        if b.get("situacao"):
            linha += f" · {b['situacao']}"
        if b.get("saude_pct"):
            cap = f"{b.get('capacidade_mah', '?')}/{b.get('capacidade_projeto_mah', '?')} mAh"
            linha += f" · capacidade real ~{b['saude_pct']}% ({cap})"
        if b.get("ciclos"):
            linha += f" · {b['ciclos']} ciclos"
        t.add_row("Bateria", linha)
    if arm:
        pct = arm["livre_gb"] / arm["total_gb"] * 100
        cor_livre = "red" if pct < 10 else "green"
        t.add_row("Armazenamento", f"[{cor_livre}]{arm['livre_gb']:.1f} GB livres[/] de {arm['total_gb']:.0f} GB")
    if ram:
        t.add_row("RAM", f"{ram['disponivel_gb']:.1f} GB disponíveis de {ram['total_gb']:.1f} GB")
    if d["ligado_dias"] is not None:
        dica = " [yellow](reiniciar ajuda)[/]" if d["ligado_dias"] > 7 else ""
        t.add_row("Ligado há", f"{d['ligado_dias']:.1f} dias{dica}")
    for p in d["pastas"][:5]:
        t.add_row(f"  {p['pasta']}", f"{p['gb']:.1f} GB")
    con.print(Panel(t, title="Diagnóstico", border_style="cyan"))
    for av in d.get("avisos", []):
        con.print(f"[yellow]Aviso:[/] {av}")

    tudo = a.tudo
    feitos = []
    if tudo or a.cache or Confirm.ask("Limpar o cache de todos os apps?", default=True):
        with con.status("Limpando cache..."):
            mb = ot.limpar_cache(ap)
        feitos.append(f"Cache limpo: {mb:.0f} MB liberados" if mb is not None else "Cache limpo")
        con.print(f"[green]✔[/] {feitos[-1]}")
    lixo = ot.medir_lixo(ap)
    if lixo and (tudo or a.lixo or Confirm.ask(
            f"Apagar lixo seguro ({sum(i['kb'] for i in lixo) / 1024:.0f} MB: miniaturas, temporários, cache)?",
            default=True)):
        with con.status("Apagando lixo seguro..."):
            mb = ot.limpar_lixo(ap, [i["chave"] for i in lixo])
        feitos.append(f"Lixo apagado: {mb:.0f} MB liberados" if mb is not None else "Lixo apagado")
        con.print(f"[green]✔[/] {feitos[-1]}")
    if tudo or a.compilar or Confirm.ask("Otimizar apps (compilação — pode levar vários minutos)?", default=False):
        with con.status("Compilando apps... não desconecte"):
            ot.compilar(ap)
        feitos.append("Apps recompilados")
        con.print("[green]✔[/] Apps recompilados")
    if a.animacoes is not None or tudo or Confirm.ask("Deixar animações mais rápidas (0.5x)?", default=False):
        v = a.animacoes if a.animacoes is not None else 0.5
        ident = ot.animacoes(ap, v)
        feitos.append(f"Animações em {v}x (desfaça com: celscan quarentena restaurar {ident})")
        con.print(f"[green]✔[/] {feitos[-1]}")
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
            esc = perguntar("Desativar quais? (ex: 1,3,5 · 'todos' · Enter = nenhum)", default="")
            if esc.strip():
                idx = range(len(sug)) if esc.strip().lower() == "todos" else \
                    [int(x) - 1 for x in esc.replace(" ", "").split(",") if x.isdigit() and 0 < int(x) <= len(sug)]
                ok = sum(ot.desativar(ap, sug[i]["pacote"]) for i in idx)
                feitos.append(f"{ok} app(s) pré-instalados desativados")
                con.print(f"[green]✔[/] {feitos[-1]} (desfaça com: celscan quarentena restaurar ID)")
    if feitos:
        con_db = db.conectar()
        for f in feitos:
            db.registrar_acao(con_db, ap.serial, "otimizacao", None, f)
        con.print(Panel("\n".join(f"• {f}" for f in feitos), title="Feito", border_style="green"))


# ---------------------------------------------------------------- quarentena
def cmd_quarentena(a):
    from celscan.acoes import quarentena
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
        if ok:
            db.marcar_desfeita(db.conectar(), a.id)
        con.print(("[green]✔ Restaurado[/]" if ok else "[red]✘ Falhou[/]") + f"  {out[-300:]}")


# ---------------------------------------------------------------- ios
def cmd_ios(a):
    from celscan.ios import mvt as ios
    if getattr(a, "info", False):
        if not ios.ferramentas_ok():
            sys.exit("Instale o libimobiledevice (idevice_id, ideviceinfo). No Windows vem com o iTunes/Apple Devices.")
        udids = ios.aparelhos()
        if not udids:
            sys.exit("Nenhum iPhone conectado. Desbloqueie e toque em 'Confiar'.")
        for u in udids:
            try:
                d = ios.info(u)
            except ios.IOSErro as e:
                con.print(Panel(str(e), title=u, border_style="red"))
                continue
            t = Table.grid(padding=(0, 2))
            for chave in ("nome", "modelo", "ios", "serial", "imei", "telefone"):
                if d.get(chave):
                    t.add_row(chave.capitalize(), str(d[chave]))
            if d.get("bateria", {}).get("saude_pct"):
                b = d["bateria"]
                t.add_row("Bateria", f"saúde ~{b['saude_pct']}% · {b.get('ciclos', '?')} ciclos")
            con.print(Panel(t, title=f"iPhone {u}", border_style="cyan"))
        return
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


def cmd_historico(a):
    con_db = db.conectar()
    linhas = db.varreduras(con_db, a.serial, a.limite)
    if not linhas:
        return con.print("Nenhuma varredura registrada ainda.")
    t = Table(header_style="bold")
    for c in ("#", "Data", "Aparelho", "Nota", "Apps", "Com risco", "Duração"):
        t.add_column(c)
    for v in linhas:
        cor = "green" if v["nota"] >= 70 else "yellow" if v["nota"] >= 50 else "red"
        t.add_row(str(v["id"]), v["data"].replace("T", " "), f"{v['fabricante']} {v['modelo']} ({v['serial']})",
                  f"[{cor}]{v['nota']} {v['veredito']}[/]", str(v["apps_total"]), str(v["apps_risco"]),
                  f"{v['duracao_s']:.0f} s" if v["duracao_s"] is not None else "—")
    con.print(t)
    acoes_feitas = db.acoes(con_db, a.serial, a.limite)
    if acoes_feitas:
        t = Table(header_style="bold", title="Ações")
        for c in ("Data", "Tipo", "App", "Detalhe", "Desfeita"):
            t.add_column(c, overflow="fold")
        for x in acoes_feitas:
            t.add_row(x["data"].replace("T", " "), x["tipo"], x["pacote"] or "—", x["detalhe"] or "",
                      (x["desfeita_em"] or "").replace("T", " "))
        con.print(t)


def cmd_laudo(a):
    from celscan.relatorio import pdf

    con_db = db.conectar()
    meta, retrato = db.meta_varredura(con_db, a.id), db.retrato(con_db, a.id)
    if not meta:
        sys.exit(f"Varredura {a.id} não encontrada (veja: celscan historico)")
    conteudo, h = pdf.gerar_pdf(meta, retrato, a.versao, a.loja, db.acoes_da_varredura(con_db, a.id))
    db.registrar_laudo(con_db, a.id, h)
    arq = Path(a.saida or f"laudo_celscan_{a.id}_{a.versao}.pdf")
    arq.write_bytes(conteudo)
    con.print(f"[green]✔[/] Laudo salvo em [bold]{arq}[/] · código de verificação {pdf.codigo_curto(h)}")


def cmd_verificar(a):
    achado = db.verificar_laudo(db.conectar(), a.codigo)
    if not achado:
        con.print(Panel("Código não encontrado neste computador. O laudo pode ser falso ou ter sido emitido em "
                        "outro computador.", title="Não verificado", border_style="red"))
        sys.exit(1)
    con.print(Panel(f"Laudo nº {achado['varredura_id']} de {achado['data'].replace('T', ' ')}\n"
                    f"{achado['fabricante']} {achado['modelo']} ({achado['serial']}) · nota {achado['nota']} "
                    f"{achado['veredito']}", title="Laudo autêntico", border_style="green"))


def cmd_espelhar(a):
    from celscan.acoes.espelho import EspelhoErro, Espelhos, OpcoesEspelho

    serial = None
    if a.modo != "otg":
        serial = escolher_aparelho(a.serial).serial
    elif not Confirm.ask("Modo mouse: o celular recebe mouse e teclado do PC (sem imagem). Continuar?", default=True):
        return
    if a.modo == "otg":
        adb.run(["kill-server"], timeout=15)  # o modo mouse precisa da porta USB livre
    esp = Espelhos()
    opcoes = OpcoesEspelho.compativel(a.modo) if a.compativel else OpcoesEspelho(modo=a.modo)
    opcoes.tela_desligada, opcoes.gravar = a.tela_desligada, a.gravar
    try:
        sessao = esp.abrir(serial, opcoes)
    except EspelhoErro as e:
        sys.exit(str(e))
    erro = esp.erro_inicial(sessao)
    if erro:
        sys.exit(f"O espelhamento não abriu: {erro}")
    con.print("[green]✔[/] Janela aberta. Feche a janela do scrcpy para terminar.")
    sessao.processo.wait()


def cmd_backup(a):
    from celscan.acoes import backup

    ap = escolher_aparelho(a.serial)
    categorias = a.categorias.split(",") if a.categorias else list(backup.PADRAO)
    with con.status("Procurando arquivos no celular..."):
        arquivos = backup.listar(ap, categorias)
    resumo = backup.resumo_listagem(arquivos)
    t = Table(header_style="bold")
    for c in ("Categoria", "Arquivos", "Tamanho"):
        t.add_column(c)
    for c in categorias:
        t.add_row(resumo[c]["nome"], str(resumo[c]["arquivos"]), f"{resumo[c]['bytes'] / 1048576:.1f} MB")
    con.print(t)
    if a.listar or not arquivos:
        return con.print("Nada para copiar." if not arquivos else "")
    raiz = Path(a.destino) if a.destino else backup.pasta_padrao() / backup.nome_seguro(ap.serial)
    if not Confirm.ask(f"Copiar {len(arquivos)} arquivos para {raiz}?", default=True):
        return
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "apps_instalados.txt").write_text(backup.lista_de_apps(ap), encoding="utf-8")
    with barra() as p:
        t_id = p.add_task("Copiando", total=len(arquivos))
        res = backup.copiar(ap, arquivos, raiz, lambda ev: p.update(t_id, completed=ev["atual"]),
                            verificar_hash=a.verificar)
    con.print(Panel(f"Copiados agora: {res.copiados} · já estavam no PC: {res.pulados} · falhas: {len(res.falhas)}\n"
                    f"Pasta: {raiz}\n[dim]Dados pessoais do cliente: entregue e apague do PC depois (LGPD).[/]",
                    title="Backup", border_style="green" if not res.falhas else "yellow"))


def cmd_recuperar(a):
    from celscan.acoes import backup, recuperacao

    ap = escolher_aparelho(a.serial)
    con.print("[dim]Sem root não há 'undelete' real nem recuperação de mensagens do WhatsApp. "
              "O CelScan resgata o que ainda está no aparelho: lixeira, miniaturas e sobras dos apps.[/]")
    categorias = a.categorias.split(",") if a.categorias else list(recuperacao.PADRAO)
    with con.status("Procurando o que dá para recuperar..."):
        arquivos = recuperacao.procurar(ap, categorias)
    resumo = recuperacao.resumo(arquivos)
    t = Table(header_style="bold")
    for c in ("Origem", "Arquivos", "Tamanho"):
        t.add_column(c)
    for v in resumo.values():
        t.add_row(str(v["nome"]), str(v["arquivos"]), f"{int(v['bytes']) / 1048576:.1f} MB")
    con.print(t)
    if a.listar or not arquivos:
        return con.print("Nada recuperável encontrado." if not arquivos else "")
    raiz = Path(a.destino) if a.destino else backup.pasta_padrao() / backup.nome_seguro(ap.serial)
    if not Confirm.ask(f"Recuperar {len(arquivos)} arquivos para {raiz}?", default=True):
        return
    with barra() as p:
        t_id = p.add_task("Recuperando", total=len(arquivos))
        res = backup.copiar(ap, arquivos, raiz, lambda ev: p.update(t_id, completed=ev["atual"]),
                            verificar_hash=a.verificar, destino_de=recuperacao.destino_recuperado)
    con.print(Panel(f"Recuperados: {res.copiados} · já estavam no PC: {res.pulados} · falhas: {len(res.falhas)}\n"
                    f"Pasta: {raiz / 'Recuperados'}\n[dim]Dados pessoais: entregue e apague do PC depois (LGPD).[/]",
                    title="Recuperação", border_style="green" if not res.falhas else "yellow"))


def cmd_permissoes(a):
    from celscan.acoes import permissoes

    ap = escolher_aparelho(a.serial)
    r = permissoes.aplicar(ap, a.pacote, a.acoes or [], a.revogar or [])
    if not r["feitas"]:
        return con.print("Nada a fazer (o app já não tinha esses poderes).")
    for f in r["feitas"]:
        con.print(f"[green]✔[/] {f}")
    con.print(f"[dim]Desfaça com: celscan quarentena restaurar {r['quarentena_id']}[/]")


def cmd_certificados_bancos(a):
    from celscan.analise import certificados

    ap = escolher_aparelho(a.serial)
    with con.status("Lendo os certificados dos apps de banco instalados pela Play Store..."):
        novos = certificados.registrar_do_aparelho(ap)
    if not novos:
        return con.print("Nenhum app de banco da lista instalado pela Play Store neste aparelho.")
    for n in novos:
        con.print(f"[green]✔[/] {n['nome']} ({n['pacote']}): {n['sha256'][0][:16]}…")
    con.print(f"[dim]Guardado em {certificados.BASE.caminho}. Cópias falsas desses apps agora são detectadas.[/]")


def cmd_interface(a):
    from celscan.api import servidor

    servidor.abrir("navegador" if a.navegador else "janela", a.porta)


def cmd_fixtures(a):
    from celscan.core import fixtures

    ap = escolher_aparelho(a.serial)
    con.print(Panel("Vou gravar a saída de cada comando adb deste aparelho para os testes do CelScan.\n"
                    "Serial, IMEI, e-mails, MACs, redes Wi-Fi e IPs são anonimizados.\n"
                    "[bold]A lista de apps instalados não é anonimizada[/]: revise antes de publicar.",
                    title="Fixtures reais", border_style="cyan"))
    with con.status("Gravando...") as st:
        pasta = fixtures.gravar(ap, Path(a.pasta), progresso=lambda m: st.update(f"Gravando {m}"))
    con.print(f"[green]✔[/] Gravado em [bold]{pasta}[/]")
    con.print(f"[dim]Para testar com ele: CELSCAN_FIXTURE={pasta.name} (com o testes/fake_adb.py)[/]")


def cmd_bases(a):
    if a.atualizar:
        for b in bases.todas():
            with con.status(f"Atualizando {b.descricao}..."):
                ok, msg = bases.atualizar(b.nome, forcar=True)
            con.print(f"{'[green]✔' if ok else '[yellow]!'}[/] {b.nome}: {msg}")
    t = Table(header_style="bold", title="Bases" + (" (modo offline)" if config.OFFLINE else ""))
    for c in ("Base", "Descrição", "Cópia local", "Idade", "Situação"):
        t.add_column(c)
    for s in bases.situacao():
        idade = "—" if s["idade_h"] is None else f"{s['idade_h']:.0f} h"
        local = "sim" if s["local"] else ("só a que vem com o programa" if s["embutida"] else "não")
        t.add_row(str(s["nome"]), str(s["descricao"]), local, idade,
                  "[yellow]vencida[/]" if s["vencida"] else "[green]ok[/]")
    con.print(t)


def cmd_iocs(a):
    from celscan.analise import iocs as iocmod
    with con.status("Baixando indicadores..."):
        i = iocmod.carregar(forcar=True, avisar=con.print)
    con.print(f"{len(i) if i else 0} indicadores ({len(i.pacotes)} pacotes, {len(i.certs)} certificados, "
              f"{len(i.hashes)} hashes)." if i else "Falhou.")


def main():
    p = argparse.ArgumentParser(prog="celscan", description=f"CelScan {VERSAO} — segurança e otimização via USB")
    p.add_argument("--offline", action="store_true", help="Não acessa a internet (usa só as cópias locais)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("android", help="Varredura de segurança do Android")
    s.add_argument("--serial")
    s.add_argument("--sistema", action="store_true", help="Inclui apps do sistema (pré-instalados)")
    s.add_argument("--modo", choices=["rapido", "completo", "profundo"],
                   help="Padrão: completo se houver chave do VirusTotal, senão rápido")
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
    s.add_argument("--lixo", action="store_true", help="Apaga lixo seguro (miniaturas, temporários, cache do Telegram)")
    s.add_argument("--compilar", action="store_true")
    s.add_argument("--animacoes", type=float, help="Escala das animações (ex: 0.5; 1 = padrão)")
    s.add_argument("--debloat", action="store_true")
    s.set_defaults(func=cmd_otimizar)

    s = sub.add_parser("quarentena", help="Lista ou desfaz remoções")
    s.add_argument("acao", choices=["listar", "restaurar"])
    s.add_argument("id", nargs="?")
    s.add_argument("--serial")
    s.set_defaults(func=cmd_quarentena)

    s = sub.add_parser("ios", help="iPhone: ver info (--info) ou varredura completa (backup + MVT)")
    s.add_argument("--info", action="store_true", help="Só mostra os iPhones conectados (nome, modelo, iOS, IMEI)")
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

    s = sub.add_parser("historico", help="Varreduras e ações anteriores (banco local)")
    s.add_argument("--serial")
    s.add_argument("--limite", type=int, default=20)
    s.set_defaults(func=cmd_historico)

    s = sub.add_parser("laudo", help="Gera o laudo PDF de uma varredura do histórico")
    s.add_argument("id", type=int)
    s.add_argument("--versao", choices=["cliente", "tecnico"], default="cliente")
    s.add_argument("--loja")
    s.add_argument("--saida")
    s.set_defaults(func=cmd_laudo)

    s = sub.add_parser("verificar", help="Confere o código de verificação de um laudo")
    s.add_argument("codigo")
    s.set_defaults(func=cmd_verificar)

    s = sub.add_parser("espelhar", help="Mostra e controla a tela do celular no PC (scrcpy)")
    s.add_argument("--serial")
    s.add_argument("--modo", choices=["controlar", "ver", "otg"], default="controlar",
                   help="otg = mouse/teclado do PC no celular, sem depuração USB (toque quebrado)")
    s.add_argument("--tela-desligada", action="store_true", help="Desliga a tela do celular enquanto espelha")
    s.add_argument("--gravar", help="Grava a tela neste arquivo .mp4")
    s.add_argument("--compativel", action="store_true",
                   help="PC fraco ou vídeo (streaming) travando/preto: resolução e taxa menores + buffer")
    s.set_defaults(func=cmd_espelhar)

    s = sub.add_parser("backup", help="Copia fotos, vídeos, documentos e WhatsApp para o PC")
    s.add_argument("--serial")
    s.add_argument("--categorias", help="Lista separada por vírgula (padrão: todas menos Telegram)")
    s.add_argument("--destino")
    s.add_argument("--verificar", action="store_true", help="Confere o SHA-256 de cada arquivo (mais lento)")
    s.add_argument("--listar", action="store_true", help="Só mostra quanto há para copiar")
    s.set_defaults(func=cmd_backup)

    s = sub.add_parser("recuperar", help="Resgata sobras apagadas: lixeira, miniaturas e mídia deixada nos apps")
    s.add_argument("--serial")
    s.add_argument("--categorias", help="Lista separada por vírgula (padrão: lixeira,miniaturas,status_whatsapp)")
    s.add_argument("--destino")
    s.add_argument("--verificar", action="store_true", help="Confere o SHA-256 de cada arquivo (mais lento)")
    s.add_argument("--listar", action="store_true", help="Só mostra o que dá para recuperar")
    s.set_defaults(func=cmd_recuperar)

    s = sub.add_parser("permissoes", help="Tira poderes perigosos de um app (com desfazer)")
    s.add_argument("pacote")
    s.add_argument("--serial")
    s.add_argument("--acoes", nargs="*",
                   help="acessibilidade, notificacoes, sobreposicao, captura_tela, instalar_apps, parar")
    s.add_argument("--revogar", nargs="*", help="permissões Android a revogar (ex: android.permission.READ_SMS)")
    s.set_defaults(func=cmd_permissoes)

    s = sub.add_parser("certificados-bancos",
                       help="Registra os certificados oficiais dos apps de banco deste celular (Play Store)")
    s.add_argument("--serial")
    s.set_defaults(func=cmd_certificados_bancos)

    s = sub.add_parser("interface", help="Abre a interface gráfica")
    s.add_argument("--navegador", action="store_true", help="Abre no navegador em vez de janela própria")
    s.add_argument("--porta", type=int, default=0)
    s.set_defaults(func=cmd_interface)

    s = sub.add_parser("fixtures", help="Grava as saídas reais do aparelho para os testes")
    s.add_argument("--serial")
    s.add_argument("--pasta", default="testes/fixtures")
    s.set_defaults(func=cmd_fixtures)

    s = sub.add_parser("bases", help="Situação das bases (indicadores, UAD, certificados)")
    s.add_argument("--atualizar", action="store_true", help="Baixa todas agora")
    s.set_defaults(func=cmd_bases)

    s = sub.add_parser("iocs", help="Atualiza os indicadores de ameaças")
    s.set_defaults(func=cmd_iocs)

    a = p.parse_args()
    if a.offline:
        config.OFFLINE = True
    preferencias.aplicar()
    arquivo_log = log.configurar()
    log.LOGGER.info("CelScan %s: %s", VERSAO, " ".join(sys.argv[1:]))
    try:
        a.func(a)
    except (servicos.ModoIndisponivel, servicos.Cancelado) as e:
        con.print(Panel(str(e), border_style="yellow"))
        sys.exit(1)
    except adb.AdbErro as e:
        log.LOGGER.error("erro de conexão: %s", e)
        con.print(Panel(f"{e}\n\n[dim]Detalhes no log: {arquivo_log}[/]", title="Erro de conexão", border_style="red"))
        sys.exit(1)
    except KeyboardInterrupt:
        con.print("\n[yellow]Interrompido.[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()
