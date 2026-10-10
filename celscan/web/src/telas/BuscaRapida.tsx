import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { AppResultado } from "../api";
import { IconeApp, Selo, nomeApp } from "../ui";

/** Busca rápida (Ctrl+K): digita parte do nome ou do pacote, Enter abre o cartão do app. */
export function BuscaRapida({ apps, fechar, escolher }: { apps: AppResultado[]; fechar: () => void; escolher: (pacote: string) => void }) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const campo = useRef<HTMLInputElement>(null);
  useEffect(() => { campo.current?.focus(); }, []);
  const achados = useMemo(() => {
    const t = q.trim().toLocaleLowerCase("pt-BR");
    const base = t ? apps.filter((r) => nomeApp(r).toLocaleLowerCase("pt-BR").includes(t) || r.pacote.toLowerCase().includes(t)) : apps;
    return base.slice(0, 30);
  }, [q, apps]);
  const atual = Math.min(i, Math.max(0, achados.length - 1));

  function tecla(e: React.KeyboardEvent) {
    if (e.key === "Escape") { e.preventDefault(); fechar(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setI(Math.min(atual + 1, achados.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setI(Math.max(atual - 1, 0)); }
    else if (e.key === "Enter" && achados[atual]) { e.preventDefault(); escolher(achados[atual].pacote); }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-black/40 p-4 pt-[12vh]" onMouseDown={(e) => { if (e.target === e.currentTarget) fechar(); }}>
      <div role="dialog" aria-modal="true" aria-label="Procurar app" className="entrar w-full max-w-lg overflow-hidden rounded-xl border border-linha bg-superficie shadow-2xl">
        <label className="flex items-center gap-2 border-b border-linha px-4 py-3">
          <Search size={16} className="text-fraco" aria-hidden />
          <input ref={campo} value={q} onChange={(e) => { setQ(e.target.value); setI(0); }} onKeyDown={tecla}
            placeholder="Nome ou pacote do app…" aria-label="Nome ou pacote do app" className="w-full bg-transparent outline-none"
            role="combobox" aria-expanded="true" aria-controls="busca-lista" aria-activedescendant={achados[atual] ? `busca-${atual}` : undefined} />
        </label>
        <ul id="busca-lista" role="listbox" className="max-h-[50vh] overflow-auto py-1">
          {achados.length === 0 && <li className="px-4 py-3 text-sm text-fraco">Nenhum app com “{q}”.</li>}
          {achados.map((r, k) => (
            <li key={r.pacote} id={`busca-${k}`} role="option" aria-selected={k === atual}
              onMouseEnter={() => setI(k)} onMouseDown={(e) => { e.preventDefault(); escolher(r.pacote); }}
              className={`flex cursor-pointer items-center gap-3 px-4 py-2 ${k === atual ? "bg-superficie-2" : ""}`}>
              <IconeApp nome={r.nome} pacote={r.pacote} icone={r.icone} tamanho={24} />
              <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{nomeApp(r)}</span>
                <span className="block truncate font-mono text-xs text-fraco">{r.pacote}</span></span>
              <Selo nivel={r.nivel} />
            </li>
          ))}
        </ul>
        <p className="border-t border-linha px-4 py-2 text-xs text-fraco">↑↓ para escolher · Enter abre · Esc fecha</p>
      </div>
    </div>
  );
}
