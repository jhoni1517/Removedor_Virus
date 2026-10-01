import { describe, expect, it } from "vitest";
import { corDominante } from "../tema";

function pixels(cores: [number, number, number][]): Uint8ClampedArray {
  const p = new Uint8ClampedArray(cores.length * 4);
  cores.forEach(([r, g, b], i) => p.set([r, g, b, 255], i * 4));
  return p;
}

function luminancia(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((s) => (s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

describe("cor da marca a partir do logo", () => {
  it("ignora branco/preto/cinza e pega a cor que mais aparece", () => {
    const c = corDominante(pixels([
      ...Array(50).fill([255, 255, 255]), ...Array(20).fill([0, 0, 0]), ...Array(20).fill([128, 128, 128]),
      ...Array(30).fill([220, 30, 30]), ...Array(10).fill([30, 30, 220]),
    ]));
    expect(c).not.toBeNull();
    const [r, , b] = [1, 3, 5].map((i) => parseInt(c!.destaque.slice(i, i + 2), 16));
    expect(r).toBeGreaterThan(b); // vermelho venceu
  });

  it("escurece até ter contraste AA com texto branco", () => {
    const c = corDominante(pixels(Array(40).fill([255, 230, 60]))); // amarelo claro
    expect(luminancia(c!.destaque)).toBeLessThanOrEqual(0.183 + 1e-3);
  });

  it("logo só em tons de cinza não gera tema", () => {
    expect(corDominante(pixels(Array(40).fill([120, 120, 120])))).toBeNull();
  });
});
