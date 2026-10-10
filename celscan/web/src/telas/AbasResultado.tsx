// Abas extras do resultado: anúncios/pop-ups, câmera e microfone, internet por app e lista completa.
import { Camera, Crosshair, Megaphone, Wifi } from "lucide-react";
import { useMemo, useState } from "react";
import { api, type AppResultado, type Consumo, type NaTela, type Varredura } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, IconeApp, Selo, Vazio, dataBr, nomeApp, quando } from "../ui";

function LinhaApp({ r, aoAbrir, children }: { r: AppResultado; aoAbrir: (p: string) => void; children?: React.ReactNode }) {
  return (
    <button type="button" onClick={() => aoAbrir(r.pacote)} className="flex min-w-0 items-center gap-3 text-left hover:underline">
      <IconeApp nome={r.nome} pacote={r.pacote} icone={r.icone} tamanho={32} />
      <span className="min-w-0">
        <span className="block truncate font-medium">{nomeApp(r)}</span>
        <span className="block truncate font-mono text-xs text-fraco">{r.pacote}</span>
        {children}
      </span>
    </button>
  );
}

export function AbaAnuncios({ v, aoAbrir, conectado }: { v: Varredura; aoAbrir: (p: string) => void; conectado: boolean }) {
  const { avisar } = useApp();
  const [flagra, setFlagra] = useState<(NaTela & { r?: AppResultado }) | null>(null);
  const lista = useMemo(() => v.resultados
    .filter((r) => r.anuncios && (r.anuncios.tela_cheia || r.anuncios.fora_do_app || (r.anuncios.sdks.length && r.sobreposicao)))
    .sort((a, b) => (b.anuncios!.fora_do_app - a.anuncios!.fora_do_app) || (b.anuncios!.tela_cheia - a.anuncios!.tela_cheia)), [v]);
  const spam = v.resultados.filter((r) => (r.notificacoes ?? 0) > 0).sort((a, b) => (b.notificacoes ?? 0) - (a.notificacoes ?? 0)).slice(0, 8);

  async function quemEsta() {
    try {
      const x = await api<NaTela>("/na-tela", { corpo: { serial: v.info.serial } });
      setFlagra({ ...x, r: v.resultados.find((r) => r.pacote === x.pacote) });
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }

  return (
    <div className="space-y-4">
      <Cartao className="flex flex-wrap items-center gap-4 p-4">
        <Crosshair size={22} className="text-destaque" aria-hidden />
        <div className="min-w-[240px] flex-1">
          <p className="font-medium">Pegue o pop-up no flagra</p>
          <p className="text-sm text-fraco">Quando a propaganda aparecer no celular, não feche: clique aqui e o CelScan diz qual app abriu.</p>
        </div>
        <Botao variante="primario" onClick={quemEsta} disabled={!conectado}>Quem está na tela agora?</Botao>
        {flagra && (
          <div className="w-full rounded-lg border border-linha bg-superficie-2 p-3 text-sm" role="status">
            <p><strong>{flagra.r ? nomeApp(flagra.r) : flagra.pacote}</strong> <span className="font-mono text-xs text-fraco">{flagra.pacote}</span></p>
            <p className="text-fraco">{flagra.anuncio ? `Está mostrando um anúncio da rede ${flagra.anuncio}.` : "Não é uma tela de anúncio conhecida."}
              {flagra.r && <> <button className="ml-1 text-destaque underline" onClick={() => aoAbrir(flagra.pacote)}>Ver o app na lista</button></>}</p>
          </div>
        )}
      </Cartao>
      <p className="text-sm text-fraco">
        Pop-up fora do app é a propaganda que aparece na tela inicial ou por cima de outro app. O CelScan cruza o histórico de telas
        do Android com as redes de anúncio conhecidas.
      </p>
      {lista.length === 0 ? <Vazio>Nenhum app mostrando anúncios fora do comum.</Vazio> : (
        <Cartao className="overflow-x-auto">
          <table className="tabela w-full text-sm">
            <thead><tr><th>App</th><th className="num">Pop-ups fora do app</th><th className="num">Em tela cheia</th><th>Último</th><th>Redes de anúncio</th></tr></thead>
            <tbody>
              {lista.map((r) => (
                <tr key={r.pacote}>
                  <td><LinhaApp r={r} aoAbrir={aoAbrir} /></td>
                  <td className={`num font-semibold ${r.anuncios!.fora_do_app ? "text-perigo" : ""}`}>{r.anuncios!.fora_do_app}</td>
                  <td className="num">{r.anuncios!.tela_cheia}</td>
                  <td>{dataBr(r.anuncios!.ultimo, true)}</td>
                  <td>{r.anuncios!.sdks.join(", ") || "—"}{r.anuncios!.gatilhos.length > 0 &&
                    <span className="block text-xs text-fraco">Escuta: {r.anuncios!.gatilhos.join(", ")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>
      )}
      {spam.length > 0 && (
        <Cartao className="p-4">
          <h3 className="mb-2 flex items-center gap-2 font-semibold"><Megaphone size={16} aria-hidden /> Quem mais manda notificação</h3>
          <ul className="space-y-2 text-sm">
            {spam.map((r) => <li key={r.pacote} className="flex items-center justify-between gap-3">
              <LinhaApp r={r} aoAbrir={aoAbrir} /><span className="numeros font-semibold">{r.notificacoes}</span></li>)}
          </ul>
        </Cartao>
      )}
    </div>
  );
}

export function AbaSensores({ v, aoAbrir }: { v: Varredura; aoAbrir: (p: string) => void }) {
  const usos = v.resultados.flatMap((r) => Object.entries(r.sensores ?? {}).filter(([, s]) => s < 7 * 86400)
    .map(([sensor, seg]) => ({ r, sensor, seg }))).sort((a, b) => a.seg - b.seg);
  if (!usos.length) return <Vazio>Nenhum uso de câmera, microfone, localização ou SMS registrado nos últimos 7 dias.</Vazio>;
  return (
    <Cartao className="overflow-x-auto">
      <p className="flex items-center gap-2 px-4 pt-4 text-sm text-fraco"><Camera size={15} aria-hidden /> Últimos 7 dias, segundo o próprio Android.</p>
      <table className="tabela w-full text-sm">
        <thead><tr><th>App</th><th>Usou</th><th>Quando</th><th>Origem</th></tr></thead>
        <tbody>
          {usos.map(({ r, sensor, seg }) => (
            <tr key={r.pacote + sensor}>
              <td><LinhaApp r={r} aoAbrir={aoAbrir} /></td>
              <td className="capitalize">{sensor}</td>
              <td>{quando(seg)}</td>
              <td>{r.loja ?? (r.sistema ? "Sistema" : <span className="text-atencao">Fora da loja</span>)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Cartao>
  );
}

export function AbaInternet({ v, aoAbrir, conectado }: { v: Varredura; aoAbrir: (p: string) => void; conectado: boolean }) {
  const { avisar } = useApp();
  const [dados, setDados] = useState<Consumo | null>(null);
  const [lendo, setLendo] = useState(false);
  async function ler() {
    setLendo(true);
    try { setDados(await api<Consumo>("/consumo", { corpo: { serial: v.info.serial } })); }
    catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setLendo(false); }
  }
  const por = new Map(v.resultados.map((r) => [r.pacote, r]));
  const maximo = Math.max(1, ...(dados?.apps ?? []).map((a) => a.total_mb));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Botao variante="primario" onClick={ler} disabled={!conectado || lendo}><Wifi size={15} aria-hidden /> {lendo ? "Lendo..." : dados ? "Ler de novo" : "Ver quem gasta internet"}</Botao>
        <span className="text-sm text-fraco">{dados?.observacao ?? "Mostra dados móveis e Wi-Fi por app, direto das estatísticas do Android."}</span>
      </div>
      {dados && !dados.disponivel && <Vazio>Este aparelho não expôs o consumo por app pelo cabo.</Vazio>}
      {dados?.disponivel && (
        <Cartao className="overflow-x-auto">
          <table className="tabela w-full text-sm">
            <thead><tr><th>App</th><th className="num">Dados móveis</th><th className="num">Wi-Fi</th><th className="num">Enviado</th><th className="w-1/4">Total</th></tr></thead>
            <tbody>
              {dados.apps.map((a) => {
                const r = por.get(a.pacote);
                return (
                  <tr key={a.pacote}>
                    <td>{r ? <LinhaApp r={r} aoAbrir={aoAbrir} /> : <span className="font-mono text-xs">{a.pacote}</span>}</td>
                    <td className="num">{a.movel_mb} MB</td><td className="num">{a.wifi_mb} MB</td>
                    <td className={`num ${r && !r.loja && !r.sistema && a.enviado_mb > 50 ? "font-semibold text-perigo" : ""}`}>{a.enviado_mb} MB</td>
                    <td><span className="barra-consumo" style={{ width: `${(a.total_mb / maximo) * 100}%` }} aria-label={`${a.total_mb} MB`} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Cartao>
      )}
    </div>
  );
}

export function AbaTodos({ v, aoAbrir }: { v: Varredura; aoAbrir: (p: string) => void }) {
  const [busca, setBusca] = useState("");
  const [ordem, setOrdem] = useState<"risco" | "nome" | "instalado" | "uso">("risco");
  const lista = v.resultados
    .filter((r) => !busca || `${r.nome ?? ""} ${r.pacote}`.toLowerCase().includes(busca.toLowerCase()))
    .sort((a, b) => ordem === "nome" ? nomeApp(a).localeCompare(nomeApp(b), "pt-BR")
      : ordem === "instalado" ? (b.instalado ?? "").localeCompare(a.instalado ?? "")
      : ordem === "uso" ? (a.ultimo_uso ?? "").localeCompare(b.ultimo_uso ?? "") : b.score - a.score);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar pelo nome"
          aria-label="Buscar app" className="min-w-[220px] flex-1 rounded-md border border-linha bg-superficie px-3 py-2 text-sm" />
        <Botao onClick={() => exportarCsv(v, lista)}>Exportar planilha (CSV)</Botao>
        <select value={ordem} onChange={(e) => setOrdem(e.target.value as typeof ordem)} aria-label="Ordenar"
          className="rounded-md border border-linha bg-superficie px-3 py-2 text-sm">
          <option value="risco">Maior risco primeiro</option><option value="nome">Nome (A-Z)</option>
          <option value="instalado">Instalados mais recentes</option><option value="uso">Sem uso há mais tempo</option>
        </select>
      </div>
      <Cartao className="overflow-x-auto">
        <table className="tabela w-full text-sm">
          <thead><tr><th>App</th><th>Instalado em</th><th>Último uso</th><th>Origem</th><th className="num">Risco</th></tr></thead>
          <tbody>
            {lista.map((r) => (
              <tr key={r.pacote}>
                <td><LinhaApp r={r} aoAbrir={aoAbrir} /></td>
                <td>{dataBr(r.instalado)}</td><td>{dataBr(r.ultimo_uso)}</td>
                <td>{r.loja ?? (r.sistema ? "Sistema" : r.origem ?? "Fora da loja")}</td>
                <td className="num"><Selo nivel={r.nivel} /> <span className="numeros">{r.score}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Cartao>
    </div>
  );
}

/** Planilha da lista de apps (abre no Excel com acentos corretos). */
function exportarCsv(v: Varredura, lista: AppResultado[]) {
  const cel = (x: unknown) => `"${String(x ?? "").replace(/"/g, '""')}"`;
  const linhas = [["App", "Pacote", "Versão", "Instalado em", "Último uso", "Origem", "Nível", "Pontos", "Motivos"].map(cel).join(";"),
    ...lista.map((r) => [nomeApp(r), r.pacote, r.versao, dataBr(r.instalado), dataBr(r.ultimo_uso),
      r.loja ?? (r.sistema ? "Sistema" : r.origem ?? "Fora da loja"), r.nivel, r.score, r.motivos.join(" | ")].map(cel).join(";"))];
  const blob = new Blob(["\ufeff" + linhas.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `apps_${v.info.modelo.replace(/\W+/g, "_")}_${v.varredura_id}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
