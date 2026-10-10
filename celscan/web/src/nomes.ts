// Funções puras sobre nomes de app (sem React nem API: testáveis direto no Vitest).

/** Nome legível do app; sem rótulo, usa a parte mais significativa do pacote ("com.whatsapp" -> "Whatsapp"). */
export function nomeApp(r: { nome?: string | null; pacote: string }): string {
  return r.nome && r.nome !== r.pacote ? r.nome : r.pacote.split(".").filter((p) => !["com", "br", "org", "android", "app"].includes(p)).pop()
    ?.replace(/[_-]/g, " ").replace(/^./, (c) => c.toUpperCase()) ?? r.pacote;
}
