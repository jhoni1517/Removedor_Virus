// Temas do CelScan: tokens vêm do estilo.css; aqui só se escolhe qual vale e se aplica a marca da loja.

export const TEMAS: { id: string; nome: string; amostra: [string, string, string] }[] = [
  { id: "oficina", nome: "Oficina (destaque)", amostra: ["#0a0c10", "#00e0c6", "#39ff8b"] },
  { id: "sistema", nome: "Igual ao sistema", amostra: ["#eef0f4", "#1f6feb", "#0b0e12"] },
  { id: "claro", nome: "Bancada", amostra: ["#eef0f4", "#1f6feb", "#141a22"] },
  { id: "escuro", nome: "Noite", amostra: ["#0b0e12", "#3cc6ff", "#e9edf3"] },
  { id: "terminal", nome: "Terminal", amostra: ["#050705", "#5df26b", "#ffb84d"] },
  { id: "contraste", nome: "Alto contraste", amostra: ["#000000", "#ffd400", "#ffffff"] },
  { id: "loja", nome: "Minha loja", amostra: ["#eef0f4", "#888888", "#141a22"] },
];

// Temas que usam o atributo data-tema (em vez da classe .escuro)
const TEMAS_ATRIBUTO = new Set(["terminal", "contraste", "oficina"]);

export interface CoresLoja { destaque: string; suave: string }
const CHAVE_LOJA = "celscan-cores-loja";

export function lerCoresLoja(): CoresLoja | null {
  try { return JSON.parse(localStorage.getItem(CHAVE_LOJA) ?? "null"); } catch { return null; }
}

export function salvarCoresLoja(c: CoresLoja | null) {
  try { if (c) localStorage.setItem(CHAVE_LOJA, JSON.stringify(c)); else localStorage.removeItem(CHAVE_LOJA); } catch { /* sem storage */ }
}

export function aplicarTema(tema: string, escala = 1) {
  const raiz = document.documentElement;
  const sistemaEscuro = window.matchMedia("(prefers-color-scheme: dark)").matches;
  raiz.classList.toggle("escuro", tema === "escuro" || (tema === "sistema" && sistemaEscuro));
  if (TEMAS_ATRIBUTO.has(tema)) raiz.setAttribute("data-tema", tema);
  else raiz.removeAttribute("data-tema");
  for (const k of ["--destaque", "--destaque-2", "--destaque-suave", "--foco"]) raiz.style.removeProperty(k);
  const loja = tema === "loja" ? lerCoresLoja() : null;
  if (loja) {
    raiz.style.setProperty("--destaque", loja.destaque);
    raiz.style.setProperty("--destaque-2", loja.destaque);
    raiz.style.setProperty("--foco", loja.destaque);
    raiz.style.setProperty("--destaque-suave", loja.suave);
  }
  raiz.style.setProperty("--escala", String(escala));
}

// ---------- cor da marca a partir do logo (tudo no navegador, nada sai do PC)

function hex(r: number, g: number, b: number) {
  return "#" + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
}

function luminancia(r: number, g: number, b: number) {
  const c = [r, g, b].map((v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

/** Escolhe a cor mais marcante do logo e escurece até ter contraste AA com texto branco (botões). */
export function corDominante(pixels: Uint8ClampedArray): CoresLoja | null {
  const baldes = new Map<number, { n: number; r: number; g: number; b: number }>();
  for (let i = 0; i < pixels.length; i += 4) {
    const [r, g, b, a] = [pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3]];
    if (a < 128) continue;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    if (max - min < 40 || max < 40 || min > 225) continue; // ignora cinzas, preto e branco
    let h = 0;
    if (max === r) h = ((g - b) / (max - min)) % 6;
    else if (max === g) h = (b - r) / (max - min) + 2;
    else h = (r - g) / (max - min) + 4;
    const k = Math.round(((h * 60 + 360) % 360) / 20);
    const bk = baldes.get(k) ?? { n: 0, r: 0, g: 0, b: 0 };
    bk.n++; bk.r += r; bk.g += g; bk.b += b;
    baldes.set(k, bk);
  }
  const melhor = [...baldes.values()].sort((a, b) => b.n - a.n)[0];
  if (!melhor) return null;
  let [r, g, b] = [melhor.r / melhor.n, melhor.g / melhor.n, melhor.b / melhor.n];
  // Contraste com branco >= 4.5:1  <=>  luminância <= ~0.183
  for (let i = 0; i < 30 && luminancia(r, g, b) > 0.183; i++) { r *= 0.9; g *= 0.9; b *= 0.9; }
  const suave = hex(r + (255 - r) * 0.88, g + (255 - g) * 0.88, b + (255 - b) * 0.88);
  return { destaque: hex(r, g, b), suave };
}

export async function coresDoLogo(arquivo: File): Promise<CoresLoja | null> {
  const url = URL.createObjectURL(arquivo);
  try {
    const img = new Image();
    await new Promise<void>((ok, erro) => { img.onload = () => ok(); img.onerror = () => erro(new Error("imagem inválida")); img.src = url; });
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const ctx = c.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, 64, 64);
    return corDominante(ctx.getImageData(0, 0, 64, 64).data);
  } finally {
    URL.revokeObjectURL(url);
  }
}
