import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useEffect, useState } from "react";
import type { Nivel } from "./api";
import { useApp } from "./estado";
import { nomeApp } from "./nomes";

export { nomeApp };

type Variante = "primario" | "secundario" | "perigo" | "fantasma";

const VARIANTES: Record<Variante, string> = {
  primario: "bg-[image:var(--grad-destaque)] text-superficie border-transparent shadow-[var(--brilho)] hover:brightness-110",
  secundario: "bg-superficie text-tinta border-linha shadow-[var(--sombra)] hover:bg-superficie-2",
  perigo: "bg-perigo text-superficie hover:brightness-110 border-transparent",
  fantasma: "bg-transparent text-fraco border-transparent hover:text-tinta hover:bg-superficie-2",
};

export function Botao({
  variante = "secundario",
  className = "",
  children,
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-md border px-3.5 py-2 text-sm font-medium transition
        disabled:cursor-not-allowed disabled:opacity-45 ${VARIANTES[variante]} ${className}`}
      {...resto}
    >
      {children}
    </button>
  );
}

export function Cartao({ children, className = "", id }: { children: ReactNode; className?: string; id?: string }) {
  return <section id={id} className={`cartao realce rounded-xl border border-linha bg-superficie shadow-[var(--sombra)] ${className}`}>{children}</section>;
}

/** Miniatura do celular conectado: moldura desenhada (sem internet) com a marca e o modelo na tela. */
export function Miniatura({ fabricante, modelo, wifi = false, tamanho = "md" }:
  { fabricante?: string; modelo?: string; wifi?: boolean; tamanho?: "md" | "lg" }) {
  const dim = tamanho === "lg" ? "h-36 w-[4.5rem]" : "h-24 w-12";
  const marca = (fabricante || "Android").trim();
  return (
    <div className={`relative shrink-0 ${dim} rounded-[0.9rem] border-2 border-zinc-600 bg-zinc-900 p-[3px] shadow-sm`}
      role="img" aria-label={`Celular ${marca} ${modelo ?? ""}`.trim()}>
      <div className="flex h-full w-full flex-col items-center justify-center overflow-hidden rounded-[0.65rem] bg-superficie-2 bg-gradient-to-b from-destaque/30 to-transparent px-0.5 text-center">
        <span className="absolute top-[5px] h-[3px] w-3 rounded-full bg-zinc-500" aria-hidden />
        <span className={`font-semibold leading-tight text-tinta ${tamanho === "lg" ? "text-xs" : "text-[0.55rem]"}`}>{marca}</span>
        {modelo && <span className={`mt-0.5 line-clamp-2 leading-tight text-fraco ${tamanho === "lg" ? "text-[0.6rem]" : "text-[0.45rem]"}`}>{modelo}</span>}
      </div>
      <span className={`absolute -right-1 -top-1 h-3 w-3 rounded-full border-2 border-superficie ${wifi ? "bg-destaque" : "bg-ok"}`}
        title={wifi ? "Conectado por Wi-Fi" : "Conectado por USB"} aria-hidden />
    </div>
  );
}

const COR_NIVEL: Record<string, string> = {
  ALTO: "bg-perigo-suave text-perigo border-perigo/30",
  "MÉDIO": "bg-atencao-suave text-atencao border-atencao/30",
  BAIXO: "bg-superficie-2 text-fraco border-linha",
  OK: "bg-ok-suave text-ok border-ok/30",
  PERMITIDO: "bg-ok-suave text-ok border-ok/30",
};
const NOME_NIVEL: Record<string, string> = { ALTO: "Alto", "MÉDIO": "Médio", BAIXO: "Baixo", OK: "Sem alertas", PERMITIDO: "Confiável" };

export function Selo({ nivel }: { nivel: Nivel | string }) {
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${COR_NIVEL[nivel] ?? COR_NIVEL.BAIXO}`}>
      {NOME_NIVEL[nivel] ?? nivel}
    </span>
  );
}

export function corNota(n: number): string {
  return n >= 70 ? "var(--ok)" : n >= 50 ? "var(--atencao)" : "var(--perigo)";
}

/** Nota grande com medidor em arco. */
export function Medidor({ nota, veredito }: { nota: number; veredito: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const [valor, setValor] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setValor(nota));
    return () => cancelAnimationFrame(id);
  }, [nota]);
  const cor = corNota(nota);
  const gid = `g-medidor-${Math.round(nota)}`;
  return (
    <div className="relative h-36 w-36 shrink-0" role="img" aria-label={`Nota ${nota} de 100: ${veredito}`}>
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={cor} stopOpacity="0.65" />
            <stop offset="100%" stopColor={cor} />
          </linearGradient>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--linha)" strokeWidth="9" />
        <circle
          cx="60" cy="60" r={r} fill="none" stroke={`url(#${gid})`} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - valor / 100)}
          style={{ transition: "stroke-dashoffset 0.9s ease-out", filter: `drop-shadow(0 0 5px ${cor}66)` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="numeros font-mono text-4xl font-semibold" style={{ color: cor }}>{nota}</span>
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: cor }}>{veredito}</span>
      </div>
    </div>
  );
}

export function Barra({ valor, total, indeterminada = false }: { valor?: number | null; total?: number | null; indeterminada?: boolean }) {
  const pct = !indeterminada && total ? Math.min(100, ((valor ?? 0) / total) * 100) : 0;
  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-linha" role="progressbar"
      aria-valuemin={0} aria-valuemax={total ?? undefined} aria-valuenow={indeterminada ? undefined : valor ?? undefined}>
      {indeterminada || !total ? (
        <div className="varrer absolute inset-y-0 w-1/3 rounded-full bg-destaque" />
      ) : (
        <div className="h-full rounded-full bg-destaque transition-[width] duration-300" style={{ width: `${pct}%` }} />
      )}
    </div>
  );
}

export function Titulo({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">{children}</h1>
      {sub && <p className="mt-1 text-fraco">{sub}</p>}
    </header>
  );
}

export function Avisos() {
  const { avisos, fecharAviso } = useApp();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
      {avisos.map((t) => (
        <div key={t.id} className={`entrar pointer-events-auto rounded-lg border bg-superficie p-3 shadow-lg ${
          t.tipo === "erro" ? "border-perigo/50" : t.tipo === "ok" ? "border-ok/40" : "border-linha"}`}>
          <div className="flex items-start gap-3">
            <p className="flex-1 text-sm">{t.texto}</p>
            {t.acao && (
              <Botao variante="secundario" className="py-1" onClick={() => { t.acao!.executar(); fecharAviso(t.id); }}>
                {t.acao.rotulo}
              </Botao>
            )}
            <button className="text-fraco hover:text-tinta" aria-label="Fechar aviso" onClick={() => fecharAviso(t.id)}>×</button>
          </div>
          {t.acao && (
            <div className="mt-2 h-0.5 overflow-hidden rounded bg-linha">
              <div className="h-full bg-destaque" style={{ animation: `esvaziar ${t.duracao}ms linear forwards` }} />
            </div>
          )}
        </div>
      ))}
      <style>{"@keyframes esvaziar{from{width:100%}to{width:0}}"}</style>
    </div>
  );
}

export function Vazio({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-linha p-6 text-center text-fraco">{children}</p>;
}

/** Ícone real do app (PNG/WebP/SVG); sem ícone (ou se a imagem falhar), uma inicial com cor estável por pacote. */
export function IconeApp({ nome, pacote, icone, tamanho = 40 }: { nome?: string | null; pacote: string; icone?: string | null; tamanho?: number }) {
  const [falhou, setFalhou] = useState(false);
  const matiz = [...pacote].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  const mostrar = icone && !falhou;
  return (
    <span className="icone-app grid shrink-0 place-items-center overflow-hidden" aria-hidden
      style={{ width: tamanho, height: tamanho, background: mostrar ? "transparent" : `hsl(${matiz} 38% 42%)` }}>
      {mostrar ? <img src={icone} alt="" className="h-full w-full object-contain" loading="lazy" onError={() => setFalhou(true)} />
        : <span className="font-bold text-white" style={{ fontSize: tamanho * 0.45 }}>{(nome || pacote)[0]?.toUpperCase()}</span>}
    </span>
  );
}

/** "há 3 dias" (com a data exata para o title). */
export function dataRelativa(iso?: string | null): { texto: string; exata: string } {
  if (!iso) return { texto: "—", exata: "" };
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return { texto: "—", exata: "" };
  const dias = Math.floor((Date.now() - d.getTime()) / 86400000);
  const texto = dias < 0 ? dataBr(iso) : dias === 0 ? "hoje" : dias === 1 ? "ontem" : dias < 31 ? `há ${dias} dias`
    : dias < 365 ? `há ${Math.floor(dias / 30)} mês(es)` : `há ${Math.floor(dias / 365)} ano(s)`;
  return { texto, exata: dataBr(iso, true) };
}

export function Data({ iso }: { iso?: string | null }) {
  const r = dataRelativa(iso);
  return <time dateTime={iso ?? undefined} title={r.exata}>{r.texto}</time>;
}

export function tamanhoLegivel(bytes?: number | null): string {
  if (!bytes) return "—";
  return bytes >= 1073741824 ? `${(bytes / 1073741824).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1048576))} MB`;
}

/** Data ISO -> Date; "AAAA-MM-DD" vira meia-noite LOCAL (new Date("2026-10-10") seria UTC e cairia no dia anterior no Brasil). */
export function lerData(iso?: string | null): Date | null {
  if (!iso) return null;
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function recente(iso?: string | null, dias = 7): boolean {
  if (!iso) return false;
  const d = lerData(iso) ?? new Date(NaN);
  return !Number.isNaN(d.getTime()) && Date.now() - d.getTime() < dias * 86400000;
}


export function dataBr(iso?: string | null, hora = false): string {
  if (!iso) return "—";
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR") + (hora ? ` ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}` : "");
}

export function quando(seg?: number | null): string {
  if (seg == null) return "—";
  if (seg < 120) return "agora há pouco";
  if (seg < 3600) return `há ${Math.floor(seg / 60)} min`;
  if (seg < 86400) return `há ${Math.floor(seg / 3600)} h`;
  return `há ${Math.floor(seg / 86400)} dia(s)`;
}

/** Raio-X: a tela do celular desenhada com os ícones reais; os perigosos ganham anel e selo. */
export function RaioX({ apps, aoEscolher, removidos = new Set<string>() }: {
  apps: { pacote: string; nome: string | null; icone: string | null; nivel: string; score: number; sistema: boolean; motivos?: string[] }[];
  aoEscolher?: (pacote: string) => void; removidos?: Set<string>;
}) {
  const todos = [...apps].filter((a) => !a.sistema).sort((a, b) => b.score - a.score || nomeApp(a).localeCompare(nomeApp(b), "pt-BR"));
  const lista = todos.slice(0, 24);
  const resto = todos.length - lista.length;
  const vermelhos = lista.filter((a) => a.nivel === "ALTO" && !removidos.has(a.pacote)).length;
  const hora = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return (
    <figure className="raio-x" aria-label="Raio-X dos apps do celular">
      <div className="raio-x-tela">
        <p className="raio-x-hora numeros">{hora}</p>
        <p className="raio-x-legenda">{vermelhos ? `${vermelhos} app(s) em vermelho` : "Nenhum app em vermelho"}</p>
        <ul className="raio-x-grade">
          {lista.map((a) => (
            <li key={a.pacote}>
              <button type="button" onClick={() => aoEscolher?.(a.pacote)} data-nivel={a.nivel}
                className={removidos.has(a.pacote) ? "removido" : ""}
                title={`${nomeApp(a)}: risco ${a.score}${a.motivos?.[0] ? `\n${a.motivos[0]}` : ""}`}
                aria-label={`${nomeApp(a)}, risco ${a.score}${removidos.has(a.pacote) ? ", removido" : ""}`}>
                <span className="relative">
                  <IconeApp nome={a.nome} pacote={a.pacote} icone={a.icone} tamanho={46} />
                  {(a.nivel === "ALTO" || a.nivel === "MÉDIO") && !removidos.has(a.pacote) &&
                    <i className={`raio-x-selo ${a.nivel === "MÉDIO" ? "medio" : ""}`}>{a.score}</i>}
                </span>
                <span className="raio-x-nome">{nomeApp(a)}</span>
              </button>
            </li>
          ))}
          {resto > 0 && <li className="raio-x-mais" aria-label={`e mais ${resto} apps sem alerta`}><span>+{resto}</span></li>}
        </ul>
      </div>
      <figcaption>
        <span className="raio-x-legenda-cores"><i className="alto" /> risco alto <i className="medio" /> médio</span>
        {todos.length} apps analisados. Toque num ícone para ver os detalhes.
      </figcaption>
    </figure>
  );
}

/** 5400 -> "1 h 30 min"; 300 -> "5 min". */
export function duracaoCurta(s: number): string {
  if (s < 60) return "menos de 1 min";
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
}
