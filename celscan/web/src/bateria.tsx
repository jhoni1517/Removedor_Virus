import { BatteryLow } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api";

interface Bateria { nivel: number | null; carregando: boolean; baixa: boolean }

/** Nível da bateria do celular. Pergunta de novo a cada minuto (o técnico pode ligar o carregador). */
export function useBateria(serial: string | undefined | null): Bateria | null {
  const [b, setB] = useState<Bateria | null>(null);
  useEffect(() => {
    if (!serial) { setB(null); return; }
    let vivo = true;
    const ler = () => api<Bateria>(`/bateria?serial=${encodeURIComponent(serial)}`)
      .then((x) => { if (vivo) setB(x); }).catch(() => { if (vivo) setB(null); });
    ler();
    const t = setInterval(ler, 60000);
    return () => { vivo = false; clearInterval(t); };
  }, [serial]);
  return b;
}

/** Aviso que só aparece com bateria baixa e sem carregar: remover, copiar ou otimizar com o celular desligando
 * no meio deixa o app pela metade ou a cópia cortada. */
export function BateriaBaixa({ serial }: { serial: string | undefined | null }) {
  const b = useBateria(serial);
  if (!b?.baixa) return null;
  return (
    <p className="my-3 flex items-start gap-2 rounded-md bg-atencao-suave p-2 text-sm text-atencao" role="alert">
      <BatteryLow size={18} className="mt-0.5 shrink-0" aria-hidden />
      <span>Bateria do celular em <strong>{b.nivel}%</strong> e sem carregar. Se ele desligar no meio, o trabalho pode ficar
        pela metade. Ligue o carregador antes de continuar.</span>
    </p>
  );
}
