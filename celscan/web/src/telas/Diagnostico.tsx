import { Activity, Apple, BatteryCharging, HardDrive, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Dispositivo, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, Titulo } from "../ui";
import { tamanho } from "./Resgate";

interface Diag {
  bateria: Record<string, string | number>;
  armazenamento: { total_gb: number; livre_gb: number } | null;
  ram: { total_gb: number; disponivel_gb: number } | null;
  pastas: { pasta: string; gb: number }[];
  ligado_dias: number | null;
  identificacao: Record<string, string>;
  avisos: string[];
}
interface Lixo { itens: { chave: string; nome: string; kb: number }[]; total_mb: number }
interface IPhone { udid: string; nome?: string; modelo?: string; ios?: string; imei?: string; erro?: string; bateria?: { saude_pct?: number; ciclos?: number } }

function Linha({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return <div className="flex justify-between gap-4 border-b border-linha/60 py-1.5 text-sm last:border-0">
    <span className="text-fraco">{rotulo}</span><span className="numeros text-right font-medium">{children}</span></div>;
}

function PainelDiagnostico({ d }: { d: Dispositivo | undefined }) {
  const { esperar, avisar } = useApp();
  const [diag, setDiag] = useState<Diag | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const pronto = d?.estado === "device";

  async function rodar() {
    setOcupado(true);
    setDiag(null);
    try {
      const t = await esperar(await api<Tarefa<Diag>>("/diagnostico", { corpo: { serial: d!.serial } }));
      if (t.estado === "concluida" && t.resultado) setDiag(t.resultado);
      else avisar({ tipo: "erro", texto: t.erro ?? "O diagnóstico não terminou." });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }

  const b = diag?.bateria ?? {};
  const id = diag?.identificacao ?? {};
  const arm = diag?.armazenamento;
  return (
    <Cartao className="p-5">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-semibold"><Activity size={18} aria-hidden /> Diagnóstico do aparelho</h3>
        <Botao variante="primario" onClick={rodar} disabled={!pronto || ocupado}>{ocupado ? "Lendo..." : "Rodar diagnóstico"}</Botao>
      </div>
      {diag && (
        <div className="mt-4 grid gap-5 md:grid-cols-2">
          <div>
            <h4 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-fraco"><HardDrive size={14} aria-hidden /> Identificação</h4>
            {(id.marketname || id.model) && <Linha rotulo="Modelo">{id.marketname || id.model}</Linha>}
            {id.manufacturer && <Linha rotulo="Fabricante">{id.manufacturer}</Linha>}
            {id.release && <Linha rotulo="Android">{id.release}</Linha>}
            {id.security_patch && <Linha rotulo="Patch de segurança">{id.security_patch}</Linha>}
            {id.imei && <Linha rotulo="IMEI">{id.imei}</Linha>}
            {id.serial && <Linha rotulo="Série">{id.serial}</Linha>}
          </div>
          <div>
            <h4 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-fraco"><BatteryCharging size={14} aria-hidden /> Bateria e memória</h4>
            {b.nivel !== undefined && <Linha rotulo="Nível / situação">{b.nivel}% · {b.situacao ?? b.saude}</Linha>}
            {b.saude_pct !== undefined && <Linha rotulo="Capacidade real">~{b.saude_pct}% ({b.capacidade_mah}/{b.capacidade_projeto_mah} mAh)</Linha>}
            {b.ciclos !== undefined && <Linha rotulo="Ciclos">{b.ciclos}</Linha>}
            {b.temperatura && <Linha rotulo="Temperatura">{b.temperatura}</Linha>}
            {arm && <Linha rotulo="Armazenamento">{arm.livre_gb.toFixed(1)} GB livres de {arm.total_gb.toFixed(0)} GB</Linha>}
            {diag.ram && <Linha rotulo="RAM">{diag.ram.disponivel_gb.toFixed(1)} de {diag.ram.total_gb.toFixed(1)} GB livres</Linha>}
            {diag.ligado_dias !== null && <Linha rotulo="Ligado há">{diag.ligado_dias.toFixed(1)} dias</Linha>}
          </div>
          {diag.pastas.length > 0 && (
            <div className="md:col-span-2">
              <h4 className="mb-1 text-sm font-semibold text-fraco">O que mais ocupa espaço</h4>
              {diag.pastas.slice(0, 6).map((p) => <Linha key={p.pasta} rotulo={p.pasta}>{p.gb.toFixed(1)} GB</Linha>)}
            </div>
          )}
          {diag.avisos.map((a) => <p key={a} className="md:col-span-2 text-xs text-atencao">{a}</p>)}
        </div>
      )}
      {!pronto && <p className="mt-2 text-sm text-fraco">Precisa do celular conectado e autorizado.</p>}
    </Cartao>
  );
}

function PainelLimpeza({ d }: { d: Dispositivo | undefined }) {
  const { esperar, avisar } = useApp();
  const [lixo, setLixo] = useState<Lixo | null>(null);
  const [ocupado, setOcupado] = useState("");
  const pronto = d?.estado === "device";

  async function medir() {
    setOcupado("medir");
    try { setLixo(await api<Lixo>("/limpeza/lixo", { corpo: { serial: d!.serial } })); }
    catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(""); }
  }
  async function limparCache() {
    setOcupado("cache");
    try {
      const t = await esperar(await api<Tarefa<{ liberado_mb: number | null }>>("/limpeza/cache", { corpo: { serial: d!.serial } }));
      const mb = t.resultado?.liberado_mb;
      avisar({ tipo: "ok", texto: mb != null ? `Cache limpo: ~${mb.toFixed(0)} MB liberados.` : "Cache limpo." });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(""); }
  }
  async function apagarLixo() {
    setOcupado("lixo");
    try {
      const r = await api<{ liberado_mb: number | null }>("/limpeza/lixo/apagar", { corpo: { serial: d!.serial, categorias: lixo!.itens.map((i) => i.chave) } });
      avisar({ tipo: "ok", texto: r.liberado_mb != null ? `Lixo apagado: ~${r.liberado_mb.toFixed(0)} MB liberados.` : "Lixo apagado." });
      setLixo(null);
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(""); }
  }

  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><Sparkles size={18} aria-hidden /> Limpeza que libera espaço</h3>
      <p className="mt-1 text-sm text-fraco">Só apaga o que o celular refaz sozinho (cache, miniaturas, temporários). Nunca toca em foto, vídeo ou documento.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Botao onClick={limparCache} disabled={!pronto || !!ocupado}>{ocupado === "cache" ? "Limpando..." : "Limpar cache dos apps"}</Botao>
        <Botao onClick={medir} disabled={!pronto || !!ocupado}>{ocupado === "medir" ? "Medindo..." : "Ver lixo seguro"}</Botao>
      </div>
      {lixo && (
        <div className="mt-4 space-y-1 text-sm">
          {lixo.itens.length === 0 ? <p className="text-fraco">Nada de lixo seguro encontrado.</p> : (<>
            {lixo.itens.map((i) => <Linha key={i.chave} rotulo={i.nome}>{tamanho(i.kb * 1024)}</Linha>)}
            <Botao variante="perigo" onClick={apagarLixo} disabled={!!ocupado} className="mt-3">
              <Trash2 size={15} aria-hidden /> Apagar {tamanho(lixo.total_mb * 1024 * 1024)} de lixo
            </Botao>
          </>)}
        </div>
      )}
    </Cartao>
  );
}

interface ItemDebloat { pacote: string; grupo: string; descricao: string; nivel: string }
const NOMES_NIVEL: Record<string, string> = { recomendado: "Recomendado", avancado: "Avançado", especialista: "Especialista" };

function PainelDebloat({ d }: { d: Dispositivo | undefined }) {
  const { esperar, avisar } = useApp();
  const [nivel, setNivel] = useState("recomendado");
  const [dados, setDados] = useState<{ niveis: Record<string, string>; itens: ItemDebloat[] } | null>(null);
  const [escolhidos, setEscolhidos] = useState<Set<string>>(new Set());
  const [ocupado, setOcupado] = useState(false);
  const pronto = d?.estado === "device";

  async function buscar(n = nivel) {
    setOcupado(true);
    try {
      const r = await api<{ niveis: Record<string, string>; itens: ItemDebloat[] }>(`/debloat?serial=${encodeURIComponent(d!.serial)}&nivel=${n}`);
      setDados(r);
      setEscolhidos(new Set(r.itens.filter((i) => i.nivel === "recomendado").map((i) => i.pacote)));
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }
  async function desativar() {
    setOcupado(true);
    try {
      const t = await esperar(await api<Tarefa<{ pacote: string; ok: boolean }[]>>("/debloat", { corpo: { serial: d!.serial, pacotes: [...escolhidos] } }));
      const ok = (t.resultado ?? []).filter((x) => x.ok).length;
      avisar({ tipo: ok ? "ok" : "erro", texto: `${ok} app(s) desativado(s). Dá para desfazer pelo Histórico/quarentena.` });
      await buscar();
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }

  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><Trash2 size={18} aria-hidden /> Apps pré-instalados desnecessários</h3>
      <p className="mt-1 text-sm text-fraco">Lista da comunidade (UAD). Desativa — não apaga — e dá para desfazer. Apps que podem impedir o celular de ligar nunca aparecem.</p>
      <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label="Nível">
        {Object.entries(NOMES_NIVEL).map(([k, nome]) => (
          <button key={k} role="radio" aria-checked={nivel === k} disabled={!pronto}
            onClick={() => { setNivel(k); if (dados) buscar(k); }}
            className={`rounded-full border px-3 py-1 text-sm ${nivel === k ? "border-destaque bg-destaque-suave text-destaque" : "border-linha"}`}>{nome}</button>
        ))}
        <Botao onClick={() => buscar()} disabled={!pronto || ocupado}>{ocupado && !dados ? "Procurando..." : "Procurar"}</Botao>
      </div>
      {dados && <p className="mt-2 text-xs text-fraco">{dados.niveis[nivel]}</p>}
      {dados && (dados.itens.length === 0 ? <p className="mt-3 text-sm text-fraco">Nada para desativar neste nível.</p> : (
        <>
          <ul className="mt-3 max-h-72 space-y-1 overflow-auto text-sm">
            {dados.itens.map((i) => (
              <li key={i.pacote}>
                <label className="flex items-start gap-2 rounded-md border border-linha p-2">
                  <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={escolhidos.has(i.pacote)}
                    onChange={() => setEscolhidos((x) => { const n = new Set(x); if (n.has(i.pacote)) n.delete(i.pacote); else n.add(i.pacote); return n; })} />
                  <span className="flex-1"><span className="font-mono text-xs">{i.pacote}</span>
                    <span className={`ml-2 rounded px-1 text-[10px] ${i.nivel === "recomendado" ? "bg-ok-suave text-ok" : "bg-atencao-suave text-atencao"}`}>{NOMES_NIVEL[i.nivel]}</span>
                    <span className="block text-fraco">{i.descricao || i.grupo}</span></span>
                </label>
              </li>
            ))}
          </ul>
          <Botao className="mt-3" variante="primario" onClick={desativar} disabled={ocupado || escolhidos.size === 0}>
            Desativar {escolhidos.size} app(s)
          </Botao>
        </>
      ))}
      {!pronto && <p className="mt-2 text-sm text-fraco">Precisa do celular conectado e autorizado.</p>}
    </Cartao>
  );
}

function PainelIPhone() {
  const [dados, setDados] = useState<{ disponivel: boolean; aparelhos: IPhone[]; aviso?: string } | null>(null);
  useEffect(() => { api<{ disponivel: boolean; aparelhos: IPhone[]; aviso?: string }>("/ios/estado").then(setDados).catch(() => undefined); }, []);
  if (!dados) return null;
  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><Apple size={18} aria-hidden /> iPhone (por USB)</h3>
      {!dados.disponivel && <p className="mt-2 text-sm text-fraco">{dados.aviso}</p>}
      {dados.disponivel && dados.aparelhos.length === 0 && <p className="mt-2 text-sm text-fraco">{dados.aviso ?? "Nenhum iPhone conectado. Desbloqueie e toque em 'Confiar'."}</p>}
      {dados.aparelhos.map((p) => (
        <div key={p.udid} className="mt-3">
          {p.erro ? <p className="text-sm text-atencao">{p.erro}</p> : (<>
            {p.nome && <Linha rotulo="Nome">{p.nome}</Linha>}
            {p.modelo && <Linha rotulo="Modelo">{p.modelo}</Linha>}
            {p.ios && <Linha rotulo="iOS">{p.ios}</Linha>}
            {p.imei && <Linha rotulo="IMEI">{p.imei}</Linha>}
            {p.bateria?.saude_pct !== undefined && <Linha rotulo="Bateria">~{p.bateria.saude_pct}% · {p.bateria.ciclos ?? "?"} ciclos</Linha>}
          </>)}
        </div>
      ))}
      <p className="mt-3 text-xs text-fraco">A varredura completa do iPhone (backup + MVT) fica no comando <span className="font-mono">celscan ios</span>.</p>
    </Cartao>
  );
}

export default function Diagnostico() {
  const { dispositivos } = useApp();
  const prontos = dispositivos.filter((x) => x.estado === "device");
  const [serial, setSerial] = useState<string | null>(null);
  const d = prontos.find((x) => x.serial === serial) ?? prontos[0];

  return (
    <div className="max-w-4xl space-y-6">
      <Titulo sub="Saúde da bateria e das peças, espaço, memória, IMEI e limpeza — tudo do jeito honesto, medindo antes e depois.">
        Diagnóstico e limpeza
      </Titulo>
      {prontos.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {prontos.map((x) => (
            <button key={x.serial} onClick={() => setSerial(x.serial)}
              className={`rounded-full border px-3 py-1 text-sm ${d?.serial === x.serial ? "border-ok bg-ok-suave text-ok" : "border-linha"}`}>
              {x.fabricante ? `${x.fabricante} ${x.modelo}` : x.serial}
            </button>
          ))}
        </div>
      )}
      <PainelDiagnostico d={d} />
      <PainelLimpeza d={d} />
      <PainelDebloat d={d} />
      <PainelIPhone />
    </div>
  );
}
