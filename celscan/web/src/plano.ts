// Plano de ação e detecção de espião: funções puras (testadas no Vitest).
import type { Varredura } from "./api";
import { nomeApp } from "./nomes";

export function ehVigilancia(ameaca: string | null | undefined): boolean {
  const a = (ameaca ?? "").toLowerCase();
  return !!a && ["stalkerware", "spyware", "pegasus", "predator", "espião"].some((p) => a.includes(p));
}

/** Plano de ação em passos, do mais urgente ao menos (aba Problemas). */
export function planoDeAcao(v: Varredura): string[] {
  const passos: string[] = [];
  const altos = v.resultados.filter((r) => r.nivel === "ALTO" && !r.sistema);
  const medios = v.resultados.filter((r) => r.nivel === "MÉDIO" && !r.sistema);
  if (v.resultados.some((r) => ehVigilancia(r.ameaca))) passos.push("Há sinal de app espião: leia o aviso de segurança antes de remover qualquer coisa.");
  if (v.resultados.some((r) => r.achados.some((a) => a.chave === "administrador" || a.chave === "device_owner"))) passos.push("Retire o administrador do aparelho antes de remover o app (senão ele se protege).");
  if (altos.length) passos.push(`Remova ${altos.length === 1 ? "o app de risco alto" : `os ${altos.length} apps de risco alto`}: ${altos.slice(0, 4).map(nomeApp).join(", ")}${altos.length > 4 ? "…" : ""}.`);
  if (medios.length) passos.push(`Revise ${medios.length} app(s) de risco médio: remova os que o cliente não reconhecer.`);
  v.achados.filter((a) => a.nivel !== "BAIXO").slice(0, 3).forEach((a) => passos.push(a.fazer));
  if (passos.length) passos.push("Faça uma nova varredura para confirmar que ficou tudo limpo.");
  return passos;
}
