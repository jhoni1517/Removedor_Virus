import { ClipboardList, Download, MessageCircle, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, TOKEN } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, Titulo } from "../ui";

interface Servico { nome: string; preco: number; minutos: number; etapas: string[] }
interface Ordem {
  id: number; cliente: string | null; telefone: string | null; aparelho: string | null; imei: string | null;
  servicos: string[]; valor: number; status: string; criado_em: string; entregue_em: string | null;
}
interface Periodo { atendimentos: number; entregues: number; faturamento: number; tempo_medio_min: number | null;
  por_servico: { nome: string; qtd: number; valor: number }[] }
interface Painel { dia: Periodo; mes: Periodo; por_status: Record<string, number> }

const COLUNAS: [string, string][] = [["aguardando", "Aguardando"], ["analisando", "Analisando"], ["pronto", "Pronto"], ["entregue", "Entregue"]];
const real = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

function NovaOrdem({ catalogo, aoCriar }: { catalogo: Record<string, Servico>; aoCriar: () => void }) {
  const { avisar, dispositivos } = useApp();
  const pronto = dispositivos.find((d) => d.estado === "device");
  const [servicos, setServicos] = useState<Set<string>>(new Set(["checkup"]));
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [consentimento, setConsentimento] = useState(false);
  const [aparelho, setAparelho] = useState("");
  const [imei, setImei] = useState("");
  const total = [...servicos].reduce((s, k) => s + (catalogo[k]?.preco ?? 0), 0);

  useEffect(() => { if (pronto && !aparelho) setAparelho(`${pronto.fabricante ?? ""} ${pronto.modelo ?? ""}`.trim()); }, [pronto, aparelho]);

  async function criar() {
    try {
      await api("/ordens", { corpo: { servicos: [...servicos], aparelho: aparelho || null, imei: imei || null,
        serial: pronto?.serial ?? null, cliente_nome: nome || null, cliente_telefone: telefone || null, consentimento } });
      avisar({ tipo: "ok", texto: "Ordem de serviço aberta." });
      setNome(""); setTelefone(""); setImei(""); setConsentimento(false);
      aoCriar();
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }

  const campo = "rounded-md border border-linha bg-superficie-2 px-3 py-2 text-sm";
  return (
    <Cartao className="p-5">
      <h2 className="flex items-center gap-2 font-semibold"><Plus size={18} aria-hidden /> Nova ordem de serviço</h2>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(catalogo).map(([k, s]) => (
          <label key={k} className={`flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm ${servicos.has(k) ? "border-destaque bg-destaque-suave" : "border-linha"}`}>
            <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={servicos.has(k)}
              onChange={() => setServicos((x) => { const n = new Set(x); if (n.has(k)) n.delete(k); else n.add(k); return n; })} />
            <span className="flex-1"><span className="font-medium">{s.nome}</span>
              <span className="numeros block text-xs text-fraco">{real(s.preco)} · ~{s.minutos} min</span></span>
          </label>
        ))}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <input className={campo} placeholder="Aparelho (ex.: Redmi Note 14)" value={aparelho} onChange={(e) => setAparelho(e.target.value)} aria-label="Aparelho" />
        <input className={`${campo} font-mono`} placeholder="IMEI (opcional)" value={imei} onChange={(e) => setImei(e.target.value)} aria-label="IMEI" />
        <input className={campo} placeholder="Nome do cliente (opcional)" value={nome} onChange={(e) => setNome(e.target.value)} aria-label="Nome do cliente" />
        <input className={campo} placeholder="WhatsApp do cliente (opcional)" value={telefone} onChange={(e) => setTelefone(e.target.value)} aria-label="Telefone" />
      </div>
      {nome && (
        <label className="mt-2 flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={consentimento} onChange={(e) => setConsentimento(e.target.checked)} />
          <span>O cliente autorizou guardar nome e telefone para contato sobre este serviço (LGPD).</span>
        </label>
      )}
      <div className="mt-4 flex items-center justify-between">
        <p className="numeros text-lg font-semibold">{real(total)}</p>
        <Botao variante="primario" onClick={criar} disabled={servicos.size === 0 || (!!nome && !consentimento)}>Abrir OS</Botao>
      </div>
    </Cartao>
  );
}

function CartaoOrdem({ o, catalogo, mover }: { o: Ordem; catalogo: Record<string, Servico>; mover: (id: number, st: string) => void }) {
  const { avisar } = useApp();
  const i = COLUNAS.findIndex(([k]) => k === o.status);
  async function whatsapp() {
    try {
      const m = await api<{ texto: string; link: string }>(`/ordens/${o.id}/mensagem`);
      if (m.link) window.open(m.link, "_blank", "noopener");
      else { await navigator.clipboard.writeText(m.texto); avisar({ tipo: "info", texto: "Sem telefone: mensagem copiada." }); }
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }
  return (
    <div className="entrar rounded-md border border-linha bg-superficie p-3 text-sm shadow-sm">
      <div className="flex items-center justify-between">
        <span className="numeros font-mono text-xs text-fraco">OS {o.id}</span>
        <span className="numeros font-semibold">{real(o.valor)}</span>
      </div>
      <p className="mt-1 font-medium">{o.aparelho || "Aparelho"}</p>
      {o.cliente && <p className="text-fraco">{o.cliente}</p>}
      <p className="mt-1 text-xs text-fraco">{o.servicos.map((s) => catalogo[s]?.nome ?? s).join(" · ")}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {i > 0 && <Botao variante="fantasma" className="px-2 py-1 text-xs" onClick={() => mover(o.id, COLUNAS[i - 1][0])} aria-label="Voltar etapa">←</Botao>}
        {i < COLUNAS.length - 1 && <Botao className="px-2 py-1 text-xs" onClick={() => mover(o.id, COLUNAS[i + 1][0])}>{COLUNAS[i + 1][1]} →</Botao>}
        <Botao variante="fantasma" className="px-2 py-1 text-xs" onClick={whatsapp} aria-label="Mensagem para o cliente"><MessageCircle size={13} aria-hidden /></Botao>
      </div>
    </div>
  );
}

function Numeros({ titulo, p }: { titulo: string; p: Periodo }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-fraco">{titulo}</h3>
      <div className="numeros mt-1 grid grid-cols-3 gap-2">
        <div><p className="text-2xl font-semibold">{p.atendimentos}</p><p className="text-xs text-fraco">atendimentos</p></div>
        <div><p className="text-2xl font-semibold">{real(p.faturamento)}</p><p className="text-xs text-fraco">faturado (entregues)</p></div>
        <div><p className="text-2xl font-semibold">{p.tempo_medio_min != null ? `${p.tempo_medio_min} min` : "—"}</p><p className="text-xs text-fraco">tempo médio</p></div>
      </div>
      {p.por_servico.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs">
          {p.por_servico.map((s) => <li key={s.nome} className="flex justify-between"><span>{s.nome} ×{s.qtd}</span><span className="numeros">{real(s.valor)}</span></li>)}
        </ul>
      )}
    </div>
  );
}

export default function Balcao() {
  const { avisar } = useApp();
  const [catalogo, setCatalogo] = useState<Record<string, Servico>>({});
  const [ordens, setOrdens] = useState<Ordem[]>([]);
  const [painel, setPainel] = useState<Painel | null>(null);

  const carregar = useCallback(() => {
    api<Ordem[]>("/ordens").then(setOrdens).catch(() => undefined);
    api<Painel>("/painel").then(setPainel).catch(() => undefined);
  }, []);
  useEffect(() => { api<Record<string, Servico>>("/servicos").then(setCatalogo).catch(() => undefined); carregar(); }, [carregar]);

  async function mover(id: number, status: string) {
    try { await api(`/ordens/${id}/status`, { corpo: { status } }); carregar(); }
    catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }
  async function exportar() {
    const r = await fetch("/api/painel/ordens.csv", { headers: { "X-CelScan-Token": TOKEN } });
    const url = URL.createObjectURL(await r.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "ordens_celscan.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <Titulo sub="Ordens de serviço, pacotes de 1 clique e os números da loja — tudo neste computador.">
        <span className="flex items-center gap-2"><ClipboardList aria-hidden /> Balcão</span>
      </Titulo>
      <NovaOrdem catalogo={catalogo} aoCriar={carregar} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" aria-label="Quadro de ordens">
        {COLUNAS.map(([k, nome]) => {
          const lista = ordens.filter((o) => o.status === k).slice(0, k === "entregue" ? 8 : 50);
          return (
            <section key={k} className="rounded-lg border border-linha bg-superficie-2 p-3" aria-label={nome}>
              <h3 className="mb-2 flex justify-between text-sm font-semibold">{nome}<span className="numeros text-fraco">{painel?.por_status[k] ?? lista.length}</span></h3>
              <div className="space-y-2">
                {lista.length === 0 ? <p className="text-xs text-fraco">Vazio</p> :
                  lista.map((o) => <CartaoOrdem key={o.id} o={o} catalogo={catalogo} mover={mover} />)}
              </div>
            </section>
          );
        })}
      </div>
      {painel && (
        <Cartao className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Painel da loja</h2>
            <Botao variante="fantasma" onClick={exportar}><Download size={15} aria-hidden /> Exportar CSV</Botao>
          </div>
          <div className="grid gap-6 md:grid-cols-2">
            <Numeros titulo="Hoje" p={painel.dia} />
            <Numeros titulo="Este mês" p={painel.mes} />
          </div>
        </Cartao>
      )}
    </div>
  );
}
