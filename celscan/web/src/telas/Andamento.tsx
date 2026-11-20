import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Tarefa } from "../api";
import { useApp } from "../estado";

/** Nome amigável de cada operação que roda no celular. */
export const NOMES_TAREFA: Record<string, string> = {
  turbo_analise: "Analisando o celular", turbo_receita: "Otimizando o celular", turbo_compilar: "Compilando apps",
  turbo_manutencao: "Manutenção", faxina_apps: "Removendo apps do sistema", faxina_camera: "Otimizando a câmera",
  destravar: "Destravando app", espaco: "Procurando o que ocupa espaço", apagar: "Guardando no PC e apagando",
  flagrante: "Observando o celular", varredura: "Verificando vírus", turbo_nota: "Medindo a nota",
  turbo_reset: "Desfazendo a compilação", remocao: "Removendo vírus", backup: "Fazendo backup", desfazer: "Desfazendo",
  limpeza_cache: "Limpando cache", recuperacao: "Recuperando arquivos", debloat: "Removendo apps",
  diagnostico: "Diagnóstico", otimizar_apps: "Otimizando apps", apps_esquecidos: "Fazendo apps esquecidos dormirem",
};

function tempo(s: number) {
  if (s < 60) return `${Math.max(1, Math.round(s))} s`;
  return `${Math.round(s / 60)} min`;
}

/** Barra de andamento em tempo real: etapa, detalhe, porcentagem e tempo que falta. */
export function ProgressoTarefa({ tarefa }: { tarefa: Tarefa }) {
  const p = tarefa.progresso ?? {};
  const [seg, setSeg] = useState(0);
  useEffect(() => {
    const ini = (tarefa.criada ?? Date.now() / 1000) * 1000;
    const id = window.setInterval(() => setSeg((Date.now() - ini) / 1000), 1000);
    return () => window.clearInterval(id);
  }, [tarefa.criada]);
  // a estimativa vem a cada etapa: desconta o tempo já passado nela para o "falta" andar sozinho
  const marco = useRef({ chave: "", seg: 0 });
  const chave = `${p.descricao}|${p.atual}|${p.estimativa_s}`;
  if (marco.current.chave !== chave) marco.current = { chave, seg };
  const falta = p.estimativa_s ? Math.max(0, p.estimativa_s - (seg - marco.current.seg)) : 0;
  const total = p.total ?? null;
  const atual = p.atual ?? null;
  const pct = total ? Math.min(99, Math.round(((atual ?? 0) + 0.5) / total * 100)) : null;
  return (
    <div className="andamento" role="status" aria-live="polite">
      <div className="flex items-center gap-3">
        <Loader2 size={20} className="animate-spin text-destaque" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{NOMES_TAREFA[tarefa.tipo] ?? "Trabalhando no celular"}</p>
          <p className="truncate text-sm text-fraco">{p.descricao || "Começando..."}{p.detalhe ? ` · ${p.detalhe}` : ""}</p>
        </div>
        <div className="text-right">
          {pct != null && <p className="numeros text-lg font-semibold">{pct}%</p>}
          <p className="numeros text-xs text-fraco">{tempo(seg)}{p.estimativa_s ? (falta > 0 ? ` · falta ≈ ${tempo(falta)}` : " · quase lá") : ""}</p>
        </div>
      </div>
      <div className="andamento-trilho mt-3" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? undefined}>
        {pct != null
          ? <div className="andamento-cheio" style={{ width: `${pct}%` }} />
          : <div className="andamento-cheio andamento-indeterminado" />}
      </div>
      {total != null && total > 1 && total <= 8 && (
        <ol className="mt-3 flex gap-1.5" aria-hidden>
          {Array.from({ length: total }, (_, i) => (
            <li key={i} className={`h-1 flex-1 rounded-full ${atual != null && i < atual ? "bg-ok" : atual === i ? "bg-destaque" : "bg-linha"}`} />
          ))}
        </ol>
      )}
    </div>
  );
}

/** Tudo que está rodando agora neste celular. Fica visível em qualquer aba e volta depois de trocar de tela. */
export function EmAndamento({ serial, ignorar = [] }: { serial: string; ignorar?: string[] }) {
  const { tarefas } = useApp();
  const ativas = Object.values(tarefas).filter((t) => t.serial === serial && t.estado === "executando" && !ignorar.includes(t.tipo));
  if (!ativas.length) return null;
  return <div className="space-y-3">{ativas.map((t) => <ProgressoTarefa key={t.id} tarefa={t} />)}</div>;
}

/** A tarefa mais recente de um tipo neste celular (rodando ou já terminada). */
export function useUltimaTarefa<R>(serial: string, tipo: string): Tarefa<R> | undefined {
  const { tarefas } = useApp();
  return Object.values(tarefas)
    .filter((t) => t.serial === serial && t.tipo === tipo)
    .sort((a, b) => (b.criada ?? 0) - (a.criada ?? 0))[0] as Tarefa<R> | undefined;
}
