// Verificação do laudo do CelScan no navegador: confere a assinatura Ed25519 (WebCrypto).
// Os dados vêm depois do "#" da URL e nunca são enviados a servidor nenhum.

export function deB64(s) {
  const b = atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4));
  return Uint8Array.from(b, (c) => c.charCodeAt(0));
}

export function lerDados(fragmento) {
  return JSON.parse(new TextDecoder().decode(deB64(fragmento.replace(/^#/, ""))));
}

// Igual a celscan/core/assinatura.py: mensagem()
export function mensagem(d) {
  return new TextEncoder().encode("CELSCAN1|" + ["i", "d", "m", "n", "v", "h"].map((c) => (d[c] ?? "") + "").join("|"));
}

export async function impressaoDigital(pub) {
  const h = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", pub)))
    .map((x) => x.toString(16).padStart(2, "0")).join("").toUpperCase();
  return [0, 4, 8, 12].map((i) => h.slice(i, i + 4)).join("-");
}

/** Devolve {ok, dados, digital} ou {ok:false, erro}. */
export async function verificar(fragmento) {
  let d;
  try {
    d = lerDados(fragmento);
  } catch {
    return { ok: false, erro: "O link está incompleto ou foi alterado." };
  }
  if (!crypto?.subtle) return { ok: false, erro: "Este navegador não consegue conferir assinaturas." };
  try {
    const pub = deB64(d.k);
    const chave = await crypto.subtle.importKey("raw", pub, { name: "Ed25519" }, false, ["verify"]);
    const ok = await crypto.subtle.verify({ name: "Ed25519" }, chave, deB64(d.s), mensagem(d));
    return { ok, dados: d, digital: await impressaoDigital(pub), erro: ok ? null : "A assinatura não confere: os dados do laudo foram alterados." };
  } catch (e) {
    return { ok: false, dados: d, erro: "Seu navegador não suporta este tipo de assinatura (Ed25519). Atualize o navegador e tente de novo." };
  }
}
