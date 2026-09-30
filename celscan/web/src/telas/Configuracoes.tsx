import { useEffect, useState } from "react";
import { api, type Tarefa } from "../api";
import { useApp } from "../estado";
import { Botao, Cartao, Titulo } from "../ui";

interface Config { chave_virustotal: string | null; offline: boolean; tema: string; pasta_dados: string }

export default function Configuracoes() {
  const { avisar, recarregar, tema, mudarTema, estado, dispositivos, esperar } = useApp();
  const pronto = dispositivos.find((d) => d.estado === "device");

  async function registrarCertificados() {
    try {
      const t = await esperar(await api<Tarefa<{ nome: string }[]>>(`/certificados/registrar?serial=${encodeURIComponent(pronto!.serial)}`, { corpo: {} }));
      if (t.estado !== "concluida") throw new Error(t.erro ?? "Não terminou.");
      const n = t.resultado ?? [];
      avisar({ tipo: "ok", texto: n.length ? `Certificados registrados: ${n.map((x) => x.nome).join(", ")}.` :
        "Nenhum app de banco da lista instalado pela Play Store neste celular." });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }
  const [cfg, setCfg] = useState<Config | null>(null);
  const [chave, setChave] = useState("");

  useEffect(() => { api<Config>("/config").then(setCfg).catch(() => undefined); }, []);

  async function salvar(dados: Partial<Config>) {
    try {
      setCfg(await api<Config>("/config", { metodo: "PUT", corpo: dados }));
      await recarregar();
      avisar({ tipo: "ok", texto: "Configuração salva." });
    } catch (e) {
      avisar({ tipo: "erro", texto: (e as Error).message });
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <Titulo sub={`CelScan ${estado?.versao ?? ""}`}>Configurações</Titulo>

      <Cartao className="p-5">
        <h2 className="font-semibold">VirusTotal</h2>
        <p className="mt-1 text-sm text-fraco">
          Com uma chave gratuita, o modo Completo consulta mais de 70 antivírus. Crie a conta em virustotal.com e copie a "API key".
          {cfg?.chave_virustotal ? ` Chave atual: ${cfg.chave_virustotal}` : " Nenhuma chave cadastrada."}
        </p>
        <form className="mt-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); salvar({ chave_virustotal: chave.trim() }); setChave(""); }}>
          <input type="password" autoComplete="off" className="w-96 max-w-full rounded-md border border-linha bg-superficie-2 px-3 py-2 font-mono text-sm"
            placeholder="Cole a chave aqui" value={chave} onChange={(e) => setChave(e.target.value)} aria-label="Chave do VirusTotal" />
          <Botao type="submit" variante="primario" disabled={!chave.trim()}>Salvar chave</Botao>
          {cfg?.chave_virustotal && <Botao onClick={() => salvar({ chave_virustotal: "" })}>Remover chave</Botao>}
        </form>
      </Cartao>

      <Cartao className="p-5">
        <h2 className="font-semibold">Proteção Pix</h2>
        <p className="mt-1 text-sm text-fraco">
          Guarda a "assinatura digital" dos apps de banco oficiais instalados pela Play Store no celular conectado.
          Depois disso, cópias falsas desses apps são apontadas em qualquer celular analisado neste computador.
        </p>
        <Botao className="mt-3" onClick={registrarCertificados} disabled={!pronto}>
          Registrar certificados dos apps de banco{pronto?.modelo ? ` (${pronto.modelo})` : ""}
        </Botao>
      </Cartao>

      <Cartao className="p-5">
        <h2 className="font-semibold">Internet</h2>
        <label className="mt-2 flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-1 h-4 w-4 accent-[var(--destaque)]" checked={cfg?.offline ?? false}
            onChange={(e) => salvar({ offline: e.target.checked })} />
          <span>Modo offline: não baixar nada. Usa só as cópias locais da lista de ameaças (pode ficar desatualizada).</span>
        </label>
      </Cartao>

      <Cartao className="p-5">
        <h2 className="font-semibold">Aparência</h2>
        <div className="mt-3 flex gap-2" role="radiogroup" aria-label="Tema">
          {[["sistema", "Igual ao sistema"], ["claro", "Claro"], ["escuro", "Escuro"]].map(([k, nome]) => (
            <button key={k} role="radio" aria-checked={tema === k} onClick={() => mudarTema(k)}
              className={`rounded-full border px-3 py-1 text-sm ${tema === k ? "border-destaque bg-destaque-suave text-destaque" : "border-linha hover:bg-superficie-2"}`}>
              {nome}
            </button>
          ))}
        </div>
      </Cartao>

      <Cartao className="p-5 text-sm">
        <h2 className="font-semibold">Dados</h2>
        <p className="mt-1 text-fraco">Histórico, quarentena, laudos e registros ficam só neste computador:</p>
        <p className="mt-1 break-all font-mono">{cfg?.pasta_dados}</p>
      </Cartao>
    </div>
  );
}
