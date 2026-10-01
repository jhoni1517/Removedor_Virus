// Teste da página (roda no CI com Node): o mesmo vetor assinado que o pytest confere em Python.
import { readFileSync } from "node:fs";
import { verificar } from "./verificar.js";

const [frag, digital] = readFileSync(new URL("../../testes/fixtures/laudo_assinado.txt", import.meta.url), "utf8")
  .trim().split("\n");
const valido = await verificar("#" + frag);
const dados = JSON.parse(Buffer.from(frag.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8"));
dados.n = 100;
const adulterado = await verificar("#" + Buffer.from(JSON.stringify(dados)).toString("base64url"));
const falhas = [];
if (!valido.ok) falhas.push("assinatura válida recusada");
if (valido.digital !== digital) falhas.push(`digital ${valido.digital} != ${digital}`);
if (adulterado.ok) falhas.push("laudo adulterado aceito");
if ((await verificar("#lixo")).ok) falhas.push("lixo aceito");
if (falhas.length) { console.error("FALHOU:", falhas.join("; ")); process.exit(1); }
console.log("página de verificação: ok");
