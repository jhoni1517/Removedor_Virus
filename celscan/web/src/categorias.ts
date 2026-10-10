// Tipos de problema (para filtrar e para o plano de ação). A chave vem das regras (regras.yaml).
import type { AppResultado } from "./api";

export type Categoria = "ameaca" | "golpe" | "espionagem" | "anuncio" | "privacidade" | "origem";

export const CATEGORIAS: { id: Categoria; nome: string }[] = [
  { id: "ameaca", nome: "Ameaça conhecida" },
  { id: "golpe", nome: "Golpe e Pix" },
  { id: "espionagem", nome: "Pode espionar" },
  { id: "anuncio", nome: "Anúncios" },
  { id: "privacidade", nome: "Privacidade" },
  { id: "origem", nome: "Origem duvidosa" },
];

const POR_CHAVE: Record<string, Categoria> = {
  ameaca_conhecida: "ameaca", virustotal_detectado: "ameaca",
  imita_app_conhecido: "golpe", imita_pelo_nome: "golpe", certificado_falso: "golpe", trojan_bancario: "golpe",
  sms_padrao: "golpe", nome_com_truque: "golpe", instalou_outros: "golpe",
  acessibilidade: "espionagem", administrador: "espionagem", device_owner: "espionagem", leitor_notificacoes: "espionagem",
  sem_icone: "espionagem", disfarce: "espionagem", disfarce_escondido: "espionagem", sensor_recente: "espionagem",
  envio_dados: "espionagem", sempre_ativo: "espionagem", finge_sistema: "espionagem", mesmo_autor: "espionagem",
  anuncio_popup: "anuncio", anuncio_gatilho: "anuncio", anuncio_escondido: "anuncio", anuncio_tela_cheia: "anuncio", notificacoes_excesso: "anuncio",
  SYSTEM_ALERT_WINDOW: "anuncio",
  fora_da_loja: "origem", certificado_debug: "origem", virustotal_desconhecido: "origem", lote_suspeito: "origem",
  sem_nome: "origem", REQUEST_INSTALL_PACKAGES: "origem", instalado_recente: "origem",
};

export function categoriaDaChave(chave: string): Categoria {
  return POR_CHAVE[chave] ?? (chave.startsWith("android.permission.") || chave === "PROJECT_MEDIA" ? "privacidade" : "origem");
}

/** Categorias de um app que contam pontos (achados com peso > 0). */
export function categoriasDoApp(r: AppResultado): Set<Categoria> {
  return new Set(r.achados.filter((a) => a.peso > 0).map((a) => categoriaDaChave(a.chave)));
}
