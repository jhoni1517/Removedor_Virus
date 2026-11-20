import { Activity } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Botao } from "../ui";

interface Amostra { t: number; app: string | null; termico: number | null; cpu_c: number | null; bateria_c: number | null; nucleos: { grupo: string; mhz: number; max_mhz: number; pct: number }[]; quadros: number | null; travados: number | null }
interface Ponto { t: number; temp: number | null; fps: number | null; jank: number | null; cpu: number | null }

const MAX = 90; // ~3 min com uma leitura a cada 2 s

function Linha({ pontos, campo, min, max, cor, rotulo, unidade }: { pontos: Ponto[]; campo: keyof Ponto; min: number; max: number; cor: string; rotulo: string; unidade: string }) {
  const L = 300, A = 60;
  const val = pontos.map((p) => p[campo] as number | null);
  const ult = [...val].reverse().find((v) => v != null);
  const d = val.map((v, i) => v == null ? null : `${(i / (MAX - 1)) * L},${A - ((Math.min(max, Math.max(min, v)) - min) / (max - min)) * A}`)
    .filter(Boolean).join(" ");
  return (
    <div>
      <div className="flex justify-between text-xs"><span className="text-fraco">{rotulo}</span><span className="numeros font-semibold">{ult != null ? `${Math.round(ult)}${unidade}` : "—"}</span></div>
      <svg viewBox={`0 0 ${L} ${A}`} className="h-14 w-full" preserveAspectRatio="none" role="img" aria-label={rotulo}>
        <line x1="0" y1={A} x2={L} y2={A} stroke="var(--linha)" />
        {d && <polyline points={d} fill="none" stroke={cor} strokeWidth="2" vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
  );
}

/** Lê o celular a cada 2 s durante o jogo: temperatura, uso dos núcleos, FPS e quadros travados. */
export function MonitorJogo({ serial, pacote }: { serial: string; pacote: string }) {
  const [ligado, setLigado] = useState(false);
  const [pontos, setPontos] = useState<Ponto[]>([]);
  const [ultima, setUltima] = useState<Amostra | null>(null);
  const [erro, setErro] = useState("");
  const anterior = useRef<Amostra | null>(null);

  useEffect(() => {
    if (!ligado) return;
    let vivo = true;
    async function ler() {
      try {
        const a = await api<Amostra>(`/turbo/monitor?serial=${encodeURIComponent(serial)}${pacote ? `&pacote=${encodeURIComponent(pacote)}` : ""}`);
        if (!vivo) return;
        const p = anterior.current;
        let fps: number | null = null, jank: number | null = null;
        if (p && a.quadros != null && p.quadros != null && a.quadros >= p.quadros && a.t > p.t) {
          const q = a.quadros - p.quadros;
          fps = q / (a.t - p.t);
          jank = q > 0 && a.travados != null && p.travados != null ? (100 * (a.travados - p.travados)) / q : null;
        }
        const cpu = a.nucleos.length ? Math.max(...a.nucleos.map((n) => n.pct)) : null;
        anterior.current = a;
        setUltima(a); setErro("");
        setPontos((ps) => [...ps, { t: a.t, temp: a.cpu_c ?? a.bateria_c, fps, jank, cpu }].slice(-MAX));
      } catch (e) { if (vivo) setErro((e as Error).message); }
    }
    ler();
    const id = window.setInterval(ler, 2000);
    return () => { vivo = false; window.clearInterval(id); };
  }, [ligado, serial, pacote]);

  const semQuadros = pontos.length > 4 && pontos.every((p) => !p.fps);
  return (
    <div className="mt-4 rounded-md border border-linha p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold"><Activity size={16} aria-hidden /> Monitor ao vivo</p>
        <Botao onClick={() => { if (!ligado) { setPontos([]); anterior.current = null; } setLigado(!ligado); }}>{ligado ? "Parar" : "Ligar e abrir o jogo"}</Botao>
      </div>
      {ligado && <p className="mt-1 text-xs text-fraco">Jogue normalmente. {ultima?.app ? `App na frente: ${ultima.app}.` : ""}{ultima?.termico != null && ultima.termico >= 3 ? " O celular está segurando o processador pelo calor." : ""}</p>}
      {erro && <p className="mt-1 text-xs text-perigo">{erro}</p>}
      {pontos.length > 0 && (
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <Linha pontos={pontos} campo="temp" min={25} max={55} cor="var(--perigo)" rotulo="Temperatura" unidade=" °C" />
          <Linha pontos={pontos} campo="cpu" min={0} max={100} cor="var(--acao)" rotulo="Núcleo mais rápido (% do máximo)" unidade="%" />
          {!semQuadros && <Linha pontos={pontos} campo="fps" min={0} max={120} cor="var(--ok)" rotulo="Quadros por segundo" unidade=" fps" />}
          {!semQuadros && <Linha pontos={pontos} campo="jank" min={0} max={50} cor="var(--atencao)" rotulo="Quadros travados" unidade="%" />}
        </div>
      )}
      {semQuadros && <p className="mt-2 text-xs text-fraco">Este jogo desenha direto na tela (Unity/Unreal) e não informa os quadros ao Android: aparecem só temperatura e processador.</p>}
    </div>
  );
}
