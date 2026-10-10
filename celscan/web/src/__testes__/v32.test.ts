import { describe, expect, it } from "vitest";
import type { AppResultado, Varredura } from "../api";
import { categoriaDaChave, categoriasDoApp } from "../categorias";

function app(p: Partial<AppResultado>): AppResultado {
  return { pacote: "com.x", score: 0, nivel: "OK", motivos: [], achados: [], ameaca: null, instalador: null, loja: null,
    sistema: false, versao: null, instalado: null, sha256: null, nome: null, icone: null, ...p };
}
const achado = (chave: string, peso = 10) => ({ chave, peso, nivel: "ALTO", titulo: chave, significa: "", fazer: "" });

describe("categorias", () => {
  it("mapeia chaves conhecidas e permissões", () => {
    expect(categoriaDaChave("anuncio_tela_cheia")).toBe("anuncio");
    expect(categoriaDaChave("android.permission.CAMERA")).toBe("privacidade");
    expect(categoriaDaChave("chave_inventada")).toBe("origem");
  });
  it("ignora achados sem peso", () => {
    const r = app({ achados: [achado("acessibilidade"), achado("anuncio_popup", 0)] });
    expect([...categoriasDoApp(r)]).toEqual(["espionagem"]);
  });
});

describe("plano de ação", async () => {
  // função pura, fora do componente
  const { planoDeAcao } = await import("../plano");
  const base = { varredura_id: 1, modo: "rapido", info: { fabricante: "X", modelo: "Y", android: "14", patch_seguranca: "2026-01-01", serial: "s" },
    nota: 50, veredito: "Atenção", achados: [], avisos: [], duracao_s: 1 } as unknown as Varredura;
  it("vazio quando não há problema", () => {
    expect(planoDeAcao({ ...base, resultados: [app({})] })).toEqual([]);
  });
  it("manda tirar o administrador antes de remover", () => {
    const p = planoDeAcao({ ...base, resultados: [app({ nivel: "ALTO", nome: "Espião", achados: [achado("administrador")] })] });
    expect(p[0]).toMatch(/administrador/);
    expect(p.some((x) => x.includes("Espião"))).toBe(true);
    expect(p.at(-1)).toMatch(/nova varredura/);
  });
});
