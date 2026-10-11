import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, urlWebSocket, type Dispositivo, type Estado, type Tarefa } from "./api";
import { aplicarModelo, aplicarTema } from "./tema";
import { ErroApi } from "./api";

// localStorage pode lançar exceção (WebView com armazenamento bloqueado): antes isso deixava a tela em branco
/** Guarda só as últimas tarefas: cada varredura traz o retrato inteiro (com ícones) e, num dia de balcão,
 * a memória da aba crescia sem parar. As que ainda estão rodando nunca saem. */
const MAX_TAREFAS = 30;
function limitar(t: Record<string, Tarefa>): Record<string, Tarefa> {
  const ids = Object.keys(t);
  if (ids.length <= MAX_TAREFAS) return t;
  const sobra = ids.length - MAX_TAREFAS;
  const fora = new Set(ids.filter((id) => t[id].estado !== "executando").slice(0, sobra));
  return Object.fromEntries(Object.entries(t).filter(([id]) => !fora.has(id)));
}

export function lerLocal(chave: string): string | null {
  try { return localStorage.getItem(chave); } catch { return null; }
}
export function gravarLocal(chave: string, valor: string): void {
  try { localStorage.setItem(chave, valor); } catch { /* sem armazenamento: só não lembra */ }
}

export interface Toast {
  id: number;
  texto: string;
  tipo: "ok" | "erro" | "info";
  acao?: { rotulo: string; executar: () => void };
  duracao: number; // ms
}

interface Contexto {
  estado: Estado | null;
  online: boolean;
  dispositivos: Dispositivo[];
  tarefas: Record<string, Tarefa>;
  recarregar: () => Promise<void>;
  esperar: <R>(t: Tarefa<R>) => Promise<Tarefa<R>>;
  avisar: (t: Omit<Toast, "id" | "duracao"> & { duracao?: number }) => void;
  fecharAviso: (id: number) => void;
  avisos: Toast[];
  tema: string;
  mudarTema: (t: string) => void;
  escala: number;
  mudarEscala: (e: number) => void;
  modelo: string;
  mudarModelo: (m: string) => void;
  erroBackend: string | null;
}

const Ctx = createContext<Contexto | null>(null);

export function useApp(): Contexto {
  const c = useContext(Ctx);
  if (!c) throw new Error("fora do ProvedorApp");
  return c;
}

export function ProvedorApp({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<Estado | null>(null);
  const [online, setOnline] = useState(false);
  const [dispositivos, setDispositivos] = useState<Dispositivo[]>([]);
  const [tarefas, setTarefas] = useState<Record<string, Tarefa>>({});
  const [avisos, setAvisos] = useState<Toast[]>([]);
  const [tema, setTema] = useState(() => lerLocal("celscan-tema") ?? "sistema");
  const [escala, setEscala] = useState(() => Number(lerLocal("celscan-escala")) || 1);
  const [modelo, setModelo] = useState(() => lerLocal("celscan-modelo") ?? "estudio");
  const proximo = useRef(1);

  const [erroBackend, setErroBackend] = useState<string | null>(null);

  const wsAberto = useRef(false);

  const recarregar = useCallback(async () => {
    try {
      const e = await api<Estado>("/estado");
      setEstado(e);
      setDispositivos(e.dispositivos);
      setErroBackend(null);
      // O WebSocket é só um atalho de tempo real; se o polling responde, o programa está conectado.
      setOnline(true);
    } catch (e) {
      setErroBackend((e as Error).message);
      if (!wsAberto.current) setOnline(false);
      throw e;
    }
  }, []);

  // Tempo real: reconecta sozinho se a conexão cair. Se o WebSocket não subir (ex.: certos WebView2),
  // o polling de 3s abaixo mantém a interface viva e o status verde.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let parar = false;
    let espera = 500;
    const conectar = () => {
      if (parar) return; // a reconexão agendada podia abrir um WebSocket novo depois de a tela fechar
      try {
        ws = new WebSocket(urlWebSocket());
      } catch {
        return; // sem WebSocket: o polling assume
      }
      ws.onopen = () => {
        wsAberto.current = true;
        setOnline(true);
        espera = 500;
      };
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.tipo === "estado") {
          setEstado(msg);
          setDispositivos(msg.dispositivos);
        } else if (msg.tipo === "dispositivos") {
          setDispositivos(msg.dispositivos);
        } else if (msg.tipo === "tarefa") {
          setTarefas((t) => limitar({ ...t, [msg.tarefa.id]: msg.tarefa }));
        } else if (msg.tipo === "progresso") {
          setTarefas((t) => (t[msg.tarefa] ? { ...t, [msg.tarefa]: { ...t[msg.tarefa], progresso: msg.evento } } : t));
        }
      };
      ws.onclose = () => {
        wsAberto.current = false;
        if (!parar) setTimeout(conectar, (espera = Math.min(espera * 2, 5000)));
      };
    };
    conectar();
    recarregar().catch(() => undefined);
    // Rede de segurança: mesmo que uma mensagem do WebSocket se perca, o estado se atualiza sozinho.
    const timer = setInterval(() => recarregar().catch(() => undefined), 3000);
    return () => {
      parar = true;
      clearInterval(timer);
      ws?.close();
    };
  }, [recarregar]);

  useEffect(() => {
    aplicarTema(tema, escala);
    gravarLocal("celscan-tema", tema);
    gravarLocal("celscan-escala", String(escala));
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const ouvir = () => aplicarTema(tema, escala);
    mq.addEventListener("change", ouvir);
    return () => mq.removeEventListener("change", ouvir);
  }, [tema, escala]);

  useEffect(() => {
    aplicarModelo(modelo);
    gravarLocal("celscan-modelo", modelo);
  }, [modelo]);

  const esperar = useCallback(<R,>(t: Tarefa<R>) => {
    setTarefas((ts) => limitar({ ...ts, [t.id]: t as Tarefa }));
    // Consulta periódica como garantia, caso alguma mensagem do WebSocket se perca.
    return new Promise<Tarefa<R>>((resolver) => {
      const checar = async () => {
        try {
          const atual = await api<Tarefa<R>>(`/tarefas/${t.id}`);
          if (atual.estado !== "executando") {
            setTarefas((ts) => ({ ...ts, [t.id]: atual as Tarefa }));
            resolver(atual);
            return;
          }
        } catch (e) {
          // tarefa sumiu (o CelScan foi reiniciado): antes a tela ficava em "Removendo..." para sempre
          if (e instanceof ErroApi && e.status === 404) {
            resolver({ ...t, estado: "erro", erro: "A operação foi interrompida (o CelScan foi reiniciado). "
              + "Confira o Histórico antes de repetir." });
            return;
          }
        }
        setTimeout(checar, 800);
      };
      setTimeout(checar, 400);
    });
  }, []);

  const fecharAviso = useCallback((id: number) => setAvisos((a) => a.filter((x) => x.id !== id)), []);
  const avisar = useCallback<Contexto["avisar"]>(
    (t) => {
      const id = proximo.current++;
      const duracao = t.duracao ?? (t.tipo === "erro" ? 8000 : 5000);
      setAvisos((a) => [...a, { ...t, id, duracao }]);
      setTimeout(() => fecharAviso(id), duracao);
    },
    [fecharAviso],
  );

  return (
    <Ctx.Provider
      value={{ estado, online, dispositivos, tarefas, recarregar, esperar, avisar, fecharAviso, avisos, tema, mudarTema: setTema, escala, mudarEscala: setEscala, modelo, mudarModelo: setModelo, erroBackend }}
    >
      {children}
    </Ctx.Provider>
  );
}
