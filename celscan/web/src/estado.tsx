import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, urlWebSocket, type Dispositivo, type Estado, type Tarefa } from "./api";

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
}

const Ctx = createContext<Contexto | null>(null);

export function useApp(): Contexto {
  const c = useContext(Ctx);
  if (!c) throw new Error("fora do ProvedorApp");
  return c;
}

function aplicarTema(tema: string) {
  const escuro = tema === "escuro" || (tema === "sistema" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("escuro", escuro);
}

export function ProvedorApp({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<Estado | null>(null);
  const [online, setOnline] = useState(false);
  const [dispositivos, setDispositivos] = useState<Dispositivo[]>([]);
  const [tarefas, setTarefas] = useState<Record<string, Tarefa>>({});
  const [avisos, setAvisos] = useState<Toast[]>([]);
  const [tema, setTema] = useState(() => localStorage.getItem("celscan-tema") ?? "sistema");
  const proximo = useRef(1);

  const recarregar = useCallback(async () => {
    const e = await api<Estado>("/estado");
    setEstado(e);
    setDispositivos(e.dispositivos);
  }, []);

  // Tempo real: reconecta sozinho se a conexão cair.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let parar = false;
    let espera = 500;
    const conectar = () => {
      ws = new WebSocket(urlWebSocket());
      ws.onopen = () => {
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
          setTarefas((t) => ({ ...t, [msg.tarefa.id]: msg.tarefa }));
        } else if (msg.tipo === "progresso") {
          setTarefas((t) => (t[msg.tarefa] ? { ...t, [msg.tarefa]: { ...t[msg.tarefa], progresso: msg.evento } } : t));
        }
      };
      ws.onclose = () => {
        setOnline(false);
        if (!parar) setTimeout(conectar, (espera = Math.min(espera * 2, 5000)));
      };
    };
    conectar();
    recarregar().catch(() => undefined);
    return () => {
      parar = true;
      ws?.close();
    };
  }, [recarregar]);

  useEffect(() => {
    aplicarTema(tema);
    localStorage.setItem("celscan-tema", tema);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const ouvir = () => aplicarTema(tema);
    mq.addEventListener("change", ouvir);
    return () => mq.removeEventListener("change", ouvir);
  }, [tema]);

  const esperar = useCallback(<R,>(t: Tarefa<R>) => {
    setTarefas((ts) => ({ ...ts, [t.id]: t as Tarefa }));
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
        } catch {
          /* tenta de novo */
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
      value={{ estado, online, dispositivos, tarefas, recarregar, esperar, avisar, fecharAviso, avisos, tema, mudarTema: setTema }}
    >
      {children}
    </Ctx.Provider>
  );
}
