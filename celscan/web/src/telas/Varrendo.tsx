import { Check, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Tarefa, type Varredura } from "../api";
import { useApp } from "../estado";
import { Barra, Botao, Cartao, Titulo } from "../ui";

const ETAPAS: [string, string][] = [
  ["coleta", "Lendo apps e configurações do aparelho"],
  ["iocs", "Carregando a lista de ameaças conhecidas"],
  ["hashes", "Calculando a impressão digital de cada app"],
  ["assinaturas", "Conferindo a assinatura dos apps suspeitos"],
  ["virustotal", "Consultando o VirusTotal"],
  ["analise", "Analisando e montando o resultado"],
];

const TEMPOS: Record<string, number> = { iocs: 5, hashes: 40, assinaturas: 15, analise: 2 };

function formatarTempo(s: number): string {
  if (s < 60) return `${Math.max(1, Math.round(s))} s`;
  return `${Math.round(s / 60)} min`;
}

export default function Varrendo({ tarefa, modo, onFim, onCancelado }: {
  tarefa: Tarefa<Varredura>; modo: string; onFim: (v: Varredura) => void; onCancelado: (erro: string) => void;
}) {
  const etapas = ETAPAS.filter(([k]) => k !== "virustotal" || modo === "completo");
  const { tarefas, esperar } = useApp();
  const [inicio] = useState(() => Date.now());
  const [agora, setAgora] = useState(Date.now());
  const vistas = useRef<string[]>([]);
  const retorno = useRef({ onFim, onCancelado });
  retorno.current = { onFim, onCancelado };
  const atual = tarefas[tarefa.id] ?? tarefa;
  const ev = atual.progresso ?? {};

  useEffect(() => {
    const id = setInterval(() => setAgora(Date.now()), 1000);
    esperar(tarefa).then((t) => {
      clearInterval(id);
      if (t.estado === "concluida" && t.resultado) retorno.current.onFim(t.resultado);
      else retorno.current.onCancelado(t.erro ?? "A varredura não terminou.");
    });
    return () => clearInterval(id);
  }, [tarefa, esperar]);

  if (ev.etapa && !vistas.current.includes(ev.etapa)) vistas.current.push(ev.etapa);
  const indiceAtual = etapas.findIndex(([k]) => k === ev.etapa);
  // Estimativa: o que falta da etapa atual + as etapas seguintes que costumam aparecer
  const fracao = ev.total ? (ev.atual ?? 0) / ev.total : 0;
  const restante = (ev.estimativa_s ?? 0) * (1 - fracao) +
    etapas.slice(indiceAtual + 1).reduce((soma, [k]) => soma + (TEMPOS[k] ?? 0), 0);

  return (
    <div className="max-w-3xl">
      <Titulo sub={`Não desconecte o cabo. Tempo decorrido: ${formatarTempo((agora - inicio) / 1000)}${restante > 0 ? ` · faltam cerca de ${formatarTempo(restante)}` : ""}`}>
        Verificando o celular
      </Titulo>
      <Cartao className="p-6">
        <ol className="space-y-4">
          {etapas.map(([k, texto], i) => {
            const feita = i < indiceAtual || (vistas.current.includes(k) && k !== ev.etapa);
            const agoraAqui = k === ev.etapa;
            const pulada = !feita && !agoraAqui && indiceAtual > i;
            return (
              <li key={k} className={`flex gap-3 ${!feita && !agoraAqui ? "opacity-55" : ""}`} aria-current={agoraAqui ? "step" : undefined}>
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-linha">
                  {feita || pulada ? <Check size={14} className="marcar text-ok" aria-label="concluída" /> :
                    agoraAqui ? <Loader2 size={14} className="animate-spin text-destaque" aria-label="em andamento" /> : null}
                </span>
                <div className="flex-1">
                  <p className={agoraAqui ? "font-medium" : ""}>{texto}</p>
                  {agoraAqui && (
                    <div className="mt-2 space-y-1">
                      <Barra valor={ev.atual} total={ev.total} indeterminada={!ev.total} />
                      <p className="numeros truncate font-mono text-xs text-fraco">
                        {ev.total ? `${ev.atual}/${ev.total} · ` : ""}{ev.detalhe}
                      </p>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </Cartao>
      <Botao className="mt-4" onClick={() => api(`/tarefas/${tarefa.id}/cancelar`, { corpo: {} })}>Cancelar</Botao>
    </div>
  );
}
