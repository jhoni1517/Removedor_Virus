import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao } from "../ui";

interface Estado { play_protect: boolean; instaladores: string[]; dns: string | null; dns_golpes: boolean; nota: number; checklist: { id: string; texto: string }[] }

/** Depois de limpar: fecha as portas por onde o vírus entrou. Tudo volta pelo Histórico. */
export function PainelBlindagem({ serial, destaque = false }: { serial: string; destaque?: boolean }) {
  const { avisar } = useApp();
  const [e, setE] = useState<Estado | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [feitos, setFeitos] = useState<Set<string>>(new Set());
  const carregar = () => api<Estado>(`/blindagem?serial=${encodeURIComponent(serial)}`).then(setE).catch(() => undefined);
  useEffect(() => { carregar(); }, [serial]);

  async function blindar() {
    if (!e) return;
    const itens = [!e.play_protect && "play_protect", e.instaladores.length > 0 && "instaladores", !e.dns && "dns"].filter(Boolean);
    if (!itens.length) return;
    setOcupado(true);
    try {
      const r = await api<{ estado: Estado }>("/blindagem", { corpo: { serial, itens } });
      setE(r.estado);
      avisar({ tipo: "ok", texto: "Celular blindado. Dá para desfazer no Histórico." });
    } catch (x) { avisar({ tipo: "erro", texto: (x as Error).message }); }
    finally { setOcupado(false); }
  }

  const marcar = (id: string) => setFeitos((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const falta = e ? 3 - e.nota : 0;
  return (
    <Cartao className={`p-5 ${destaque ? "border-ok/50" : ""}`}>
      <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck size={18} aria-hidden /> Blindar o celular</h2>
      <p className="mt-1 text-sm text-fraco">Fecha as portas por onde o vírus entra de novo.</p>
      {e && (
        <ul className="mt-3 space-y-1 text-sm">
          <li>{e.play_protect ? "✓" : "✗"} Play Protect {e.play_protect ? "ligado" : "desligado"}</li>
          <li>{e.instaladores.length ? `✗ ${e.instaladores.length} app(s) de fora da loja podem instalar outros apps` : "✓ Só a loja instala apps"}
            {e.instaladores.length > 0 && <span className="block font-mono text-xs text-fraco">{e.instaladores.join(", ")}</span>}</li>
          <li>{e.dns ? `✓ DNS protegido (${e.dns})` : "✗ Sem DNS contra sites de golpe"}</li>
        </ul>
      )}
      {e && falta > 0 && <Botao className="mt-3" variante="primario" onClick={blindar} disabled={ocupado}>{ocupado ? "Blindando..." : "Blindar agora"}</Botao>}
      {e && (
        <div className="mt-4">
          <p className="text-sm font-semibold">Só o dono do celular pode fazer</p>
          <ul className="mt-1 space-y-1 text-sm">
            {e.checklist.map((c) => (
              <li key={c.id}><label className="flex cursor-pointer gap-2"><input type="checkbox" checked={feitos.has(c.id)} onChange={() => marcar(c.id)} /> <span className={feitos.has(c.id) ? "text-fraco line-through" : ""}>{c.texto}</span></label></li>
            ))}
          </ul>
        </div>
      )}
    </Cartao>
  );
}
