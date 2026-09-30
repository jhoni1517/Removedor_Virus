import { FileSearch, FolderOpen, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type Dispositivo, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Barra, Botao, Cartao, Titulo } from "../ui";
import { tamanho } from "./Resgate";

interface Cats { categorias: Record<string, string>; padrao: string[]; aviso: string }
interface Achados { categorias: Record<string, { nome: string; arquivos: number; bytes: number }>; total_arquivos: number; total_bytes: number }
interface ResumoBackup { destino: string; copiados: number; pulados: number; falhas: { arquivo: string; erro: string }[]; bytes_copiados: number; duracao_s: number }

async function abrirPasta(caminho: string, avisar: ReturnType<typeof useApp>["avisar"]) {
  try { await api("/abrir-pasta", { corpo: { caminho } }); } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
}

function Painel({ d }: { d: Dispositivo | undefined }) {
  const { esperar, avisar, tarefas } = useApp();
  const [cats, setCats] = useState<Cats | null>(null);
  const [escolhidas, setEscolhidas] = useState<Set<string>>(new Set());
  const [achados, setAchados] = useState<Achados | null>(null);
  const [tarefa, setTarefa] = useState<Tarefa | null>(null);
  const [resumo, setResumo] = useState<ResumoBackup | null>(null);
  const pronto = d?.estado === "device";

  useEffect(() => {
    api<Cats>("/recuperacao/categorias").then((c) => { setCats(c); setEscolhidas(new Set(c.padrao)); }).catch(() => undefined);
  }, []);

  const corpo = useMemo(() => ({ serial: d?.serial, categorias: [...escolhidas] }), [d?.serial, escolhidas]);

  async function procurar() {
    setAchados(null);
    const t = await esperar(await api<Tarefa<Achados>>("/recuperacao/procurar", { corpo }));
    if (t.estado === "concluida" && t.resultado) setAchados(t.resultado);
    else avisar({ tipo: "erro", texto: t.erro ?? "Não consegui procurar." });
  }
  async function recuperar() {
    setResumo(null);
    try {
      const t0 = await api<Tarefa<ResumoBackup>>("/recuperacao/recuperar", { corpo });
      setTarefa(t0);
      const t = await esperar(t0);
      setTarefa(null);
      if (t.estado === "concluida" && t.resultado) {
        setResumo(t.resultado);
        avisar({ tipo: t.resultado.falhas.length ? "erro" : "ok", texto: `Recuperados ${t.resultado.copiados} arquivo(s).` });
      } else avisar({ tipo: "erro", texto: t.erro ?? "A recuperação não terminou." });
    } catch (e) { setTarefa(null); avisar({ tipo: "erro", texto: (e as Error).message }); }
  }

  const ev = tarefa ? (tarefas[tarefa.id]?.progresso as Record<string, number | string> | undefined) : undefined;
  return (
    <Cartao className="p-5">
      <h3 className="flex items-center gap-2 font-semibold"><FileSearch size={18} aria-hidden /> Procurar sobras recuperáveis</h3>
      {cats && (
        <fieldset className="mt-4 grid gap-2 sm:grid-cols-2" disabled={!!tarefa}>
          <legend className="sr-only">O que procurar</legend>
          {Object.entries(cats.categorias).map(([k, nome]) => {
            const info = achados?.categorias[k];
            return (
              <label key={k} className="flex items-start gap-2 rounded-md border border-linha p-2 text-sm">
                <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={escolhidas.has(k)}
                  onChange={() => setEscolhidas((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; })} />
                <span className="flex-1">{nome}
                  {info && <span className="numeros block font-mono text-xs text-fraco">{info.arquivos} arquivo(s) · {tamanho(info.bytes)}</span>}
                </span>
              </label>
            );
          })}
        </fieldset>
      )}
      {achados && <p className="numeros mt-3 text-sm"><strong>{achados.total_arquivos}</strong> arquivo(s), <strong>{tamanho(achados.total_bytes)}</strong> recuperável(is).</p>}
      {tarefa && (
        <div className="mt-4 space-y-1">
          <Barra valor={Number(ev?.bytes ?? 0)} total={Number(ev?.bytes_total ?? 0) || null} indeterminada={!ev?.bytes_total} />
          <p className="numeros truncate font-mono text-xs text-fraco">{ev?.total ? `${ev.atual}/${ev.total}` : String(ev?.descricao ?? "Preparando")} · {String(ev?.detalhe ?? "")}</p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {!tarefa && <Botao onClick={procurar} disabled={!pronto || escolhidas.size === 0}>Procurar</Botao>}
        {!tarefa && <Botao variante="primario" onClick={recuperar} disabled={!pronto || escolhidas.size === 0}><Undo2 size={15} aria-hidden /> Recuperar para o PC</Botao>}
        {resumo && <Botao variante="fantasma" onClick={() => abrirPasta(resumo.destino, avisar)}><FolderOpen size={15} aria-hidden /> Abrir pasta</Botao>}
      </div>
      {resumo && (
        <div className={`mt-4 rounded-md border p-3 text-sm ${resumo.falhas.length ? "border-atencao/40 bg-atencao-suave" : "border-ok/40 bg-ok-suave"}`} role="status">
          <p><strong>{resumo.copiados}</strong> recuperado(s) · <strong>{resumo.falhas.length}</strong> falha(s) · {tamanho(resumo.bytes_copiados)}</p>
          <p className="mt-1 text-xs text-fraco">Tudo vai para a subpasta "Recuperados". Dados pessoais: entregue e apague do PC depois (LGPD).</p>
        </div>
      )}
      {!pronto && <p className="mt-2 text-sm text-fraco">Precisa do celular conectado e autorizado.</p>}
    </Cartao>
  );
}

export default function Recuperar() {
  const { dispositivos } = useApp();
  const prontos = dispositivos.filter((x) => x.estado === "device");
  const [cats, setCats] = useState<Cats | null>(null);
  useEffect(() => { api<Cats>("/recuperacao/categorias").then(setCats).catch(() => undefined); }, []);
  const d = prontos[0];

  return (
    <div className="max-w-4xl space-y-6">
      <Titulo sub="Resgata o que ainda está no aparelho, só escondido: lixeira da galeria, miniaturas e mídia deixada nos apps.">
        Recuperar arquivos
      </Titulo>
      {cats && (
        <div className="rounded-lg border border-atencao/40 bg-atencao-suave p-3 text-sm">{cats.aviso}</div>
      )}
      <Painel d={d} />
    </div>
  );
}
