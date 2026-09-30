import { Gauge, Microscope, ShieldCheck, Zap } from "lucide-react";
import { useState } from "react";
import { useApp } from "../estado";
import { Botao, Cartao, Titulo } from "../ui";

const MODOS = [
  { id: "rapido", nome: "Rápido", tempo: "1 a 2 minutos", icone: Zap,
    texto: "Apps, permissões, assinaturas e comparação com a lista pública de ameaças conhecidas." },
  { id: "completo", nome: "Completo", tempo: "3 a 10 minutos", icone: ShieldCheck,
    texto: "Tudo do rápido e mais a opinião de mais de 70 antivírus (VirusTotal) sobre os apps suspeitos." },
  { id: "profundo", nome: "Profundo", tempo: "15 minutos ou mais", icone: Microscope,
    texto: "Coleta forense completa (AndroidQF + MVT) para suspeita de espionagem. Chega na próxima etapa." },
];

export default function Modo({ serial, onIniciar, onVoltar, onConfig }: {
  serial: string; onIniciar: (modo: string) => void; onVoltar: () => void; onConfig: () => void;
}) {
  const { estado, dispositivos } = useApp();
  const [modo, setModo] = useState("rapido");
  const d = dispositivos.find((x) => x.serial === serial);
  const conectado = d?.estado === "device";

  return (
    <div className="max-w-4xl">
      <Titulo sub={d?.fabricante ? `${d.fabricante} ${d.modelo} · Android ${d.android}` : serial}>Escolha o tipo de varredura</Titulo>
      <div className="grid gap-4 md:grid-cols-3" role="radiogroup" aria-label="Tipo de varredura">
        {MODOS.map((m) => {
          const indisponivel = m.id === "profundo";
          const ativo = modo === m.id;
          const Icone = m.icone;
          return (
            <button key={m.id} role="radio" aria-checked={ativo} disabled={indisponivel} onClick={() => setModo(m.id)}
              aria-label={`${m.nome}, ${m.tempo}`} aria-describedby={`modo-${m.id}`}
              className={`rounded-lg border p-5 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
                ativo ? "border-destaque bg-destaque-suave" : "border-linha bg-superficie hover:bg-superficie-2"}`}>
              <Icone className={ativo ? "text-destaque" : "text-fraco"} aria-hidden />
              <p className="mt-3 text-lg font-semibold">{m.nome}</p>
              <p className="flex items-center gap-1 font-mono text-xs text-fraco"><Gauge size={12} aria-hidden /> {m.tempo}</p>
              <p id={`modo-${m.id}`} className="mt-2 text-sm text-fraco">{m.texto}</p>
            </button>
          );
        })}
      </div>
      {modo === "completo" && estado && !estado.vt && (
        <Cartao className="mt-4 border-atencao/40 bg-atencao-suave p-4 text-sm text-atencao">
          Sem a chave gratuita do VirusTotal, o modo Completo funciona como o Rápido.{" "}
          <button className="font-semibold underline" onClick={onConfig}>Cadastrar a chave</button>
        </Cartao>
      )}
      {!conectado && (
        <p className="mt-4 text-perigo" role="alert">O celular foi desconectado. Reconecte o cabo para continuar.</p>
      )}
      <div className="mt-6 flex gap-3">
        <Botao variante="primario" disabled={!conectado} onClick={() => onIniciar(modo)} autoFocus>Iniciar varredura</Botao>
        <Botao onClick={onVoltar}>Trocar de aparelho</Botao>
      </div>
    </div>
  );
}
