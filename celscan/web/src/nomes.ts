// Funções puras sobre nomes de app (sem React nem API: testáveis direto no Vitest).

/** Nome legível do app; sem rótulo, usa a parte mais significativa do pacote ("com.whatsapp" -> "Whatsapp"). */
export function nomeApp(r: { nome?: string | null; pacote: string }): string {
  return r.nome && r.nome !== r.pacote ? r.nome : r.pacote.split(".").filter((p) => !["com", "br", "org", "android", "app"].includes(p)).pop()
    ?.replace(/[_-]/g, " ").replace(/^./, (c) => c.toUpperCase()) ?? r.pacote;
}

/** 5400 -> "1 h 30 min"; 300 -> "5 min". */
export function duracaoCurta(s: number): string {
  if (s < 60) return "menos de 1 min";
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
}
