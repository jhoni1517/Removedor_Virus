import { AlertTriangle, ArrowUp, ChevronDown, PartyPopper, Copy, Download, ExternalLink, FileText, MessageCircle, Monitor, PowerOff,
  RotateCcw, Search, ShieldAlert, SlidersHorizontal, Smartphone, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { BateriaBaixa } from "../bateria";
import { BuscaRapida } from "./BuscaRapida";
import { ehVigilancia, planoDeAcao, planoRemocao } from "../plano";

import { CATEGORIAS, categoriasDoApp, type Categoria } from "../categorias";
import { api, urlLaudo, type Achado, type AppResultado, type Remocao, type Tarefa, type Varredura } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, Data, IconeApp, Medidor, RaioX, Selo, Vazio, duracaoCurta, nomeApp, recente, tamanhoLegivel } from "../ui";
import { AbaAnuncios, AbaInternet, AbaPoderes, AbaSensores, AbaTodos, ApksGuardados } from "./AbasResultado";

type Filtro = "alerta" | "ALTO" | "MÉDIO" | "BAIXO" | "todos";
const FILTROS: [Filtro, string][] = [["alerta", "Com alerta"], ["ALTO", "Alto"], ["MÉDIO", "Médio"], ["BAIXO", "Baixo"], ["todos", "Todos"]];
type Aba = "problemas" | "todos" | "poderes" | "anuncios" | "sensores" | "internet";
const ABAS_VALIDAS: Aba[] = ["problemas", "todos", "poderes", "anuncios", "sensores", "internet"];
function lerLocal<T extends string>(chave: string, validos: readonly T[], padrao: T): T {
  try { const x = localStorage.getItem(chave) as T | null; return x && validos.includes(x) ? x : padrao; } catch { return padrao; }
}
function gravarLocal(chave: string, valor: string) { try { localStorage.setItem(chave, valor); } catch { /* sem storage */ } }


function contagemLimpa(v: Varredura): boolean {
  return !v.resultados.some((r) => r.nivel === "ALTO" || r.nivel === "MÉDIO") && !v.achados.some((a) => a.nivel === "ALTO" || a.nivel === "MÉDIO");
}

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

const ACOES_APP: [string, string][] = [
  ["acessibilidade", "Tirar do controle de tela"],
  ["notificacoes", "Tirar do acesso às notificações"],
  ["sobreposicao", "Bloquear janelas sobre outros apps"],
  ["captura_tela", "Bloquear captura de tela"],
  ["instalar_apps", "Bloquear instalar apps"],
  ["segundo_plano", "Bloquear em segundo plano"],
  ["silenciar", "Silenciar notificações"],
  ["parar", "Forçar parada agora"],
];

function CartaoApp({ r, selecionado, alternar, remover, permissoes, abrirNoCelular, removido, podeAgir, foco }: {
  r: AppResultado; selecionado: boolean; alternar: () => void; remover: () => void;
  permissoes: (pkg: string, acoes: string[]) => void; abrirNoCelular: (pkg: string) => void;
  removido: boolean; podeAgir: boolean; foco?: boolean;
}) {
  const [aberto, setAberto] = useState(r.nivel === "ALTO");
  useEffect(() => { if (foco) setAberto(true); }, [foco]);
  const [ajustar, setAjustar] = useState(false);
  const { avisar } = useApp();
  const copiar = (texto: string, msg: string) => {
    navigator.clipboard?.writeText(texto).then(() => { if (msg) avisar({ tipo: "ok", texto: msg, duracao: 2000 }); }).catch(() => undefined);
  };
  const achados = r.achados.filter((a) => a.chave !== "ameaca_conhecida");
  const acionavel = !r.sistema && r.nivel !== "OK" && r.nivel !== "PERMITIDO" && !removido;
  return (
    <Cartao id={`app-${r.pacote}`} className={`entrar cartao-app border-l-4 ${COR_BORDA[r.nivel] ?? "border-l-ok"} ${removido ? "opacity-60" : ""} ${foco ? "ring-2 ring-destaque" : ""}`}>
      <div className="flex items-start gap-3 p-4">
        {acionavel && (
          <input type="checkbox" className="mt-1.5 h-4 w-4 accent-[var(--destaque)]" checked={selecionado} onChange={alternar}
            aria-label={`Selecionar ${r.pacote}`} disabled={!podeAgir} />
        )}
        <IconeApp nome={r.nome} pacote={r.pacote} icone={r.icone} tamanho={44} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold">{nomeApp(r)}</span>
            <Selo nivel={r.nivel} />
            {recente(r.instalado) && <span className="rounded bg-destaque-suave px-1.5 py-0.5 text-xs font-semibold text-destaque">Novo</span>}
            <span className="numeros font-mono text-xs text-fraco">{r.score} pts</span>
            {removido && <span className="rounded bg-ok-suave px-1.5 py-0.5 text-xs font-semibold text-ok">Removido</span>}
            {r.removido_antes && !removido && <span className="rounded bg-perigo-suave px-1.5 py-0.5 text-xs font-semibold text-perigo"
              title={`O CelScan já tinha removido este app em ${r.removido_antes} e ele foi instalado de novo`}>Voltou</span>}
            {r.rodando && !removido && !r.sistema && <span className="selo-vivo rounded bg-atencao-suave px-1.5 py-0.5 text-xs font-semibold text-atencao"
              title="Estava aberto ou rodando em segundo plano no momento da análise">Rodando agora</span>}
            {r.sensivel && <span className="rounded bg-superficie-2 px-1.5 py-0.5 text-xs text-fraco"
              title="Guarda senhas, códigos de 2 etapas, carteira ou conversas: remover exige confirmação do dono">Dados importantes</span>}
          </div>
          <p className="flex min-w-0 items-center gap-1.5 font-mono text-xs text-fraco">
            <span className="truncate">{r.pacote}</span>
            <button className="shrink-0 rounded p-0.5 hover:bg-superficie-2" title="Copiar o nome do pacote" aria-label={`Copiar ${r.pacote}`}
              onClick={() => copiar(r.pacote, "Pacote copiado.")}><Copy size={12} aria-hidden /></button>
            {r.sha256 && !r.sistema && (
              <a className="inline-flex shrink-0 items-center gap-0.5 font-sans text-destaque hover:underline" target="_blank" rel="noreferrer"
                href={`https://www.virustotal.com/gui/file/${r.sha256}`} title="Abre o resultado deste APK no VirusTotal (só o hash é enviado)"
                onClick={() => copiar(r.sha256!, "")}>VirusTotal <ExternalLink size={11} aria-hidden /></a>
            )}
            {!r.sistema && (
              <a className="inline-flex shrink-0 items-center gap-0.5 font-sans text-destaque hover:underline" target="_blank" rel="noreferrer"
                href={`https://play.google.com/store/apps/details?id=${encodeURIComponent(r.pacote)}`}
                title="Abre a página do app na Play Store para conferir quem publica">
                Play Store <ExternalLink size={11} aria-hidden /></a>
            )}
          </p>
          <p className="mt-0.5 text-xs text-fraco">
            {r.instalado && <>Instalado <Data iso={r.instalado} /> · </>}
            {r.loja ? `pela ${r.loja}` : r.sistema ? "app do sistema" : `fora da loja (${r.origem ?? r.instalador ?? "origem desconhecida"})`}
            {r.ultimo_uso && <> · último uso <Data iso={r.ultimo_uso} /></>}
            {r.versao ? ` · versão ${r.versao}` : ""}
            {r.tamanho ? ` · ${tamanhoLegivel(r.tamanho)}` : ""}
            {r.tempo_uso_s ? ` · ${duracaoCurta(r.tempo_uso_s)} de tela na semana` : ""}
            {r.bateria_mah && r.bateria_mah >= 1 ? ` · ${Math.round(r.bateria_mah).toLocaleString("pt-BR")} mAh de bateria` : ""}
          </p>
          {r.ameaca && (
            <p className="mt-2 flex items-center gap-2 rounded-md bg-perigo-suave px-2 py-1 text-sm font-semibold text-perigo">
              <ShieldAlert size={16} aria-hidden /> {r.ameaca}
            </p>
          )}
          {achados.length === 0 && (r.nivel === "OK" || r.nivel === "PERMITIDO") && (r.seguro_porque?.length ?? 0) > 0 && (
            <p className="mt-1.5 text-xs text-ok">Por que está ok: {r.seguro_porque!.join(" · ")}.</p>
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
          <div className="flex shrink-0 flex-col gap-2">
            <Botao variante={r.nivel === "ALTO" ? "perigo" : "secundario"} onClick={remover} disabled={!podeAgir}
              title={podeAgir ? "Remove o app (fica uma cópia na quarentena)" : "Conecte o celular para agir"}>
              <Trash2 size={15} aria-hidden /> Remover
            </Botao>
            <Botao onClick={() => setAjustar((v) => !v)} disabled={!podeAgir} aria-expanded={ajustar}
              title="Tira poderes do app sem desinstalar">
              <SlidersHorizontal size={15} aria-hidden /> Permissões
            </Botao>
          </div>
        )}
      </div>
      {ajustar && acionavel && (
        <div className="border-t border-linha p-4">
          <p className="mb-2 text-sm text-fraco">Tirar poderes deste app sem desinstalar (dá para desfazer no Histórico):</p>
          <div className="flex flex-wrap gap-2">
            {ACOES_APP.map(([k, nome]) => (
              <Botao key={k} className="py-1" disabled={!podeAgir}
                onClick={() => { permissoes(r.pacote, [k]); setAjustar(false); }}>{nome}</Botao>
            ))}
            <Botao className="py-1" variante="fantasma" disabled={!podeAgir} onClick={() => abrirNoCelular(r.pacote)}
              title="Abre a página deste app nos Ajustes do celular (desinstalar, forçar parada, permissões)">
              <Smartphone size={14} aria-hidden /> Abrir no celular</Botao>
          </div>
        </div>
      )}
    </Cartao>
  );
}

interface Apoio { aviso: string; passos: { titulo: string; texto: string }[]; contatos: { nome: string; descricao: string; contato: string }[]; lgpd: string }


function PainelVitima({ v, espioes }: { v: Varredura; espioes: AppResultado[] }) {
  const { esperar, avisar } = useApp();
  const [apoio, setApoio] = useState<Apoio | null>(null);
  const [documentando, setDocumentando] = useState(false);
  const [pasta, setPasta] = useState<string | null>(null);
  useEffect(() => { api<Apoio>("/apoio").then(setApoio).catch(() => undefined); }, []);

  async function documentar() {
    setDocumentando(true);
    try {
      const t = await esperar(await api<Tarefa<{ pasta: string }>>("/evidencias", {
        corpo: { serial: v.info.serial, varredura_id: v.varredura_id, pacotes: espioes.map((e) => e.pacote) } }));
      if (t.estado === "concluida" && t.resultado) {
        setPasta(t.resultado.pasta);
        avisar({ tipo: "ok", texto: "Provas guardadas no computador, com o hash de cada arquivo.", duracao: 9000 });
      } else avisar({ tipo: "erro", texto: t.erro ?? "Não consegui guardar as provas." });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setDocumentando(false); }
  }

  if (!apoio) return null;
  return (
    <div className="my-3 space-y-3 rounded-lg border border-atencao/50 bg-atencao-suave p-4 text-sm" role="alert">
      <p className="flex items-start gap-2 font-semibold"><ShieldAlert size={18} className="mt-0.5 shrink-0 text-atencao" aria-hidden />{apoio.aviso}</p>
      <ol className="list-decimal space-y-1 pl-5">
        {apoio.passos.map((p) => <li key={p.titulo}><strong>{p.titulo}.</strong> {p.texto}</li>)}
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <Botao variante="primario" onClick={documentar} disabled={documentando || !!pasta}>
          {pasta ? "Provas guardadas" : documentando ? "Guardando..." : "Documentar antes de remover"}
        </Botao>
        {pasta && <span className="break-all font-mono text-xs">{pasta}</span>}
      </div>
      <details>
        <summary className="cursor-pointer font-medium">Onde buscar ajuda</summary>
        <ul className="mt-2 space-y-1">
          {apoio.contatos.map((c) => <li key={c.nome}><strong>{c.nome}</strong> ({c.contato}): {c.descricao}</li>)}
        </ul>
      </details>
    </div>
  );
}

/** Mantém o Tab dentro do diálogo e devolve o foco a quem abriu quando fechar. */
function useFocoPreso(ativo: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ativo) return;
    const antes = document.activeElement as HTMLElement | null;
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !ref.current) return;
      const foco = [...ref.current.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])")]
        .filter((el) => !el.hasAttribute("disabled"));
      if (!foco.length) return;
      const [primeiro, ultimo] = [foco[0], foco[foco.length - 1]];
      if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
    };
    document.addEventListener("keydown", tecla);
    return () => { document.removeEventListener("keydown", tecla); antes?.focus?.(); };
  }, [ativo]);
  return ref;
}

function Confirmar({ v, pacotes, confirmar, cancelar }: { v: Varredura; pacotes: string[]; confirmar: (ciente: boolean, sensivel: boolean) => void; cancelar: () => void }) {
  const espioes = v.resultados.filter((r) => pacotes.includes(r.pacote) && ehVigilancia(r));
  const sensiveis = v.resultados.filter((r) => pacotes.includes(r.pacote) && r.sensivel);
  const [ciente, setCiente] = useState(false);
  const [cienteSensivel, setCienteSensivel] = useState(false);
  const ref = useFocoPreso(true);
  const porPacote = new Map(v.resultados.map((r) => [r.pacote, r]));

  return (
    <div ref={ref} className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="titulo-confirmar"
      onKeyDown={(e) => e.key === "Escape" && cancelar()}>
      <Cartao className="entrar max-h-[90vh] w-full max-w-xl overflow-auto p-6 shadow-xl">
        <h2 id="titulo-confirmar" className="text-lg font-semibold">Remover {pacotes.length} app(s)?</h2>
        <ul className="my-3 max-h-48 space-y-1.5 overflow-auto text-sm">{pacotes.map((p) => {
          const r = porPacote.get(p);
          const plano = r ? planoRemocao(r) : null;
          return <li key={p} className="flex items-start gap-2">
            {r && <IconeApp nome={r.nome} pacote={p} icone={r.icone} tamanho={24} />}
            <span className="min-w-0"><span className="font-medium">{r ? nomeApp(r) : p}</span>
              <span className="ml-2 truncate font-mono text-xs text-fraco">{p}</span>
              {plano && <span className={`block text-xs ${plano.alerta ? "text-atencao" : "text-fraco"}`}>{plano.texto}</span>}</span></li>;
        })}</ul>
        {espioes.length > 0 && <PainelVitima v={v} espioes={espioes} />}
        <BateriaBaixa serial={v.info.serial} />
        <p className="text-sm text-fraco">
          Antes de remover, o CelScan guarda uma cópia de cada app na quarentena e tira as permissões perigosas.
          Você pode desfazer logo em seguida ou depois, pelo Histórico.
        </p>
        {espioes.length > 0 && (
          <label className="mt-3 flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={ciente} onChange={(e) => setCiente(e.target.checked)} />
            <span>Li o aviso e a pessoa dona do celular decidiu remover agora.</span>
          </label>
        )}
        {sensiveis.length > 0 && (
          <label className="mt-3 flex items-start gap-2 rounded-md bg-atencao-suave p-2 text-sm">
            <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={cienteSensivel} onChange={(e) => setCienteSensivel(e.target.checked)} />
            <span><strong>{sensiveis.map(nomeApp).join(", ")}</strong> guarda(m) senhas, códigos de 2 etapas, carteira ou conversas.
              O dono confirmou que tem como entrar nas contas (backup das conversas, códigos de recuperação) antes de remover.</span>
          </label>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Botao onClick={cancelar} autoFocus={espioes.length > 0 || sensiveis.length > 0}>Cancelar</Botao>
          <Botao variante="perigo" onClick={() => confirmar(espioes.length > 0, sensiveis.length > 0)}
            disabled={(espioes.length > 0 && !ciente) || (sensiveis.length > 0 && !cienteSensivel)}
            autoFocus={espioes.length === 0 && sensiveis.length === 0}>Remover</Botao>
        </div>
      </Cartao>
    </div>
  );
}

interface Mudanca { pacote: string; nome: string; nivel?: string; de?: string; para?: string; alertas?: string[] }
interface Diferencas {
  primeira_visita: boolean; anterior_data?: string; sem_mudancas?: boolean;
  nota?: { antes: number | null; depois: number | null };
  apps_novos?: Mudanca[]; apps_removidos?: Mudanca[]; risco_subiu?: Mudanca[]; risco_caiu?: Mudanca[];
  alertas_novos?: Mudanca[]; certificado_trocado?: Mudanca[]; aparelho_novos?: string[]; aparelho_resolvidos?: string[];
}

function DesdeUltimaVisita({ vid }: { vid: number }) {
  const [d, setD] = useState<Diferencas | null>(null);
  useEffect(() => { api<Diferencas>(`/varreduras/${vid}/diferencas`).then(setD).catch(() => undefined); }, [vid]);
  if (!d || d.primeira_visita) return null;
  const data = d.anterior_data ? new Date(d.anterior_data).toLocaleDateString("pt-BR") : "a anterior";
  const linhas: [string, string, Mudanca[] | string[] | undefined][] = [
    ["perigo", "Certificado trocado (app pode ter sido substituído por cópia)", d.certificado_trocado],
    ["perigo", "Risco subiu", d.risco_subiu],
    ["atencao", "Apps novos", d.apps_novos],
    ["atencao", "Alertas novos em apps que já existiam", d.alertas_novos],
    ["atencao", "Problemas novos no aparelho", d.aparelho_novos],
    ["ok", "Risco caiu", d.risco_caiu],
    ["ok", "Problemas resolvidos no aparelho", d.aparelho_resolvidos],
    ["fraco", "Apps que saíram", d.apps_removidos],
  ];
  const nome = (x: Mudanca | string) => typeof x === "string" ? x
    : `${x.nome}${x.de && x.para ? ` (${x.de} → ${x.para})` : ""}${x.alertas ? `: ${x.alertas.join(", ")}` : ""}`;
  return (
    <Cartao className="mb-6 p-5">
      <h2 className="font-semibold">Desde a última visita <span className="text-sm font-normal text-fraco">({data})</span></h2>
      {d.nota && d.nota.antes != null && d.nota.depois != null && (
        <p className="numeros mt-1 text-sm">Nota: {d.nota.antes} → <strong>{d.nota.depois}</strong></p>
      )}
      {d.sem_mudancas ? <p className="mt-2 text-sm text-fraco">Nada mudou desde a última varredura.</p> : (
        <ul className="mt-3 space-y-2 text-sm">
          {linhas.filter(([, , itens]) => itens && itens.length).map(([cor, titulo, itens]) => (
            <li key={titulo}>
              <span className={`font-medium text-${cor}`}>{titulo}:</span>{" "}
              {(itens as (Mudanca | string)[]).slice(0, 6).map(nome).join(" · ")}
              {itens!.length > 6 && ` e mais ${itens!.length - 6}`}
            </li>
          ))}
        </ul>
      )}
    </Cartao>
  );
}

export default function Resultado({ v, onNova }: { v: Varredura; onNova: () => void }) {
  const { dispositivos, esperar, avisar } = useApp();
  const [filtro, setFiltroEstado] = useState<Filtro>(() => lerLocal("celscan-filtro", FILTROS.map(([f]) => f), "alerta"));
  const setFiltro = (f: Filtro) => { setFiltroEstado(f); gravarLocal("celscan-filtro", f); };
  const [selecao, setSelecao] = useState<Set<string>>(new Set());
  const [removidos, setRemovidos] = useState<Set<string>>(new Set());
  const [confirmando, setConfirmando] = useState<string[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aba, setAbaEstado] = useState<Aba>(() => lerLocal("celscan-aba", ABAS_VALIDAS, "problemas"));
  const setAba = (a: Aba) => { setAbaEstado(a); gravarLocal("celscan-aba", a); };
  const [tipo, setTipo] = useState<Categoria | null>(null);
  const [foco, setFoco] = useState<string | null>(null);
  const [busca, setBusca] = useState<string | null>(null);
  const [desfeitos, setDesfeitos] = useState<{ pacote: string; quarentena_id: string }[]>([]);
  const [topo, setTopo] = useState(false);
  const conectado = dispositivos.some((d) => d.serial === v.info.serial && d.estado === "device");
  const nomeDe = (pkg: string) => { const r = v.resultados.find((x) => x.pacote === pkg); return r ? nomeApp(r) : pkg; };

  // Título da janela com o aparelho e a nota (aparece na barra de tarefas)
  useEffect(() => {
    const antes = document.title;
    document.title = `CelScan — ${v.info.modelo}: ${v.nota}/100`;
    return () => { document.title = antes; };
  }, [v]);
  // L3: ícone da aba com a cor da nota (verde/amarelo/vermelho): dá para ver com várias abas abertas
  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
    if (!link) return;
    const antes = link.href;
    const cor = v.nota >= 70 ? "%2316a34a" : v.nota >= 50 ? "%23d97706" : "%23dc2626";
    link.href = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='8' y='3' width='16' height='26' rx='3' fill='${cor}'/%3E%3Cpath d='M12 16l3 3 6-6' stroke='white' stroke-width='2.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E`;
    return () => { link.href = antes; };
  }, [v.nota]);
  const limpo = v.nota >= 90 && contagemLimpa(v);
  // Ctrl+K: busca rápida de app
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setBusca(""); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);
  // Botão "voltar ao topo" quando a lista é longa
  useEffect(() => {
    const main = document.getElementById("conteudo");
    const rolar = () => setTopo((main?.scrollTop ?? window.scrollY) > 900);
    main?.addEventListener("scroll", rolar);
    window.addEventListener("scroll", rolar);
    return () => { main?.removeEventListener("scroll", rolar); window.removeEventListener("scroll", rolar); };
  }, []);

  const contagem = useMemo(() => {
    const c: Record<string, number> = { ALTO: 0, "MÉDIO": 0, BAIXO: 0 };
    v.resultados.forEach((r) => { if (r.nivel in c) c[r.nivel]++; });
    return c;
  }, [v]);
  const porTipo = useMemo(() => {
    const c = new Map<Categoria, number>();
    v.resultados.filter((r) => r.nivel === "ALTO" || r.nivel === "MÉDIO").forEach((r) => categoriasDoApp(r).forEach((k) => c.set(k, (c.get(k) ?? 0) + 1)));
    return c;
  }, [v]);
  const origens = useMemo(() => {
    const c = { loja: 0, outras: 0, fora: 0, sistema: 0 };
    v.resultados.forEach((r) => {
      if (r.sistema) c.sistema++; else if (r.loja === "Google Play") c.loja++; else if (r.loja) c.outras++; else c.fora++;
    });
    return c;
  }, [v]);
  const visiveis = v.resultados.filter((r) =>
    (filtro === "todos" ? true : filtro === "alerta" ? ["ALTO", "MÉDIO", "BAIXO"].includes(r.nivel) : r.nivel === filtro)
    && (!tipo || categoriasDoApp(r).has(tipo)));
  const plano = useMemo(() => planoDeAcao(v), [v]);
  const mesesPatch = (() => {
    const d = new Date(`${v.info.patch_seguranca}T00:00:00`);
    return Number.isNaN(d.getTime()) ? null : Math.floor((Date.now() - d.getTime()) / (30 * 86400000));
  })();

  function resumoTexto(): string {
    const risco = v.resultados.filter((r) => r.nivel === "ALTO" || r.nivel === "MÉDIO");
    const linhas = [`Análise do ${v.info.fabricante} ${v.info.modelo}: nota ${v.nota}/100 (${v.veredito}).`];
    if (risco.length) linhas.push("", "Apps que precisam de atenção:", ...risco.slice(0, 8).map((r) => `- ${nomeApp(r)}: ${r.motivos[0] ?? r.nivel}`));
    else linhas.push("Nenhum app perigoso encontrado.");
    const aparelho = v.achados.filter((a) => a.nivel !== "BAIXO");
    if (aparelho.length) linhas.push("", "No aparelho:", ...aparelho.map((a) => `- ${a.titulo}`));
    if (removidos.size) linhas.push("", `Removidos: ${[...removidos].map(nomeDe).join(", ")}.`);
    return linhas.join("\n");
  }
  async function copiarListaRisco() {
    const risco = v.resultados.filter((r) => r.nivel === "ALTO" || r.nivel === "MÉDIO");
    const linhas = ["App\tPacote\tNível\tPontos\tOrigem\tMotivos",
      ...risco.map((r) => [nomeApp(r), r.pacote, r.nivel, r.score, r.loja ?? r.origem ?? (r.sistema ? "sistema" : "fora da loja"),
        r.motivos.join("; ")].join("\t"))];
    try {
      await navigator.clipboard.writeText(linhas.join("\n"));
      avisar({ tipo: "ok", texto: `${risco.length} app(s) copiados. Cole numa planilha ou no sistema da loja.` });
    } catch { avisar({ tipo: "erro", texto: "Não consegui copiar." }); }
  }
  async function copiarResumo() {
    try { await navigator.clipboard.writeText(resumoTexto()); avisar({ tipo: "ok", texto: "Resumo copiado. Cole no WhatsApp do cliente." }); }
    catch { avisar({ tipo: "erro", texto: "Não consegui copiar. Selecione e copie manualmente." }); }
  }
  function exportarJson() {
    const blob = new Blob([JSON.stringify({ ...v, exportado_em: new Date().toISOString() }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `celscan_varredura_${v.varredura_id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  async function desfazerTudo() {
    const lista = [...desfeitos];
    const falharam: typeof lista = [];
    let ok = 0;
    for (const d of [...lista].reverse()) {
      try {
        const t = await esperar(await api<Tarefa<{ ok: boolean; mensagem: string }>>("/desfazer", {
          corpo: { serial: v.info.serial, quarentena_id: d.quarentena_id } }));
        if (t.estado === "concluida" && t.resultado?.ok) {
          ok++;
          setRemovidos((s) => { const n = new Set(s); n.delete(d.pacote); return n; });
        } else falharam.push(d);
      } catch { falharam.push(d); }
    }
    // antes a lista era zerada mesmo com falhas: o botão sumia e não dava para tentar de novo
    setDesfeitos(falharam);
    avisar({ tipo: ok === lista.length ? "ok" : "erro", texto: `${ok} de ${lista.length} ação(ões) desfeita(s).` });
  }

  async function desfazer(feitos: Remocao[]) {
    for (const f of feitos.filter((x) => x.ok && x.quarentena_id)) {
      try {
        const t = await esperar(await api<Tarefa<{ ok: boolean; mensagem: string }>>("/desfazer", {
          corpo: { serial: v.info.serial, quarentena_id: f.quarentena_id } }));
        if (t.estado === "concluida" && t.resultado?.ok) {
          setRemovidos((s) => { const n = new Set(s); n.delete(f.pacote); return n; });
          setDesfeitos((l) => l.filter((x) => x.quarentena_id !== f.quarentena_id));
          avisar({ tipo: "ok", texto: `${nomeDe(f.pacote)} restaurado.` });
        } else avisar({ tipo: "erro", texto: `Não consegui restaurar ${nomeDe(f.pacote)}: ${t.erro ?? t.resultado?.mensagem ?? ""}` });
      } catch (e) { avisar({ tipo: "erro", texto: `Não consegui restaurar ${nomeDe(f.pacote)}: ${(e as Error).message}` }); }
    }
  }

  async function executarRemocao(pacotes: string[], cienteVitima = false, cienteSensivel = false) {
    setConfirmando(null);
    setOcupado(true);
    try {
      const t = await esperar(await api<Tarefa<Remocao[]>>("/remover", {
        corpo: { serial: v.info.serial, varredura_id: v.varredura_id, pacotes, ciente_vitima: cienteVitima,
          confirmar_sensivel: cienteSensivel } }));
      if (t.estado !== "concluida" || !t.resultado) throw new Error(t.erro ?? "A remoção não terminou.");
      const feitos = t.resultado;
      const ok = feitos.filter((f) => f.ok);
      setRemovidos((s) => new Set([...s, ...ok.map((f) => f.pacote)]));
      setDesfeitos((l) => [...l, ...ok.filter((f) => f.quarentena_id).map((f) => ({ pacote: f.pacote, quarentena_id: f.quarentena_id! }))]);
      setSelecao(new Set());
      feitos.filter((f) => !f.ok).forEach((f) => avisar({ tipo: "erro", texto: `${nomeDe(f.pacote)}: ${f.mensagem}`, duracao: 12000,
        // remoção parcial: o que já foi tirado (acessibilidade, sobreposição) pode ser devolvido;
        // senão, o atalho leva direto à página do app no celular para o técnico resolver por lá
        acao: f.parcial && f.quarentena_id ? { rotulo: "Desfazer o que foi tirado", executar: () => { desfazer([{ ...f, ok: true }]); } }
          : { rotulo: "Abrir no celular", executar: () => { abrirNoCelular(f.pacote); } } }));
      if (ok.length) {
        avisar({ tipo: "ok", texto: `${ok.length} app(s) removido(s). Cópia guardada na quarentena.`, duracao: 10000,
          acao: { rotulo: "Desfazer", executar: () => { desfazer(ok); } } });
        conferir(ok.map((f) => f.pacote));
      }
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    } finally {
      setOcupado(false);
    }
  }

  async function abrirNoCelular(pacote: string) {
    try {
      await api("/abrir-app", { corpo: { serial: v.info.serial, pacote } });
      avisar({ tipo: "ok", texto: `A página de ${nomeDe(pacote)} abriu nos Ajustes do celular.` });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }

  /** Depois de remover: confere se os apps sumiram mesmo e não deixaram acessibilidade/admin/notificações. */
  async function conferir(pacotes: string[]) {
    try {
      const res = await api<{ pacote: string; instalado: boolean; sobrou: string[]; limpo: boolean }[]>("/conferir",
        { corpo: { serial: v.info.serial, pacotes } });
      const sujos = res.filter((r) => !r.limpo);
      if (!sujos.length) avisar({ tipo: "ok", texto: `Conferido no celular: ${pacotes.length} app(s) saíram de vez, sem deixar rastro.` });
      else sujos.forEach((r) => avisar({ tipo: "erro", duracao: 12000,
        texto: `${nomeDe(r.pacote)}: ${r.instalado ? "ainda está instalado" : "saiu"}${r.sobrou.length ? `, mas sobrou: ${r.sobrou.join(", ")}` : ""}.`,
        acao: { rotulo: "Abrir no celular", executar: () => { abrirNoCelular(r.pacote); } } }));
    } catch { /* conferência é um extra: a remoção já foi informada */ }
  }

  async function finalizarAtendimento() {
    if (!window.confirm("Finalizar o atendimento?\n\nO CelScan apaga o que deixou no celular e desliga a Depuração USB e as "
      + "Opções do desenvolvedor. A conexão com este PC cai em seguida.")) return;
    try {
      const r = await api<{ feito: string[] }>("/finalizar", { corpo: { serial: v.info.serial, desligar_depuracao: true } });
      avisar({ tipo: "ok", duracao: 12000, texto: `Atendimento finalizado: ${r.feito.join("; ")}. Pode desconectar o cabo.` });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }

  async function verTela() {
    try {
      await api("/espelho", { corpo: { serial: v.info.serial, modo: "controlar" } });
      avisar({ tipo: "ok", texto: "A tela do celular abriu numa janela nova." });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }

  async function ajustarPermissoes(pacote: string, acoes: string[]) {
    try {
      const t = await esperar(await api<Tarefa<{ feitas: string[]; quarentena_id: string }>>("/permissoes", {
        corpo: { serial: v.info.serial, pacote, acoes } }));
      if (t.estado !== "concluida" || !t.resultado) throw new Error(t.erro ?? "Não terminou.");
      const feitas = t.resultado.feitas;
      const qid = t.resultado.quarentena_id;
      if (feitas.length) setDesfeitos((l) => [...l, { pacote, quarentena_id: qid }]);
      avisar({ tipo: "ok", duracao: 10000, texto: feitas.length ? `${nomeDe(pacote)}: ${feitas.join("; ")}` : "O app já não tinha esse poder.",
        acao: feitas.length ? { rotulo: "Desfazer", executar: async () => {
          try {
            const d = await esperar(await api<Tarefa<{ ok: boolean; mensagem: string }>>("/desfazer", { corpo: { serial: v.info.serial, quarentena_id: qid } }));
            if (d.estado === "concluida" && d.resultado?.ok) {
              setDesfeitos((l) => l.filter((x) => x.quarentena_id !== qid));
              avisar({ tipo: "ok", texto: "Desfeito." });
            } else avisar({ tipo: "erro", texto: `Não consegui desfazer: ${d.erro ?? d.resultado?.mensagem ?? ""}` });
          } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
        } } : undefined });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }

  // Clique no Raio-X ou numa tabela: mostra o cartão do app (troca para a aba certa e rola até ele)
  function abrirApp(pacote: string) {
    const r = v.resultados.find((x) => x.pacote === pacote);
    if (!r) return;
    setAba("problemas");
    if (!["ALTO", "MÉDIO", "BAIXO"].includes(r.nivel) || (filtro !== "todos" && filtro !== "alerta" && filtro !== r.nivel)) setFiltro("todos");
    setFoco(pacote);
    setTimeout(() => document.getElementById(`app-${pacote}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  }

  const abas: [typeof aba, string, number][] = [
    ["problemas", "Problemas", contagem.ALTO + contagem["MÉDIO"] + v.achados.length],
    ["todos", "Todos os apps", v.resultados.length],
    ["poderes", "Poderes especiais", v.resultados.filter((r) => !r.sistema && (r.poderes?.length ?? 0) > 0).length],
    ["anuncios", "Anúncios", v.resultados.filter((r) => r.anuncios && (r.anuncios.tela_cheia || r.anuncios.fora_do_app)).length],
    ["sensores", "Câmera e microfone", v.resultados.filter((r) => Object.values(r.sensores ?? {}).some((s) => s < 7 * 86400)).length],
    ["internet", "Internet por app", 0],
  ];

  function alternar(p: string) {
    setSelecao((s) => { const n = new Set(s); if (n.has(p)) n.delete(p); else n.add(p); return n; });
  }

  return (
    <div className="resultado max-w-6xl pb-24">
      {limpo && (
        <div className="comemorar mb-4 flex items-center gap-3 rounded-lg border border-ok/40 bg-ok-suave p-4 text-ok" role="status">
          <PartyPopper size={22} aria-hidden />
          <p><strong>Celular limpo!</strong> Nenhum app de risco e nada perigoso nas configurações. Bom momento para mostrar o laudo ao cliente.</p>
        </div>
      )}
      <Cartao className="mb-6 flex flex-wrap items-center gap-6 p-6">
        <Medidor nota={v.nota} veredito={v.veredito} />
        <div className="min-w-[220px] flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">{v.info.fabricante} {v.info.modelo}</h1>
          <p className="font-mono text-sm text-fraco">
            Android {v.info.android} · patch {v.info.patch_seguranca}
            {mesesPatch !== null && mesesPatch >= 1 && <span className={mesesPatch >= 12 ? "text-perigo" : mesesPatch >= 6 ? "text-atencao" : ""}> ({mesesPatch} {mesesPatch === 1 ? "mês" : "meses"} atrás)</span>}
            {" · "}{v.info.serial}
          </p>
          <dl className="numeros mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div><dt className="inline text-fraco">Apps: </dt><dd className="inline font-semibold">{v.resultados.length}</dd></div>
            <div><dt className="inline text-perigo">Alto: </dt><dd className="inline font-semibold">{contagem.ALTO}</dd></div>
            <div><dt className="inline text-atencao">Médio: </dt><dd className="inline font-semibold">{contagem["MÉDIO"]}</dd></div>
            <div><dt className="inline text-fraco">Duração: </dt><dd className="inline font-semibold">{Math.round(v.duracao_s)} s</dd></div>
            <div><dt className="inline text-fraco">Varredura nº </dt><dd className="inline font-semibold">{v.varredura_id}</dd></div>
          </dl>
          <p className="numeros mt-1 text-xs text-fraco" title="De onde vieram os apps">
            Play Store {origens.loja} · outras lojas {origens.outras} · fora da loja <span className={origens.fora ? "text-atencao" : ""}>{origens.fora}</span> · de fábrica {origens.sistema}
          </p>
          {(v.decomposicao?.length ?? 0) > 0 && (
            <details className="decomposicao mt-2 text-sm">
              <summary className="cursor-pointer text-fraco">Por que {v.nota}? ({v.decomposicao!.length} item(ns) tiraram pontos)</summary>
              <ul className="mt-1 space-y-0.5">
                {v.decomposicao!.slice(0, 12).map((d, i) => (
                  <li key={i} className="flex justify-between gap-4"><span className="truncate">{d.texto}</span><span className="numeros font-semibold text-perigo">{d.pontos}</span></li>
                ))}
                {v.decomposicao!.length > 12 && <li className="text-fraco">+{v.decomposicao!.length - 12}…</li>}
              </ul>
            </details>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <a className="inline-flex items-center gap-2 rounded-md border border-linha px-3.5 py-2 text-sm font-medium hover:bg-superficie-2"
            href={urlLaudo(v.varredura_id, "cliente")} target="_blank" rel="noreferrer"><FileText size={15} aria-hidden /> Laudo (cliente)</a>
          <a className="inline-flex items-center gap-2 rounded-md border border-linha px-3.5 py-2 text-sm font-medium hover:bg-superficie-2"
            href={urlLaudo(v.varredura_id, "tecnico")} target="_blank" rel="noreferrer"><FileText size={15} aria-hidden /> Laudo técnico</a>
          <a className="inline-flex items-center gap-2 rounded-md border border-linha px-3.5 py-2 text-sm font-medium hover:bg-superficie-2"
            href={urlLaudo(v.varredura_id, "seminovo")} target="_blank" rel="noreferrer"
            title="Bateria, IMEI, espaço, segurança e checklist de hardware (deixe o celular conectado)"><FileText size={15} aria-hidden /> Laudo de seminovo</a>
          <Botao onClick={verTela} disabled={!conectado} title={conectado ? "Abre a tela do celular numa janela" : "Conecte o celular"}>
            <Monitor size={15} aria-hidden /> Ver a tela
          </Botao>
          <Botao onClick={copiarResumo} title="Texto curto para mandar ao cliente"><MessageCircle size={15} aria-hidden /> Copiar resumo</Botao>
          <Botao onClick={copiarListaRisco} disabled={contagem.ALTO + contagem["MÉDIO"] === 0}
            title="Apps de risco alto e médio, em colunas (cola direto numa planilha)"><Copy size={15} aria-hidden /> Copiar lista de risco</Botao>
          <Botao onClick={exportarJson} title="Todos os dados desta varredura em JSON"><Download size={15} aria-hidden /> Exportar JSON</Botao>
          <Botao onClick={() => setBusca("")} title="Procurar um app (Ctrl+K)"><Search size={15} aria-hidden /> Procurar app</Botao>
          {desfeitos.length > 0 && conectado && (
            <Botao onClick={desfazerTudo} title="Restaura tudo que foi removido ou alterado nesta sessão">
              <RotateCcw size={15} aria-hidden /> Desfazer tudo ({desfeitos.length})
            </Botao>
          )}
          <Botao onClick={finalizarAtendimento} disabled={!conectado || ocupado}
            title="Apaga o que o CelScan deixou no celular e desliga a Depuração USB (o cliente não sai com o celular aberto)">
            <PowerOff size={15} aria-hidden /> Finalizar atendimento
          </Botao>
          <Botao variante="fantasma" onClick={onNova}>Nova varredura</Botao>
        </div>
      </Cartao>

      <div className="resultado-grade">
      <RaioX apps={v.resultados} aoEscolher={abrirApp} removidos={removidos} />
      <div className="min-w-0">
      <DesdeUltimaVisita vid={v.varredura_id} />

      {v.avisos.length > 0 && (
        <details className="mb-6 rounded-lg border border-atencao/40 bg-atencao-suave p-4 text-sm text-atencao">
          <summary className="cursor-pointer font-semibold"><AlertTriangle size={15} className="mr-1 inline" aria-hidden />{v.avisos.length} verificação(ões) não disponível(is) neste aparelho</summary>
          <ul className="mt-2 list-disc pl-5">{v.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}

      <div className="abas mb-5" role="tablist" aria-label="Partes do resultado">
        {abas.map(([id, nome, n]) => (
          <button key={id} role="tab" aria-selected={aba === id} onClick={() => setAba(id)}>
            {nome}{n > 0 && <span className="abas-n numeros">{n}</span>}
          </button>
        ))}
      </div>
      {aba === "todos" && <AbaTodos v={v} aoAbrir={abrirApp} />}
      {aba === "poderes" && <AbaPoderes v={v} aoAbrir={abrirApp} />}
      {aba === "anuncios" && <AbaAnuncios v={v} aoAbrir={abrirApp} conectado={conectado} />}
      {aba === "sensores" && <AbaSensores v={v} aoAbrir={abrirApp} />}
      {aba === "internet" && <AbaInternet v={v} aoAbrir={abrirApp} conectado={conectado} />}
      {aba === "problemas" && <>
      {plano.length > 0 && (
        <Cartao className="plano mb-6 p-4">
          <h2 className="mb-2 font-semibold">Plano de ação</h2>
          <ol className="list-decimal space-y-1 pl-5 text-sm">{plano.map((p, i) => <li key={i}>{p}</li>)}</ol>
        </Cartao>
      )}
      <h2 className="mb-3 text-lg font-semibold">Configurações do aparelho</h2>
      {v.achados.length === 0 ? <Vazio>Nenhum problema nas configurações.</Vazio> : (
        <div className="mb-8 space-y-3">
          {v.achados.map((a) => (
            <Cartao key={a.chave + a.titulo} className={`border-l-4 p-4 ${COR_BORDA[a.nivel] ?? ""}`}>
              <div className="flex items-center gap-2"><Selo nivel={a.nivel} /><p className="font-medium">{a.titulo}</p></div>
              <p className="mt-1 text-sm text-fraco">{a.significa}</p>
              <p className="mt-0.5 text-sm"><span className="font-semibold">O que fazer: </span>{a.fazer}</p>
              {(a.chave === "apks_guardados" || a.chave === "apk_ameaca_guardado") && <ApksGuardados serial={v.info.serial} conectado={conectado} />}
            </Cartao>
          ))}
        </div>
      )}

      <div className="mb-3 mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Apps
          <details className="legenda-niveis ml-2 inline-block align-middle text-sm font-normal">
            <summary className="cursor-pointer text-fraco">o que os níveis querem dizer?</summary>
            <dl className="mt-1 space-y-0.5 text-xs">
              <div><dt className="inline font-semibold text-perigo">Alto (60+ pts): </dt><dd className="inline">sinais fortes de golpe, espião ou vírus. Remova, salvo se o cliente reconhecer e confiar.</dd></div>
              <div><dt className="inline font-semibold text-atencao">Médio (30–59): </dt><dd className="inline">comportamento suspeito. Pergunte ao cliente se ele instalou e usa.</dd></div>
              <div><dt className="inline font-semibold">Baixo (1–29): </dt><dd className="inline">detalhe para conferir, normalmente inofensivo.</dd></div>
              <div><dt className="inline font-semibold text-ok">Ok / Permitido: </dt><dd className="inline">nenhum sinal, ou app da lista de permitidos da loja.</dd></div>
            </dl>
          </details>
        </h2>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Filtrar por nível">
          {FILTROS.map(([f, nome]) => (
            <button key={f} role="radio" aria-checked={filtro === f} onClick={() => setFiltro(f)}
              className={`rounded-full border px-3 py-1 text-sm ${filtro === f ? "border-destaque bg-destaque-suave text-destaque" : "border-linha hover:bg-superficie-2"}`}>
              {nome}{f in contagem ? ` (${contagem[f]})` : ""}
            </button>
          ))}
        </div>
      </div>
      {porTipo.size > 0 && (
        <div className="mb-3 flex flex-wrap gap-2" role="radiogroup" aria-label="Filtrar por tipo de problema">
          {CATEGORIAS.filter((c) => porTipo.has(c.id)).map((c) => (
            <button key={c.id} role="radio" aria-checked={tipo === c.id} onClick={() => setTipo(tipo === c.id ? null : c.id)}
              className={`rounded-md border px-2.5 py-0.5 text-xs ${tipo === c.id ? "border-destaque bg-destaque-suave text-destaque" : "border-linha text-fraco hover:bg-superficie-2"}`}>
              {c.nome} <span className="numeros">{porTipo.get(c.id)}</span>
            </button>
          ))}
        </div>
      )}
      {!conectado && <p className="mb-3 text-sm text-fraco">Conecte o celular para remover apps.</p>}
      {conectado && contagem.ALTO > 1 && (
        <Botao className="mb-3" onClick={() => setSelecao(new Set(v.resultados.filter((r) => r.nivel === "ALTO" && !r.sistema && !removidos.has(r.pacote)).map((r) => r.pacote)))}>
          Selecionar os {contagem.ALTO} de risco alto
        </Botao>
      )}
      <div className="space-y-3">
        {visiveis.length === 0 ? <Vazio>Nenhum app neste filtro. Ótimo sinal.</Vazio> :
          visiveis.map((r) => (
            <CartaoApp key={r.pacote} r={r} selecionado={selecao.has(r.pacote)} alternar={() => alternar(r.pacote)}
              removido={removidos.has(r.pacote)} podeAgir={conectado && !ocupado} remover={() => setConfirmando([r.pacote])}
              permissoes={ajustarPermissoes} abrirNoCelular={abrirNoCelular} foco={foco === r.pacote} />
          ))}
      </div>
      </>}
      </div>
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
      {topo && (
        <button className="voltar-topo" aria-label="Voltar ao topo" title="Voltar ao topo"
          onClick={() => { document.getElementById("conteudo")?.scrollTo({ top: 0, behavior: "smooth" }); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
          <ArrowUp size={18} aria-hidden />
        </button>
      )}
      {busca !== null && <BuscaRapida apps={v.resultados} fechar={() => setBusca(null)} escolher={(p) => { setBusca(null); abrirApp(p); }} />}
      {confirmando && <Confirmar v={v} pacotes={confirmando} confirmar={(ciente, sensivel) => executarRemocao(confirmando, ciente, sensivel)} cancelar={() => setConfirmando(null)} />}
    </div>
  );
}
