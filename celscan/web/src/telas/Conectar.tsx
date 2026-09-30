import { Cable, Download, Smartphone, Wifi } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, ErroApi, type Dispositivo, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Barra, Botao, Cartao, Titulo } from "../ui";

interface Passo {
  titulo: string;
  texto: string;
}
interface Ajuda {
  comum_final: Passo[];
  marcas: Record<string, { nome: string; passos: Passo[] }>;
  wifi: Passo[];
}

function Passos({ passos, inicio = 1 }: { passos: Passo[]; inicio?: number }) {
  return (
    <ol className="space-y-4">
      {passos.map((p, i) => (
        <li key={p.titulo} className="flex gap-3">
          <span className="numeros flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-linha bg-superficie-2 font-mono text-sm">
            {i + inicio}
          </span>
          <div>
            <p className="font-medium">{p.titulo}</p>
            <p className="text-sm text-fraco">{p.texto}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ModalWifi({ ajuda, fechar }: { ajuda: Ajuda; fechar: () => void }) {
  const { esperar, avisar, tarefas } = useApp();
  const [qr, setQr] = useState<{ qr_svg: string; tarefa: Tarefa } | null>(null);
  const [endereco, setEndereco] = useState("");
  const [codigo, setCodigo] = useState("");
  const fecharRef = useRef(fechar);
  fecharRef.current = fechar;

  useEffect(() => {
    let vivo = true;
    let tarefaId = "";
    api<{ qr_svg: string; tarefa: Tarefa }>("/wifi/qr", { corpo: {} })
      .then((r) => {
        if (!vivo) return;
        tarefaId = r.tarefa.id;
        setQr(r);
        esperar(r.tarefa).then((t) => {
          if (!vivo) return;
          if (t.estado === "concluida") {
            avisar({ tipo: "ok", texto: "Celular conectado pelo Wi-Fi." });
            fecharRef.current();
          } else if (t.estado === "erro") avisar({ tipo: "erro", texto: t.erro ?? "Falha no pareamento." });
        });
      })
      .catch((e) => avisar({ tipo: "erro", texto: e.message }));
    const esc = (ev: KeyboardEvent) => ev.key === "Escape" && fecharRef.current();
    window.addEventListener("keydown", esc);
    return () => {
      vivo = false;
      window.removeEventListener("keydown", esc);
      if (tarefaId) api(`/tarefas/${tarefaId}/cancelar`, { corpo: {} }).catch(() => undefined);
    };
  }, [esperar, avisar]);

  const progresso = qr ? tarefas[qr.tarefa.id]?.progresso : undefined;

  async function parearManual() {
    try {
      const r = await api<{ resposta: string }>("/wifi/parear", { corpo: { endereco, codigo } });
      avisar({ tipo: r.resposta.includes("Success") ? "ok" : "erro", texto: r.resposta || "Sem resposta do celular." });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="titulo-wifi">
      <Cartao className="entrar w-full max-w-3xl p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="titulo-wifi" className="text-lg font-semibold">Conectar pelo Wi-Fi</h2>
          <Botao variante="fantasma" onClick={fechar} aria-label="Fechar">Fechar</Botao>
        </div>
        <div className="grid gap-6 md:grid-cols-[240px_1fr]">
          <div>
            <div className="qr rounded-lg border border-linha bg-white p-3">
              {qr ? <div dangerouslySetInnerHTML={{ __html: qr.qr_svg }} /> : <div className="aspect-square" />}
            </div>
            <p className="mt-2 text-center text-sm text-fraco">{progresso?.descricao ?? "Gerando código..."}</p>
            <div className="mt-2"><Barra indeterminada /></div>
          </div>
          <div className="space-y-6">
            <Passos passos={ajuda.wifi} />
            <details className="rounded-md border border-linha p-3 text-sm">
              <summary className="cursor-pointer font-medium">O QR não funcionou? Parear com código</summary>
              <p className="mt-2 text-fraco">Em Depuração por Wi-Fi, toque em "Parear dispositivo com código de pareamento".</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <input className="w-44 rounded-md border border-linha bg-superficie-2 px-2 py-1.5 font-mono text-sm" placeholder="IP:porta"
                  value={endereco} onChange={(e) => setEndereco(e.target.value)} aria-label="Endereço IP e porta" />
                <input className="w-28 rounded-md border border-linha bg-superficie-2 px-2 py-1.5 font-mono text-sm" placeholder="Código"
                  value={codigo} onChange={(e) => setCodigo(e.target.value)} aria-label="Código de 6 dígitos" />
                <Botao onClick={parearManual} disabled={!endereco || !codigo}>Parear</Botao>
              </div>
            </details>
          </div>
        </div>
      </Cartao>
    </div>
  );
}

function CartaoAparelho({ d, escolher }: { d: Dispositivo; escolher: () => void }) {
  return (
    <Cartao className="entrar flex items-center gap-4 p-4">
      <Smartphone className="text-destaque" aria-hidden />
      <div className="flex-1">
        <p className="font-semibold">{d.fabricante ? `${d.fabricante} ${d.modelo}` : "Android"}</p>
        <p className="font-mono text-xs text-fraco">
          {d.android ? `Android ${d.android} · ` : ""}{d.serial}{d.wifi ? " · Wi-Fi" : " · USB"}
        </p>
      </div>
      <Botao variante="primario" onClick={escolher} autoFocus>Usar este aparelho</Botao>
    </Cartao>
  );
}

export default function Conectar({ onEscolher }: { onEscolher: (serial: string) => void }) {
  const { estado, dispositivos, avisar, esperar, recarregar } = useApp();
  const [ajuda, setAjuda] = useState<Ajuda | null>(null);
  const [marca, setMarca] = useState("samsung");
  const [wifi, setWifi] = useState(false);
  const [baixando, setBaixando] = useState(false);

  useEffect(() => {
    api<Ajuda>("/ajuda/conexao").then(setAjuda).catch(() => undefined);
  }, []);

  const prontos = dispositivos.filter((d) => d.estado === "device");
  const naoAutorizado = dispositivos.some((d) => d.estado === "unauthorized");

  async function baixarAdb() {
    setBaixando(true);
    try {
      const t = await esperar(await api<Tarefa>("/adb/instalar", { corpo: {} }));
      if (t.estado === "concluida") avisar({ tipo: "ok", texto: "ADB instalado." });
      else avisar({ tipo: "erro", texto: t.erro ?? "Não foi possível baixar o ADB." });
      await recarregar();
    } catch (e) {
      avisar({ tipo: "erro", texto: e instanceof ErroApi ? e.message : "Falha ao baixar." });
    } finally {
      setBaixando(false);
    }
  }

  if (estado && !estado.adb) {
    return (
      <div className="max-w-2xl">
        <Titulo sub="O CelScan usa o ADB, a ferramenta oficial do Google, para conversar com o celular.">Falta uma peça</Titulo>
        <Cartao className="p-6">
          <p>O ADB não foi encontrado neste computador. Baixe a versão oficial (cerca de 10 MB).</p>
          <Botao variante="primario" className="mt-4" onClick={baixarAdb} disabled={baixando}>
            <Download size={16} aria-hidden /> {baixando ? "Baixando..." : "Baixar o ADB oficial"}
          </Botao>
        </Cartao>
      </div>
    );
  }

  return (
    <div className="max-w-4xl">
      <Titulo sub="Ligue o celular no cabo USB. O CelScan percebe sozinho quando ele estiver pronto.">Conectar o celular</Titulo>

      {prontos.length > 0 && (
        <div className="mb-8 space-y-3">
          {prontos.map((d) => <CartaoAparelho key={d.serial} d={d} escolher={() => onEscolher(d.serial)} />)}
        </div>
      )}

      {naoAutorizado && (
        <div className="mb-6 rounded-lg border border-atencao/40 bg-atencao-suave p-4 text-atencao" role="status">
          <strong>Quase lá:</strong> desbloqueie a tela do celular e toque em <strong>Permitir</strong> no aviso "Permitir depuração USB?".
        </div>
      )}

      {prontos.length === 0 && (
        <p className="mb-6 flex items-center gap-2 text-fraco" role="status">
          <span className="pulsar inline-block h-2 w-2 rounded-full bg-destaque" aria-hidden />
          Esperando o celular...
        </p>
      )}

      {ajuda && (
        <Cartao className="p-6">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 font-semibold"><Cable size={18} aria-hidden /> Como ligar a depuração USB</h2>
            <Botao onClick={() => setWifi(true)}><Wifi size={16} aria-hidden /> Conectar pelo Wi-Fi</Botao>
          </div>
          <div className="mb-6 flex flex-wrap gap-2" role="radiogroup" aria-label="Marca do celular">
            {Object.entries(ajuda.marcas).map(([k, m]) => (
              <button key={k} role="radio" aria-checked={marca === k} onClick={() => setMarca(k)}
                className={`rounded-full border px-3 py-1 text-sm transition ${marca === k ? "border-destaque bg-destaque-suave text-destaque" : "border-linha hover:bg-superficie-2"}`}>
                {m.nome}
              </button>
            ))}
          </div>
          <Passos passos={[...ajuda.marcas[marca].passos, ...ajuda.comum_final]} />
        </Cartao>
      )}
      {wifi && ajuda && <ModalWifi ajuda={ajuda} fechar={() => setWifi(false)} />}
    </div>
  );
}
