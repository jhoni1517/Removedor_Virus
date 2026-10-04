import { Check, FolderOpen, Search, Usb } from "lucide-react";
import { useState } from "react";
import { api, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Barra, Botao, Cartao } from "../ui";
import { tamanho } from "./Resgate";

interface Pasta { caminho: string; nome: string }
interface Armazenamento { nome: string; pastas: Pasta[] }
interface AparelhoMtp { nome: string; armazenamentos: Armazenamento[] }
interface Lista { windows: boolean; aparelhos: AparelhoMtp[]; so_carregando: string[] }
interface Resumo { total: number; copiados: number; pulados: number; falhas: string[]; bytes: number; cancelado: boolean; pasta: string }

/** Resgate de fotos e arquivos SEM depuração USB, pelo modo "Transferência de arquivos" do celular. */
export function PainelMtp() {
  const { esperar, avisar, tarefas } = useApp();
  const [lista, setLista] = useState<Lista | null>(null);
  const [procurando, setProcurando] = useState(false);
  const [escolha, setEscolha] = useState<{ aparelho: string; armazenamento: string } | null>(null);
  const [pastas, setPastas] = useState<Set<string>>(new Set());
  const [tarefa, setTarefa] = useState<Tarefa | null>(null);
  const [resumo, setResumo] = useState<Resumo | null>(null);

  function escolher(ap: AparelhoMtp, arm: Armazenamento) {
    setEscolha({ aparelho: ap.nome, armazenamento: arm.nome });
    setPastas(new Set(arm.pastas.map((p) => p.caminho)));
  }

  async function procurar() {
    setProcurando(true); setResumo(null);
    try {
      const r = await api<Lista>("/mtp/aparelhos");
      setLista(r);
      const ap = r.aparelhos[0];
      if (ap?.armazenamentos[0]) escolher(ap, ap.armazenamentos[0]); else setEscolha(null);
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setProcurando(false); }
  }

  async function copiar() {
    if (!escolha) return;
    setResumo(null);
    try {
      const t0 = await api<Tarefa<Resumo>>("/mtp/copiar", { corpo: { ...escolha, pastas: [...pastas] } });
      setTarefa(t0);
      const t = await esperar(t0);
      setTarefa(null);
      if (t.estado === "concluida" && t.resultado) {
        setResumo(t.resultado);
        avisar({ tipo: t.resultado.falhas.length ? "erro" : "ok", texto: `${t.resultado.copiados} arquivo(s) copiado(s) para o PC.` });
      } else avisar({ tipo: "erro", texto: t.erro ?? "A cópia não terminou.", duracao: 12000 });
    } catch (e) { setTarefa(null); avisar({ tipo: "erro", texto: (e as Error).message }); }
  }

  const arm = lista?.aparelhos.find((a) => a.nome === escolha?.aparelho)?.armazenamentos.find((a) => a.nome === escolha?.armazenamento);
  const ev = tarefa ? (tarefas[tarefa.id]?.progresso as Record<string, number | string> | undefined) : undefined;
  const alternar = (c: string) => setPastas((s) => { const n = new Set(s); if (n.has(c)) n.delete(c); else n.add(c); return n; });

  return (
    <Cartao className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold"><Usb size={18} aria-hidden /> Sem depuração? Resgatar fotos e arquivos</h3>
        <Botao onClick={procurar} disabled={procurando || !!tarefa}>
          <Search size={15} aria-hidden /> {procurando ? "Procurando..." : "Procurar celular"}
        </Botao>
      </div>
      <p className="mt-1 text-sm text-fraco">
        Funciona sem ligar a depuração: desbloqueie o celular, ligue o cabo e, no aviso do USB, escolha <strong>Transferência de arquivos</strong>.
        Copia fotos, vídeos, downloads e mídia do WhatsApp. Conversas e dados de apps <strong>não</strong> passam por esse modo. Nada é apagado.
      </p>

      {lista && !lista.windows && <p className="mt-3 text-sm text-atencao">Esse modo só funciona no Windows. Em outro sistema, abra o celular pelo gerenciador de arquivos.</p>}
      {lista?.so_carregando.map((n) => (
        <p key={n} className="mt-3 rounded-lg border border-atencao/40 bg-atencao-suave p-3 text-sm">
          <strong>{n}</strong> está só carregando. Desbloqueie a tela, puxe a barra de notificações, toque no aviso do USB e escolha <strong>Transferência de arquivos</strong>. Depois clique em "Procurar celular".
        </p>
      ))}
      {lista?.windows && lista.aparelhos.length === 0 && lista.so_carregando.length === 0 && (
        <p className="mt-3 text-sm text-fraco">Nenhum celular apareceu. Confira se ele está desbloqueado, se o cabo é de dados (alguns só carregam) e se você escolheu Transferência de arquivos.</p>
      )}

      {lista && lista.aparelhos.length > 0 && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            {lista.aparelhos.flatMap((ap) => ap.armazenamentos.map((a) => {
              const ativo = escolha?.aparelho === ap.nome && escolha.armazenamento === a.nome;
              return (
                <button key={`${ap.nome}/${a.nome}`} onClick={() => escolher(ap, a)}
                  className={`rounded-full border px-3 py-1 text-sm ${ativo ? "border-destaque bg-destaque-suave text-destaque" : "border-linha"}`}>
                  {ap.nome} · {a.nome}
                </button>
              );
            }))}
          </div>
          {arm && arm.pastas.length === 0 && <p className="text-sm text-fraco">Nenhuma pasta de fotos ou arquivos encontrada nesse armazenamento.</p>}
          {arm && arm.pastas.length > 0 && (
            <>
              <div className="grid gap-2 sm:grid-cols-2">
                {arm.pastas.map((p) => (
                  <label key={p.caminho} className="flex cursor-pointer items-center gap-2 rounded-lg border border-linha bg-superficie-2 p-2.5 text-sm">
                    <input type="checkbox" className="accent-[var(--destaque)]" checked={pastas.has(p.caminho)} onChange={() => alternar(p.caminho)} />
                    {p.nome}
                  </label>
                ))}
              </div>
              <Botao variante="primario" onClick={copiar} disabled={!pastas.size || !!tarefa}>
                {tarefa ? "Copiando..." : "Copiar para o computador"}
              </Botao>
            </>
          )}
        </div>
      )}

      {tarefa && (
        <div className="mt-3 space-y-1.5">
          <Barra valor={Number(ev?.atual ?? 0)} total={Number(ev?.total ?? 0) || null} indeterminada={!ev?.total} />
          <p className="truncate font-mono text-xs text-fraco">{ev?.total ? `${ev.atual}/${ev.total} · ` : ""}{String(ev?.detalhe ?? "Contando os arquivos...")}</p>
          <Botao onClick={() => api(`/tarefas/${tarefa.id}/cancelar`, { corpo: {} })}>Pausar</Botao>
        </div>
      )}

      {resumo && (
        <div className="mt-3 rounded-lg border border-linha bg-superficie-2 p-3 text-sm">
          <p className="flex items-center gap-2 text-ok"><Check size={15} aria-hidden /> {resumo.copiados} copiado(s) ({tamanho(resumo.bytes)}){resumo.pulados ? `, ${resumo.pulados} já estavam no PC` : ""}.</p>
          {resumo.cancelado && <p className="text-atencao">Pausado. Clique em Copiar de novo para continuar de onde parou.</p>}
          {resumo.falhas.length > 0 && <p className="text-perigo">{resumo.falhas.length} arquivo(s) não copiaram (o celular bloqueou a tela?). Rode de novo para tentar só esses.</p>}
          <p className="mt-1 break-all font-mono text-xs text-fraco">{resumo.pasta}</p>
          <Botao className="mt-2" onClick={() => api("/abrir-pasta", { corpo: { caminho: resumo.pasta } }).catch((e) => avisar({ tipo: "erro", texto: (e as Error).message }))}>
            <FolderOpen size={15} aria-hidden /> Abrir pasta
          </Botao>
        </div>
      )}
    </Cartao>
  );
}
