import { FolderOpen, HardDriveDownload, Monitor, MousePointer2, ShieldAlert, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type Dispositivo, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Barra, Botao, Cartao, Titulo } from "../ui";

interface Passo { titulo: string; texto: string; ferramenta?: "otg" | "espelhar" | "backup" }
interface Caso { titulo: string; resumo: string; passos: Passo[]; alternativa?: string }
interface Guia { aviso_consentimento: string; limites: string; casos: Record<string, Caso> }
interface Categorias { categorias: Record<string, string>; padrao: string[]; destino: string }
interface Listagem { categorias: Record<string, { nome: string; arquivos: number; bytes: number }>; total_arquivos: number; total_bytes: number; destino: string }
interface ResumoBackup { destino: string; copiados: number; pulados: number; falhas: { arquivo: string; erro: string }[]; bytes_copiados: number; duracao_s: number }

const ORDEM = ["autorizado", "toque", "imagem", "morto"];

export function tamanho(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes <= 0) return "0 KB";
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

async function abrirPasta(caminho: string, avisar: ReturnType<typeof useApp>["avisar"]) {
  try { await api("/abrir-pasta", { corpo: { caminho } }); } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
}

export function PainelEspelho({ d }: { d: Dispositivo | undefined }) {
  const { avisar } = useApp();
  const [modo, setModo] = useState<"controlar" | "ver">("controlar");
  const [telaDesligada, setTelaDesligada] = useState(false);
  const [gravar, setGravar] = useState(false);
  const [compativel, setCompativel] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const pronto = d?.estado === "device";

  async function abrir() {
    setOcupado(true);
    try {
      const r = await api<{ gravacao: string | null }>("/espelho", { corpo: { serial: d!.serial, modo, tela_desligada: telaDesligada, gravar, compativel } });
      setAberto(true);
      avisar({ tipo: "ok", texto: r.gravacao ? `Tela aberta. Gravando em ${r.gravacao}` : "A tela do celular abriu numa janela nova." });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    } finally {
      setOcupado(false);
    }
  }
  async function fechar() {
    await api("/espelho/parar", { corpo: { serial: d?.serial } }).catch(() => undefined);
    setAberto(false);
  }

  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><Monitor size={18} aria-hidden /> Ver a tela do celular no PC</h3>
      <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label="Modo do espelhamento">
        {([["controlar", "Ver e controlar com mouse e teclado"], ["ver", "Só ver (para mostrar ao cliente)"]] as const).map(([k, nome]) => (
          <button key={k} role="radio" aria-checked={modo === k} onClick={() => setModo(k)}
            className={`rounded-full border px-3 py-1 text-sm ${modo === k ? "border-destaque bg-destaque-suave text-destaque" : "border-linha hover:bg-superficie-2"}`}>{nome}</button>
        ))}
      </div>
      <div className="mt-3 space-y-2 text-sm">
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={telaDesligada}
          onChange={(e) => setTelaDesligada(e.target.checked)} disabled={modo === "ver"} />
          <span>Desligar a tela do celular enquanto espelha <span className="text-fraco">(tela queimada, vazando ou esquentando)</span></span></label>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={gravar}
          onChange={(e) => setGravar(e.target.checked)} /> <span>Gravar a tela em vídeo</span></label>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={compativel}
          onChange={(e) => setCompativel(e.target.checked)} />
          <span>Modo compatível <span className="text-fraco">(PC fraco ou vídeo travando/preto: resolução e taxa menores)</span></span></label>
      </div>
      <p className="mt-2 text-xs text-fraco">Vídeo de streaming com proteção (Netflix, Prime etc.) aparece preto de propósito — isso não tem como contornar.</p>
      <div className="mt-4 flex gap-2">
        <Botao variante="primario" onClick={abrir} disabled={!pronto || ocupado || aberto}><Monitor size={15} aria-hidden /> {ocupado ? "Abrindo..." : "Abrir a tela"}</Botao>
        {aberto && <Botao onClick={fechar}><Square size={14} aria-hidden /> Fechar</Botao>}
      </div>
      {!pronto && <p className="mt-2 text-sm text-fraco">Precisa do celular conectado e autorizado.</p>}
    </Cartao>
  );
}

function PainelOtg() {
  const { avisar } = useApp();
  const [aberto, setAberto] = useState(false);
  async function abrir() {
    try {
      await api("/espelho", { corpo: { modo: "otg" } });
      setAberto(true);
      avisar({ tipo: "ok", texto: "Modo mouse aberto: clique na janela preta e olhe para a tela do celular.", duracao: 9000 });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }
  async function fechar() {
    await api("/espelho/parar", { corpo: { modo: "otg" } }).catch(() => undefined);
    setAberto(false);
  }
  return (
    <div className="mt-2 flex gap-2">
      <Botao variante="primario" onClick={abrir} disabled={aberto}><MousePointer2 size={15} aria-hidden /> Usar o mouse do PC no celular</Botao>
      {aberto && <Botao onClick={fechar}><Square size={14} aria-hidden /> Fechar modo mouse</Botao>}
    </div>
  );
}

export function PainelAtalhos({ d }: { d: Dispositivo | undefined }) {
  const { avisar } = useApp();
  const [ajustes, setAjustes] = useState<Record<string, string>>({});
  const pronto = d?.estado === "device";
  useEffect(() => { api<Record<string, string>>("/ajustes").then(setAjustes).catch(() => undefined); }, []);
  async function abrir(chave: string) {
    try {
      const r = await api<{ aberto: string }>("/ajustes/abrir", { corpo: { serial: d!.serial, ajuste: chave } });
      avisar({ tipo: "ok", texto: `Abri "${r.aberto}" no celular. Olhe a tela (ou o espelho).` });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }
  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><Monitor size={18} aria-hidden /> Abrir ajustes direto no celular</h3>
      <p className="mt-1 text-sm text-fraco">Cai na tela certa sem procurar no menu — combine com o espelho ou o modo mouse.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {Object.entries(ajustes).map(([k, nome]) => (
          <Botao key={k} variante="fantasma" onClick={() => abrir(k)} disabled={!pronto}>{nome}</Botao>
        ))}
      </div>
      {!pronto && <p className="mt-2 text-sm text-fraco">Precisa do celular conectado e autorizado.</p>}
    </Cartao>
  );
}

export function PainelBackup({ d }: { d: Dispositivo | undefined }) {
  const { esperar, avisar, tarefas } = useApp();
  const [cats, setCats] = useState<Categorias | null>(null);
  const [escolhidas, setEscolhidas] = useState<Set<string>>(new Set());
  const [destino, setDestino] = useState("");
  const [verificar, setVerificar] = useState(false);
  const [lista, setLista] = useState<Listagem | null>(null);
  const [tarefa, setTarefa] = useState<Tarefa | null>(null);
  const [resumo, setResumo] = useState<ResumoBackup | null>(null);
  const pronto = d?.estado === "device";

  useEffect(() => {
    if (!d) return;
    api<Categorias>(`/backup/categorias?serial=${encodeURIComponent(d.serial)}`).then((c) => {
      setCats(c);
      setEscolhidas(new Set(c.padrao));
      setDestino(c.destino);
    }).catch(() => undefined);
  }, [d?.serial]);

  const corpo = useMemo(() => ({ serial: d?.serial, categorias: [...escolhidas], destino: destino || null, verificar }),
    [d?.serial, escolhidas, destino, verificar]);

  async function calcular() {
    setLista(null);
    const t = await esperar(await api<Tarefa<Listagem>>("/backup/listar", { corpo }));
    if (t.estado === "concluida" && t.resultado) setLista(t.resultado);
    else avisar({ tipo: "erro", texto: t.erro ?? "Não consegui listar os arquivos." });
  }
  async function copiar() {
    setResumo(null);
    try {
      const t0 = await api<Tarefa<ResumoBackup>>("/backup/copiar", { corpo });
      setTarefa(t0);
      const t = await esperar(t0);
      setTarefa(null);
      if (t.estado === "concluida" && t.resultado) {
        setResumo(t.resultado);
        avisar({ tipo: t.resultado.falhas.length ? "erro" : "ok", texto: `Backup terminado: ${t.resultado.copiados + t.resultado.pulados} arquivo(s) no PC.` });
      } else avisar({ tipo: "erro", texto: t.erro ?? "O backup não terminou.", duracao: 12000 });
    } catch (e) {
      setTarefa(null);
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }

  const ev = tarefa ? (tarefas[tarefa.id]?.progresso as Record<string, number | string> | undefined) : undefined;

  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><HardDriveDownload size={18} aria-hidden /> Copiar os dados para o PC</h3>
      <p className="mt-1 text-sm text-fraco">Só lê do celular: nada é apagado. Se o cabo cair, é só rodar de novo que continua de onde parou.</p>
      {cats && (
        <fieldset className="mt-4 grid gap-2 sm:grid-cols-2" disabled={!!tarefa}>
          <legend className="sr-only">O que copiar</legend>
          {Object.entries(cats.categorias).map(([k, nome]) => {
            const info = lista?.categorias[k];
            return (
              <label key={k} className="flex items-start gap-2 rounded-md border border-linha p-2 text-sm">
                <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={escolhidas.has(k)}
                  onChange={() => setEscolhidas((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; })} />
                <span className="flex-1">{nome}
                  {info && escolhidas.has(k) && <span className="numeros block font-mono text-xs text-fraco">{info.arquivos} arquivo(s) · {tamanho(info.bytes)}</span>}
                </span>
              </label>
            );
          })}
        </fieldset>
      )}
      <div className="mt-4 grid gap-3 text-sm">
        <label className="grid gap-1"><span className="text-fraco">Salvar em</span>
          <input className="rounded-md border border-linha bg-superficie-2 px-3 py-2 font-mono text-xs" value={destino}
            onChange={(e) => setDestino(e.target.value)} disabled={!!tarefa} /></label>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={verificar}
          onChange={(e) => setVerificar(e.target.checked)} disabled={!!tarefa} />
          <span>Conferir cada arquivo byte a byte (SHA-256) <span className="text-fraco">(mais lento; o tamanho é sempre conferido)</span></span></label>
      </div>
      {lista && <p className="numeros mt-3 text-sm"><strong>{lista.total_arquivos}</strong> arquivo(s), <strong>{tamanho(lista.total_bytes)}</strong> no total.</p>}
      {tarefa && (
        <div className="mt-4 space-y-1">
          <Barra valor={Number(ev?.bytes ?? 0)} total={Number(ev?.bytes_total ?? 0) || null} indeterminada={!ev?.bytes_total} />
          <p className="numeros truncate font-mono text-xs text-fraco">
            {ev?.total ? `${ev.atual}/${ev.total} · ` : `${ev?.descricao ?? "Preparando"} · `}
            {ev?.velocidade ? `${tamanho(Number(ev.velocidade))}/s · faltam ~${Math.ceil(Number(ev.estimativa_s) / 60)} min · ` : ""}{String(ev?.detalhe ?? "")}
          </p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {!tarefa && <Botao onClick={calcular} disabled={!pronto || escolhidas.size === 0}>Calcular tamanho</Botao>}
        {!tarefa && <Botao variante="primario" onClick={copiar} disabled={!pronto || escolhidas.size === 0}><HardDriveDownload size={15} aria-hidden /> Copiar para o PC</Botao>}
        {tarefa && <Botao onClick={() => api(`/tarefas/${tarefa.id}/cancelar`, { corpo: {} })}>Pausar</Botao>}
        {destino && <Botao variante="fantasma" onClick={() => abrirPasta(resumo?.destino ?? destino, avisar)}><FolderOpen size={15} aria-hidden /> Abrir pasta</Botao>}
      </div>
      {resumo && (
        <div className={`mt-4 rounded-md border p-3 text-sm ${resumo.falhas.length ? "border-atencao/40 bg-atencao-suave" : "border-ok/40 bg-ok-suave"}`} role="status">
          <p><strong>{resumo.copiados}</strong> copiado(s) agora · <strong>{resumo.pulados}</strong> já estavam no PC · <strong>{resumo.falhas.length}</strong> falha(s) · {tamanho(resumo.bytes_copiados)} em {Math.round(resumo.duracao_s)} s</p>
          {resumo.falhas.slice(0, 5).map((f) => <p key={f.arquivo} className="truncate font-mono text-xs">{f.arquivo}: {f.erro}</p>)}
          <p className="mt-1 text-xs text-fraco">Lista de apps, relatório e LEIA-ME ficam na mesma pasta.</p>
        </div>
      )}
      {!pronto && <p className="mt-2 text-sm text-fraco">Precisa do celular conectado e autorizado.</p>}
    </Cartao>
  );
}

export default function Resgate() {
  const { dispositivos } = useApp();
  const [guia, setGuia] = useState<Guia | null>(null);
  const prontos = dispositivos.filter((d) => d.estado === "device");
  const [serial, setSerial] = useState<string | null>(null);
  const [caso, setCaso] = useState<string | null>(null);
  const d = prontos.find((x) => x.serial === serial) ?? prontos[0];
  const casoAtual = caso ?? (d ? "autorizado" : "toque");

  useEffect(() => { api<Guia>("/resgate").then(setGuia).catch(() => undefined); }, []);
  if (!guia) return <p className="text-fraco">Carregando...</p>;
  const c = guia.casos[casoAtual];

  return (
    <div className="max-w-4xl space-y-6">
      <Titulo sub="Espelhar a tela, controlar pelo PC e salvar fotos e arquivos de um celular com a tela quebrada, queimada ou sem toque.">
        Tela quebrada e backup
      </Titulo>

      <div className="rounded-lg border border-linha bg-superficie-2 p-3 text-sm text-fraco">
        <ShieldAlert size={15} className="mr-1 inline text-atencao" aria-hidden />{guia.aviso_consentimento}
      </div>

      <Cartao className="p-5">
        <p className="text-sm text-fraco">Aparelho</p>
        {prontos.length === 0 ? (
          <p className="mt-1">Nenhum celular autorizado agora. {dispositivos.some((x) => x.estado === "unauthorized") && <strong className="text-atencao">Há um celular esperando você tocar em Permitir.</strong>}</p>
        ) : (
          <div className="mt-2 flex flex-wrap gap-2">
            {prontos.map((x) => (
              <button key={x.serial} onClick={() => { setSerial(x.serial); setCaso("autorizado"); }}
                className={`rounded-full border px-3 py-1 text-sm ${d?.serial === x.serial ? "border-ok bg-ok-suave text-ok" : "border-linha"}`}>
                {x.fabricante ? `${x.fabricante} ${x.modelo}` : x.serial}
              </button>
            ))}
          </div>
        )}
      </Cartao>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Qual é a situação?</h2>
        <div className="grid gap-3 md:grid-cols-2" role="radiogroup" aria-label="Situação do celular">
          {ORDEM.map((k) => (
            <button key={k} role="radio" aria-checked={casoAtual === k} onClick={() => setCaso(k)}
              className={`rounded-lg border p-4 text-left transition ${casoAtual === k ? "border-destaque bg-destaque-suave" : "border-linha bg-superficie hover:bg-superficie-2"}`}>
              <p className="font-semibold">{guia.casos[k].titulo}</p>
              <p className="mt-1 text-sm text-fraco">{guia.casos[k].resumo}</p>
            </button>
          ))}
        </div>
      </div>

      <Cartao className="p-6">
        <h2 className="font-semibold">{c.titulo}</h2>
        <ol className="mt-4 space-y-5">
          {c.passos.map((p, i) => (
            <li key={p.titulo} className="flex gap-3">
              <span className="numeros flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-linha bg-superficie-2 font-mono text-sm">{i + 1}</span>
              <div className="flex-1">
                <p className="font-medium">{p.titulo}</p>
                <p className="text-sm text-fraco">{p.texto}</p>
                {p.ferramenta === "otg" && <PainelOtg />}
              </div>
            </li>
          ))}
        </ol>
        {c.alternativa && <p className="mt-5 rounded-md bg-superficie-2 p-3 text-sm"><strong>Outra saída: </strong>{c.alternativa}</p>}
      </Cartao>

      {casoAtual === "autorizado" && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <PainelEspelho d={d} />
            <PainelBackup d={d} />
          </div>
          <PainelAtalhos d={d} />
        </div>
      )}

      <p className="text-sm text-fraco"><strong>Limite:</strong> {guia.limites}</p>
    </div>
  );
}
