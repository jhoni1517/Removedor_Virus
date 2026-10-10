// Abas extras do resultado: anúncios/pop-ups, câmera e microfone, internet por app e lista completa.
import { Camera, Crosshair, Megaphone, Wifi } from "lucide-react";
import { useMemo, useState } from "react";
import { api, type AppResultado, type Consumo, type NaTela, type Varredura } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, Data, IconeApp, Selo, Vazio, dataBr, duracaoCurta, nomeApp, quando, recente, tamanhoLegivel } from "../ui";

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
  const spam = v.resultados.filter((r) => (r.notificacoes ?? 0) > 0)
    .sort((a, b) => (b.notificacoes ?? 0) - (a.notificacoes ?? 0) || nomeApp(a).localeCompare(nomeApp(b), "pt-BR")).slice(0, 8);

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
              <LinhaApp r={r} aoAbrir={aoAbrir} />
              <span className="numeros text-right"><strong>{r.notificacoes}</strong>
                {r.notificacoes_dia ? <span className="block text-xs text-fraco">{r.notificacoes_dia.toLocaleString("pt-BR")}/dia</span> : null}</span></li>)}
          </ul>
        </Cartao>
      )}
    </div>
  );
}

export function AbaSensores({ v, aoAbrir }: { v: Varredura; aoAbrir: (p: string) => void }) {
  const LIMITE = 7 * 86400;
  // um app por linha (antes: uma linha por sensor, o mesmo app aparecia 3–4 vezes)
  const usos = v.resultados
    .map((r) => ({ r, lista: Object.entries(r.sensores ?? {}).filter(([, s]) => s < LIMITE).sort((a, b) => a[1] - b[1]) }))
    .filter((x) => x.lista.length)
    .sort((a, b) => (Number(b.r.nivel === "ALTO") - Number(a.r.nivel === "ALTO")) || a.lista[0][1] - b.lista[0][1]);
  if (!usos.length) return <Vazio>Nenhum uso de câmera, microfone, localização ou SMS registrado nos últimos 7 dias.</Vazio>;
  return (
    <Cartao className="overflow-x-auto">
      <p className="flex items-center gap-2 px-4 pt-4 text-sm text-fraco"><Camera size={15} aria-hidden /> Últimos 7 dias, segundo o próprio Android.</p>
      <table className="tabela w-full text-sm">
        <thead><tr><th>App</th><th>Usou</th><th>Origem</th></tr></thead>
        <tbody>
          {usos.map(({ r, lista }) => (
            <tr key={r.pacote}>
              <td><LinhaApp r={r} aoAbrir={aoAbrir} /></td>
              <td><ul className="space-y-0.5">{lista.map(([sensor, seg]) => (
                <li key={sensor}><span className="capitalize">{sensor}</span> <span className="text-fraco">· {quando(seg)}</span></li>
              ))}</ul></td>
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
                    <td>{r ? <LinhaApp r={r} aoAbrir={aoAbrir}>
                      {!r.sistema && (!r.loja || r.sem_icone) && <span className="selo-mini">{r.sem_icone ? "escondido" : "fora da loja"}</span>}
                    </LinhaApp> : <span className="font-mono text-xs">{a.pacote}</span>}</td>
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

type Ordem = "risco" | "nome" | "instalado" | "uso" | "tamanho" | "tela" | "bateria";
type Periodo = "todos" | "7" | "30";

export function AbaTodos({ v, aoAbrir }: { v: Varredura; aoAbrir: (p: string) => void }) {
  const [busca, setBusca] = useState("");
  const [ordem, setOrdem] = useState<Ordem>("risco");
  const [periodo, setPeriodo] = useState<Periodo>("todos");
  const lista = useMemo(() => {
    const t = busca.trim().toLocaleLowerCase("pt-BR");
    return v.resultados
      .filter((r) => !t || `${nomeApp(r)} ${r.pacote}`.toLocaleLowerCase("pt-BR").includes(t))
      .filter((r) => periodo === "todos" || recente(r.instalado, Number(periodo)))
      .sort((a, b) => (ordem === "nome" ? 0
        : ordem === "instalado" ? (b.instalado ?? "").localeCompare(a.instalado ?? "")
        // sem uso registrado = há mais tempo sem uso: vai para o topo
        : ordem === "uso" ? (a.ultimo_uso ?? "").localeCompare(b.ultimo_uso ?? "")
        : ordem === "tamanho" ? (b.tamanho ?? 0) - (a.tamanho ?? 0)
        : ordem === "tela" ? (b.tempo_uso_s ?? 0) - (a.tempo_uso_s ?? 0)
        : ordem === "bateria" ? (b.bateria_mah ?? 0) - (a.bateria_mah ?? 0) : b.score - a.score)
        || nomeApp(a).localeCompare(nomeApp(b), "pt-BR") || a.pacote.localeCompare(b.pacote));
  }, [v, busca, ordem, periodo]);
  const temTamanho = v.resultados.some((r) => r.tamanho);
  const temTela = v.resultados.some((r) => r.tempo_uso_s);
  const temBateria = v.resultados.some((r) => (r.bateria_mah ?? 0) >= 1);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar pelo nome ou pacote"
          aria-label="Buscar app" className="min-w-[220px] flex-1 rounded-md border border-linha bg-superficie px-3 py-2 text-sm" />
        <select value={periodo} onChange={(e) => setPeriodo(e.target.value as Periodo)} aria-label="Instalados quando"
          className="rounded-md border border-linha bg-superficie px-3 py-2 text-sm">
          <option value="todos">Instalados a qualquer momento</option><option value="7">Instalados nos últimos 7 dias</option>
          <option value="30">Instalados nos últimos 30 dias</option>
        </select>
        <select value={ordem} onChange={(e) => setOrdem(e.target.value as Ordem)} aria-label="Ordenar"
          className="rounded-md border border-linha bg-superficie px-3 py-2 text-sm">
          <option value="risco">Maior risco primeiro</option><option value="nome">Nome (A-Z)</option>
          <option value="instalado">Instalados mais recentes</option><option value="uso">Sem uso há mais tempo</option>
          {temTamanho && <option value="tamanho">Maiores primeiro</option>}
          {temTela && <option value="tela">Mais tempo de tela</option>}
          {temBateria && <option value="bateria">Mais gasto de bateria</option>}
        </select>
        <Botao onClick={() => exportarCsv(v, lista)}>Exportar planilha (CSV)</Botao>
      </div>
      <p className="text-xs text-fraco numeros">{lista.length} de {v.resultados.length} app(s)</p>
      <Cartao className="overflow-x-auto">
        <table className="tabela w-full text-sm">
          <thead><tr><th>App</th><th>Instalado</th><th>Último uso</th>{temTela && <th className="num" title="Tempo com o app na tela nos últimos 7 dias">Tela (semana)</th>}{temBateria && <th className="num" title="Energia gasta desde a última carga completa">Bateria</th>}{temTamanho && <th className="num">Tamanho</th>}<th>Origem</th><th className="num">Risco</th></tr></thead>
          <tbody>
            {lista.map((r) => (
              <tr key={r.pacote}>
                <td><LinhaApp r={r} aoAbrir={aoAbrir} /></td>
                <td><Data iso={r.instalado} /></td><td><Data iso={r.ultimo_uso} /></td>
                {temTela && <td className="num numeros">{r.tempo_uso_s ? duracaoCurta(r.tempo_uso_s) : "—"}</td>}
                {temBateria && <td className="num numeros">{r.bateria_mah && r.bateria_mah >= 1 ? `${Math.round(r.bateria_mah).toLocaleString("pt-BR")} mAh` : "—"}</td>}
                {temTamanho && <td className="num numeros">{tamanhoLegivel(r.tamanho)}</td>}
                <td>{r.loja ?? (r.sistema ? "Sistema" : r.origem ?? "Fora da loja")}</td>
                <td className="num"><Selo nivel={r.nivel} /> <span className="numeros">{r.score}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {lista.length === 0 && <Vazio>Nenhum app com esse filtro.</Vazio>}
      </Cartao>
    </div>
  );
}

/** Planilha da lista de apps (abre no Excel com acentos corretos). */
function exportarCsv(v: Varredura, lista: AppResultado[]) {
  // Nome de app vem do APK (controlado por quem fez o app): "=HYPERLINK(...)" viraria fórmula no Excel.
  const cel = (x: unknown) => {
    let t = String(x ?? "");
    if (/^[=+\-@\t\r]/.test(t)) t = `'${t}`;
    return `"${t.replace(/"/g, '""')}"`;
  };
  const linhas = [["App", "Pacote", "Versão", "Instalado em", "Último uso", "Tamanho", "Origem", "Nível", "Pontos", "Motivos"].map(cel).join(";"),
    ...lista.map((r) => [nomeApp(r), r.pacote, r.versao, dataBr(r.instalado), dataBr(r.ultimo_uso), tamanhoLegivel(r.tamanho),
      r.loja ?? (r.sistema ? "Sistema" : r.origem ?? "Fora da loja"), r.nivel, r.score, r.motivos.join(" | ")].map(cel).join(";"))];
  const blob = new Blob(["\ufeff" + linhas.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `apps_${v.info.modelo.replace(/\W+/g, "_")}_${v.varredura_id}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}


const EXPLICA_PODER: Record<string, string> = {
  "administrador": "impede a própria remoção e pode bloquear ou apagar o celular",
  "controla a tela": "lê tudo o que aparece e toca na tela no lugar da pessoa",
  "lê notificações": "vê mensagens, códigos de banco e de 2 etapas que chegam",
  "janela sobre outros apps": "desenha por cima de qualquer app (tela falsa de banco, pop-up)",
  "grava a tela": "captura ou transmite o que aparece na tela",
  "instala apps": "pode instalar outros apps sozinho",
  "teclado": "vê tudo o que é digitado, inclusive senhas",
  "SMS padrão": "recebe todos os SMS, inclusive códigos",
  "lê SMS": "lê os SMS, inclusive códigos de confirmação",
};

/** Quem tem poderes especiais agora: o resumo que o técnico confere com o cliente ("você reconhece estes?"). */
export function AbaPoderes({ v, aoAbrir }: { v: Varredura; aoAbrir: (p: string) => void }) {
  const lista = useMemo(() => v.resultados.filter((r) => (r.poderes?.length ?? 0) > 0)
    .sort((a, b) => Number(a.sistema) - Number(b.sistema) || (b.poderes!.length - a.poderes!.length) || b.score - a.score), [v]);
  const usados = [...new Set(lista.flatMap((r) => r.poderes!))];
  return (
    <div className="space-y-4">
      <p className="text-sm text-fraco">Apps que conseguem mais do que um app comum. Confira com o cliente se ele reconhece cada um; o que ele não
        reconhecer, tire o poder (botão Permissões no cartão do app) ou remova.</p>
      {lista.length === 0 ? <Vazio>Nenhum app com poderes especiais.</Vazio> : (
        <Cartao className="overflow-x-auto">
          <table className="tabela w-full text-sm">
            <thead><tr><th>App</th><th>Poderes</th><th className="num">Risco</th></tr></thead>
            <tbody>
              {lista.map((r) => (
                <tr key={r.pacote}>
                  <td><LinhaApp r={r} aoAbrir={aoAbrir}>{r.sistema && <span className="block text-xs text-fraco">de fábrica</span>}</LinhaApp></td>
                  <td><span className="flex flex-wrap gap-1">{r.poderes!.map((p) => (
                    <span key={p} title={EXPLICA_PODER[p]} className={`rounded px-1.5 py-0.5 text-xs ${r.sistema ? "bg-superficie-2 text-fraco" : "bg-atencao-suave text-atencao"}`}>{p}</span>
                  ))}</span></td>
                  <td className="num"><Selo nivel={r.nivel} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>
      )}
      {usados.length > 0 && (
        <dl className="grid gap-x-6 gap-y-1 text-xs text-fraco md:grid-cols-2">
          {usados.map((p) => <div key={p}><dt className="inline font-semibold">{p}: </dt><dd className="inline">{EXPLICA_PODER[p] ?? ""}</dd></div>)}
        </dl>
      )}
    </div>
  );
}

interface ApkGuardado { caminho: string; nome: string; tamanho: number | null; sha256: string | null; ameaca: string | null }

/** Instaladores .apk esquecidos no armazenamento: lista na hora e apaga com cópia na quarentena. */
export function ApksGuardados({ serial, conectado }: { serial: string; conectado: boolean }) {
  const { avisar } = useApp();
  const [lista, setLista] = useState<ApkGuardado[] | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [ocupado, setOcupado] = useState(false);
  async function carregar() {
    try {
      const l = await api<ApkGuardado[]>(`/apks-guardados?serial=${encodeURIComponent(serial)}`);
      setLista(l);
      setMarcados(new Set(l.filter((x) => x.ameaca).map((x) => x.caminho)));
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
  }
  async function apagar() {
    if (!window.confirm(`Apagar ${marcados.size} instalador(es) do celular? Fica uma cópia na quarentena (dá para desfazer no Histórico).`)) return;
    setOcupado(true);
    try {
      const r = await api<{ apagados: string[] }>("/apks-guardados/apagar", { corpo: { serial, caminhos: [...marcados] } });
      avisar({ tipo: "ok", texto: `${r.apagados.length} instalador(es) apagado(s). Cópia na quarentena.` });
      await carregar();
    } catch (e) { avisar({ tipo: "erro", texto: (e as Error).message }); }
    finally { setOcupado(false); }
  }
  if (!conectado) return null;
  if (lista === null) return <Botao className="mt-2 py-1" onClick={carregar}>Ver os arquivos .apk</Botao>;
  if (lista.length === 0) return <p className="mt-2 text-sm text-fraco">Nenhum instalador .apk no armazenamento agora.</p>;
  return (
    <div className="mt-3 space-y-2">
      <ul className="space-y-1 text-sm">{lista.map((f) => (
        <li key={f.caminho}><label className="flex items-start gap-2">
          <input type="checkbox" className="mt-1 accent-[var(--destaque)]" checked={marcados.has(f.caminho)}
            onChange={() => setMarcados((m) => { const n = new Set(m); if (n.has(f.caminho)) n.delete(f.caminho); else n.add(f.caminho); return n; })} />
          <span className="min-w-0"><span className="font-medium">{f.nome}</span>{f.ameaca && <span className="ml-2 font-semibold text-perigo">{f.ameaca}</span>}
            <span className="block break-all font-mono text-xs text-fraco">{f.caminho}{f.tamanho ? ` · ${tamanhoLegivel(f.tamanho)}` : ""}</span></span>
        </label></li>))}</ul>
      <Botao variante="perigo" className="py-1" disabled={!marcados.size || ocupado} onClick={apagar}>Apagar selecionados</Botao>
    </div>
  );
}
