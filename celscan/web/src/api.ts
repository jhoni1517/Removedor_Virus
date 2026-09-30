// Comunicação com o backend local (FastAPI). O token chega na URL (?t=) e fica só nesta sessão.

export type Nivel = "ALTO" | "MÉDIO" | "BAIXO" | "OK" | "PERMITIDO";

export interface Achado {
  chave: string;
  peso: number;
  nivel: string;
  titulo: string;
  significa: string;
  fazer: string;
}

export interface AppResultado {
  pacote: string;
  score: number;
  nivel: Nivel;
  motivos: string[];
  achados: Achado[];
  ameaca: string | null;
  instalador: string | null;
  loja: string | null;
  sistema: boolean;
  versao: string | null;
  instalado: string | null;
  sha256: string | null;
  nome: string | null;
  icone: string | null;
}

export interface InfoAparelho {
  fabricante: string;
  modelo: string;
  android: string;
  patch_seguranca: string;
  serial: string;
}

export interface Varredura {
  varredura_id: number;
  modo: string;
  info: InfoAparelho;
  nota: number;
  veredito: string;
  achados: Achado[];
  resultados: AppResultado[];
  avisos: string[];
  duracao_s: number;
  data?: string;
}

export interface Dispositivo {
  serial: string;
  estado: string;
  wifi: boolean;
  fabricante?: string;
  modelo?: string;
  android?: string;
  marca?: string;
}

export interface Evento {
  etapa: string;
  descricao: string;
  detalhe: string;
  atual: number | null;
  total: number | null;
  estimativa_s: number;
}

export interface Tarefa<R = unknown> {
  id: string;
  tipo: string;
  serial: string | null;
  estado: "executando" | "concluida" | "erro" | "cancelada";
  progresso: Partial<Evento>;
  resultado: R | null;
  erro: string | null;
}

export interface Estado {
  versao: string;
  adb: boolean;
  offline: boolean;
  vt: boolean;
  modos: Record<string, string>;
  dispositivos: Dispositivo[];
  tarefas: Tarefa[];
}

export interface Remocao {
  pacote: string;
  ok: boolean;
  mensagem: string;
  quarentena_id: string | null;
}

const CHAVE = "celscan-token";

function lerToken(): string {
  const url = new URL(window.location.href);
  const t = url.searchParams.get("t");
  if (t) {
    sessionStorage.setItem(CHAVE, t);
    url.searchParams.delete("t");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
  return sessionStorage.getItem(CHAVE) ?? "";
}

export const TOKEN = lerToken();

export class ErroApi extends Error {
  status: number;
  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.status = status;
  }
}

export async function api<T>(caminho: string, opcoes: { metodo?: string; corpo?: unknown } = {}): Promise<T> {
  const r = await fetch(`/api${caminho}`, {
    method: opcoes.metodo ?? (opcoes.corpo === undefined ? "GET" : "POST"),
    headers: { "X-CelScan-Token": TOKEN, "Content-Type": "application/json" },
    body: opcoes.corpo === undefined ? undefined : JSON.stringify(opcoes.corpo),
  });
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : msg;
    } catch {
      /* resposta sem JSON */
    }
    throw new ErroApi(r.status, msg);
  }
  return r.json() as Promise<T>;
}

export function urlLaudo(varreduraId: number, versao: "cliente" | "tecnico"): string {
  return `/api/varreduras/${varreduraId}/laudo.pdf?versao=${versao}&t=${encodeURIComponent(TOKEN)}`;
}

export function urlWebSocket(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/ws?t=${encodeURIComponent(TOKEN)}`;
}

/** Varredura salva (GET /api/varreduras/{id}) no mesmo formato do resultado de uma tarefa. */
export async function obterVarredura(id: number): Promise<Varredura> {
  const v = await api<Record<string, any>>(`/varreduras/${id}`);
  return {
    varredura_id: v.id,
    modo: v.modo,
    info: v.aparelho,
    nota: v.nota,
    veredito: v.veredito,
    achados: v.achados_aparelho ?? [],
    resultados: v.apps ?? [],
    avisos: v.avisos ?? [],
    duracao_s: v.duracao_s ?? 0,
    data: v.data,
  };
}
