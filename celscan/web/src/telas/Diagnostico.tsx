import { Activity, Apple, BatteryCharging, Camera, Cpu, FolderOpen, Gauge, HardDrive, Power, Sparkles, Trash2, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Dispositivo, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, corNota, Miniatura, Titulo } from "../ui";
import { tamanho } from "./Resgate";

interface Bateria {
  nivel?: string; saude?: string; situacao?: string; temperatura?: string; tensao?: string;
  ciclos?: string | number; saude_pct?: number; capacidade_mah?: number; capacidade_projeto_mah?: number;
  veredito?: string;
  ciclos_restantes?: { restantes: number; base: "medido" | "referencia"; ate_pct: number; obs: string };
}
interface Peca { peca: string; nivel: "alto" | "medio" | "baixo"; texto: string }
interface Diag {
  bateria: Bateria;
  pecas?: Peca[];
  armazenamento: { total_gb: number; livre_gb: number } | null;
  ram: { total_gb: number; disponivel_gb: number } | null;
  pastas: { pasta: string; gb: number }[];
  ligado_dias: number | null;
  identificacao: Record<string, string>;
  avisos: string[];
}
interface Lixo { itens: { chave: string; nome: string; kb: number }[]; total_mb: number }
interface IPhone { udid: string; nome?: string; modelo?: string; ios?: string; imei?: string; erro?: string; bateria?: { saude_pct?: number; ciclos?: number } }

// Bateria tem escala própria: abaixo de 80% de saúde a troca já começa a valer a pena.
const corBateria = (pct?: number) =>
  pct == null ? "inherit" : pct >= 80 ? "var(--ok)" : pct >= 70 ? "var(--atencao)" : "var(--perigo)";

const COR_PECA: Record<Peca["nivel"], string> = {
  alto: "border-perigo/40 bg-perigo-suave",
  medio: "border-atencao/40 bg-atencao-suave",
  baixo: "border-linha bg-superficie-2",
};

interface ModoEnergia { chave: string; nome: string; descricao: string; aviso: string }

function PainelEnergia({ d }: { d: Dispositivo | undefined }) {
  const { avisar } = useApp();
  const [modos, setModos] = useState<ModoEnergia[]>([]);
  const [confirmar, setConfirmar] = useState<ModoEnergia | null>(null);
  const pronto = d?.estado === "device";

  useEffect(() => { api<ModoEnergia[]>("/energia/modos").then(setModos).catch(() => undefined); }, []);

  async function reiniciar(m: ModoEnergia) {
    setConfirmar(null);
    try {
      const r = await api<{ nome: string; aviso: string }>("/energia/reiniciar", { corpo: { serial: d!.serial, modo: m.chave } });
      avisar({ tipo: "ok", texto: `${r.nome} enviado. ${r.aviso}`, duracao: 12000 });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }

  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><Power size={18} aria-hidden /> Reiniciar e modos de manutenção</h3>
      <p className="mt-1 text-sm text-fraco">Reiniciar não apaga nada nem mexe na senha — é o mesmo que segurar o botão de ligar.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {modos.map((m) => (
          <button key={m.chave} onClick={() => setConfirmar(m)} disabled={!pronto}
            className="realce rounded-lg border border-linha bg-superficie-2 p-3 text-left text-sm transition hover:border-destaque/50 disabled:cursor-not-allowed disabled:opacity-45">
            <span className="font-semibold">{m.nome}</span>
            <span className="mt-1 block text-xs text-fraco">{m.descricao}</span>
          </button>
        ))}
      </div>
      {!pronto && <p className="mt-2 text-sm text-fraco">Precisa do celular conectado e autorizado.</p>}
      {confirmar && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" onClick={() => setConfirmar(null)}>
          <Cartao className="max-w-md p-5" >
            <div onClick={(e) => e.stopPropagation()}>
              <h4 className="flex items-center gap-2 font-semibold"><Power size={16} aria-hidden /> {confirmar.nome}?</h4>
              <p className="mt-2 text-sm">{confirmar.aviso}</p>
              <div className="mt-4 flex justify-end gap-2">
                <Botao onClick={() => setConfirmar(null)}>Cancelar</Botao>
                <Botao variante={confirmar.chave === "bootloader" ? "perigo" : "primario"} onClick={() => reiniciar(confirmar)}>
                  {confirmar.nome}
                </Botao>
              </div>
            </div>
          </Cartao>
        </div>
      )}
    </Cartao>
  );
}

function PainelPrint({ d }: { d: Dispositivo | undefined }) {
  const { avisar } = useApp();
  const [print, setPrint] = useState<{ caminho: string; pasta: string; png_b64: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const pronto = d?.estado === "device";

  async function tirar() {
    setOcupado(true);
    try {
      setPrint(await api<{ caminho: string; pasta: string; png_b64: string }>("/captura", { corpo: { serial: d!.serial } }));
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }

  return (
    <Cartao className="p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold"><Camera size={18} aria-hidden /> Print da tela do celular</h3>
        <Botao variante="primario" onClick={tirar} disabled={!pronto || ocupado}>{ocupado ? "Tirando..." : "Tirar print"}</Botao>
      </div>
      <p className="mt-1 text-sm text-fraco">Salva uma imagem da tela no computador, para documentar um defeito ou mandar para alguém. Apps de banco e a tela bloqueada podem sair pretos (proteção do Android).</p>
      {print && (
        <div className="mt-3 flex flex-wrap items-start gap-4">
          <img src={`data:image/png;base64,${print.png_b64}`} alt="Print da tela do celular"
            className="max-h-72 rounded-md border border-linha" />
          <div className="space-y-2 text-sm">
            <p className="break-all font-mono text-xs text-fraco">{print.caminho}</p>
            <Botao onClick={() => api("/abrir-pasta", { corpo: { caminho: print.pasta } }).catch((e) => avisar({ tipo: "erro", texto: (e as Error).message }))}>
              <FolderOpen size={15} aria-hidden /> Abrir pasta
            </Botao>
          </div>
        </div>
      )}
    </Cartao>
  );
}

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
            {b.saude_pct !== undefined && <Linha rotulo="Saúde da bateria">~{b.saude_pct}%{b.capacidade_projeto_mah ? ` (${b.capacidade_mah}/${b.capacidade_projeto_mah} mAh)` : ""}</Linha>}
            {b.veredito && <Linha rotulo="Situação da bateria"><span style={{ color: corBateria(b.saude_pct) }}>{b.veredito}</span></Linha>}
            {b.ciclos !== undefined && <Linha rotulo="Ciclos usados">{b.ciclos}</Linha>}
            {b.ciclos_restantes && (
              <Linha rotulo={`Ciclos restantes (até ${b.ciclos_restantes.ate_pct}%)`}>
                <span title={b.ciclos_restantes.obs}>~{b.ciclos_restantes.restantes.toLocaleString("pt-BR")}{b.ciclos_restantes.base === "referencia" ? " *" : ""}</span>
              </Linha>
            )}
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
          {diag.pecas && diag.pecas.length > 0 && (
            <div className="md:col-span-2">
              <h4 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-fraco"><Wrench size={14} aria-hidden /> Peças originais ou trocadas</h4>
              <p className="mb-2 text-xs text-fraco">Por USB só dá para ver <strong>indícios</strong>, nunca prova. Confirme com inspeção física.</p>
              <ul className="space-y-2">
                {diag.pecas.map((p) => (
                  <li key={p.peca} className={`rounded-md border p-2.5 text-sm ${COR_PECA[p.nivel]}`}>
                    <strong>{p.peca}:</strong> {p.texto}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {b.ciclos_restantes?.base === "referencia" && (
            <p className="md:col-span-2 text-xs text-fraco">* Estimativa pela vida típica de uma bateria; este aparelho não informou o desgaste real.</p>
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

interface Desempenho { apps: { pacote: string; ms: number | null; erro: string | null }[]; media_abertura_ms: number | null;
  armazenamento: { gravacao_mb_s: number | null; leitura_mb_s: number | null; obs: string };
  hardware?: { nucleos: number | null; ghz_max: number | null; ram_gb: number | null };
  cameras?: { total: number | null; traseiras: number | null; frontais: number | null; megapixels_max: number | null; obs: string };
  pontuacao?: { total: number | null; categorias: Record<"hardware" | "armazenamento" | "fluidez", number | null>; obs: string } }

const NOME_CATEGORIA = { hardware: "Hardware (processador e RAM)", armazenamento: "Armazenamento", fluidez: "Fluidez (abertura de apps)" } as const;

function Pontuacao({ p }: { p: NonNullable<Desempenho["pontuacao"]> }) {
  if (p.total == null) return <p className="text-sm text-fraco">Não deu para calcular a pontuação neste aparelho.</p>;
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="text-center">
        <p className="numeros font-mono text-5xl font-semibold" style={{ color: corNota(p.total / 10) }}>{p.total}</p>
        <p className="text-xs uppercase tracking-wider text-fraco">pontos de 1000</p>
      </div>
      <div className="min-w-56 flex-1 space-y-2">
        {(Object.keys(NOME_CATEGORIA) as (keyof typeof NOME_CATEGORIA)[]).map((k) => {
          const v = p.categorias[k];
          return (
            <div key={k}>
              <div className="flex justify-between text-xs"><span className="text-fraco">{NOME_CATEGORIA[k]}</span>
                <span className="numeros font-medium">{v == null ? "não medido" : `${v}/100`}</span></div>
              <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-linha">
                <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${v ?? 0}%`, background: corNota(v ?? 0) }} />
              </div>
            </div>
          );
        })}
      </div>
      <p className="w-full text-xs text-fraco">{p.obs}</p>
    </div>
  );
}

function PainelDesempenho({ d }: { d: Dispositivo | undefined }) {
  const { esperar, avisar } = useApp();
  const [r, setR] = useState<Desempenho | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const pronto = d?.estado === "device";
  async function medir() {
    setOcupado(true);
    try {
      const t = await esperar(await api<Tarefa<Desempenho>>("/desempenho", { corpo: { serial: d!.serial } }));
      if (t.estado === "concluida" && t.resultado) setR(t.resultado);
      else avisar({ tipo: "erro", texto: t.erro ?? "O teste não terminou." });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }
  const s = (v: number | null) => (v == null ? "não medido" : `${v.toLocaleString("pt-BR")} MB/s`);
  return (
    <Cartao className="p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold"><Gauge size={18} aria-hidden /> Teste de desempenho (pontuação)</h3>
        <Botao onClick={medir} disabled={!pronto || ocupado}>{ocupado ? "Medindo..." : "Medir agora"}</Botao>
      </div>
      <p className="mt-1 text-sm text-fraco">Lê processador, RAM e câmeras, abre alguns apps "a frio" e mede o tempo, depois grava e lê 64 MB (arquivo apagado no fim). Dá uma nota de 0 a 1000 — use antes e depois da otimização para comparar.</p>
      {r?.pontuacao && <div className="mt-4"><Pontuacao p={r.pontuacao} /></div>}
      {r && (r.hardware || r.cameras) && (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {r.hardware && (
            <div>
              <h4 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-fraco"><Cpu size={14} aria-hidden /> Hardware</h4>
              <Linha rotulo="Núcleos do processador">{r.hardware.nucleos ?? "não verificado"}</Linha>
              <Linha rotulo="Clock máximo">{r.hardware.ghz_max != null ? `${r.hardware.ghz_max.toLocaleString("pt-BR")} GHz` : "não verificado"}</Linha>
              <Linha rotulo="RAM">{r.hardware.ram_gb != null ? `${r.hardware.ram_gb.toLocaleString("pt-BR")} GB` : "não verificado"}</Linha>
            </div>
          )}
          {r.cameras && (
            <div>
              <h4 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-fraco"><Camera size={14} aria-hidden /> Câmeras</h4>
              <Linha rotulo="Sensores (total)">{r.cameras.total ?? "não verificado"}</Linha>
              {r.cameras.traseiras != null && <Linha rotulo="Traseiras">{r.cameras.traseiras}</Linha>}
              {r.cameras.frontais != null && <Linha rotulo="Frontais">{r.cameras.frontais}</Linha>}
              <Linha rotulo="Maior foto">{r.cameras.megapixels_max != null ? `${r.cameras.megapixels_max.toLocaleString("pt-BR")} MP` : "não verificado"}</Linha>
              <p className="mt-1 text-xs text-fraco">{r.cameras.obs}</p>
            </div>
          )}
        </div>
      )}
      {r && (
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-sm font-semibold text-fraco">Abertura de apps{r.media_abertura_ms != null && ` · média ${(r.media_abertura_ms / 1000).toFixed(2)} s`}</h4>
            {r.apps.map((a) => <Linha key={a.pacote} rotulo={a.pacote}>{a.ms != null ? `${(a.ms / 1000).toFixed(2)} s` : a.erro}</Linha>)}
          </div>
          <div>
            <h4 className="mb-1 text-sm font-semibold text-fraco">Armazenamento</h4>
            <Linha rotulo="Gravação">{s(r.armazenamento.gravacao_mb_s)}</Linha>
            <Linha rotulo="Leitura">{s(r.armazenamento.leitura_mb_s)}</Linha>
            <p className="mt-1 text-xs text-fraco">{r.armazenamento.obs}</p>
          </div>
        </div>
      )}
    </Cartao>
  );
}

interface Esquecido { pacote: string; nome: string; icone: string | null; instalado: string | null; ultimo_uso: string | null }

function PainelEsquecidos({ d }: { d: Dispositivo | undefined }) {
  const { esperar, avisar } = useApp();
  const [dados, setDados] = useState<{ dias: number; apps: Esquecido[]; total_usuario: number } | null>(null);
  const [escolhidos, setEscolhidos] = useState<Set<string>>(new Set());
  const [ocupado, setOcupado] = useState(false);
  const pronto = d?.estado === "device";
  const data = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—");

  async function procurar() {
    setOcupado(true);
    try {
      const t = await esperar(await api<Tarefa<{ dias: number; apps: Esquecido[]; total_usuario: number }>>("/apps-esquecidos", { corpo: { serial: d!.serial, dias: 90 } }));
      if (t.estado === "concluida" && t.resultado) { setDados(t.resultado); setEscolhidos(new Set()); }
      else avisar({ tipo: "erro", texto: t.erro ?? "Não consegui ler o uso dos apps." });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }
  async function remover() {
    setOcupado(true);
    try {
      const t = await esperar(await api<Tarefa<{ pacote: string; ok: boolean }[]>>("/apps-esquecidos/remover", { corpo: { serial: d!.serial, pacotes: [...escolhidos] } }));
      const ok = (t.resultado ?? []).filter((x) => x.ok).map((x) => x.pacote);
      avisar({ tipo: ok.length ? "ok" : "erro", texto: `${ok.length} app(s) removido(s), com cópia na quarentena (dá para desfazer).` });
      setDados((x) => x && { ...x, apps: x.apps.filter((a) => !ok.includes(a.pacote)) });
      setEscolhidos(new Set());
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }

  return (
    <Cartao className="p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold"><HardDrive size={18} aria-hidden /> Apps esquecidos</h3>
        <Botao onClick={procurar} disabled={!pronto || ocupado}>{ocupado && !dados ? "Lendo..." : "Procurar"}</Botao>
      </div>
      <p className="mt-1 text-sm text-fraco">Apps que você instalou e não abre há 90 dias. Para ler o uso, o CelScan instala um app auxiliar temporário (sem ícone, sem internet) e o remove no fim.</p>
      {dados && (dados.apps.length === 0 ? <p className="mt-3 text-sm text-fraco">Nenhum app esquecido. Todos os {dados.total_usuario} apps foram usados recentemente.</p> : (
        <>
          <p className="mt-3 text-sm"><strong>{dados.apps.length}</strong> de {dados.total_usuario} apps não foram abertos nos últimos {dados.dias} dias.</p>
          <ul className="mt-2 max-h-80 space-y-1 overflow-auto">
            {dados.apps.map((a) => (
              <li key={a.pacote}>
                <label className="flex items-center gap-3 rounded-md border border-linha p-2 text-sm">
                  <input type="checkbox" className="accent-[var(--destaque)]" checked={escolhidos.has(a.pacote)}
                    onChange={() => setEscolhidos((x) => { const n = new Set(x); if (n.has(a.pacote)) n.delete(a.pacote); else n.add(a.pacote); return n; })} />
                  {a.icone ? <img src={a.icone} alt="" className="h-8 w-8 rounded" /> : <span className="h-8 w-8 rounded bg-superficie-2" />}
                  <span className="flex-1"><span className="font-medium">{a.nome}</span>
                    <span className="block text-xs text-fraco">Instalado em {data(a.instalado)} · último uso: {a.ultimo_uso ? data(a.ultimo_uso) : "não usado no período"}</span></span>
                </label>
              </li>
            ))}
          </ul>
          <Botao className="mt-3" variante="perigo" onClick={remover} disabled={ocupado || escolhidos.size === 0}>
            Remover {escolhidos.size} app(s)
          </Botao>
        </>
      ))}
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
      {d && (
        <div className="flex items-center gap-4">
          <Miniatura fabricante={d.fabricante} modelo={d.modelo} wifi={d.wifi} tamanho="lg" />
          <div>
            <p className="text-lg font-semibold">{d.fabricante ? `${d.fabricante} ${d.modelo}` : "Android"}</p>
            <p className="font-mono text-xs text-fraco">{d.android ? `Android ${d.android} · ` : ""}{d.serial}{d.wifi ? " · Wi-Fi" : " · USB"}</p>
          </div>
        </div>
      )}
      <PainelDiagnostico d={d} />
      <PainelPrint d={d} />
      <PainelEnergia d={d} />
      <PainelLimpeza d={d} />
      <PainelDebloat d={d} />
      <PainelDesempenho d={d} />
      <PainelEsquecidos d={d} />
      <PainelIPhone />
    </div>
  );
}
