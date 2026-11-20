import { ClipboardList, FileSearch, Gauge, ScanLine, Settings, Smartphone } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, obterVarredura, type Tarefa, type Varredura } from "./api";
import ModoCliente from "./telas/ModoCliente";
import { useApp } from "./estado";
import Configuracoes from "./telas/Configuracoes";
import Balcao from "./telas/Balcao";
import Conectar from "./telas/Conectar";
import Historico from "./telas/Historico";
import Modo from "./telas/Modo";
import Recuperar from "./telas/Recuperar";
import Resgate from "./telas/Resgate";
import Resultado from "./telas/Resultado";
import Turbo from "./telas/Turbo";
import Varrendo, { porcentagem } from "./telas/Varrendo";
import { Avisos } from "./ui";

const ATALHOS: [string, string][] = [
  ["Alt + 1…5", "Trocar de seção"], ["Ctrl + K", "Procurar um app no resultado"], ["Ctrl + Enter", "Iniciar a varredura"], ["?", "Mostrar esta lista"],
  ["Esc", "Fechar janelas e diálogos"], ["Tab / Shift + Tab", "Andar pelos botões"],
];

function Atalhos({ fechar }: { fechar: () => void }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") fechar(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [fechar]);
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) fechar(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="atalhos-titulo" className="entrar w-full max-w-sm rounded-xl border border-linha bg-superficie p-5 shadow-2xl">
        <h2 id="atalhos-titulo" className="mb-3 font-semibold">Atalhos do teclado</h2>
        <dl className="space-y-2 text-sm">
          {ATALHOS.map(([k, o]) => <div key={k} className="flex justify-between gap-4"><dt><kbd className="font-mono">{k}</kbd></dt><dd className="text-fraco">{o}</dd></div>)}
        </dl>
        <button autoFocus className="mt-4 w-full rounded-md border border-linha py-1.5 text-sm hover:bg-superficie-2" onClick={fechar}>Fechar</button>
      </div>
    </div>
  );
}

/** Aviso de fim da varredura: bipe curto (se ligado em Configurações) e título piscando com a janela em segundo plano. */
export function avisarFim(texto: string) {
  let som = false;
  try { som = localStorage.getItem("celscan-som") === "1"; } catch { /* sem storage */ }
  if (som) {
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (Ctx) {
        const ctx = new Ctx(), osc = ctx.createOscillator(), vol = ctx.createGain();
        osc.frequency.value = 880; vol.gain.setValueAtTime(0.15, ctx.currentTime);
        vol.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
        osc.connect(vol).connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + 0.35);
        osc.onended = () => { ctx.close().catch(() => undefined); };
      }
    } catch { /* sem áudio */ }
  }
  if (document.hidden) {
    const original = document.title;
    let n = 0;
    const id = window.setInterval(() => {
      document.title = n++ % 2 ? original : `✔ ${texto}`;
      if (!document.hidden || n > 40) { window.clearInterval(id); document.title = original; }
    }, 900);
  }
}

type Fluxo =
  | { tela: "conectar" }
  | { tela: "modo"; serial: string }
  | { tela: "varrendo"; tarefa: Tarefa<Varredura>; modo: string }
  | { tela: "resultado"; v: Varredura };
type Secao = "varredura" | "otimizar" | "recuperar" | "atendimentos" | "config";

// 3.6: 5 seções em vez de 8. As que eram parecidas viraram abas dentro de uma só.
const SECOES: { id: Secao; nome: string; icone: typeof ScanLine }[] = [
  { id: "varredura", nome: "Verificar vírus", icone: ScanLine },
  { id: "otimizar", nome: "Otimizar", icone: Gauge },
  { id: "recuperar", nome: "Recuperar arquivos", icone: FileSearch },
  { id: "atendimentos", nome: "Atendimentos", icone: ClipboardList },
  { id: "config", nome: "Configurações", icone: Settings },
];
const ABAS: Partial<Record<Secao, [string, string][]>> = {
  recuperar: [["apagados", "Fotos e arquivos apagados"], ["quebrada", "Celular com tela quebrada"]],
  atendimentos: [["balcao", "Balcão"], ["historico", "Histórico"]],
};

function Abas({ secao, aba, mudar }: { secao: Secao; aba: string; mudar: (a: string) => void }) {
  const abas = ABAS[secao];
  if (!abas) return null;
  return (
    <div className="abas-secao" role="tablist">
      {abas.map(([id, nome]) => (
        <button key={id} role="tab" aria-selected={aba === id} onClick={() => mudar(id)}>{nome}</button>
      ))}
    </div>
  );
}

function Marca() {
  return (
    <div className="flex items-center gap-2.5 px-4">
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
        <rect x="7" y="2" width="16" height="27" rx="4" fill="#2b3033" stroke="#5a6266" strokeWidth="1.5" />
        <rect x="9.5" y="6" width="11" height="17" rx="2" fill="#e9f1f3" />
        <circle cx="21.5" cy="19.5" r="6" fill="rgba(240,180,0,.25)" stroke="var(--acao)" strokeWidth="2.5" />
        <path d="M25.8 23.8l4 4" stroke="var(--acao)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <span className="marca-nome nav-texto text-xl font-bold" style={{ fontStretch: "118%" }}>CelScan</span>
    </div>
  );
}

function AvisoAtualizacao() {
  const { esperar, avisar } = useApp();
  const [info, setInfo] = useState<{ disponivel: boolean; versao?: string; tamanho_mb?: number; beta?: boolean } | null>(null);
  const [baixando, setBaixando] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => api<typeof info>("/atualizacao").then(setInfo).catch(() => undefined), 3000);
    return () => clearTimeout(t);
  }, []);
  if (!info?.disponivel) return null;
  async function atualizar() {
    setBaixando(true);
    try {
      const t = await esperar(await api<Tarefa>("/atualizacao/instalar", { corpo: {} }));
      if (t.estado === "concluida") avisar({ tipo: "info", texto: "Instalando a nova versão. O CelScan vai fechar e abrir de novo.", duracao: 15000 });
      else avisar({ tipo: "erro", texto: t.erro ?? "Não consegui atualizar." });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setBaixando(false); }
  }
  return (
    <div className="rounded-md border border-destaque/40 bg-destaque-suave p-2 text-tinta" role="status">
      <p className="font-semibold">Versão {info.versao} disponível{info.beta ? " (beta)" : ""}</p>
      <button className="mt-1 underline disabled:opacity-50" onClick={atualizar} disabled={baixando}>
        {baixando ? "Baixando..." : `Atualizar (${info.tamanho_mb ?? "?"} MB)`}
      </button>
    </div>
  );
}

function Passos({ fluxo }: { fluxo: Fluxo }) {
  const atual = fluxo.tela === "conectar" ? 0 : fluxo.tela === "modo" ? 1 : fluxo.tela === "varrendo" ? 1 : 2;
  return (
    <ol className="passos" aria-label="Etapas">
      {["Conectar o celular", "Analisar", "Resolver e entregar o laudo"].map((n, i) => (
        <li key={n} className={i < atual ? "feito" : i === atual ? "atual" : ""} aria-current={i === atual ? "step" : undefined}>{n}</li>
      ))}
    </ol>
  );
}

export default function App() {
  const { estado, online, dispositivos, avisar, erroBackend, modelo, mudarModelo } = useApp();
  const [secao, setSecaoBruta] = useState<Secao>("varredura");
  const [abas, setAbas] = useState<Record<string, string>>({ otimizar: "turbo", recuperar: "apagados", atendimentos: "balcao" });
  const setSecao = useCallback((s: Secao) => setSecaoBruta(s), []);
  const aba = abas[secao] ?? "";
  const mudarAba = (a: string) => setAbas((x) => ({ ...x, [secao]: a }));
  const [fluxo, setFluxo] = useState<Fluxo>({ tela: "conectar" });
  const [atalhos, setAtalhos] = useState(false);

  // Alt+1..5 muda de seção; "?" mostra os atalhos (fora de campos de texto)
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      const alvo = e.target as HTMLElement | null;
      const digitando = alvo && (alvo.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(alvo.tagName));
      if (e.key === "?" && !digitando && !e.ctrlKey && !e.altKey) { e.preventDefault(); setAtalhos(true); return; }
      if (!e.altKey) return;
      const i = Number(e.key) - 1;
      if (SECOES[i]) { e.preventDefault(); setSecao(SECOES[i].id); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [setSecao]);

  const iniciar = useCallback(async (serial: string, modo: string) => {
    try {
      const t = await api<Tarefa<Varredura>>("/varreduras", { corpo: { serial, modo } });
      setFluxo({ tela: "varrendo", tarefa: t, modo });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }, [avisar]);
  const aoTerminar = useCallback((v: Varredura) => {
    setFluxo({ tela: "resultado", v });
    avisarFim(`Análise pronta: nota ${v.nota}`);
  }, []);
  const aoCancelar = useCallback((erro: string) => {
    avisar({ tipo: "erro", texto: erro });
    setFluxo({ tela: "conectar" });
  }, [avisar]);
  const abrirHistorico = useCallback(async (id: number) => {
    try {
      setFluxo({ tela: "resultado", v: await obterVarredura(id) });
      setSecao("varredura");
    } catch (e) {
      avisar({ tipo: "erro", texto: `Não consegui abrir a varredura ${id}: ${(e as Error).message}` });
    }
  }, [avisar, setSecao]);

  const prontos = dispositivos.filter((d) => d.estado === "device");
  const { tarefas } = useApp();
  const varrendo = fluxo.tela === "varrendo"
    ? Math.max(1, porcentagem((tarefas[fluxo.tarefa.id] ?? fluxo.tarefa).progresso ?? {}, fluxo.modo, !!estado?.vt)) : 0;

  const telaVarredura = (
    fluxo.tela === "conectar" ? <Conectar onEscolher={(serial) => setFluxo({ tela: "modo", serial })} /> :
    fluxo.tela === "modo" ? <Modo serial={fluxo.serial} onIniciar={(m) => iniciar(fluxo.serial, m)}
      onVoltar={() => setFluxo({ tela: "conectar" })} onConfig={() => setSecao("config")} /> :
    fluxo.tela === "varrendo" ? <Varrendo tarefa={fluxo.tarefa} modo={fluxo.modo} onFim={aoTerminar} onCancelado={aoCancelar} /> :
    <Resultado v={fluxo.v} onNova={() => setFluxo({ tela: "conectar" })} />
  );
  const erro = erroBackend && (
    <div className="mb-4 rounded-lg border border-perigo/50 bg-perigo-suave p-3 text-sm text-perigo" role="alert">
      Não consegui falar com o CelScan ({erroBackend}). Feche e abra o programa. Se continuar, me mande o
      arquivo celscan.log da pasta .celscan\logs.
    </div>
  );
  const voltarPainel = (
    <button className="sair-modelo" onClick={() => mudarModelo("estudio")}>Voltar ao modo completo</button>
  );

  // Modo cliente: segunda tela, sem menus nem botões de ação.
  if (modelo === "cliente") {
    return (
      <div className="h-full overflow-auto">
        <main id="conteudo" className="bancada min-h-full px-6 py-8" tabIndex={-1}><ModoCliente /></main>
        {voltarPainel}
        <Avisos />{atalhos && <Atalhos fechar={() => setAtalhos(false)} />}
      </div>
    );
  }
  // Assistente: um passo por vez, só a varredura, botões grandes.
  if (modelo === "assistente") {
    return (
      <div className="h-full overflow-auto">
        <a href="#conteudo" className="pular-link">Pular para o conteúdo</a>
        <header className="assistente-topo"><Marca /><Passos fluxo={fluxo} /></header>
        <main id="conteudo" className="bancada assistente-corpo" tabIndex={-1}>{erro}{telaVarredura}</main>
        {voltarPainel}
        <Avisos />{atalhos && <Atalhos fechar={() => setAtalhos(false)} />}
      </div>
    );
  }

  const conteudo = (
    <>
      {erro}
      <Abas secao={secao} aba={aba} mudar={mudarAba} />
      {secao === "atendimentos" && aba === "balcao" && <Balcao />}
      {secao === "atendimentos" && aba === "historico" && <Historico onAbrir={abrirHistorico} />}
      {secao === "otimizar" && <Turbo />}
      {secao === "recuperar" && aba === "apagados" && <Recuperar />}
      {secao === "recuperar" && aba === "quebrada" && <Resgate />}
      {secao === "config" && <Configuracoes />}
      {secao === "varredura" && telaVarredura}
    </>
  );
  const status = (
    <p className="flex items-center gap-2">
      <span className={`inline-block h-2 w-2 rounded-full ${online ? "bg-ok" : "pulsar bg-atencao"}`} aria-hidden />
      {online ? (estado?.offline ? "Pronto (sem internet)" : "Pronto") : "Reconectando..."}
    </p>
  );

  // Revista (menu no topo) e Toque (barra embaixo): navegação horizontal.
  if (modelo === "revista" || modelo === "toque") {
    const barra = (
      <nav className={modelo === "revista" ? "nav-topo" : "nav-baixo"} aria-label="Seções">
        {modelo === "revista" && <Marca />}
        <ul>
          {SECOES.map((s) => {
            const Icone = s.icone;
            return (
              <li key={s.id}>
                <button onClick={() => setSecao(s.id)} aria-current={secao === s.id ? "page" : undefined}>
                  <Icone size={modelo === "toque" ? 24 : 16} aria-hidden /><span>{s.nome}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {modelo === "revista" && <div className="nav-topo-status">{status}<AvisoAtualizacao /></div>}
      </nav>
    );
    return (
      <div className={`casca-${modelo} h-full`}>
        <a href="#conteudo" className="pular-link">Pular para o conteúdo</a>
        {modelo === "revista" && barra}
        <main id="conteudo" className="bancada" tabIndex={-1}>{conteudo}</main>
        {modelo === "toque" && barra}
        <Avisos />{atalhos && <Atalhos fechar={() => setAtalhos(false)} />}
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <a href="#conteudo" className="pular-link">Pular para o conteúdo</a>
      <nav className="nav-lateral trilho flex w-56 shrink-0 flex-col py-5" aria-label="Seções">
        <Marca />
        <ul className="mt-8 space-y-0.5">
          {SECOES.map((s) => {
            const Icone = s.icone;
            const ativo = secao === s.id;
            return (
              <li key={s.id}>
                <button onClick={() => setSecao(s.id)} aria-current={ativo ? "page" : undefined} title={s.nome}
                  className={`trilho-item flex w-full items-center gap-3 px-5 py-2.5 text-[0.95rem] ${ativo ? "nav-ativo font-semibold" : ""}`}>
                  <Icone size={18} aria-hidden /> <span className="nav-texto flex-1 text-left">{s.nome}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {varrendo > 0 && secao !== "varredura" && (
          <div className="nav-texto mt-6 px-3">
            <button className="em-andamento" onClick={() => setSecao("varredura")}>
              Verificação em andamento: {varrendo}%
              <span className="em-andamento-barra"><i style={{ width: `${varrendo}%` }} /></span>
            </button>
          </div>
        )}
        <div className="nav-texto mt-auto space-y-3 px-5 text-xs">
          <div className="space-y-1.5" aria-live="polite">
            {prontos.length === 0 ? <p>Nenhum celular conectado</p> : prontos.map((d) => (
              <p key={d.serial} className="flex items-center gap-2 text-white">
                <Smartphone size={14} className="text-[var(--acao)]" aria-hidden />
                <span className="truncate">{d.fabricante ? `${d.fabricante} ${d.modelo}` : d.serial}</span>
              </p>
            ))}
          </div>
          {status}
          <AvisoAtualizacao />
          <p className="opacity-60">versão {estado?.versao}</p>
        </div>
      </nav>

      <main id="conteudo" className="bancada flex-1 overflow-auto px-10 py-8" tabIndex={-1}><div className="mx-auto max-w-5xl">{conteudo}</div></main>
      <Avisos />{atalhos && <Atalhos fechar={() => setAtalhos(false)} />}
    </div>
  );
}
