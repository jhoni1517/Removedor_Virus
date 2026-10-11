// Plano de ação e detecção de espião: funções puras (testadas no Vitest).
import type { AppResultado, Varredura } from "./api";
import { nomeApp } from "./nomes";

/** Aciona o modo vítima: stalkerware conhecido OU comportamento de espião (flag calculada no backend). */
export function ehVigilancia(r: Pick<AppResultado, "ameaca"> & Partial<Pick<AppResultado, "vigilancia" | "achados">> | string | null | undefined): boolean {
  if (r && typeof r === "object") {
    if (r.vigilancia) return true;
    if ((r.achados ?? []).some((a) => a.chave === "padrao_espiao")) return true;
  }
  const a = ((typeof r === "object" ? r?.ameaca : r) ?? "").toLowerCase();
  return !!a && ["stalkerware", "spyware", "pegasus", "predator", "espião"].some((p) => a.includes(p));
}

/** O que vai acontecer com cada app ao clicar em Remover (mostrado antes de confirmar). */
export function planoRemocao(r: AppResultado): { texto: string; alerta: boolean } {
  if (r.essencial) return { texto: "não sai: é essencial para o celular funcionar", alerta: true };
  if (r.sensivel) return { texto: "app com senhas, códigos ou conversas: o desfazer devolve, mas confirme com o dono", alerta: true };
  if (r.loja) return { texto: `remove mantendo os dados (veio da ${r.loja}); o desfazer devolve tudo`, alerta: false };
  return { texto: "cópia conferida na quarentena e remoção; sem cópia, remoção reversível", alerta: false };
}

/** Plano de ação em passos, do mais urgente ao menos (aba Problemas). */
export function planoDeAcao(v: Varredura): string[] {
  const passos: string[] = [];
  const altos = v.resultados.filter((r) => r.nivel === "ALTO" && !r.sistema);
  const medios = v.resultados.filter((r) => r.nivel === "MÉDIO" && !r.sistema);
  if (v.resultados.some((r) => ehVigilancia(r))) passos.push("Há sinal de app espião: leia o aviso de segurança antes de remover qualquer coisa.");
  if (v.resultados.some((r) => r.achados.some((a) => a.chave === "administrador" || a.chave === "device_owner"))) passos.push("Retire o administrador do aparelho antes de remover o app (senão ele se protege).");
  if (v.resultados.some((r) => r.removido_antes)) passos.push("Um app removido antes voltou: procure e remova primeiro quem instala outros apps, depois os demais.");
  if (altos.length) passos.push(`Remova ${altos.length === 1 ? "o app de risco alto" : `os ${altos.length} apps de risco alto`}: ${altos.slice(0, 4).map(nomeApp).join(", ")}${altos.length > 4 ? "…" : ""}.`);
  if (medios.length) passos.push(`Revise ${medios.length} app(s) de risco médio: remova os que o cliente não reconhecer.`);
  v.achados.filter((a) => a.nivel !== "BAIXO").slice(0, 3).forEach((a) => passos.push(a.fazer));
  if (passos.length) passos.push("Faça uma nova varredura para confirmar que ficou tudo limpo.");
  return passos;
}
