// Modo cliente: segunda tela virada para o cliente. Mostra a última análise em linguagem simples,
// sem botões de ação, e atualiza sozinho quando o técnico termina uma nova varredura.
import { useEffect, useState } from "react";
import { api, obterVarredura, type Varredura } from "../api";
import { useApp } from "../estado";
import { Cartao, Data, IconeApp, Medidor, RaioX, nomeApp } from "../ui";

export default function ModoCliente() {
  const { tarefas, estado } = useApp();
  const [v, setV] = useState<Varredura | null>(null);
  const analisando = Object.values(tarefas).find((t) => t.tipo === "varredura" && t.estado === "executando");

  useEffect(() => {
    let atual: number | null = null;
    let parar = false;
    const ler = async () => {
      try {
        const lista = await api<{ id: number }[]>("/varreduras?limite=1");
        if (!parar && lista[0] && lista[0].id !== atual) {
          atual = lista[0].id;
          setV(await obterVarredura(atual));
        }
      } catch { /* tenta de novo */ }
    };
    ler();
    const t = setInterval(ler, 4000);
    return () => { parar = true; clearInterval(t); };
  }, []);

  if (analisando) {
    const p = analisando.progresso;
    const pct = p.total ? Math.round(((p.atual ?? 0) / p.total) * 100) : 0;
    return (
      <div className="cliente-centro">
        <h1 className="cliente-titulo">Analisando o seu celular</h1>
        <p className="text-fraco">{p.descricao ?? "Preparando"}</p>
        <div className="mt-6 h-3 w-full max-w-xl overflow-hidden rounded-full bg-superficie-2" aria-hidden>
          <div className="h-full bg-destaque transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  }
  if (!v) {
    return (
      <div className="cliente-centro">
        <h1 className="cliente-titulo">Análise de segurança do celular</h1>
        <p className="text-fraco">Aguardando a primeira análise{estado?.versao ? "" : "..."}</p>
      </div>
    );
  }
  const problemas = v.resultados.filter((r) => r.nivel === "ALTO" || r.nivel === "MÉDIO");
  return (
    <div className="resultado-grade mx-auto max-w-6xl">
      <RaioX apps={v.resultados} />
      <div className="space-y-4">
        <Cartao className="flex flex-wrap items-center gap-6 p-6">
          <Medidor nota={v.nota} veredito={v.veredito} />
          <div>
            <h1 className="cliente-titulo">{problemas.length ? `Encontramos ${problemas.length} app(s) que precisam de atenção` : "Nenhum app perigoso encontrado"}</h1>
            <p className="text-fraco">{v.info.fabricante} {v.info.modelo}</p>
          </div>
        </Cartao>
        {v.achados.filter((a) => a.nivel !== "BAIXO").map((a) => (
          <Cartao key={a.chave + a.titulo} className="border-l-4 border-l-atencao p-4">
            <p className="font-semibold">{a.titulo}</p><p className="text-fraco">{a.significa}</p>
          </Cartao>
        ))}
        {problemas.map((r) => (
          <Cartao key={r.pacote} className={`flex items-start gap-4 border-l-4 p-4 ${r.nivel === "ALTO" ? "border-l-perigo" : "border-l-atencao"}`}>
            <IconeApp nome={r.nome} pacote={r.pacote} icone={r.icone} tamanho={48} />
            <div>
              <p className="text-lg font-semibold">{nomeApp(r)}</p>
              <p className="text-fraco">{r.achados[0]?.significa}</p>
              <p className="mt-1 text-sm text-fraco">
                {r.sistema ? "Veio de fábrica" : r.loja ? `Baixado da ${r.loja}` : "Instalado fora da loja"}
                {r.instalado && <> · instalado <Data iso={r.instalado} /></>}
              </p>
            </div>
          </Cartao>
        ))}
      </div>
    </div>
  );
}
