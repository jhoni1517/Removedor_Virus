import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useEffect, useState } from "react";
import type { Nivel } from "./api";
import { useApp } from "./estado";

type Variante = "primario" | "secundario" | "perigo" | "fantasma";

const VARIANTES: Record<Variante, string> = {
  primario: "bg-destaque text-superficie hover:brightness-110 border-transparent",
  secundario: "bg-superficie text-tinta border-linha hover:bg-superficie-2",
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

export function Cartao({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-lg border border-linha bg-superficie ${className}`}>{children}</section>;
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
  return (
    <div className="relative h-36 w-36 shrink-0" role="img" aria-label={`Nota ${nota} de 100: ${veredito}`}>
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--linha)" strokeWidth="9" />
        <circle
          cx="60" cy="60" r={r} fill="none" stroke={corNota(nota)} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - valor / 100)}
          style={{ transition: "stroke-dashoffset 0.9s ease-out" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="numeros font-mono text-4xl font-semibold" style={{ color: corNota(nota) }}>{nota}</span>
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: corNota(nota) }}>{veredito}</span>
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
