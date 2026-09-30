import { History, MonitorSmartphone, ScanLine, Settings, Smartphone } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, obterVarredura, type Tarefa, type Varredura } from "./api";
import { useApp } from "./estado";
import Configuracoes from "./telas/Configuracoes";
import Conectar from "./telas/Conectar";
import Historico from "./telas/Historico";
import Modo from "./telas/Modo";
import Resgate from "./telas/Resgate";
import Resultado from "./telas/Resultado";
import Varrendo from "./telas/Varrendo";
import { Avisos } from "./ui";

type Fluxo =
  | { tela: "conectar" }
  | { tela: "modo"; serial: string }
  | { tela: "varrendo"; tarefa: Tarefa<Varredura>; modo: string }
  | { tela: "resultado"; v: Varredura };
type Secao = "varredura" | "resgate" | "historico" | "config";

const SECOES: { id: Secao; nome: string; icone: typeof ScanLine }[] = [
  { id: "varredura", nome: "Varredura", icone: ScanLine },
  { id: "resgate", nome: "Tela quebrada", icone: MonitorSmartphone },
  { id: "historico", nome: "Histórico", icone: History },
  { id: "config", nome: "Configurações", icone: Settings },
];

function Marca() {
  return (
    <div className="flex items-center gap-2 px-2">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect x="8" y="3" width="16" height="26" rx="3" fill="none" stroke="var(--tinta)" strokeWidth="2" />
        <path d="M4 16h24" stroke="var(--destaque)" strokeWidth="2" strokeLinecap="round" />
        <path d="M4 10V6a2 2 0 0 1 2-2h2M28 10V6a2 2 0 0 0-2-2h-2M4 22v4a2 2 0 0 0 2 2h2M28 22v4a2 2 0 0 1-2 2h-2"
          fill="none" stroke="var(--destaque)" strokeWidth="1.5" />
      </svg>
      <span className="font-mono text-lg font-semibold tracking-tight">CelScan</span>
    </div>
  );
}

export default function App() {
  const { estado, online, dispositivos, avisar, erroBackend } = useApp();
  const [secao, setSecao] = useState<Secao>("varredura");
  const [fluxo, setFluxo] = useState<Fluxo>({ tela: "conectar" });

  // Alt+1..4 muda de seção
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (!e.altKey) return;
      const i = Number(e.key) - 1;
      if (SECOES[i]) { e.preventDefault(); setSecao(SECOES[i].id); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);

  const iniciar = useCallback(async (serial: string, modo: string) => {
    try {
      const t = await api<Tarefa<Varredura>>("/varreduras", { corpo: { serial, modo } });
      setFluxo({ tela: "varrendo", tarefa: t, modo });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }, [avisar]);
  const aoTerminar = useCallback((v: Varredura) => setFluxo({ tela: "resultado", v }), []);
  const aoCancelar = useCallback((erro: string) => {
    avisar({ tipo: "erro", texto: erro });
    setFluxo({ tela: "conectar" });
  }, [avisar]);
  const abrirHistorico = useCallback(async (id: number) => {
    setFluxo({ tela: "resultado", v: await obterVarredura(id) });
    setSecao("varredura");
  }, []);

  const prontos = dispositivos.filter((d) => d.estado === "device");

  return (
    <div className="flex h-full">
      <a href="#conteudo" className="pular-link">Pular para o conteúdo</a>
      <nav className="flex w-60 shrink-0 flex-col border-r border-linha bg-superficie py-5" aria-label="Seções">
        <Marca />
        <ul className="mt-8 space-y-1 px-3">
          {SECOES.map((s, i) => {
            const Icone = s.icone;
            const ativo = secao === s.id;
            return (
              <li key={s.id}>
                <button onClick={() => setSecao(s.id)} aria-current={ativo ? "page" : undefined}
                  className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition ${
                    ativo ? "bg-destaque-suave font-semibold text-destaque" : "text-fraco hover:bg-superficie-2 hover:text-tinta"}`}>
                  <Icone size={17} aria-hidden /> <span className="flex-1 text-left">{s.nome}</span>
                  <kbd className="font-mono text-[10px] text-fraco">Alt {i + 1}</kbd>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="mt-auto space-y-3 px-5 text-xs text-fraco">
          <div className="space-y-1.5" aria-live="polite">
            {prontos.length === 0 ? <p>Nenhum celular conectado</p> : prontos.map((d) => (
              <p key={d.serial} className="flex items-center gap-2 text-tinta">
                <Smartphone size={14} className="text-ok" aria-hidden />
                <span className="truncate">{d.fabricante ? `${d.fabricante} ${d.modelo}` : d.serial}</span>
              </p>
            ))}
          </div>
          <p className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${online ? "bg-ok" : "pulsar bg-atencao"}`} aria-hidden />
            {online ? "Conectado ao CelScan" : "Reconectando..."}
            {estado?.offline && <span className="rounded bg-superficie-2 px-1">offline</span>}
          </p>
          <p className="font-mono">v{estado?.versao}</p>
        </div>
      </nav>

      <main id="conteudo" className="bancada flex-1 overflow-auto px-10 py-8" tabIndex={-1}>
        {erroBackend && (
          <div className="mb-4 rounded-lg border border-perigo/50 bg-perigo-suave p-3 text-sm text-perigo" role="alert">
            Não consegui falar com o CelScan ({erroBackend}). Feche e abra o programa. Se continuar, me mande o
            arquivo celscan.log da pasta .celscan\logs.
          </div>
        )}
        {secao === "resgate" && <Resgate />}
        {secao === "historico" && <Historico onAbrir={abrirHistorico} />}
        {secao === "config" && <Configuracoes />}
        {secao === "varredura" && (
          fluxo.tela === "conectar" ? <Conectar onEscolher={(serial) => setFluxo({ tela: "modo", serial })} /> :
          fluxo.tela === "modo" ? <Modo serial={fluxo.serial} onIniciar={(m) => iniciar(fluxo.serial, m)}
            onVoltar={() => setFluxo({ tela: "conectar" })} onConfig={() => setSecao("config")} /> :
          fluxo.tela === "varrendo" ? <Varrendo tarefa={fluxo.tarefa} modo={fluxo.modo} onFim={aoTerminar} onCancelado={aoCancelar} /> :
          <Resultado v={fluxo.v} onNova={() => setFluxo({ tela: "conectar" })} />
        )}
      </main>
      <Avisos />
    </div>
  );
}
