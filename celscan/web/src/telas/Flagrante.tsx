import { Eye } from "lucide-react";
import { useState } from "react";
import { api, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Barra, Botao, Cartao } from "../ui";

interface AppFlagra { pacote: string; nivel: "ALTO" | "MÉDIO" | "BAIXO"; motivos: string[]; anuncio_fora: number; rede_fundo_pct: number }
interface Flagra { amostras: number; rede_disponivel: boolean; eventos: { t: number; pacote: string; texto: string }[]; apps: AppFlagra[] }

const DURACOES: [number, string][] = [[60, "1 min"], [120, "2 min"], [300, "5 min"]];

/** Observa o celular em uso e aponta quem mostra anúncio do nada, desenha por cima ou usa a internet escondido. */
export function PainelFlagrante({ serial }: { serial: string }) {
  const { esperar, avisar, tarefas } = useApp();
  const [duracao, setDuracao] = useState(120);
  const [tarefa, setTarefa] = useState<string | null>(null);
  const [r, setR] = useState<Flagra | null>(null);
  const prog = tarefa ? tarefas[tarefa]?.progresso : undefined;

  async function iniciar() {
    setR(null);
    try {
      const t = await api<Tarefa<Flagra>>("/flagrante", { corpo: { serial, duracao_s: duracao } });
      setTarefa(t.id);
      const fim = await esperar(t);
      if (fim.estado === "erro") throw new Error(fim.erro ?? "Falhou.");
      setR(fim.resultado);
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setTarefa(null); }
  }
  async function parar() {
    if (tarefa) await api(`/tarefas/${tarefa}/cancelar`, { corpo: {} }).catch(() => undefined);
  }

  return (
    <Cartao className="p-5">
      <h2 className="flex items-center gap-2 font-semibold"><Eye size={18} aria-hidden /> Pegar no flagra</h2>
      <p className="mt-1 text-sm text-fraco">
        Para o anúncio que aparece do nada. Inicie e use o celular normalmente (abra apps, volte à tela inicial, espere o anúncio aparecer).
        O CelScan anota de qual app é cada anúncio e quem usa a internet escondido.
      </p>
      {!tarefa && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {DURACOES.map(([s, n]) => (
            <button key={s} onClick={() => setDuracao(s)} className={`rounded-full border px-3 py-1 text-sm ${duracao === s ? "border-ok bg-ok-suave text-ok" : "border-linha"}`}>{n}</button>
          ))}
          <Botao variante="primario" onClick={iniciar}>Começar a observar</Botao>
        </div>
      )}
      {tarefa && (
        <div className="mt-3">
          <p className="text-sm">{prog?.detalhe ?? "Observando..."}</p>
          <Barra valor={prog?.atual ?? 0} total={prog?.total ?? null} indeterminada={!prog?.total} />
          <Botao className="mt-2" onClick={parar}>Parar e ver o resultado</Botao>
        </div>
      )}
      {r && (
        <div className="mt-4 text-sm">
          {r.apps.length === 0 ? <p className="text-ok">Nada suspeito nos {r.amostras} momentos observados.</p> : (
            <ul className="divide-y divide-linha">
              {r.apps.map((a) => (
                <li key={a.pacote} className="py-2">
                  <span className={`mr-2 font-semibold ${a.nivel === "ALTO" ? "text-perigo" : a.nivel === "MÉDIO" ? "text-atencao" : "text-fraco"}`}>{a.nivel}</span>
                  <span className="font-mono">{a.pacote}</span>
                  <span className="block text-fraco">{a.motivos.join("; ")}</span>
                </li>
              ))}
            </ul>
          )}
          {!r.rede_disponivel && <p className="mt-2 text-fraco">Este Android não deixa ler as conexões de internet; só anúncios e sobreposições foram observados.</p>}
          {r.apps.some((a) => a.nivel === "ALTO") && <p className="mt-2">Faça uma nova verificação e remova os apps marcados em ALTO.</p>}
        </div>
      )}
    </Cartao>
  );
}
