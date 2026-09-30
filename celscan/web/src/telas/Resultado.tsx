import { AlertTriangle, ChevronDown, FileText, Monitor, ShieldAlert, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api, urlLaudo, type Achado, type AppResultado, type Remocao, type Tarefa, type Varredura } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, Medidor, Selo, Vazio } from "../ui";

type Filtro = "alerta" | "ALTO" | "MÉDIO" | "BAIXO" | "todos";
const FILTROS: [Filtro, string][] = [["alerta", "Com alerta"], ["ALTO", "Alto"], ["MÉDIO", "Médio"], ["BAIXO", "Baixo"], ["todos", "Todos"]];
const COR_BORDA: Record<string, string> = { ALTO: "border-l-perigo", "MÉDIO": "border-l-atencao", BAIXO: "border-l-linha" };

function ItemAchado({ a }: { a: Achado }) {
  return (
    <li className="py-2">
      <p className="font-medium">{a.titulo}</p>
      <p className="text-sm text-fraco">{a.significa}</p>
      <p className="mt-0.5 text-sm"><span className="font-semibold">O que fazer: </span>{a.fazer}</p>
    </li>
  );
}

function CartaoApp({ r, selecionado, alternar, remover, removido, podeAgir }: {
  r: AppResultado; selecionado: boolean; alternar: () => void; remover: () => void; removido: boolean; podeAgir: boolean;
}) {
  const [aberto, setAberto] = useState(r.nivel === "ALTO");
  const achados = r.achados.filter((a) => a.chave !== "ameaca_conhecida");
  const acionavel = !r.sistema && r.nivel !== "OK" && r.nivel !== "PERMITIDO" && !removido;
  return (
    <Cartao className={`entrar border-l-4 ${COR_BORDA[r.nivel] ?? "border-l-ok"} ${removido ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-3 p-4">
        {acionavel && (
          <input type="checkbox" className="mt-1.5 h-4 w-4 accent-[var(--destaque)]" checked={selecionado} onChange={alternar}
            aria-label={`Selecionar ${r.pacote}`} disabled={!podeAgir} />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-mono text-sm font-semibold">{r.pacote}</span>
            <Selo nivel={r.nivel} />
            <span className="numeros font-mono text-xs text-fraco">{r.score} pts</span>
            {removido && <span className="rounded bg-ok-suave px-1.5 py-0.5 text-xs font-semibold text-ok">Removido</span>}
          </div>
          <p className="mt-0.5 text-xs text-fraco">
            {r.loja ? `Instalado pela ${r.loja}` : r.sistema ? "App do sistema" : `Instalado fora da loja (${r.instalador ?? "origem desconhecida"})`}
            {r.versao ? ` · versão ${r.versao}` : ""}
          </p>
          {r.ameaca && (
            <p className="mt-2 flex items-center gap-2 rounded-md bg-perigo-suave px-2 py-1 text-sm font-semibold text-perigo">
              <ShieldAlert size={16} aria-hidden /> {r.ameaca}
            </p>
          )}
          {achados.length > 0 && (
            <>
              <button className="mt-2 flex items-center gap-1 text-sm text-destaque" onClick={() => setAberto(!aberto)} aria-expanded={aberto}>
                <ChevronDown size={16} className={`transition ${aberto ? "rotate-180" : ""}`} aria-hidden />
                {aberto ? "Esconder detalhes" : `${achados.length} motivo(s): ${achados.slice(0, 2).map((a) => a.titulo).join(", ")}${achados.length > 2 ? "..." : ""}`}
              </button>
              {aberto && <ul className="mt-1 divide-y divide-linha">{achados.map((a) => <ItemAchado key={a.chave + a.titulo} a={a} />)}</ul>}
            </>
          )}
        </div>
        {acionavel && (
          <Botao variante={r.nivel === "ALTO" ? "perigo" : "secundario"} onClick={remover} disabled={!podeAgir}
            title={podeAgir ? "Remove o app (fica uma cópia na quarentena)" : "Conecte o celular para agir"}>
            <Trash2 size={15} aria-hidden /> Remover
          </Botao>
        )}
      </div>
    </Cartao>
  );
}

function Confirmar({ pacotes, confirmar, cancelar }: { pacotes: string[]; confirmar: () => void; cancelar: () => void }) {
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="titulo-confirmar"
      onKeyDown={(e) => e.key === "Escape" && cancelar()}>
      <Cartao className="entrar w-full max-w-lg p-6 shadow-xl">
        <h2 id="titulo-confirmar" className="text-lg font-semibold">Remover {pacotes.length} app(s)?</h2>
        <ul className="my-3 max-h-40 overflow-auto font-mono text-sm">{pacotes.map((p) => <li key={p}>{p}</li>)}</ul>
        <p className="text-sm text-fraco">
          Antes de remover, o CelScan guarda uma cópia de cada app na quarentena e tira as permissões perigosas.
          Você pode desfazer logo em seguida ou depois, pelo Histórico.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Botao onClick={cancelar}>Cancelar</Botao>
          <Botao variante="perigo" onClick={confirmar} autoFocus>Remover</Botao>
        </div>
      </Cartao>
    </div>
  );
}

export default function Resultado({ v, onNova }: { v: Varredura; onNova: () => void }) {
  const { dispositivos, esperar, avisar } = useApp();
  const [filtro, setFiltro] = useState<Filtro>("alerta");
  const [selecao, setSelecao] = useState<Set<string>>(new Set());
  const [removidos, setRemovidos] = useState<Set<string>>(new Set());
  const [confirmando, setConfirmando] = useState<string[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const conectado = dispositivos.some((d) => d.serial === v.info.serial && d.estado === "device");

  const contagem = useMemo(() => {
    const c: Record<string, number> = { ALTO: 0, "MÉDIO": 0, BAIXO: 0 };
    v.resultados.forEach((r) => { if (r.nivel in c) c[r.nivel]++; });
    return c;
  }, [v]);
  const visiveis = v.resultados.filter((r) =>
    filtro === "todos" ? true : filtro === "alerta" ? ["ALTO", "MÉDIO", "BAIXO"].includes(r.nivel) : r.nivel === filtro);

  async function desfazer(feitos: Remocao[]) {
    for (const f of feitos.filter((x) => x.ok && x.quarentena_id)) {
      const t = await esperar(await api<Tarefa<{ ok: boolean; mensagem: string }>>("/desfazer", {
        corpo: { serial: v.info.serial, quarentena_id: f.quarentena_id } }));
      if (t.estado === "concluida" && t.resultado?.ok) {
        setRemovidos((s) => { const n = new Set(s); n.delete(f.pacote); return n; });
        avisar({ tipo: "ok", texto: `${f.pacote} restaurado.` });
      } else avisar({ tipo: "erro", texto: `Não consegui restaurar ${f.pacote}: ${t.erro ?? t.resultado?.mensagem ?? ""}` });
    }
  }

  async function executarRemocao(pacotes: string[]) {
    setConfirmando(null);
    setOcupado(true);
    try {
      const t = await esperar(await api<Tarefa<Remocao[]>>("/remover", {
        corpo: { serial: v.info.serial, varredura_id: v.varredura_id, pacotes } }));
      if (t.estado !== "concluida" || !t.resultado) throw new Error(t.erro ?? "A remoção não terminou.");
      const feitos = t.resultado;
      const ok = feitos.filter((f) => f.ok);
      setRemovidos((s) => new Set([...s, ...ok.map((f) => f.pacote)]));
      setSelecao(new Set());
      feitos.filter((f) => !f.ok).forEach((f) => avisar({ tipo: "erro", texto: `${f.pacote}: ${f.mensagem}` }));
      if (ok.length) {
        avisar({ tipo: "ok", texto: `${ok.length} app(s) removido(s). Cópia guardada na quarentena.`, duracao: 10000,
          acao: { rotulo: "Desfazer", executar: () => { desfazer(ok); } } });
      }
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    } finally {
      setOcupado(false);
    }
  }

  async function verTela() {
    try {
      await api("/espelho", { corpo: { serial: v.info.serial, modo: "controlar" } });
      avisar({ tipo: "ok", texto: "A tela do celular abriu numa janela nova." });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }

  function alternar(p: string) {
    setSelecao((s) => { const n = new Set(s); if (n.has(p)) n.delete(p); else n.add(p); return n; });
  }

  return (
    <div className="max-w-5xl pb-24">
      <Cartao className="mb-6 flex flex-wrap items-center gap-6 p-6">
        <Medidor nota={v.nota} veredito={v.veredito} />
        <div className="min-w-[220px] flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">{v.info.fabricante} {v.info.modelo}</h1>
          <p className="font-mono text-sm text-fraco">
            Android {v.info.android} · patch {v.info.patch_seguranca} · {v.info.serial}
          </p>
          <dl className="numeros mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div><dt className="inline text-fraco">Apps: </dt><dd className="inline font-semibold">{v.resultados.length}</dd></div>
            <div><dt className="inline text-perigo">Alto: </dt><dd className="inline font-semibold">{contagem.ALTO}</dd></div>
            <div><dt className="inline text-atencao">Médio: </dt><dd className="inline font-semibold">{contagem["MÉDIO"]}</dd></div>
            <div><dt className="inline text-fraco">Duração: </dt><dd className="inline font-semibold">{Math.round(v.duracao_s)} s</dd></div>
            <div><dt className="inline text-fraco">Varredura nº </dt><dd className="inline font-semibold">{v.varredura_id}</dd></div>
          </dl>
        </div>
        <div className="flex flex-col gap-2">
          <a className="inline-flex items-center gap-2 rounded-md border border-linha px-3.5 py-2 text-sm font-medium hover:bg-superficie-2"
            href={urlLaudo(v.varredura_id, "cliente")} target="_blank" rel="noreferrer"><FileText size={15} aria-hidden /> Laudo (cliente)</a>
          <a className="inline-flex items-center gap-2 rounded-md border border-linha px-3.5 py-2 text-sm font-medium hover:bg-superficie-2"
            href={urlLaudo(v.varredura_id, "tecnico")} target="_blank" rel="noreferrer"><FileText size={15} aria-hidden /> Laudo técnico</a>
          <Botao onClick={verTela} disabled={!conectado} title={conectado ? "Abre a tela do celular numa janela" : "Conecte o celular"}>
            <Monitor size={15} aria-hidden /> Ver a tela
          </Botao>
          <Botao variante="fantasma" onClick={onNova}>Nova varredura</Botao>
        </div>
      </Cartao>

      {v.avisos.length > 0 && (
        <details className="mb-6 rounded-lg border border-atencao/40 bg-atencao-suave p-4 text-sm text-atencao">
          <summary className="cursor-pointer font-semibold"><AlertTriangle size={15} className="mr-1 inline" aria-hidden />{v.avisos.length} verificação(ões) não disponível(is) neste aparelho</summary>
          <ul className="mt-2 list-disc pl-5">{v.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}

      <h2 className="mb-3 text-lg font-semibold">Configurações do aparelho</h2>
      {v.achados.length === 0 ? <Vazio>Nenhum problema nas configurações.</Vazio> : (
        <div className="mb-8 space-y-3">
          {v.achados.map((a) => (
            <Cartao key={a.chave + a.titulo} className={`border-l-4 p-4 ${COR_BORDA[a.nivel] ?? ""}`}>
              <div className="flex items-center gap-2"><Selo nivel={a.nivel} /><p className="font-medium">{a.titulo}</p></div>
              <p className="mt-1 text-sm text-fraco">{a.significa}</p>
              <p className="mt-0.5 text-sm"><span className="font-semibold">O que fazer: </span>{a.fazer}</p>
            </Cartao>
          ))}
        </div>
      )}

      <div className="mb-3 mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Apps</h2>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Filtrar por nível">
          {FILTROS.map(([f, nome]) => (
            <button key={f} role="radio" aria-checked={filtro === f} onClick={() => setFiltro(f)}
              className={`rounded-full border px-3 py-1 text-sm ${filtro === f ? "border-destaque bg-destaque-suave text-destaque" : "border-linha hover:bg-superficie-2"}`}>
              {nome}{f in contagem ? ` (${contagem[f]})` : ""}
            </button>
          ))}
        </div>
      </div>
      {!conectado && <p className="mb-3 text-sm text-fraco">Conecte o celular para remover apps.</p>}
      <div className="space-y-3">
        {visiveis.length === 0 ? <Vazio>Nenhum app neste filtro. Ótimo sinal.</Vazio> :
          visiveis.map((r) => (
            <CartaoApp key={r.pacote} r={r} selecionado={selecao.has(r.pacote)} alternar={() => alternar(r.pacote)}
              removido={removidos.has(r.pacote)} podeAgir={conectado && !ocupado} remover={() => setConfirmando([r.pacote])} />
          ))}
      </div>

      {selecao.size > 0 && (
        <div className="entrar fixed inset-x-0 bottom-0 z-20 border-t border-linha bg-superficie/95 p-3 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
            <p className="text-sm"><strong>{selecao.size}</strong> app(s) selecionado(s)</p>
            <div className="flex gap-2">
              <Botao onClick={() => setSelecao(new Set())}>Limpar seleção</Botao>
              <Botao variante="perigo" disabled={ocupado || !conectado} onClick={() => setConfirmando([...selecao])}>
                <Trash2 size={15} aria-hidden /> Remover selecionados
              </Botao>
            </div>
          </div>
        </div>
      )}
      {confirmando && <Confirmar pacotes={confirmando} confirmar={() => executarRemocao(confirmando)} cancelar={() => setConfirmando(null)} />}
    </div>
  );
}
