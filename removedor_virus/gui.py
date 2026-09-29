"""Janela do programa (Tkinter)."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from . import __version__
from .acoes import Removedor, dns_antianuncios
from .adb import ADB, Dispositivo, ErroADB, baixar_adb, localizar_adb
from .caminhos import ler_config, pasta_dados, pasta_recursos, pasta_relatorios, salvar_config
from .heuristicas import App, carregar_assinaturas
from .relatorio import salvar_relatorio
from .scanner import Scanner

TITULO = "Removedor de Vírus Android"
URL_VT = "https://www.virustotal.com/gui/join-us"

AJUDA_CONEXAO = """Nenhum celular encontrado.

Para conectar:
1. No celular, abra Configurações > Sobre o telefone e toque 7 vezes em "Número da versão" (Xiaomi: "Versão MIUI/HyperOS").
2. Volte em Configurações > Sistema > Opções do desenvolvedor e ative "Depuração USB".
3. Ligue o celular ao computador com um cabo USB de dados e escolha "Transferência de arquivos".
4. Toque em PERMITIR no aviso "Permitir depuração USB?".
5. Clique em "Conectar".

Samsung: se não aparecer, instale o driver USB da Samsung."""

CORES_NIVEL = {"ALTO": "#ffd6d6", "MEDIO": "#fff1c2", "BAIXO": "#e3f2fd", "LIMPO": "#e8f5e9"}
NOMES_NIVEL = {"ALTO": "Alto", "MEDIO": "Médio", "BAIXO": "Baixo", "LIMPO": "Limpo"}


def abrir_pasta(caminho) -> None:
    caminho.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(caminho)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(caminho)])


class Janela(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{TITULO} {__version__}")
        self.geometry("1040x660")
        self.minsize(820, 520)
        icone = pasta_recursos() / "assets" / "icone.ico"
        if os.name == "nt" and icone.is_file():
            self.iconbitmap(default=str(icone))

        self.fila: queue.Queue = queue.Queue()
        self.adb: ADB | None = None
        self.info: dict = {}
        self.dispositivos: list[Dispositivo] = []
        self.apps: list[App] = []
        self.visiveis: list[App] = []
        self.ocupado = False
        self.assinaturas = carregar_assinaturas()

        self._estilo()
        self._montar()
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.after(100, self._processar_fila)
        self.after(300, self.conectar)

    # ------------------------------------------------------------------ layout

    def _estilo(self) -> None:
        estilo = ttk.Style(self)
        if "vista" in estilo.theme_names():
            estilo.theme_use("vista")
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 15, "bold"))
        estilo.configure("Sub.TLabel", foreground="#555")
        estilo.configure("Acao.TButton", padding=(10, 6))
        estilo.configure("Treeview", rowheight=24)

    def _montar(self) -> None:
        topo = ttk.Frame(self, padding=(12, 10, 12, 4))
        topo.pack(fill="x")
        ttk.Label(topo, text=TITULO, style="Titulo.TLabel").pack(side="left")
        ttk.Button(topo, text="Conectar", command=self.conectar).pack(side="right")
        self.combo = ttk.Combobox(topo, state="readonly", width=34)
        self.combo.pack(side="right", padx=6)
        self.combo.bind("<<ComboboxSelected>>", self._trocar_dispositivo)

        self.lbl_dispositivo = ttk.Label(self, text="Procurando celular...", style="Sub.TLabel", padding=(12, 0))
        self.lbl_dispositivo.pack(fill="x")

        barra = ttk.Frame(self, padding=(12, 8))
        barra.pack(fill="x")
        self.botoes: list[ttk.Button] = []
        for texto, comando in (
            ("Escanear", self.escanear),
            ("Remover selecionados", self.remover_selecionados),
            ("Limpeza rápida", self.limpeza_rapida),
            ("Restaurar...", self.restaurar),
            ("Bloquear anúncios (DNS)", self.dns),
        ):
            botao = ttk.Button(barra, text=texto, command=comando, style="Acao.TButton")
            botao.pack(side="left", padx=(0, 6))
            self.botoes.append(botao)

        menu = tk.Menu(self)
        arquivo = tk.Menu(menu, tearoff=False)
        arquivo.add_command(label="Abrir relatórios", command=lambda: abrir_pasta(pasta_relatorios()))
        arquivo.add_command(label="Abrir pasta de dados", command=lambda: abrir_pasta(pasta_dados()))
        arquivo.add_separator()
        arquivo.add_command(label="Sair", command=self.fechar)
        menu.add_cascade(label="Arquivo", menu=arquivo)
        opcoes = tk.Menu(menu, tearoff=False)
        self.var_limpos = tk.BooleanVar(value=False)
        self.var_vt_todos = tk.BooleanVar(value=False)
        opcoes.add_checkbutton(label="Mostrar apps limpos", variable=self.var_limpos, command=self._preencher)
        opcoes.add_checkbutton(label="VirusTotal: consultar todos os apps (lento)", variable=self.var_vt_todos)
        opcoes.add_command(label="Chave do VirusTotal...", command=self.configurar_vt)
        opcoes.add_command(label="Desativar DNS bloqueador", command=lambda: self.dns(ativar=False))
        menu.add_cascade(label="Opções", menu=opcoes)
        ajuda = tk.Menu(menu, tearoff=False)
        ajuda.add_command(label="Como conectar o celular", command=lambda: messagebox.showinfo(TITULO, AJUDA_CONEXAO))
        ajuda.add_command(label="Sobre", command=self._sobre)
        menu.add_cascade(label="Ajuda", menu=ajuda)
        self.config(menu=menu)

        painel = ttk.PanedWindow(self, orient="horizontal")
        painel.pack(fill="both", expand=True, padx=12)

        quadro_lista = ttk.Frame(painel)
        colunas = ("nivel", "pontos", "pacote", "origem")
        self.tree = ttk.Treeview(quadro_lista, columns=colunas, show="headings", selectmode="extended")
        for coluna, titulo, largura, ancora in (
            ("nivel", "Risco", 70, "center"),
            ("pontos", "Pontos", 60, "center"),
            ("pacote", "App (pacote)", 300, "w"),
            ("origem", "Origem", 170, "w"),
        ):
            self.tree.heading(coluna, text=titulo)
            self.tree.column(coluna, width=largura, anchor=ancora, stretch=coluna == "pacote")
        for nivel, fundo in CORES_NIVEL.items():
            self.tree.tag_configure(nivel, background=fundo)
        rolagem = ttk.Scrollbar(quadro_lista, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=rolagem.set)
        self.tree.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._mostrar_detalhes)
        painel.add(quadro_lista, weight=3)

        self.detalhes = tk.Text(painel, wrap="word", width=40, relief="flat", padx=10, pady=8,
                                font=("Segoe UI", 10), background="#fafafa")
        painel.add(self.detalhes, weight=2)
        self._texto_detalhes("Conecte o celular e clique em Escanear.")

        rodape = ttk.Frame(self, padding=(12, 6))
        rodape.pack(fill="x")
        self.progresso = ttk.Progressbar(rodape, mode="determinate", length=220)
        self.progresso.pack(side="right")
        self.lbl_status = ttk.Label(rodape, text="Pronto.")
        self.lbl_status.pack(side="left", fill="x", expand=True)

    # ----------------------------------------------------------- tarefas/threads

    def _na_ui(self, funcao: Callable[[], None]) -> None:
        """Agenda uma função para rodar na thread da janela."""
        self.fila.put(funcao)

    def _processar_fila(self) -> None:
        try:
            while True:
                self.fila.get_nowait()()
        except queue.Empty:
            pass
        self.after(80, self._processar_fila)

    def _em_segundo_plano(self, descricao: str, tarefa: Callable[[], object],
                          ao_terminar: Callable[[object], None] | None = None) -> None:
        if self.ocupado:
            return
        self._definir_ocupado(True, descricao)

        def rodar() -> None:
            try:
                resultado = tarefa()
            except Exception as erro:  # noqa: BLE001 - qualquer falha vira mensagem na tela
                self._na_ui(lambda e=erro: self._falhou(e))
                return
            self._na_ui(lambda: self._concluir(ao_terminar, resultado))

        threading.Thread(target=rodar, daemon=True).start()

    def _concluir(self, ao_terminar, resultado) -> None:
        self._definir_ocupado(False)
        if ao_terminar:
            ao_terminar(resultado)

    def _falhou(self, erro: Exception) -> None:
        self._definir_ocupado(False, "Erro.")
        messagebox.showerror(TITULO, str(erro) or erro.__class__.__name__)

    def _definir_ocupado(self, ocupado: bool, status: str | None = None) -> None:
        self.ocupado = ocupado
        for botao in self.botoes:
            botao.state(["disabled"] if ocupado else ["!disabled"])
        self.config(cursor="watch" if ocupado else "")
        if ocupado:
            self.progresso.configure(mode="indeterminate")
            self.progresso.start(12)
        else:
            self.progresso.stop()
            self.progresso.configure(mode="determinate", value=0)
        if status:
            self.lbl_status.config(text=status)

    def _atualizar_progresso(self, atual: int, total: int, texto: str) -> None:
        def aplicar() -> None:
            self.progresso.stop()
            self.progresso.configure(mode="determinate", maximum=max(total, 1), value=atual)
            self.lbl_status.config(text=f"[{atual}/{total}] {texto}")
        self._na_ui(aplicar)

    def _precisa_celular(self) -> bool:
        if self.adb and self.adb.serial:
            return True
        messagebox.showwarning(TITULO, AJUDA_CONEXAO)
        return False

    # ----------------------------------------------------------------- conexão

    def conectar(self) -> None:
        if not localizar_adb():
            if not messagebox.askyesno(
                TITULO, "O ADB (ferramenta oficial do Google para falar com o celular) não foi encontrado.\n\n"
                "Deseja baixá-lo agora (cerca de 10 MB)?"
            ):
                return
            self._em_segundo_plano("Baixando ADB...", baixar_adb, lambda _: self.conectar())
            return

        def tarefa():
            adb = ADB(serial=self.adb.serial if self.adb else None)
            return adb, adb.dispositivos()

        self._em_segundo_plano("Procurando celular...", tarefa, self._ao_listar)

    def _ao_listar(self, resultado) -> None:
        adb, dispositivos = resultado
        self.adb = adb
        self.dispositivos = [d for d in dispositivos if d.pronto]
        self.combo["values"] = [f"{d.modelo or 'Android'} ({d.serial})" for d in self.dispositivos]
        if not self.dispositivos:
            adb.serial = None
            self.combo.set("")
            if any(d.estado == "unauthorized" for d in dispositivos):
                texto = "Celular conectado, mas não autorizado. Desbloqueie a tela e toque em PERMITIR."
            else:
                texto = "Nenhum celular conectado."
            self.lbl_dispositivo.config(text=texto)
            self.lbl_status.config(text=texto)
            self._texto_detalhes(AJUDA_CONEXAO)
            return
        seriais = [d.serial for d in self.dispositivos]
        indice = seriais.index(adb.serial) if adb.serial in seriais else 0
        self.combo.current(indice)
        self._selecionar(self.dispositivos[indice])

    def _trocar_dispositivo(self, _evento=None) -> None:
        if self.combo.current() >= 0:
            self._selecionar(self.dispositivos[self.combo.current()])

    def _selecionar(self, dispositivo: Dispositivo) -> None:
        self.adb.serial = dispositivo.serial
        self.apps, self.visiveis = [], []
        self._preencher()
        self._em_segundo_plano("Lendo informações do celular...", self.adb.info_dispositivo, self._ao_info)

    def _ao_info(self, info: dict) -> None:
        self.info = info
        texto = f"{info['fabricante']} {info['modelo']}  •  Android {info['android']}"
        if info.get("patch_seguranca"):
            texto += f"  •  Patch de segurança {info['patch_seguranca']}"
        self.lbl_dispositivo.config(text=texto)
        self.lbl_status.config(text="Celular conectado. Clique em Escanear.")
        self._texto_detalhes("Celular conectado.\n\nClique em Escanear para procurar vírus e apps de anúncios.")

    # ----------------------------------------------------------------- escanear

    def escanear(self, depois: Callable[[], None] | None = None) -> None:
        if not self._precisa_celular():
            return
        chave_vt = ler_config().get("chave_virustotal") or None
        vt_todos = self.var_vt_todos.get()

        def tarefa():
            apps = Scanner(self.adb, self.assinaturas).escanear(
                progresso=self._atualizar_progresso, chave_vt=chave_vt, vt_todos=vt_todos
            )
            return apps, salvar_relatorio(apps, self.info)

        def ao_terminar(resultado) -> None:
            self.apps, _relatorio = resultado
            self._preencher()
            contagem = {n: sum(1 for a in self.apps if a.nivel == n) for n in CORES_NIVEL}
            self.lbl_status.config(
                text=f"{len(self.apps)} apps analisados  •  Alto: {contagem['ALTO']}  •  "
                f"Médio: {contagem['MEDIO']}  •  Baixo: {contagem['BAIXO']}  •  Limpos: {contagem['LIMPO']}"
            )
            if depois:
                depois()
            elif contagem["ALTO"]:
                self._texto_detalhes(
                    f"Foram encontrados {contagem['ALTO']} app(s) de risco ALTO (em vermelho).\n\n"
                    "Clique em um app para ver os motivos. Selecione e clique em "
                    "\"Remover selecionados\", ou use \"Limpeza rápida\"."
                )
            else:
                self._texto_detalhes("Nenhum app de risco alto encontrado.\n\nClique em um app para ver detalhes.")

        self._em_segundo_plano("Escaneando...", tarefa, ao_terminar)

    def _preencher(self) -> None:
        self.tree.delete(*self.tree.get_children())
        mostrar_limpos = self.var_limpos.get()
        self.visiveis = [a for a in self.apps if mostrar_limpos or a.nivel != "LIMPO"]
        for indice, app in enumerate(self.visiveis):
            origem = "Loja oficial" if app.da_loja_oficial else (app.instalador or "APK baixado")
            self.tree.insert("", "end", iid=str(indice), tags=(app.nivel,),
                             values=(NOMES_NIVEL[app.nivel], app.pontuacao, app.pacote, origem))
        if self.apps and not self.visiveis:
            self._texto_detalhes("Nenhum app suspeito encontrado. Seu celular parece limpo!")

    def _selecionados(self) -> list[App]:
        return [self.visiveis[int(i)] for i in self.tree.selection()]

    def _mostrar_detalhes(self, _evento=None) -> None:
        selecionados = self._selecionados()
        if not selecionados:
            return
        if len(selecionados) > 1:
            self._texto_detalhes(f"{len(selecionados)} apps selecionados.")
            return
        app = selecionados[0]
        linhas = [
            app.pacote,
            f"Risco: {NOMES_NIVEL[app.nivel]} ({app.pontuacao} pontos)",
            "",
            "Motivos:" if app.motivos else "Nenhum sinal suspeito.",
            *[f"  • {m}" for m in app.motivos],
            "",
            f"Versão: {app.versao or '-'}",
            f"Instalado em: {app.instalado_em or '-'}",
            f"Instalado por: {app.instalador or 'desconhecido (APK)'}",
        ]
        if app.sha256:
            linhas.append(f"SHA-256: {app.sha256}")
        if app.virustotal and app.virustotal.get("erro"):
            linhas.append(f"VirusTotal: {app.virustotal['erro']}")
        self._texto_detalhes("\n".join(linhas))

    def _texto_detalhes(self, texto: str) -> None:
        self.detalhes.config(state="normal")
        self.detalhes.delete("1.0", "end")
        self.detalhes.insert("1.0", texto)
        self.detalhes.config(state="disabled")

    # ------------------------------------------------------------------ remover

    def remover_selecionados(self) -> None:
        if not self._precisa_celular():
            return
        alvos = self._selecionados()
        if not alvos:
            messagebox.showinfo(TITULO, "Selecione na lista os apps que deseja remover (Ctrl+clique para vários).")
            return
        self._confirmar_e_remover(alvos)

    def limpeza_rapida(self) -> None:
        if not self._precisa_celular():
            return

        def depois() -> None:
            alvos = [a for a in self.apps if a.nivel == "ALTO"]
            if not alvos:
                messagebox.showinfo(TITULO, "Nenhum app de risco ALTO encontrado. Seu celular parece limpo!")
                return
            self._confirmar_e_remover(alvos)

        self.escanear(depois=depois)

    def _confirmar_e_remover(self, alvos: list[App]) -> None:
        lista = "\n".join(f"  • {a.pacote} ({NOMES_NIVEL[a.nivel]})" for a in alvos[:15])
        if len(alvos) > 15:
            lista += f"\n  ... e mais {len(alvos) - 15}"
        if not messagebox.askyesno(
            TITULO, f"Remover {len(alvos)} app(s)?\n\n{lista}\n\n"
            "Uma cópia de cada app será guardada na quarentena, para restaurar se precisar."
        ):
            return

        def tarefa():
            removedor = Removedor(self.adb)
            resultados = []
            for indice, app in enumerate(alvos, 1):
                self._atualizar_progresso(indice, len(alvos), f"Removendo {app.pacote}")
                resultados.append(removedor.remover(app))
            return resultados

        def ao_terminar(resultados) -> None:
            ok = [r for r in resultados if r.sucesso]
            falhas = [r for r in resultados if not r.sucesso]
            texto = f"Removidos: {len(ok)}   Falhas: {len(falhas)}\n"
            for r in resultados:
                texto += f"\n{'✔' if r.sucesso else '✖'} {r.pacote}\n" + "".join(f"    - {e}\n" for e in r.etapas)
            self._texto_detalhes(texto)
            if falhas:
                messagebox.showwarning(
                    TITULO, f"{len(falhas)} app(s) não puderam ser removidos. Veja os detalhes no painel.\n\n"
                    "Se for administrador do dispositivo, desative em Configurações > Segurança > "
                    "Apps de administração do dispositivo e tente de novo."
                )
            self.escanear(depois=lambda: self._texto_detalhes(texto))

        self._em_segundo_plano("Removendo...", tarefa, ao_terminar)

    # ---------------------------------------------------------------- restaurar

    def restaurar(self) -> None:
        if not self._precisa_celular():
            return
        removedor = Removedor(self.adb)
        pastas = removedor.listar_quarentena()
        if not pastas:
            messagebox.showinfo(TITULO, "A quarentena está vazia.")
            return

        janela = tk.Toplevel(self)
        janela.title("Restaurar da quarentena")
        janela.geometry("560x360")
        janela.transient(self)
        ttk.Label(janela, text="Selecione os apps para reinstalar no celular:", padding=10).pack(anchor="w")
        lista = tk.Listbox(janela, selectmode="extended")
        for pasta in pastas:
            pacote, _, data = pasta.name.partition("__")
            lista.insert("end", f"{pacote}   ({data})   [{pasta.parent.name}]")
        lista.pack(fill="both", expand=True, padx=10)

        def confirmar() -> None:
            escolhidas = [pastas[i] for i in lista.curselection()]
            if not escolhidas:
                return
            janela.destroy()

            def tarefa():
                return [(p.name.split("__")[0], *removedor.restaurar(p)) for p in escolhidas]

            def ao_terminar(resultados) -> None:
                texto = "\n".join(f"{'✔' if ok else '✖'} {pacote}: {msg}" for pacote, ok, msg in resultados)
                self._texto_detalhes("Restauração:\n\n" + texto)

            self._em_segundo_plano("Restaurando...", tarefa, ao_terminar)

        ttk.Button(janela, text="Restaurar", command=confirmar).pack(pady=10)

    # ---------------------------------------------------------------- DNS / VT

    def dns(self, ativar: bool = True) -> None:
        if not self._precisa_celular():
            return
        pergunta = (
            "Ativar o DNS Privado AdGuard no celular?\n\n"
            "Ele bloqueia anúncios e sites perigosos em todos os apps e no navegador (Android 9+).\n"
            "Pode ser desfeito em Opções > Desativar DNS bloqueador."
            if ativar else "Desativar o DNS bloqueador de anúncios?"
        )
        if not messagebox.askyesno(TITULO, pergunta):
            return
        self._em_segundo_plano(
            "Configurando DNS...",
            lambda: dns_antianuncios(self.adb, ativar),
            lambda modo: messagebox.showinfo(
                TITULO, "Bloqueio de anúncios ativado!" if modo == "hostname" and ativar
                else f"DNS configurado (modo: {modo or 'padrão'})."
            ),
        )

    def configurar_vt(self) -> None:
        atual = ler_config().get("chave_virustotal", "")
        if not atual and messagebox.askyesno(
            TITULO, "O VirusTotal verifica cada app em mais de 70 antivírus.\n\n"
            "Crie uma conta gratuita e copie sua API Key. Abrir o site agora?"
        ):
            webbrowser.open(URL_VT)
        chave = simpledialog.askstring(TITULO, "Cole sua chave (API Key) do VirusTotal:\n(vazio para desativar)",
                                       initialvalue=atual, parent=self)
        if chave is not None:
            salvar_config(chave_virustotal=chave.strip())
            messagebox.showinfo(TITULO, "VirusTotal ativado." if chave.strip() else "VirusTotal desativado.")

    def _sobre(self) -> None:
        messagebox.showinfo(
            TITULO, f"{TITULO} {__version__}\n\n"
            "Detecta e remove vírus e apps de anúncios de celulares Android via cabo USB.\n\n"
            f"Dados e quarentena: {pasta_dados()}"
        )

    def fechar(self) -> None:
        if self.ocupado and not messagebox.askyesno(TITULO, "Uma operação está em andamento. Sair mesmo assim?"):
            return
        # Só encerra o ADB que vem com o programa (não atrapalha outras ferramentas).
        if self.adb and self.adb.caminho.startswith((str(pasta_recursos()), str(pasta_dados()))):
            self.adb.encerrar_servidor()
        self.destroy()


def main() -> int:
    Janela().mainloop()
    return 0
