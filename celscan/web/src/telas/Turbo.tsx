import { Camera, Cpu, Flame, Gamepad2, Gauge, MemoryStick, Moon, Rocket, Settings2, SlidersHorizontal, Sparkles, Trash2, Wifi, Wrench } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api, type Dispositivo, type Tarefa } from "../api";
import { useApp } from "../estado";
import Diagnostico, { PainelDebloat, PainelIPhone } from "./Diagnostico";
import { PainelBlindagem } from "./Blindagem";
import { PainelFlagrante } from "./Flagrante";
import { PainelBateria, PainelEspaco } from "./Gastos";
import { num } from "../nomes";
import { Barra, Botao, Cartao, corNota, Miniatura, nomeApp, Titulo } from "../ui";

/* ---------------------------------------------------------------- tipos (espelham celscan/acoes/turbo.py) */
interface Ficha {
  nome?: string; fabricante?: string; android?: string; interface?: string | null; patch?: string; abi?: string;
  chip?: string; gpu?: string; vulkan?: string | null; kernel?: string; selinux?: string; nucleos?: number;
  ghz_max?: number; ram_gb?: number; ram_livre_gb?: number; ram_virtual_gb?: number | null; classe: string;
  tela: { resolucao?: string; hz_atual?: number; hz_max?: number; hdr: boolean };
  termico: { status?: number; status_nome?: string; cpu_c?: number | null }; bateria_c?: number | null;
  bateria_saude?: string; ligado_h?: number | null;
}
interface Nota { total: number | null; categorias: Record<string, { nota: number | null; detalhe: string }>; obs: string }
interface Calor {
  nivel: "normal" | "quente" | "travando"; texto: string; causas: string[]; dicas: string[]; bateria_c?: number | null;
  clusters: { cluster: string; atual_ghz: number; limite_ghz: number; maximo_ghz: number; limite_pct: number | null }[];
  top: { processo: string; cpu_pct: number }[];
}
interface Ajuste { id: string; grupo: string; titulo: string; descricao: string; aviso: string; reiniciar: boolean; suportado: boolean; motivo: string; ligado: boolean }
interface Perfil { id: string; titulo: string; descricao: string; ajustes: string[] }
interface Resultado { id: string; titulo: string; ok: boolean; motivo?: string; reiniciar?: boolean }
interface AppRam { pacote: string; mb: number; estado: string; protegido: boolean; liberavel: boolean }
interface Ram { apps: AppRam[]; livre_mb: number | null; total_gb: number | null; liberavel_mb: number; modos: Record<string, string> }
interface Esquecido { pacote: string; dias: number | null }
interface Rede {
  conectado: boolean; banda?: string; rssi_dbm?: number; sinal?: string; velocidade_mbps?: number; padrao?: string;
  ping_ms?: number; oscilacao_ms?: number; perda_pct?: number; dicas: string[];
}
interface Etapa { id: string; titulo: string; detalhe: string; marcada: boolean }
interface Config { chave: string; valor: string; bloqueada: boolean }

const q = encodeURIComponent;
const NOMES_CAT: Record<string, string> = {
  fluidez: "Fluidez", processador: "Processador", memoria: "Memória", temperatura: "Temperatura",
  armazenamento: "Armazenamento", conexao: "Conexão com o PC",
};
const COR_CALOR = { normal: "border-ok/40 bg-ok-suave", quente: "border-atencao/40 bg-atencao-suave", travando: "border-perigo/40 bg-perigo-suave" };

function useAcao() {
  const { avisar } = useApp();
  const [ocupado, setOcupado] = useState("");
  async function rodar<T>(nome: string, f: () => Promise<T>): Promise<T | undefined> {
    setOcupado(nome);
    try { return await f(); }
    catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); return undefined; }
    finally { setOcupado(""); }
  }
  return { ocupado, rodar };
}

function Linha({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return <div className="flex justify-between gap-4 border-b border-linha/60 py-1.5 text-sm last:border-0">
    <span className="text-fraco">{rotulo}</span><span className="numeros text-right font-medium">{children}</span></div>;
}

function Cabeca({ icone, titulo, children }: { icone: ReactNode; titulo: string; children?: ReactNode }) {
  return (<>
    <h3 className="flex items-center gap-2 font-semibold">{icone} {titulo}</h3>
    {children && <p className="mt-1 text-sm text-fraco">{children}</p>}
  </>);
}

function Escolha<T extends string>({ opcoes, valor, mudar, rotulo }: { opcoes: [T, string][]; valor: T; mudar: (v: T) => void; rotulo: string }) {
  return (
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={rotulo}>
      {opcoes.map(([k, nome]) => (
        <button key={k} role="radio" aria-checked={valor === k} onClick={() => mudar(k)}
          className={`rounded-full border px-3 py-1 text-sm ${valor === k ? "border-destaque bg-destaque-suave text-destaque" : "border-linha"}`}>{nome}</button>
      ))}
    </div>
  );
}

function Marcador({ marcado, mudar, children, desativado = false }: { marcado: boolean; mudar: () => void; children: ReactNode; desativado?: boolean }) {
  return (
    <label className={`flex items-start gap-3 rounded-lg border border-linha p-3 text-sm ${desativado ? "opacity-50" : "cursor-pointer hover:bg-superficie-2"}`}>
      <input type="checkbox" className="mt-0.5" checked={marcado} disabled={desativado} onChange={mudar} />
      <span className="min-w-0 flex-1">{children}</span>
    </label>
  );
}

function alternar(s: Set<string>, id: string): Set<string> {
  const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n;
}

/* ---------------------------------------------------------------- ficha + nota */
function PainelFicha({ d }: { d: Dispositivo }) {
  const { esperar, avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [f, setF] = useState<Ficha | null>(null);
  const [nota, setNota] = useState<Nota | null>(null);
  const [anterior, setAnterior] = useState<number | null>(null);
  useEffect(() => { setF(null); setNota(null); rodar("ficha", async () => setF(await api<Ficha>(`/turbo/ficha?serial=${q(d.serial)}`))); }, [d.serial]); // eslint-disable-line react-hooks/exhaustive-deps

  async function examinar() {
    await rodar("nota", async () => {
      const t = await esperar(await api<Tarefa<Nota>>("/turbo/nota", { corpo: { serial: d.serial } }));
      if (!t.resultado) return;
      if (nota?.total != null) setAnterior(nota.total);
      setNota(t.resultado);
      avisar({ tipo: "ok", texto: `Nota do celular: ${t.resultado.total ?? "?"} de 100.` });
    });
  }

  return (
    <Cartao className="p-5">
      <Cabeca icone={<Cpu size={18} aria-hidden />} titulo="Ficha do aparelho e nota">
        Tudo lido do próprio sistema. A nota é medida agora (processador, memória, fluidez, armazenamento): rode antes e depois de otimizar para comparar.
      </Cabeca>
      {!f && <p className="mt-3 text-sm text-fraco">{ocupado === "ficha" ? "Conferindo com o sistema..." : "Não foi possível ler a ficha."}</p>}
      {f && (
        <div className="mt-4 grid gap-6 md:grid-cols-2">
          <div>
            <Linha rotulo="Classe">{f.classe}</Linha>
            <Linha rotulo="Chip">{[f.chip, f.gpu].filter(Boolean).join(" · ") || "—"}</Linha>
            <Linha rotulo="Processador">{f.nucleos ? `${f.nucleos} núcleos` : "—"}{f.ghz_max ? ` · até ${num(f.ghz_max, 2)} GHz` : ""}</Linha>
            <Linha rotulo="RAM">{f.ram_gb ? `${num(f.ram_gb, 1)} GB` : "—"}{f.ram_livre_gb != null ? ` (${num(f.ram_livre_gb, 1)} livres)` : ""}{f.ram_virtual_gb ? ` + ${num(f.ram_virtual_gb, 1)} GB virtual` : ""}</Linha>
            <Linha rotulo="Tela">{f.tela.resolucao ?? "—"}{f.tela.hz_atual ? ` · ${f.tela.hz_atual} Hz` : ""}{f.tela.hz_max ? ` (máx ${f.tela.hz_max} Hz)` : ""}{f.tela.hdr ? " · HDR" : ""}</Linha>
            <Linha rotulo="Vulkan">{f.vulkan ?? "—"}</Linha>
            <Linha rotulo="Android">{f.android ?? "—"}{f.interface ? ` · ${f.interface}` : ""}</Linha>
          </div>
          <div>
            <Linha rotulo="Temperatura da CPU">{f.termico.cpu_c != null ? `${num(f.termico.cpu_c, 0)} °C` : "—"}</Linha>
            <Linha rotulo="Calor (Android)">{f.termico.status_nome ?? "—"}</Linha>
            <Linha rotulo="Bateria">{[f.bateria_saude, f.bateria_c != null ? `${num(f.bateria_c, 1)} °C` : null].filter(Boolean).join(" · ") || "—"}</Linha>
            <Linha rotulo="Kernel">{f.kernel ?? "—"}</Linha>
            <Linha rotulo="Patch de segurança">{f.patch ?? "—"}</Linha>
            <Linha rotulo="ABI · SELinux">{f.abi ?? "—"} · {f.selinux ?? "—"}</Linha>
            <Linha rotulo="Ligado há">{f.ligado_h != null ? (f.ligado_h >= 24 ? `${Math.floor(f.ligado_h / 24)} d ${Math.round(f.ligado_h % 24)} h` : `${num(f.ligado_h, 1)} h`) : "—"}</Linha>
          </div>
        </div>
      )}
      <div className="mt-4"><Botao onClick={examinar} disabled={!!ocupado}><Gauge size={15} aria-hidden /> {ocupado === "nota" ? "Examinando (≈30 s)..." : "Examinar meu celular"}</Botao></div>
      {nota && (
        <div className="mt-4">
          <p className="text-4xl font-bold numeros" style={{ color: nota.total != null ? corNota(nota.total) : undefined }}>
            {nota.total ?? "—"}<span className="text-base font-normal text-fraco"> de 100</span>
            {anterior != null && nota.total != null && <span className="ml-3 text-base font-medium text-fraco">antes: {anterior} ({nota.total - anterior >= 0 ? "+" : ""}{nota.total - anterior})</span>}
          </p>
          <div className="mt-3 space-y-3">
            {Object.entries(nota.categorias).map(([k, c]) => (
              <div key={k}>
                <div className="flex justify-between text-sm"><span className="font-medium">{NOMES_CAT[k] ?? k}</span><span className="numeros">{c.nota ?? "—"}</span></div>
                <Barra valor={c.nota ?? 0} total={100} />
                <p className="text-xs text-fraco">{c.detalhe}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-fraco">{nota.obs}</p>
        </div>
      )}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- faxina geral */
interface AppMarca { pacote: string; nome: string; grupo: string; explicacao: string; perde: string; ativo: boolean; marcado: boolean }
interface Dns { modo: string; servidor: string | null; provedor: string | null; opcoes: { id: string; nome: string; servidor: string; descricao: string }[] }

function PainelFaxina({ d }: { d: Dispositivo }) {
  const { esperar, avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [dados, setDados] = useState<{ marca: string; grupos: Record<string, string>; apps: AppMarca[] } | null>(null);
  const [escolhidos, setEscolhidos] = useState<Set<string>>(new Set());
  const [dns, setDns] = useState<Dns | null>(null);
  const [proprio, setProprio] = useState("");

  async function carregar() {
    await rodar("carregar", async () => {
      const [a, n] = await Promise.all([
        api<{ marca: string; grupos: Record<string, string>; apps: AppMarca[] }>(`/faxina/apps?serial=${q(d.serial)}`),
        api<Dns>(`/faxina/dns?serial=${q(d.serial)}`),
      ]);
      setDados(a); setDns(n); setEscolhidos(new Set(a.apps.filter((x) => x.marcado && x.ativo).map((x) => x.pacote)));
    });
  }
  useEffect(() => { setDados(null); setDns(null); carregar(); }, [d.serial]); // eslint-disable-line react-hooks/exhaustive-deps

  async function remover() {
    await rodar("remover", async () => {
      const t = await esperar(await api<Tarefa<{ apps: { ok: boolean }[] }>>("/faxina/apps", { corpo: { serial: d.serial, pacotes: [...escolhidos] } }));
      const ok = (t.resultado?.apps ?? []).filter((x) => x.ok).length;
      avisar({ tipo: "ok", texto: `${ok} app(s) desativados. Reinicie o celular para os anúncios sumirem de vez. Volta pelo Histórico.` });
    });
    await carregar();
  }
  async function mudarDns(provedor: string | null, servidor?: string) {
    await rodar("dns", async () => {
      const r = await api<{ ok: boolean; servidor: string | null; obs: string }>("/faxina/dns", { corpo: { serial: d.serial, provedor, servidor: servidor ?? null } });
      avisar({ tipo: r.ok ? "ok" : "erro", texto: r.ok ? (r.servidor ? `Bloqueio de anúncios ligado (${r.servidor}). ${r.obs}` : "DNS de volta ao automático.") : "O Android não aceitou o DNS." });
      setDns(await api<Dns>(`/faxina/dns?serial=${q(d.serial)}`));
    });
  }
  async function camera() {
    await rodar("camera", async () => {
      const t = await esperar(await api<Tarefa<{ apps: { pacote: string }[]; dica: string | null; obs: string }>>("/faxina/camera", { corpo: { serial: d.serial } }));
      const r = t.resultado;
      if (r) avisar({ tipo: "ok", texto: `${r.apps.length} app(s) de câmera/galeria otimizados. ${r.dica ?? r.obs}` });
    });
  }

  const grupos = dados ? Object.keys(dados.grupos).filter((g) => dados.apps.some((a) => a.grupo === g)) : [];
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Trash2 size={18} aria-hidden />} titulo="Faxina geral: anúncios e apps inúteis">
        Tira os serviços de propaganda e os apps duplicados da marca, liga o bloqueio de anúncios e acelera a câmera. Nada é apagado do aparelho: tudo volta pelo Histórico.
      </Cabeca>
      {!dados && <p className="mt-3 text-sm text-fraco">{ocupado ? "Procurando os apps da marca..." : "Não foi possível ler os apps."}</p>}
      {dados && (<>
        {dados.apps.length === 0 && <p className="mt-3 text-sm text-fraco">Nenhum app inútil conhecido neste aparelho.</p>}
        {grupos.map((g) => (
          <div key={g} className="mt-4">
            <p className="mb-2 text-sm font-semibold">{dados.grupos[g]}</p>
            <div className="space-y-2">
              {dados.apps.filter((a) => a.grupo === g).map((a) => (
                <Marcador key={a.pacote} marcado={escolhidos.has(a.pacote)} mudar={() => setEscolhidos(alternar(escolhidos, a.pacote))} desativado={!a.ativo}>
                  <span className="font-medium">{a.nome}</span>{!a.ativo && <span className="ml-2 rounded-full bg-ok-suave px-2 text-xs text-ok">já desativado</span>}
                  <span className="block text-fraco">{a.explicacao}</span>
                  {a.perde && <span className="block text-xs text-atencao">Você perde: {a.perde}</span>}
                  <span className="block font-mono text-xs text-fraco">{a.pacote}</span>
                </Marcador>
              ))}
            </div>
          </div>
        ))}
        {dados.apps.length > 0 && <Botao className="mt-3" variante="perigo" onClick={remover} disabled={!!ocupado || escolhidos.size === 0}>{ocupado === "remover" ? "Desativando..." : `Desativar ${escolhidos.size} app(s)`}</Botao>}
      </>)}
      {dns && (
        <div className="mt-6">
          <p className="text-sm font-semibold">Bloqueio de anúncios (DNS privado, sem app e sem VPN)</p>
          <p className="text-sm text-fraco">Agora: {dns.servidor ? <b>{dns.servidor}</b> : "automático (sem bloqueio)"}. Vale no Wi-Fi e nos dados móveis, não gasta bateria. Não bloqueia anúncio do YouTube.</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {dns.opcoes.map((o) => (
              <button key={o.id} onClick={() => mudarDns(o.id)} disabled={!!ocupado}
                className={`rounded-lg border p-3 text-left text-sm disabled:opacity-50 ${dns.provedor === o.id ? "border-ok bg-ok-suave" : "border-linha hover:bg-superficie-2"}`}>
                <span className="block font-semibold">{o.nome}{dns.provedor === o.id ? " · ligado" : ""}</span><span className="text-fraco">{o.descricao}</span>
              </button>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <input value={proprio} onChange={(e) => setProprio(e.target.value)} placeholder="servidor próprio (ex.: abc123.dns.nextdns.io)" aria-label="Servidor DNS próprio"
              className="min-w-56 flex-1 rounded-md border border-linha bg-superficie px-3 py-1.5 font-mono text-sm" />
            <Botao onClick={() => mudarDns(null, proprio.trim())} disabled={!!ocupado || !proprio.trim()}>Usar este</Botao>
            <Botao variante="fantasma" onClick={() => mudarDns(null)} disabled={!!ocupado || !dns.servidor}>Voltar ao automático</Botao>
          </div>
        </div>
      )}
      <div className="mt-6">
        <p className="text-sm font-semibold">Câmera travando</p>
        <p className="text-sm text-fraco">Compila câmera e galeria por completo, limpa o cache delas e reinicia a câmera. Também avisa se o armazenamento cheio é a causa.</p>
        <Botao className="mt-2" onClick={camera} disabled={!!ocupado}><Camera size={15} aria-hidden /> {ocupado === "camera" ? "Otimizando a câmera..." : "Deixar a câmera mais rápida"}</Botao>
      </div>
    </Cartao>
  );
}

/* ---------------------------------------------------------------- calor */
function PainelCalor({ d }: { d: Dispositivo }) {
  const { ocupado, rodar } = useAcao();
  const [c, setC] = useState<Calor | null>(null);
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Flame size={18} aria-hidden />} titulo="Calor e lentidão">Descobre o que está esquentando ou travando o celular agora.</Cabeca>
      <Botao className="mt-3" onClick={() => rodar("calor", async () => setC(await api<Calor>(`/turbo/calor?serial=${q(d.serial)}`)))} disabled={!!ocupado}>
        {ocupado ? "Analisando..." : c ? "Analisar de novo" : "Analisar"}
      </Botao>
      {c && (
        <div className="mt-4 space-y-3">
          <p className={`rounded-lg border p-3 text-sm font-medium ${COR_CALOR[c.nivel]}`}>{c.texto}</p>
          {c.causas.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm">{c.causas.map((x) => <li key={x}>{x}</li>)}</ul>}
          {c.clusters.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-3">
              {c.clusters.map((k) => (
                <div key={k.cluster} className="rounded-lg border border-linha p-2 text-xs">
                  <p className="font-mono text-fraco">{k.cluster}</p>
                  <p className="numeros">agora {num(k.atual_ghz, 2)} GHz</p>
                  <p className="numeros">limite {num(k.limite_ghz, 2)} de {num(k.maximo_ghz, 2)} GHz {k.limite_pct != null && k.limite_pct < 90 && <span className="text-atencao">({k.limite_pct}%)</span>}</p>
                </div>
              ))}
            </div>
          )}
          {c.dicas.length > 0 && <div className="text-sm"><p className="font-medium">O que fazer</p><ul className="list-disc pl-5 text-fraco">{c.dicas.map((x) => <li key={x}>{x}</li>)}</ul></div>}
        </div>
      )}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- receita */
interface Diferenca { antes: number; depois: number; pontos: number; ganho_pct: number | null }
interface AntesDepois { total: Diferenca | null; categorias: Record<string, Diferenca>; obs: string }

function PainelReceita({ d }: { d: Dispositivo }) {
  const { esperar, avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [etapas, setEtapas] = useState<Etapa[] | null>(null);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [ad, setAd] = useState<AntesDepois | null>(null);

  async function montar() {
    await rodar("montar", async () => {
      const r = await api<{ etapas: Etapa[] }>(`/turbo/receita?serial=${q(d.serial)}`);
      setEtapas(r.etapas); setMarcadas(new Set(r.etapas.filter((e) => e.marcada).map((e) => e.id)));
    });
  }
  async function aplicar() {
    await rodar("aplicar", async () => {
      setAd(null);
      const t = await esperar(await api<Tarefa<{ etapas: { id: string; ok: boolean }[]; antes_depois?: AntesDepois }>>("/turbo/receita", { corpo: { serial: d.serial, etapas: [...marcadas].filter((x) => x !== "aviso_calor") } }));
      const ok = (t.resultado?.etapas ?? []).filter((e) => e.ok).length;
      if (t.resultado?.antes_depois?.total) setAd(t.resultado.antes_depois);
      avisar({ tipo: "ok", texto: `Otimização concluída: ${ok} etapa(s). Os ajustes podem ser desfeitos no Histórico.` });
    });
  }

  return (
    <Cartao className="p-5">
      <Cabeca icone={<Sparkles size={18} aria-hidden />} titulo="Otimização completa">Um plano feito para este celular (versão do Android, RAM, calor e apps mais usados). Confira as etapas e aplique tudo de uma vez.</Cabeca>
      <Botao className="mt-3" variante={etapas ? "secundario" : "primario"} onClick={montar} disabled={!!ocupado}>{ocupado === "montar" ? "Analisando o celular..." : etapas ? "Analisar de novo" : "Ver o que dá para otimizar"}</Botao>
      {etapas && (
        <div className="mt-4 space-y-2">
          {etapas.map((e) => (
            <Marcador key={e.id} marcado={marcadas.has(e.id)} mudar={() => setMarcadas(alternar(marcadas, e.id))} desativado={e.id === "aviso_calor"}>
              <span className="font-medium">{e.titulo}</span><span className="block text-fraco">{e.detalhe}</span>
            </Marcador>
          ))}
          <Botao variante="primario" onClick={aplicar} disabled={!!ocupado || marcadas.size === 0}>
            <Rocket size={15} aria-hidden /> {ocupado === "aplicar" ? "Otimizando (mede antes e depois, leva alguns minutos)..." : `Otimizar agora (${[...marcadas].filter((x) => x !== "aviso_calor").length} etapas)`}
          </Botao>
        </div>
      )}
      {ad?.total && (
        <div className="mt-4 rounded-md border border-linha p-3 text-sm">
          <p className="text-base">Nota <b className="numeros">{ad.total.antes}</b> → <b className="numeros">{ad.total.depois}</b>
            <span className={ad.total.pontos >= 0 ? "ml-2 text-ok" : "ml-2 text-atencao"}>{ad.total.pontos >= 0 ? "+" : ""}{ad.total.pontos} pontos{ad.total.ganho_pct != null ? ` (${ad.total.ganho_pct >= 0 ? "+" : ""}${ad.total.ganho_pct}%)` : ""}</span></p>
          <ul className="mt-2 space-y-0.5">
            {Object.entries(ad.categorias).map(([k, c]) => (
              <li key={k} className="flex justify-between gap-4"><span className="capitalize">{k}</span><span className="numeros">{c.antes} → {c.depois}</span></li>
            ))}
          </ul>
          <p className="mt-2 text-fraco">{ad.obs}</p>
        </div>
      )}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- ajustes e perfis */
function PainelAjustes({ d }: { d: Dispositivo }) {
  const { avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [dados, setDados] = useState<{ ajustes: Ajuste[]; perfis: Perfil[] } | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());

  async function carregar() {
    await rodar("carregar", async () => setDados(await api<{ ajustes: Ajuste[]; perfis: Perfil[] }>(`/turbo/ajustes?serial=${q(d.serial)}`)));
  }
  useEffect(() => { setDados(null); setMarcados(new Set()); carregar(); }, [d.serial]); // eslint-disable-line react-hooks/exhaustive-deps

  function relatar(r: { resultado: Resultado[] }) {
    const ok = r.resultado.filter((x) => x.ok), falhou = r.resultado.filter((x) => !x.ok);
    const reiniciar = ok.some((x) => x.reiniciar) ? " Reinicie o celular para valer tudo." : "";
    avisar({ tipo: falhou.length && !ok.length ? "erro" : "ok",
      texto: `${ok.length} ajuste(s) aplicado(s).${falhou.length ? ` Não aceitos: ${falhou.map((x) => x.titulo).join(", ")}.` : ""}${reiniciar} Dá para desfazer no Histórico.` });
  }
  async function aplicar() {
    await rodar("aplicar", async () => { relatar(await api<{ resultado: Resultado[] }>("/turbo/ajustes", { corpo: { serial: d.serial, ids: [...marcados] } })); setMarcados(new Set()); });
    await carregar();
  }
  async function perfil(id: string) {
    await rodar(`perfil-${id}`, async () => relatar(await api<{ resultado: Resultado[] }>("/turbo/perfil", { corpo: { serial: d.serial, perfil: id } })));
    await carregar();
  }

  const grupos = dados ? [...new Set(dados.ajustes.map((a) => a.grupo))] : [];
  return (
    <Cartao className="p-5">
      <Cabeca icone={<SlidersHorizontal size={18} aria-hidden />} titulo="Perfis prontos e ajustes">Cada ajuste guarda o valor de antes: o Histórico desfaz com um clique.</Cabeca>
      {dados && (<>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {dados.perfis.map((p) => (
            <button key={p.id} onClick={() => perfil(p.id)} disabled={!!ocupado} className="rounded-lg border border-linha p-3 text-left text-sm hover:bg-superficie-2 disabled:opacity-50">
              <span className="block font-semibold">{p.titulo}</span><span className="text-fraco">{p.descricao}</span>
              <span className="mt-1 block text-xs text-fraco">{p.ajustes.length} ajustes</span>
            </button>
          ))}
        </div>
        {grupos.map((g) => (
          <div key={g} className="mt-4">
            <p className="mb-2 text-sm font-semibold">{g}</p>
            <div className="space-y-2">
              {dados.ajustes.filter((a) => a.grupo === g).map((a) => (
                <Marcador key={a.id} marcado={marcados.has(a.id)} mudar={() => setMarcados(alternar(marcados, a.id))} desativado={!a.suportado || a.ligado}>
                  <span className="font-medium">{a.titulo}</span>
                  {a.ligado && <span className="ml-2 rounded-full bg-ok-suave px-2 text-xs text-ok">ligado</span>}
                  <span className="block text-fraco">{a.descricao}</span>
                  {!a.suportado && <span className="block text-xs text-atencao">{a.motivo}</span>}
                  {a.aviso && a.suportado && <span className="block text-xs text-atencao">{a.aviso}</span>}
                </Marcador>
              ))}
            </div>
          </div>
        ))}
        <Botao className="mt-4" variante="primario" onClick={aplicar} disabled={!!ocupado || marcados.size === 0}>
          {ocupado === "aplicar" ? "Aplicando..." : `Aplicar ${marcados.size} ajuste(s)`}
        </Botao>
      </>)}
      {!dados && <p className="mt-3 text-sm text-fraco">{ocupado ? "Lendo os ajustes..." : "Não foi possível ler os ajustes."}</p>}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- compilação */
const MODOS: [string, string][] = [["rapida", "Rápida"], ["completa", "Completa"], ["extrema", "Extrema"]];
const ESCOPOS: [string, string][] = [["mais_usados", "5 mais usados"], ["usuario", "Meus apps"], ["sistema", "Sistema"], ["google", "Google"], ["webview", "WebView"], ["todos", "Todos"]];
const DESC_MODO: Record<string, string> = {
  rapida: "Compila o que você mais usa de cada app. Equilibrado, rápido de fazer.",
  completa: "Compila o app inteiro: abre e roda mais liso, ocupa um pouco mais de espaço.",
  extrema: "Compila absolutamente tudo. A mais demorada e a que mais ocupa espaço.",
};

function PainelCompilacao({ d }: { d: Dispositivo }) {
  const { esperar, avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [modo, setModo] = useState("completa");
  const [escopo, setEscopo] = useState("mais_usados");
  async function compilar() {
    await rodar("compilar", async () => {
      const t = await esperar(await api<Tarefa<{ ok: string[]; falhas: unknown[]; total: number; minutos: number; cancelado: boolean }>>("/turbo/compilar", { corpo: { serial: d.serial, modo, escopo } }));
      const r = t.resultado;
      if (r) avisar({ tipo: r.falhas.length ? "info" : "ok", texto: `${r.ok.length} de ${r.total} app(s) otimizados em ${num(r.minutos, 1)} min${r.falhas.length ? ` (${r.falhas.length} não aceitaram)` : ""}${r.cancelado ? " — cancelado" : ""}.` });
    });
  }
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Rocket size={18} aria-hidden />} titulo="Otimização dos apps (compilação)">
        O Android recompila os apps no modo escolhido: abrem mais rápido e travam menos. A tela fica acesa enquanto compila; o celular pode esquentar um pouco.
      </Cabeca>
      <div className="mt-3 space-y-3">
        <Escolha rotulo="Modo" opcoes={MODOS as [string, string][]} valor={modo} mudar={setModo} />
        <p className="text-sm text-fraco">{DESC_MODO[modo]}</p>
        <Escolha rotulo="Quais apps" opcoes={ESCOPOS} valor={escopo} mudar={setEscopo} />
        <Botao variante="primario" onClick={compilar} disabled={!!ocupado}>{ocupado ? "Otimizando..." : "Iniciar otimização"}</Botao>
      </div>
    </Cartao>
  );
}

/* ---------------------------------------------------------------- RAM */
const ESTADO_RAM: Record<string, string> = { rodando: "rodando", segundo_plano: "em segundo plano", tela_inicial: "tela inicial", sistema: "sistema" };

function PainelRam({ d }: { d: Dispositivo }) {
  const { avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [ram, setRam] = useState<Ram | null>(null);
  const [modo, setModo] = useState<"leve" | "soneca" | "forte">("leve");
  const [escolhidos, setEscolhidos] = useState<Set<string>>(new Set());
  async function medir() {
    await rodar("medir", async () => {
      const r = await api<Ram>(`/turbo/ram?serial=${q(d.serial)}`);
      setRam(r); setEscolhidos(new Set(r.apps.filter((a) => a.liberavel).map((a) => a.pacote)));
    });
  }
  async function liberar() {
    await rodar("liberar", async () => {
      const r = await api<{ liberou_mb: number | null }>("/turbo/ram/liberar", { corpo: { serial: d.serial, pacotes: [...escolhidos], modo } });
      avisar({ tipo: "ok", texto: r.liberou_mb != null ? `Liberou ${num(r.liberou_mb)} MB de RAM.` : "Apps fechados." });
    });
    await medir();
  }
  return (
    <Cartao className="p-5">
      <Cabeca icone={<MemoryStick size={18} aria-hidden />} titulo="Comilões de RAM">Quanto cada app ocupa agora. Teclado e tela inicial nunca são fechados.</Cabeca>
      <Botao className="mt-3" onClick={medir} disabled={!!ocupado}>{ocupado === "medir" ? "Lendo a RAM..." : ram ? "Medir de novo" : "Medir"}</Botao>
      {ram && (
        <div className="mt-4 space-y-3">
          <p className="text-sm">Livre agora: <b className="numeros">{ram.livre_mb != null ? `${num(ram.livre_mb / 1024, 1)} GB` : "—"}</b>{ram.total_gb ? ` de ${num(ram.total_gb, 1)} GB` : ""} · dá para liberar ~<b className="numeros">{num(ram.liberavel_mb)} MB</b></p>
          <Escolha rotulo="Força" opcoes={[["leve", "Leve"], ["soneca", "Soneca"], ["forte", "Forte"]]} valor={modo} mudar={setModo} />
          <p className={`text-xs ${modo === "forte" ? "text-atencao" : "text-fraco"}`}>{ram.modos[modo]}</p>
          <div className="max-h-80 space-y-1 overflow-auto">
            {ram.apps.map((a) => (
              <Marcador key={a.pacote} marcado={escolhidos.has(a.pacote)} mudar={() => setEscolhidos(alternar(escolhidos, a.pacote))} desativado={a.protegido || (modo !== "forte" && !a.liberavel)}>
                <span className="flex justify-between gap-2"><span className="font-medium">{nomeApp(a)}</span><span className="numeros">{num(a.mb)} MB</span></span>
                <span className="text-xs text-fraco">{a.protegido ? "protegido" : ESTADO_RAM[a.estado] ?? a.estado} · {a.pacote}</span>
              </Marcador>
            ))}
          </div>
          <Botao variante="primario" onClick={liberar} disabled={!!ocupado || escolhidos.size === 0}>{ocupado === "liberar" ? "Liberando..." : `Liberar ${escolhidos.size} app(s)`}</Botao>
        </div>
      )}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- apps esquecidos */
function PainelEsquecidosTurbo({ d }: { d: Dispositivo }) {
  const { avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [dias, setDias] = useState<"7" | "30">("30");
  const [apps, setApps] = useState<Esquecido[] | null>(null);
  const [escolhidos, setEscolhidos] = useState<Set<string>>(new Set());
  async function procurar(n = dias) {
    await rodar("procurar", async () => {
      const r = await api<{ apps: Esquecido[] }>(`/turbo/esquecidos?serial=${q(d.serial)}&dias=${n}`);
      setApps(r.apps); setEscolhidos(new Set(r.apps.map((a) => a.pacote)));
    });
  }
  async function dormir(nivel: "rare" | "restricted") {
    await rodar("dormir", async () => {
      const r = await api<{ apps: { ok: boolean }[] }>("/turbo/dormir", { corpo: { serial: d.serial, pacotes: [...escolhidos], nivel } });
      avisar({ tipo: "ok", texto: `${r.apps.filter((a) => a.ok).length} app(s) dormindo. Abrir o app acorda ele sozinho.` });
    });
  }
  async function proibir() {
    await rodar("proibir", async () => {
      await api("/turbo/segundo-plano", { corpo: { serial: d.serial, pacotes: [...escolhidos] } });
      avisar({ tipo: "ok", texto: `${escolhidos.size} app(s) só rodam quando abertos. Desfaça no Histórico se algum parar de notificar.` });
    });
  }
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Moon size={18} aria-hidden />} titulo="Apps parados dormindo">Apps sem uso param de acordar o celular escondidos. Nada é desinstalado.</Cabeca>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Escolha rotulo="Sem uso há" opcoes={[["7", "7 dias"], ["30", "30 dias"]]} valor={dias} mudar={(v) => { setDias(v); if (apps) procurar(v); }} />
        <Botao onClick={() => procurar()} disabled={!!ocupado}>{ocupado === "procurar" ? "Procurando..." : "Procurar"}</Botao>
      </div>
      {apps && (apps.length === 0 ? <p className="mt-3 text-sm text-fraco">Nenhum app parado há {dias} dias.</p> : (
        <div className="mt-3 space-y-2">
          <div className="max-h-64 space-y-1 overflow-auto">
            {apps.map((a) => (
              <Marcador key={a.pacote} marcado={escolhidos.has(a.pacote)} mudar={() => setEscolhidos(alternar(escolhidos, a.pacote))}>
                <span className="font-medium">{nomeApp(a)}</span><span className="block text-xs text-fraco">{a.dias != null ? `sem uso há ${a.dias} dias` : "sem uso registrado"} · {a.pacote}</span>
              </Marcador>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Botao onClick={() => dormir("rare")} disabled={!!ocupado || !escolhidos.size}>Quase não acorda</Botao>
            <Botao onClick={() => dormir("restricted")} disabled={!!ocupado || !escolhidos.size}>Parado de vez</Botao>
            <Botao onClick={proibir} disabled={!!ocupado || !escolhidos.size}>Proibir em segundo plano</Botao>
          </div>
        </div>
      ))}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- jogo */
function PainelJogo({ d }: { d: Dispositivo }) {
  const { avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [pacote, setPacote] = useState("");
  const [modo, setModo] = useState<"desempenho" | "bateria" | "padrao">("desempenho");
  const [escala, setEscala] = useState("1");
  const [fps, setFps] = useState("auto");
  async function aplicar() {
    await rodar("jogo", async () => {
      const r = await api<{ ok: boolean; obs: string; passos: { passo: string; ok: boolean; saida: string }[] }>("/turbo/jogo", {
        corpo: { serial: d.serial, pacote: pacote.trim(), modo, escala: escala === "1" ? null : Number(escala), fps: fps === "auto" ? null : Number(fps) },
      });
      avisar({ tipo: r.ok ? "ok" : "info", texto: r.ok ? "Modo de jogo aplicado. Feche e abra o jogo." : `${r.passos.filter((p) => !p.ok).map((p) => p.passo).join(", ")}: o aparelho não aceitou. ${r.obs}` });
    });
  }
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Gamepad2 size={18} aria-hidden />} titulo="Modo de jogo">Modo desempenho do Android, resolução e FPS por jogo (Android 12/13+). Desfaz no Histórico.</Cabeca>
      <div className="mt-3 space-y-3">
        <input value={pacote} onChange={(e) => setPacote(e.target.value)} placeholder="Pacote do jogo (ex.: com.dts.freefireth)" aria-label="Pacote do jogo"
          className="w-full rounded-md border border-linha bg-superficie px-3 py-2 font-mono text-sm" />
        <Escolha rotulo="Modo" opcoes={[["desempenho", "Desempenho"], ["padrao", "Padrão"], ["bateria", "Bateria"]]} valor={modo} mudar={setModo} />
        <div><p className="mb-1 text-sm font-medium">Resolução do jogo</p><Escolha rotulo="Resolução" opcoes={[["1", "100%"], ["0.9", "90%"], ["0.8", "80%"], ["0.7", "70%"], ["0.6", "60%"]]} valor={escala} mudar={setEscala} /></div>
        <div><p className="mb-1 text-sm font-medium">FPS do jogo</p><Escolha rotulo="FPS" opcoes={[["auto", "Auto"], ["30", "30"], ["45", "45"], ["60", "60"], ["90", "90"], ["120", "120"]]} valor={fps} mudar={setFps} /></div>
        <Botao variante="primario" onClick={aplicar} disabled={!!ocupado || !/^[\w.]+\.[\w.]+$/.test(pacote.trim())}>{ocupado ? "Aplicando..." : "Aplicar no jogo"}</Botao>
      </div>
    </Cartao>
  );
}

/* ---------------------------------------------------------------- rede */
function PainelRede({ d }: { d: Dispositivo }) {
  const { ocupado, rodar } = useAcao();
  const [r, setR] = useState<Rede | null>(null);
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Wifi size={18} aria-hidden />} titulo="Rede da partida">Banda do Wi-Fi, sinal, ping e oscilação medidos no celular.</Cabeca>
      <Botao className="mt-3" onClick={() => rodar("rede", async () => setR(await api<Rede>(`/turbo/rede?serial=${q(d.serial)}`)))} disabled={!!ocupado}>{ocupado ? "Medindo (≈5 s)..." : "Medir a rede"}</Botao>
      {r && (
        <div className="mt-3">
          {!r.conectado ? <p className="text-sm text-fraco">O celular não está no Wi-Fi.</p> : (<>
            <Linha rotulo="Banda">{r.banda ?? "—"}{r.padrao ? ` · Wi-Fi ${r.padrao}` : ""}</Linha>
            <Linha rotulo="Sinal">{r.sinal ?? "—"}{r.rssi_dbm != null ? ` (${r.rssi_dbm} dBm)` : ""}</Linha>
            <Linha rotulo="Velocidade do link">{r.velocidade_mbps != null ? `${r.velocidade_mbps} Mbps` : "—"}</Linha>
          </>)}
          <Linha rotulo="Ping (8.8.8.8)">{r.ping_ms != null ? `${num(r.ping_ms)} ms` : "sem resposta"}{r.oscilacao_ms != null ? ` · oscila ${num(r.oscilacao_ms)} ms` : ""}{r.perda_pct ? ` · ${num(r.perda_pct)}% perdido` : ""}</Linha>
          {r.dicas.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-fraco">{r.dicas.map((x) => <li key={x}>{x}</li>)}</ul>}
        </div>
      )}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- manutenção */
const MANUT: [string, string, string][] = [
  ["dexopt", "Manutenção antecipada", "A faxina de compilação que o Android faria de madrugada."],
  ["art_cleanup", "Faxina do ART", "Apaga código compilado que sobrou de apps antigos (Android 14+)."],
  ["armazenamento", "Armazenamento rápido", "Manutenção (TRIM): grava mais rápido em celular cheio."],
  ["cache", "Limpar cache geral", "Apaga o cache de todos os apps."],
];

function PainelManutencao({ d }: { d: Dispositivo }) {
  const { esperar, avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  async function executar(id: string) {
    await rodar(id, async () => {
      const t = await esperar(await api<Tarefa<{ ok: boolean; titulo: string; saida: string }>>("/turbo/manutencao", { corpo: { serial: d.serial, id } }));
      const r = t.resultado;
      if (r) avisar({ tipo: r.ok ? "ok" : "info", texto: r.ok ? `${r.titulo}: feito.` : `${r.titulo}: ${r.saida || "o aparelho não aceitou."}` });
    });
  }
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Wrench size={18} aria-hidden />} titulo="Manutenção do sistema">Rotinas do próprio Android, rodadas agora em vez de esperar a madrugada.</Cabeca>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {MANUT.map(([id, titulo, desc]) => (
          <button key={id} onClick={() => executar(id)} disabled={!!ocupado} className="rounded-lg border border-linha p-3 text-left text-sm hover:bg-superficie-2 disabled:opacity-50">
            <span className="block font-semibold">{ocupado === id ? "Rodando..." : titulo}</span><span className="text-fraco">{desc}</span>
          </button>
        ))}
      </div>
    </Cartao>
  );
}

/* ---------------------------------------------------------------- editor de configurações */
function PainelEditor({ d }: { d: Dispositivo }) {
  const { avisar } = useApp();
  const { ocupado, rodar } = useAcao();
  const [ns, setNs] = useState<"global" | "system" | "secure">("global");
  const [filtro, setFiltro] = useState("");
  const [itens, setItens] = useState<Config[] | null>(null);
  const [editando, setEditando] = useState<{ chave: string; valor: string } | null>(null);
  async function buscar() {
    await rodar("buscar", async () => setItens((await api<{ itens: Config[] }>(`/turbo/config?serial=${q(d.serial)}&ns=${ns}&filtro=${q(filtro)}`)).itens));
  }
  async function salvar() {
    if (!editando) return;
    await rodar("salvar", async () => {
      const r = await api<{ ok: boolean; anterior: string | null; atual: string | null }>("/turbo/config", { corpo: { serial: d.serial, ns, chave: editando.chave, valor: editando.valor } });
      avisar({ tipo: r.ok ? "ok" : "info", texto: r.ok ? `${editando.chave}: ${r.anterior ?? "(vazio)"} → ${r.atual}. Valor antigo guardado no Histórico.` : "O Android não aceitou o valor." });
      setEditando(null);
    });
    await buscar();
  }
  return (
    <Cartao className="p-5">
      <Cabeca icone={<Settings2 size={18} aria-hidden />} titulo="Editor de configurações (técnico)">
        Lê e edita as configurações system, secure e global do Android. Todo valor original fica guardado para desfazer. Opções que derrubam o ADB ficam bloqueadas.
      </Cabeca>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Escolha rotulo="Grupo" opcoes={[["global", "global"], ["system", "system"], ["secure", "secure"]]} valor={ns} mudar={setNs} />
        <input value={filtro} onChange={(e) => setFiltro(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") buscar(); }} placeholder="filtrar (ex.: refresh)" aria-label="Filtro"
          className="min-w-40 flex-1 rounded-md border border-linha bg-superficie px-3 py-1.5 font-mono text-sm" />
        <Botao onClick={buscar} disabled={!!ocupado}>{ocupado === "buscar" ? "Lendo..." : "Listar"}</Botao>
      </div>
      {itens && (
        <div className="mt-3 max-h-80 overflow-auto rounded-lg border border-linha font-mono text-xs">
          {itens.length === 0 && <p className="p-3 text-fraco">Nada encontrado.</p>}
          {itens.map((i) => (
            <div key={i.chave} className="flex items-center gap-2 border-b border-linha/60 px-3 py-1.5 last:border-0">
              <span className="min-w-0 flex-1 truncate" title={i.chave}>{i.chave}</span>
              {editando?.chave === i.chave ? (<>
                <input autoFocus value={editando.valor} onChange={(e) => setEditando({ ...editando, valor: e.target.value })} aria-label={`Valor de ${i.chave}`}
                  className="w-32 rounded border border-linha bg-superficie px-1" />
                <button className="text-destaque" onClick={salvar} disabled={!!ocupado}>salvar</button>
                <button className="text-fraco" onClick={() => setEditando(null)}>cancelar</button>
              </>) : (<>
                <span className="max-w-[40%] truncate text-fraco" title={i.valor}>{i.valor}</span>
                <button className="text-destaque disabled:opacity-40" disabled={i.bloqueada} title={i.bloqueada ? "bloqueada" : "editar"} onClick={() => setEditando({ chave: i.chave, valor: i.valor })}>editar</button>
              </>)}
            </div>
          ))}
        </div>
      )}
    </Cartao>
  );
}

/* ---------------------------------------------------------------- tela */
type Secao = "otimizar" | "limpeza" | "saude" | "desempenho" | "tecnico";
const SECOES: [Secao, string, string][] = [
  ["otimizar", "Otimizar", "Nota do celular e a otimização completa feita para ele."],
  ["limpeza", "Limpeza", "Anúncios, apps inúteis da marca, câmera, apps parados e memória."],
  ["saude", "Bateria e espaço", "Saúde da bateria, o que ocupa espaço, limpeza de cache e lixo."],
  ["desempenho", "Desempenho", "Perfis prontos, ajustes, jogos, calor e rede."],
  ["tecnico", "Técnico", "Compilação manual, lista completa de apps de fábrica, manutenção e editor de configurações."],
];

function lerSecao(): Secao {
  try { const v = localStorage.getItem("celscan-otimizar"); return SECOES.some(([id]) => id === v) ? (v as Secao) : "otimizar"; }
  catch { return "otimizar"; }
}

export default function Turbo() {
  const { dispositivos } = useApp();
  const prontos = dispositivos.filter((x) => x.estado === "device");
  const [serial, setSerial] = useState<string | null>(null);
  const [secao, setSecaoEstado] = useState<Secao>(lerSecao);
  const setSecao = (v: Secao) => { setSecaoEstado(v); try { localStorage.setItem("celscan-otimizar", v); } catch { /* sem storage */ } };
  const d = prontos.find((x) => x.serial === serial) ?? prontos[0];
  const atual = SECOES.find(([id]) => id === secao)!;
  return (
    <div className="max-w-4xl space-y-6">
      <Titulo sub="Pelo cabo ou Wi-Fi, sem instalar nada no celular. Só entra o que tem efeito real, e tudo pode ser desfeito no Histórico.">
        Otimizar
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
      {!d && <Cartao className="p-5"><p className="text-sm text-fraco">Conecte um celular (cabo ou Wi-Fi) e autorize a depuração para otimizar.</p></Cartao>}
      {d && (<>
        <div className="flex items-center gap-4">
          <Miniatura fabricante={d.fabricante} modelo={d.modelo} wifi={d.wifi} tamanho="lg" />
          <div>
            <p className="text-lg font-semibold">{d.fabricante ? `${d.fabricante} ${d.modelo}` : "Android"}</p>
            <p className="font-mono text-xs text-fraco">{d.android ? `Android ${d.android} · ` : ""}{d.wifi ? "Wi-Fi" : "USB"}</p>
          </div>
        </div>
        <div>
          <div className="abas" role="tablist" aria-label="Partes da otimização">
            {SECOES.map(([id, nome]) => (
              <button key={id} role="tab" aria-selected={secao === id} onClick={() => setSecao(id)}>{nome}</button>
            ))}
          </div>
          <p className="mt-3 text-sm text-fraco">{atual[2]}</p>
        </div>
        {secao === "otimizar" && (<>
          <PainelReceita d={d} />
          <PainelFicha d={d} />
        </>)}
        {secao === "limpeza" && (<>
          <PainelFaxina d={d} />
          <PainelEsquecidosTurbo d={d} />
          <PainelRam d={d} />
          <PainelEspaco serial={d.serial} />
          <PainelFlagrante serial={d.serial} />
          <PainelBlindagem serial={d.serial} />
        </>)}
        {secao === "saude" && (<>
          <PainelBateria serial={d.serial} />
          <Diagnostico serialFixo={d.serial} />
        </>)}
        {secao === "desempenho" && (<>
          <PainelAjustes d={d} />
          <PainelJogo d={d} />
          <PainelCalor d={d} />
          <PainelRede d={d} />
        </>)}
        {secao === "tecnico" && (<>
          <PainelCompilacao d={d} />
          <PainelDebloat d={d} />
          <PainelManutencao d={d} />
          <PainelEditor d={d} />
          <PainelIPhone />
        </>)}
      </>)}
    </div>
  );
}
