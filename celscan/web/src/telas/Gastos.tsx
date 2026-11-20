import { BatteryWarning, HardDrive } from "lucide-react";
import { useState } from "react";
import { api, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao } from "../ui";

interface AppBateria { uid: number; pacotes: string[]; nome: string | null; usuario: boolean; mah: number; pct: number | null; acordado_min: number }
interface Bateria { dreno_mah: number; capacidade_mah: number | null; apps: AppBateria[]; obs: string }

/** Quem gastou a bateria desde a última carga completa, com o botão para segurar o app. */
export function PainelBateria({ serial }: { serial: string }) {
  const { avisar } = useApp();
  const [r, setR] = useState<Bateria | null>(null);
  const [ocupado, setOcupado] = useState("");
  const [limitados, setLimitados] = useState<Set<string>>(new Set());

  async function medir() {
    setOcupado("medir");
    try { setR(await api<Bateria>(`/gastos/bateria?serial=${encodeURIComponent(serial)}`)); }
    catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(""); }
  }
  async function limitar(pacote: string) {
    setOcupado(pacote);
    try {
      const x = await api<{ apps: { ok: boolean }[] }>("/turbo/segundo-plano", { corpo: { serial, pacotes: [pacote], permitir: false } });
      if (x.apps[0]?.ok) { setLimitados((s) => new Set(s).add(pacote)); avisar({ tipo: "ok", texto: "O app agora só roda aberto. Dá para desfazer no Histórico." }); }
      else avisar({ tipo: "info", texto: "Esse app é protegido (sistema, teclado ou essencial)." });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(""); }
  }

  return (
    <Cartao className="p-5">
      <h2 className="flex items-center gap-2 font-semibold"><BatteryWarning size={18} aria-hidden /> Quem gasta a bateria</h2>
      <p className="mt-1 text-sm text-fraco">Consumo por app desde a última carga completa e quanto tempo cada um impediu o celular de dormir.</p>
      <Botao className="mt-3" onClick={medir} disabled={!!ocupado}>{ocupado === "medir" ? "Lendo..." : r ? "Ler de novo" : "Ver quem gasta"}</Botao>
      {r && (
        <div className="mt-3 text-sm">
          <p className="text-fraco">{r.dreno_mah.toLocaleString("pt-BR")} mAh gastos{r.capacidade_mah ? ` (bateria de ${r.capacidade_mah.toLocaleString("pt-BR")} mAh)` : ""}.</p>
          <ul className="mt-2 divide-y divide-linha">
            {r.apps.slice(0, 15).map((a) => {
              const pkg = a.pacotes[0];
              return (
                <li key={a.uid} className="flex items-center justify-between gap-3 py-2">
                  <span className="min-w-0">
                    <span className="block truncate font-mono">{a.nome ?? a.pacotes.join(", ")}</span>
                    <span className="text-fraco numeros">{a.pct != null ? `${a.pct}% · ` : ""}{a.mah} mAh{a.acordado_min >= 1 ? ` · acordado ${a.acordado_min} min` : ""}</span>
                  </span>
                  {a.usuario && pkg && (limitados.has(pkg) ? <span className="text-ok">Limitado</span> :
                    <Botao onClick={() => limitar(pkg)} disabled={!!ocupado}>{ocupado === pkg ? "..." : "Só rodar aberto"}</Botao>)}
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-fraco">{r.obs}</p>
        </div>
      )}
    </Cartao>
  );
}

interface Espaco {
  livre_gb: number | null; total_gb: number | null;
  grandes: { caminho: string; mb: number }[];
  duplicados: { mb: number; arquivos: string[]; sobra_mb: number }[];
  velhos: { id: string; nome: string; arquivos: number; mb: number }[];
}

const nomeArq = (c: string) => c.split("/").pop() ?? c;
const mb = (x: number) => x >= 1024 ? `${(x / 1024).toFixed(1)} GB` : `${Math.round(x)} MB`;

/** O que ocupa o espaço. Tudo que for apagado é copiado antes para o PC. */
export function PainelEspaco({ serial }: { serial: string }) {
  const { esperar, avisar } = useApp();
  const [r, setR] = useState<Espaco | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [ocupado, setOcupado] = useState("");

  async function analisar() {
    setOcupado("analisar"); setSel(new Set());
    try {
      const t = await esperar(await api<Tarefa<Espaco>>("/gastos/espaco", { corpo: { serial } }));
      if (t.estado === "erro") throw new Error(t.erro ?? "Falhou.");
      setR(t.resultado);
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(""); }
  }
  async function apagar(corpo: { caminhos?: string[]; pasta_velha?: string }, rotulo: string) {
    if (!window.confirm(`${rotulo}\n\nUma cópia vai para a pasta "CelScan Backups" deste PC antes de apagar no celular.`)) return;
    setOcupado("apagar");
    try {
      const t = await esperar(await api<Tarefa<{ apagados: unknown[]; falhas: unknown[]; backup: string | null }>>("/gastos/apagar", { corpo: { serial, caminhos: [], ...corpo, backup: true } }));
      const x = t.resultado;
      if (x) avisar({ tipo: x.falhas.length ? "info" : "ok", duracao: 10000, texto: `${x.apagados.length} arquivo(s) apagado(s)${x.falhas.length ? `, ${x.falhas.length} falharam` : ""}. Cópia em: ${x.backup}` });
      await analisar();
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); setOcupado(""); }
  }
  const alternar = (c: string) => setSel((s) => { const n = new Set(s); if (n.has(c)) n.delete(c); else n.add(c); return n; });
  const extras = (r?.duplicados ?? []).flatMap((d) => d.arquivos.slice(1));

  return (
    <Cartao className="p-5">
      <h2 className="flex items-center gap-2 font-semibold"><HardDrive size={18} aria-hidden /> Espaço</h2>
      <p className="mt-1 text-sm text-fraco">Arquivos grandes, repetidos e mídia velha. Antes de apagar, o CelScan copia tudo para este PC.</p>
      <Botao className="mt-3" onClick={analisar} disabled={!!ocupado}>{ocupado === "analisar" ? "Procurando (≈1 min)..." : r ? "Procurar de novo" : "Ver o que ocupa espaço"}</Botao>
      {r && (
        <div className="mt-3 space-y-4 text-sm">
          {r.livre_gb != null && <p><b>{r.livre_gb} GB livres</b> de {r.total_gb} GB.</p>}
          {r.velhos.length > 0 && (
            <div>
              <p className="font-semibold">Mídia com mais de 6 meses</p>
              <ul className="mt-1 space-y-1">
                {r.velhos.map((v) => (
                  <li key={v.id} className="flex items-center justify-between gap-3">
                    <span>{v.nome}: {v.arquivos} arquivo(s), {mb(v.mb)}</span>
                    <Botao onClick={() => apagar({ pasta_velha: v.id }, `Apagar ${v.arquivos} arquivo(s) antigos de ${v.nome}?`)} disabled={!!ocupado}>Guardar no PC e apagar</Botao>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {r.duplicados.length > 0 && (
            <div className="flex items-center justify-between gap-3">
              <span><b>{extras.length} cópia(s) repetida(s)</b> ocupando {mb(r.duplicados.reduce((a, d) => a + d.sobra_mb, 0))} (fica 1 de cada).</span>
              <Botao onClick={() => apagar({ caminhos: extras }, `Apagar ${extras.length} cópia(s) repetida(s)? Fica sempre uma de cada.`)} disabled={!!ocupado}>Apagar repetidos</Botao>
            </div>
          )}
          {r.grandes.length > 0 && (
            <div>
              <p className="font-semibold">Maiores arquivos</p>
              <ul className="mt-1 divide-y divide-linha">
                {r.grandes.slice(0, 20).map((g) => (
                  <li key={g.caminho}><label className="flex cursor-pointer items-center gap-2 py-1">
                    <input type="checkbox" checked={sel.has(g.caminho)} onChange={() => alternar(g.caminho)} />
                    <span className="min-w-0 flex-1 truncate" title={g.caminho}>{nomeArq(g.caminho)}</span>
                    <span className="numeros text-fraco">{mb(g.mb)}</span>
                  </label></li>
                ))}
              </ul>
              {sel.size > 0 && <Botao className="mt-2" variante="primario" onClick={() => apagar({ caminhos: [...sel] }, `Apagar ${sel.size} arquivo(s)?`)} disabled={!!ocupado}>Guardar no PC e apagar ({sel.size})</Botao>}
            </div>
          )}
          {!r.velhos.length && !r.duplicados.length && !r.grandes.length && <p className="text-ok">Nada grande sobrando.</p>}
        </div>
      )}
    </Cartao>
  );
}
