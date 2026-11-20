import { Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Evento, type Tarefa, type Varredura } from "../api";
import { useApp } from "../estado";
import { Botao } from "../ui";

/* Etapas na ordem em que o CelScan roda (celscan/servicos.py), com o peso de tempo de cada uma.
   O peso faz a porcentagem andar no ritmo real: antes cada etapa valia o mesmo e a barra pulava. */
const ETAPAS: { id: string; nome: string; fala: string; peso: number }[] = [
  { id: "coleta", nome: "Lista de apps e configurações", peso: 25,
    fala: "Estou lendo a lista de apps e as configurações. Deixe o cabo parado aí." },
  { id: "iocs", nome: "Ameaças conhecidas", peso: 4,
    fala: "Conferindo a lista pública de vírus e espiões conhecidos." },
  { id: "hashes", nome: "Impressão digital de cada app", peso: 30,
    fala: "Tirando a impressão digital de cada app para comparar com as ameaças." },
  { id: "rotulos", nome: "Nome, ícone e assinatura", peso: 20,
    fala: "Lendo o nome, o ícone e quem assinou cada app." },
  { id: "motor", nome: "Código dos apps por dentro", peso: 35,
    fala: "Agora leio o código dos apps por dentro, atrás de vírus escondidos. É a parte que mais demora." },
  { id: "virustotal", nome: "Segunda opinião (VirusTotal)", peso: 20,
    fala: "Pedindo uma segunda opinião ao VirusTotal sobre os suspeitos." },
  { id: "analise", nome: "Montando o resultado", peso: 3,
    fala: "Juntando tudo para mostrar o resultado. Só mais um instante." },
];

function etapasDo(modo: string, vt: boolean) {
  return ETAPAS.filter((e) => e.id !== "virustotal" || (modo === "completo" && vt));
}

/** Porcentagem honesta: soma o peso das etapas concluídas e a fração da etapa atual. */
export function porcentagem(ev: Partial<Evento>, modo: string, vt: boolean, desdeEtapaS = 0): number {
  const etapas = etapasDo(modo, vt);
  const total = etapas.reduce((s, e) => s + e.peso, 0);
  const i = etapas.findIndex((e) => e.id === ev.etapa);
  if (i < 0) return 0;
  const feito = etapas.slice(0, i).reduce((s, e) => s + e.peso, 0);
  // sem contagem (ex.: lendo a lista), avança pelo tempo estimado, sem passar de 90% da etapa
  const fracao = ev.total ? (ev.atual ?? 0) / ev.total
    : ev.estimativa_s ? Math.min(0.9, desdeEtapaS / ev.estimativa_s) : 0.3;
  return Math.min(99, Math.round(((feito + etapas[i].peso * fracao) / total) * 100));
}

function tempo(s: number): string {
  if (s < 60) return `${Math.max(1, Math.round(s))} s`;
  const m = Math.floor(s / 60);
  return `${m} min${s % 60 >= 15 && m < 10 ? ` ${Math.round(s % 60)} s` : ""}`;
}

/* Personagem original do CelScan: um celular com lupa, que pede para esperar. */
export function Lupi({ falando }: { falando: string }) {
  return (
    <div className="lupi" role="img" aria-label="Personagem do CelScan segurando uma lupa">
      <svg viewBox="0 0 220 220" className="lupi-desenho" aria-hidden>
        <ellipse cx="104" cy="206" rx="54" ry="7" className="lupi-sombra" />
        <g className="lupi-corpo">
          <rect x="58" y="34" width="96" height="164" rx="20" className="lupi-casca" />
          <rect x="66" y="48" width="80" height="128" rx="10" className="lupi-tela" />
          <rect x="94" y="40" width="24" height="4" rx="2" className="lupi-detalhe" />
          <g className="lupi-olhos">
            <ellipse cx="90" cy="100" rx="8" ry="10" className="lupi-olho" />
            <ellipse cx="122" cy="100" rx="8" ry="10" className="lupi-olho" />
            <circle cx="92" cy="97" r="3" className="lupi-brilho" />
            <circle cx="124" cy="97" r="3" className="lupi-brilho" />
          </g>
          <path d="M94 128 q12 9 24 0" className="lupi-boca" />
          <path d="M60 150 q-22 6 -26 -16" className="lupi-braco" />
        </g>
        <g className="lupi-lupa">
          <line x1="176" y1="120" x2="200" y2="148" className="lupi-cabo" />
          <circle cx="160" cy="102" r="24" className="lupi-lente" />
          <circle cx="160" cy="102" r="24" className="lupi-aro" />
          <path d="M150 92 a14 14 0 0 1 14 -6" className="lupi-reflexo" />
          <path d="M152 150 q2 -16 12 -24" className="lupi-braco" />
        </g>
      </svg>
      <p className="lupi-balao" aria-live="polite">{falando}</p>
    </div>
  );
}

export default function Varrendo({ tarefa, modo, onFim, onCancelado }: {
  tarefa: Tarefa<Varredura>; modo: string; onFim: (v: Varredura) => void; onCancelado: (erro: string) => void;
}) {
  const { tarefas, esperar, estado } = useApp();
  const vt = !!estado?.vt;
  const etapas = etapasDo(modo, vt);
  // o começo vem da própria tarefa: sair da tela e voltar não zera o tempo nem as etapas
  const inicio = (tarefa.criada ? tarefa.criada * 1000 : 0) || Date.now();
  const [agora, setAgora] = useState(Date.now());
  const retorno = useRef({ onFim, onCancelado });
  retorno.current = { onFim, onCancelado };
  const atual = tarefas[tarefa.id] ?? tarefa;
  const ev = atual.progresso ?? {};
  const mudouEtapa = useRef<{ etapa?: string; em: number }>({ em: Date.now() });
  if (mudouEtapa.current.etapa !== ev.etapa) mudouEtapa.current = { etapa: ev.etapa, em: Date.now() };
  const maximo = useRef(0); // a barra nunca volta para trás

  useEffect(() => {
    const id = setInterval(() => setAgora(Date.now()), 1000);
    esperar(tarefa).then((t) => {
      clearInterval(id);
      if (t.estado === "concluida" && t.resultado) retorno.current.onFim(t.resultado);
      else retorno.current.onCancelado(t.erro ?? "A verificação não terminou.");
    });
    return () => clearInterval(id);
  }, [tarefa, esperar]);

  const pct = (maximo.current = Math.max(maximo.current,
    porcentagem(ev, modo, vt, (agora - mudouEtapa.current.em) / 1000)));
  useEffect(() => {
    const antes = document.title;
    document.title = `${pct}% verificando o celular · CelScan`;
    return () => { document.title = antes; };
  }, [pct]);

  const i = Math.max(0, etapas.findIndex((e) => e.id === ev.etapa));
  const decorrido = (agora - inicio) / 1000;
  const restante = pct > 3 ? (decorrido / pct) * (100 - pct) : null;
  const etapa = etapas[i];
  return (
    <section className="varrendo" aria-labelledby="varrendo-titulo">
      <Lupi falando={etapa.fala} />
      <h1 id="varrendo-titulo" className="varrendo-titulo">Verificando o celular</h1>
      <p className="varrendo-sub">
        {tempo(decorrido)} até agora{restante != null ? `, falta mais ou menos ${tempo(restante)}` : ""}. Não tire o cabo.
      </p>

      <div className="medidor" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        aria-label="Andamento da verificação">
        <span className="medidor-numero numeros">{pct}<small>%</small></span>
        <div className="medidor-trilho"><div className="medidor-cheio" style={{ width: `${pct}%` }} /></div>
        <p className="medidor-detalhe numeros">
          {ev.total ? `${ev.atual ?? 0} de ${ev.total} apps` : etapa.nome}
          {ev.detalhe && ev.total ? <span className="medidor-app"> · {ev.detalhe}</span> : null}
        </p>
      </div>

      <ol className="etapas-lista">
        {etapas.map((e, k) => (
          <li key={e.id} data-estado={k < i ? "feita" : k === i ? "agora" : "depois"} aria-current={k === i ? "step" : undefined}>
            <span className="etapas-marca" aria-hidden>{k < i ? <Check size={13} strokeWidth={3} /> : k + 1}</span>
            {e.nome}
          </li>
        ))}
      </ol>

      <Botao variante="fantasma" className="mt-6" onClick={() => api(`/tarefas/${tarefa.id}/cancelar`, { corpo: {} })}>
        Cancelar verificação
      </Botao>
    </section>
  );
}
