import { describe, expect, it } from "vitest";
import type { AppResultado, Varredura } from "../api";
import { ehVigilancia, planoDeAcao, planoRemocao } from "../plano";
import { duracaoCurta } from "../nomes";

function app(p: Partial<AppResultado>): AppResultado {
  return { pacote: "com.x", score: 0, nivel: "OK", motivos: [], achados: [], ameaca: null, instalador: null, loja: null,
    sistema: false, versao: null, instalado: null, sha256: null, nome: null, icone: null, ...p } as AppResultado;
}

describe("3.3", () => {
  it("formata tempo de tela", () => {
    expect(duracaoCurta(30)).toBe("menos de 1 min");
    expect(duracaoCurta(300)).toBe("5 min");
    expect(duracaoCurta(5400)).toBe("1 h 30 min");
    expect(duracaoCurta(7200)).toBe("2 h");
  });
  it("modo vítima pela flag do backend e pelo achado", () => {
    expect(ehVigilancia(app({ vigilancia: true }))).toBe(true);
    expect(ehVigilancia(app({ achados: [{ chave: "padrao_espiao", titulo: "", significa: "", fazer: "", nivel: "ALTO", peso: 40 }] as never }))).toBe(true);
    expect(ehVigilancia(app({}))).toBe(false);
    expect(ehVigilancia("Stalkerware TheTruthSpy")).toBe(true);
  });
  it("plano de remoção avisa sobre app sensível e app de loja", () => {
    expect(planoRemocao(app({ sensivel: true })).alerta).toBe(true);
    expect(planoRemocao(app({ loja: "Google Play" })).texto).toContain("mantendo os dados");
  });
  it("plano de ação manda tratar o app que voltou", () => {
    const v = { resultados: [app({ nivel: "ALTO", removido_antes: "10/09/2026", nome: "Vírus" })], achados: [] } as unknown as Varredura;
    expect(planoDeAcao(v).some((p) => p.includes("voltou"))).toBe(true);
  });
});
