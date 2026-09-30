import { BadgeCheck, RotateCcw, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, corNota, Titulo, Vazio } from "../ui";

interface LinhaVarredura {
  id: number; serial: string; data: string; modo: string; nota: number; veredito: string;
  apps_total: number; apps_risco: number; fabricante: string; modelo: string;
}
interface ItemQuarentena {
  id: string; pacote: string; serial: string; data: string; acao: string | null; restaurado?: string; motivos: string[];
}
const ACOES: Record<string, string> = {
  removido: "Removido", removido_usuario0: "Removido (usuário)", desativado: "Desativado", ajuste: "Configuração alterada",
};

function data(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export default function Historico({ onAbrir }: { onAbrir: (id: number) => void }) {
  const { dispositivos, esperar, avisar } = useApp();
  const [varreduras, setVarreduras] = useState<LinhaVarredura[] | null>(null);
  const [quarentena, setQuarentena] = useState<ItemQuarentena[]>([]);
  const [codigo, setCodigo] = useState("");
  const [verificado, setVerificado] = useState<{ ok: boolean; texto: string } | null>(null);

  const carregar = useCallback(async () => {
    setVarreduras(await api<LinhaVarredura[]>("/varreduras"));
    setQuarentena(await api<ItemQuarentena[]>("/quarentena"));
  }, []);
  useEffect(() => { carregar().catch(() => setVarreduras([])); }, [carregar]);

  const conectado = (serial: string) => dispositivos.some((d) => d.serial === serial && d.estado === "device");

  async function desfazer(item: ItemQuarentena) {
    try {
      const t = await esperar(await api<Tarefa<{ ok: boolean; mensagem: string }>>("/desfazer", {
        corpo: { serial: item.serial, quarentena_id: item.id } }));
      if (t.estado === "concluida" && t.resultado?.ok) avisar({ tipo: "ok", texto: `${item.pacote}: desfeito.` });
      else avisar({ tipo: "erro", texto: t.erro ?? t.resultado?.mensagem ?? "Não foi possível desfazer." });
      await carregar();
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }

  async function verificar() {
    try {
      const r = await api<{ varredura_id: number; data: string; fabricante: string; modelo: string; nota: number }>(
        `/laudos/verificar?codigo=${encodeURIComponent(codigo)}`);
      setVerificado({ ok: true, texto: `Autêntico: laudo nº ${r.varredura_id} de ${data(r.data)}, ${r.fabricante} ${r.modelo}, nota ${r.nota}.` });
    } catch (e) {
      setVerificado({ ok: false, texto: (e as Error).message });
    }
  }

  return (
    <div className="max-w-5xl">
      <Titulo sub="Varreduras anteriores, tudo o que foi removido ou alterado, e a verificação de laudos.">Histórico</Titulo>

      <Cartao className="mb-8 p-5">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><BadgeCheck size={18} aria-hidden /> Verificar laudo</h2>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); verificar(); }}>
          <input className="w-72 rounded-md border border-linha bg-superficie-2 px-3 py-2 font-mono text-sm uppercase"
            placeholder="XXXX-XXXX-XXXX-XXXX" value={codigo} onChange={(e) => setCodigo(e.target.value)} aria-label="Código de verificação do laudo" />
          <Botao type="submit" disabled={codigo.replace(/-/g, "").length < 16}><Search size={15} aria-hidden /> Verificar</Botao>
        </form>
        {verificado && <p className={`mt-3 text-sm ${verificado.ok ? "text-ok" : "text-perigo"}`} role="status">{verificado.texto}</p>}
      </Cartao>

      <h2 className="mb-3 text-lg font-semibold">Varreduras</h2>
      {varreduras === null ? <p className="text-fraco">Carregando...</p> : varreduras.length === 0 ? <Vazio>Nenhuma varredura ainda.</Vazio> : (
        <Cartao className="mb-8 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-superficie-2 text-left text-fraco">
              <tr><th className="p-3 font-medium">Data</th><th className="p-3 font-medium">Aparelho</th><th className="p-3 font-medium">Nota</th>
                <th className="p-3 font-medium">Apps</th><th className="p-3 font-medium">Com risco</th><th className="p-3" /></tr>
            </thead>
            <tbody className="divide-y divide-linha">
              {varreduras.map((v) => (
                <tr key={v.id} className="hover:bg-superficie-2">
                  <td className="numeros p-3 font-mono">{data(v.data)}</td>
                  <td className="p-3">{v.fabricante} {v.modelo} <span className="font-mono text-xs text-fraco">{v.serial}</span></td>
                  <td className="numeros p-3 font-mono font-semibold" style={{ color: corNota(v.nota) }}>{v.nota} <span className="font-sans text-xs">{v.veredito}</span></td>
                  <td className="numeros p-3 font-mono">{v.apps_total}</td>
                  <td className="numeros p-3 font-mono">{v.apps_risco}</td>
                  <td className="p-3 text-right"><Botao variante="fantasma" onClick={() => onAbrir(v.id)}>Abrir</Botao></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>
      )}

      <h2 className="mb-3 text-lg font-semibold">Quarentena e alterações</h2>
      {quarentena.length === 0 ? <Vazio>Nada foi removido ou alterado ainda.</Vazio> : (
        <div className="space-y-2">
          {quarentena.map((q) => (
            <Cartao key={q.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm font-semibold">{q.pacote}</p>
                <p className="text-xs text-fraco">{ACOES[q.acao ?? ""] ?? q.acao ?? "Incompleto"} · {data(q.data)} · {q.serial}
                  {q.restaurado ? ` · desfeito em ${data(q.restaurado)}` : ""}</p>
              </div>
              {!q.restaurado && q.acao && (
                <Botao onClick={() => desfazer(q)} disabled={!conectado(q.serial)}
                  title={conectado(q.serial) ? "Reinstala o app / volta a configuração" : "Conecte este aparelho para desfazer"}>
                  <RotateCcw size={15} aria-hidden /> Desfazer
                </Botao>
              )}
            </Cartao>
          ))}
        </div>
      )}
    </div>
  );
}
