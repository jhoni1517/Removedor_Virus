# CelScan Studio — Comparativo com concorrentes (v4, 30/09/2026)

Atualização da pesquisa de set/2026 com preços e reclamações de 2026. Onde a fonte pública é rasa,
marco **"não confirmado"** — conferir com uso real antes de copiar. Fontes no fim.

> Preços em dólar/euro são dos concorrentes; um dos nossos diferenciais é **cobrar em real** e
> oferecer **licença vitalícia** contra a assinatura em moeda estrangeira da maioria.

## 1. Resumo e preço de cada ferramenta (2026)

| Ferramenta | O que é | Preço 2026 | Para copiar |
|---|---|---|---|
| **UAD-ng** | Debloat via ADB, sem root, código aberto (Rust GUI) | Grátis | Níveis *Recommended/Advanced/Expert/Unsafe*; listas por marca/operadora; desativar ≠ desinstalar; reversível |
| **ADB AppControl** | Gerenciador Android no Windows | Grátis + Pro | Lote com **presets**, instalar APK/APKS, extrair APK, permissões, console com sintaxe |
| **scrcpy** | Espelho/controle via USB/Wi-Fi (Apache 2.0, v4.1) | Grátis | Latência baixa, câmera/áudio, embutível |
| **MVT + AndroidQF** (Amnesty) | Perícia: coleta + indicadores de spyware | Grátis | Coleta forense sem instalar, IOCs atualizados, saída criptografada (age) |
| **iVerify Basic** | Caça a spyware (Pegasus) no próprio celular | **US$ 0,99**; forense avançada a cada 90 dias | Varredura de 5 min "no bolso"; achou 7 Pegasus em 2.500 testes; UX de confiança |
| **Certo AntiSpy** | Anti-spyware iOS/Android | Grátis + **de US$ 8,99**; anual −53% | "Escaneia o aparelho inteiro e remove"; auditoria de privacidade; nota 4,6 na Play |
| **Kaspersky / ESET / Malwarebytes / Avast / Bitdefender** | Antivírus residente | Kaspersky US$ 11,99/ano · Bitdefender US$ 14,99/ano · Malwarebytes ~US$ 3,33–5/mês | Detecção alta (Malwarebytes 100% stalkerware, AV-Comparatives 2025); ESET "Proteção de pagamento" |
| **AirDroid Personal** | Espelho + transferência via nuvem | US$ 2,50–3,99/mês | Fluxo de transferência; **mas muita reclamação** (suporte, reembolso, cobrança) |
| **Dr.Fone** (Wondershare) | Suíte paga Android/iOS | **US$ 79,95–139,95/ano**; vitalício ~US$ 115 | Assistentes 1 clique; **nota 3,0/5, custo-benefício 2,7/5** (caro, pop-ups, trava) |
| **DroidKit** (iMobie) | Suíte Android | **US$ 39,99/ano · US$ 55,99 vitalício** | Reparo/recuperação guiados; recuperação real exige **root** |
| **iMazing** | Gerenciador de iPhone + Spyware Analyzer grátis | **de US$ 39,99** (1 disp.) | Tudo local; análise por backup; UX de backup excelente |
| **3uTools** | Gerenciador de iPhone (Windows) | Grátis | **Relatório de peças** (tela/bateria trocadas), saúde/ciclos, ativação/jailbreak |
| **AnyTrans** (iMobie) | Transferência iOS | €39,99 vitalício | Transferência entre aparelhos |
| **TinyCheck / PiRogue** | Raspberry Pi que analisa a **rede** do celular | Grátis (precisa de hardware) | Detecta stalkerware pelo tráfego — o que o ADB não vê |
| **Samsung Smart Switch / Xiaomi / Motorola** | Suítes do fabricante | Grátis | Transferência oficial; só a própria marca |

## 2. Matriz de funções (nota 0–3)

0 = não tem · 1 = fraco/indireto · 2 = bom · 3 = referência. "Cel v4" = meta do CelScan Studio.

| Função | UAD | AppControl | MVT/QF | iVerify | Certo | Antivírus | Dr.Fone/DroidKit | iMazing/3uTools | **Cel hoje** | **Cel v4** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Detecção spyware/stalkerware | 0 | 0 | 3 | 3 | 3 | 3 | 0 | 2 | **2** | **3** |
| Trojan bancário / Pix (overlay+captura) | 0 | 0 | 1 | 1 | 1 | 2 | 0 | 0 | **2** | **3** |
| Análise estática de APK (sem rodar) | 0 | 1 | 2 | 0 | 1 | 2 | 0 | 0 | **2** | **3** |
| Nome e ícone reais dos apps | 0 | 3 | 1 | 2 | 2 | 3 | 2 | 2 | **2** | **3** |
| Debloat com níveis de segurança | 3 | 2 | 0 | 0 | 0 | 0 | 1 | 0 | **1** | **3** |
| Gerenciar permissões (com desfazer) | 1 | 2 | 0 | 0 | 1 | 1 | 0 | 0 | **2** | **3** |
| Espelhar/controlar a tela | 0 | 2 | 0 | 0 | 0 | 0 | 1 | 1 | **2** | **3** |
| Análise de rede (VPN/DNS/proxy) | 0 | 0 | 2 | 1 | 1 | 1 | 0 | 0 | **1** | **2** |
| Perícia completa (bugreport/IOCs) | 0 | 0 | 3 | 2 | 1 | 1 | 0 | 0 | **0** | **2** |
| Saúde de bateria/peças (seminovo) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | **2** | **3** |
| Otimização **medida** (antes/depois) | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | **1** | **3** |
| Backup / recuperação de sobras | 0 | 1 | 1 | 0 | 0 | 0 | 3 | 3 | **2** | **2** |
| Laudo profissional com QR verificável | 0 | 0 | 1 | 1 | 1 | 0 | 0 | 1 | **2** | **3** |
| Histórico / diferenças entre visitas | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | **1** | **3** |
| Modo balcão (vários aparelhos, OS, kanban) | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | **1** | **3** |
| iPhone (spyware + peças) | 0 | 0 | 2 | 3 | 2 | 1 | 1 | 3 | **1** | **2** |
| Linguagem leiga (o que significa/fazer) | 1 | 0 | 0 | 2 | 2 | 2 | 1 | 1 | **3** | **3** |
| Proteção à vítima de stalkerware | 0 | 0 | 1 | 1 | 1 | 0 | 0 | 0 | **0** | **3** |
| Português + preço em real | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | **3** | **3** |
| Offline total / privacidade | 2 | 2 | 3 | 1 | 1 | 0 | 1 | 3 | **3** | **3** |

**Leitura:** ninguém junta segurança séria + debloat + otimização medida + laudo + balcão **em
português, offline e barato**. Os fortes em segurança (MVT, iVerify, antivírus) são fracos em
balcão/laudo; os fortes em suíte (Dr.Fone, iMazing) são caros, em dólar e fracos em
anti-stalkerware honesto.

## 3. As 15 ideias para roubar (e fazer melhor)

1. **Níveis de debloat do UAD** (Recommended/Advanced/Expert) → traduzir; **nunca** mostrar
   "Unsafe" a leigo; sempre "desativar" antes de "desinstalar", com desfazer.
2. **Presets em lote do ADB AppControl** → perfis por marca aplicáveis a vários aparelhos no balcão.
3. **Relatório de peças do 3uTools** → checklist de hardware/seminovo no Android dentro do possível.
4. **Spyware Analyzer local do iMazing** → nossa perícia (AndroidQF+MVT) roda offline e **traduz** o resultado.
5. **Varredura de 5 min do iVerify** → "check-up rápido" com barra de progresso real e resultado em 1 tela.
6. **Console com sintaxe do AppControl** → console adb ao vivo no layout técnico.
7. **Extrair/instalar APK/APKS do AppControl** → com verificação de assinatura antes de instalar.
8. **Saída criptografada do AndroidQF** → nossa quarentena/evidências em zip cifrado.
9. **Auditoria de privacidade do Certo** → painel "quem vê sua câmera/microfone/localização".
10. **Transferência do Smart Switch/AnyTrans** → transferência **entre dois aparelhos** reinstalando da Play.
11. **Reputação na Play (fonte de nome/ícone)** → confere se o pacote existe e se o dev bate — sem depender do Agente.
12. **Detecção por rede do TinyCheck** → sem hardware: ler VPN/DNS/proxy por ADB + cruzar domínios dos IOCs.
13. **Assistente 1 clique do Dr.Fone**, mas honesto → pacotes de serviço ("check-up", "espionagem", "seminovo").
14. **Backup guiado com retomada do iMazing** → já temos; falta prévia com miniaturas e escolha de pasta nativa.
15. **Wakelocks/consumo (batterystats)** → mostrar quem "não deixa o celular dormir" e restringir com desfazer.

## 4. O que os concorrentes erram (e o CelScan resolve)

- **Assinatura cara em dólar** (Dr.Fone US$ 80–140/ano; antivírus anuais) → **real + vitalício**.
- **Custo-benefício ruim / pop-ups / travas** (Dr.Fone 2,7/5) → produto enxuto, sem enganação.
- **Suporte e reembolso ruins, cobranças indevidas** (AirDroid) → offline, sem cobrança recorrente obrigatória.
- **"Limpador"/otimização falsa** (várias suítes) → só otimização **medida** (antes/depois).
- **Recuperação que exige root e frustra** (DroidKit/Dr.Fone) → dizemos o limite **antes**, sem prometer o impossível.
- **Ferramentas de segurança técnicas demais** (MVT/AndroidQF) → mesma força, em **linguagem leiga**.
- **Falta de português** e de foco no **Pix/golpes brasileiros** → nosso território.
- **Remover stalkerware sem cuidar da vítima** → **modo vítima** (documentar antes, contatos de apoio).

## 5. Oceano azul (exclusivo do CelScan Studio)

1. **Proteção Pix numa varredura por USB, em português** — cruza acessibilidade + overlay +
   captura de tela + certificado do banco + imitação de nome. Ninguém junta isso.
2. **Segurança + debloat + otimização medida + laudo com QR + balcão** num só produto, para leigo
   **e** para assistência técnica.
3. **Histórico do aparelho entre visitas** (apps novos, permissões novas, certificado trocado).
4. **Modo balcão com LGPD de verdade** (consentimento, dado mínimo, exclusão) + OS + kanban.
5. **Modo vítima de stalkerware** com documentação de evidências e orientação responsável.
6. **Laudo de seminovo** (peças + segurança + espaço/bateria) com QR verificável — vale para lojas.
7. **Marca própria da loja** (tema gerado do logo, aplicado no app e no laudo).

## 6. Posicionamento e preço sugerido

**Posição:** "O raio-X do celular, em português, honesto e offline — do leigo ao balcão."
Entre o antivírus (barato, residente, mas cego a Pix/perícia) e as suítes caras (Dr.Fone/iMazing).

| Plano | Preço sugerido (R$) | Âncora contra o concorrente |
|---|---|---|
| **Grátis** | R$ 0 | vs. iVerify/Certo grátis: fazemos varredura + laudo simples |
| **Técnico** | R$ 149 **vitalício** (ou R$ 12/mês) | vs. Dr.Fone US$ 80–140/**ano** |
| **Loja** | R$ 39–59/mês por loja | vs. suítes em dólar sem balcão/OS |
| **Rede** | sob consulta | inexistente nos concorrentes |

Recomendação: começar com **Grátis + Técnico vitalício** (o diferencial que mais dói no
concorrente) e deixar Loja/Rede para quando a Nuvem existir.

## 7. Como isso muda as prioridades do PLANO

- **Sobe:** proteção à vítima (modo stalkerware) — hoje é 0 e é diferencial ético + de marketing;
  otimização medida e histórico/diferenças (oceano azul barato de entregar); quarentena em zip
  cifrado (dívida que faz o antivírus apagar prova).
- **Mantém:** Pix, nomes/ícones, debloat com níveis, laudo com QR, balcão.
- **Desce:** transferência entre aparelhos e recuperação profunda (concorrentes pagos já fazem;
  entra só o essencial e honesto).
- **Fora de escopo (ético/jurídico):** espionagem, bypass de FRP/conta, desbloqueio de tela.

## 8. Fontes

- iVerify: [preço US$ 0,99 e caça a spyware](https://www.phonearena.com/news/app-can-tell-if-your-phone-is-compromised-by-pegasus-spyware_id165531), [iVerify Basic na Android](https://iverify.io/blog/iverify-basic-is-now-on-android)
- Certo AntiSpy: [preços e recursos 2026](https://www.certosoftware.com/android-spyware-detection/), [melhores anti-spyware 2026](https://www.certosoftware.com/insights/6-best-anti-spyware-apps-for-android/)
- AirDroid: [review e reclamações](https://deskin.io/resource/blog/airdroid-review), [Trustpilot](https://ch.trustpilot.com/review/web.airdroid.com)
- Dr.Fone/DroidKit: [preços e comparação](https://www.softwaretestinghelp.com/?p=314242), [Dr.Fone 3,0/5](https://www.capterra.com/p/210696/Dr-Fone/reviews/)
- Antivírus: [preços Bitdefender/Kaspersky/Malwarebytes](https://www.cloudwards.net/best-antivirus-for-android/), [AV-Comparatives 2025 stalkerware](https://www.eff.org/deeplinks/2025/11/eff-teams-av-comparatives-test-android-stalkerware-detection-major-antivirus-apps)
- iMazing/AnyTrans: [iMazing 3](https://imazing.com/blog/imazing-3-mac-beta), [AnyTrans vitalício](https://store.thestreet.com/sales/anytrans-for-ios-lifetime-plan)
- UAD-ng, ADB AppControl, scrcpy, AndroidQF/MVT, 3uTools, TinyCheck/PiRogue, PixRevolution: ver
  a versão de set/2026 no histórico do git (fontes mantidas).
