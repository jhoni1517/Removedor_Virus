# CelScan Studio (v4) — Plano de transformação

> **Status: aguardando sua aprovação.** Este plano (seção "CelScan Studio (v4)") ainda **não**
> começou a ser implementado. Leia com o `AUDITORIA.md` e o `COMPARATIVO.md`. Abaixo dele fica o
> plano da v3 (já executado), preservado como histórico.

Base: a v3 está sólida e testada (ver `AUDITORIA.md`). O salto para o Studio é de **arquitetura**
(motor com plugins + adbutils/asyncio, front Tauri, Agente Android, Nuvem) e de **cobertura**
(funções ❌ da auditoria). **Nada do que existe será jogado fora**: `core/analise/acoes` viram os
plugins do motor; as telas React migram de pywebview para Tauri.

## Beta 3.0.0b6 (01/10/2026) — entregue

| Item | Situação |
|---|---|
| Domínios dos indicadores do MVT (dívida 4) | ✅ usados, com checagem de subdomínio |
| Temas Bancada, Noite, Terminal, Alto contraste, Minha Loja (cor do logo) + tamanho de texto | ✅ com Vitest no CI |
| Modo proteção à vítima de stalkerware (documentar antes, contatos de apoio, confirmação) | ✅ |
| Histórico: o que mudou desde a última visita (inclui certificado trocado) | ✅ |
| Balcão: ordem de serviço, pacotes de 1 clique, WhatsApp, painel do dia/mês, CSV | ✅ |
| Laudo de seminovo (bateria com veredito, IMEI, checklist de hardware, assinaturas) | ✅ |
| Debloat com níveis Recomendado/Avançado/Especialista (nunca "inseguro") | ✅ |
| Teste de desempenho real (abertura de apps, gravação/leitura) | ✅ |

**Pendências (para revisar juntos ou depender de você):**
- Interrompidos por um filtro automático de segurança, não retomados por conta própria: análise de
  APK por conteúdo, painel de consumo de bateria por app e leitura da configuração de rede.
- Depende do celular real: confirmar tudo acima, conexão Wi-Fi/USB, bateria/IMEI por fabricante,
  keyring e aviso de driver no Windows.
- Reescritas grandes: adbutils + vários aparelhos em paralelo, Tauri, Agente Android, Nuvem.
- Custo seu (pergunto na hora): assinatura de código e hospedagem da nuvem.

## Decisões que eu preciso de você (com minha recomendação)

Antes de começar, preciso destas respostas — algumas têm custo:

| # | Decisão | Minha recomendação |
|---|---|---|
| D-A | **Migrar para Tauri 2 agora** ou manter pywebview e migrar por último? | **Migrar por último.** O front React já roda; Tauri dá instalador nativo/auto-update, mas trava tudo se vier primeiro. Faço o motor e as funções antes; Tauri na Fase 2. |
| D-B | **Empacotar o motor Python** com Nuitka ou PyInstaller? | **PyInstaller agora** (já funciona), avaliar **Nuitka** depois (mais rápido/menor, porém mais frágil com FastAPI/uvicorn). |
| D-C | **Agente Android (Kotlin)**: construo? Exige build Android (Gradle) no CI. | **Sim, mas na Fase 3.** Resolve nome/ícone/uso/rede de um jeito que o ADB não faz. Enquanto isso, uso a Play Store como fonte de nome/ícone. |
| D-D | **Assinatura de código** (Windows ~US$ 200–400/ano; EV mais caro). Sem ela: "editor desconhecido" e antivírus reclamando. | **Comprar antes do auto-update (Fase 2/D7).** Recomendo certificado OV; te pergunto de novo na hora. **Custo seu.** |
| D-E | **CelScan Nuvem (Next.js/Vercel)**: verificação de laudo, licença, painel. Tem custo de hospedagem. | **Só na Fase 7.** Começo com verificação de laudo estática (grátis na Vercel); licença Ed25519 **offline** não precisa de servidor. |
| D-F | **IA opcional** (resumo do laudo): qual provedor e **quem paga a chave**? | **Desligada por padrão**, o usuário põe a própria chave (guardada no keyring). Recomendo Claude; te consulto sobre custo antes de ligar. |
| D-G | **Repositório público ou privado?** Hoje é público. | Com marca própria e venda, **tornar privado** antes da Fase 5 (balcão/negócio). |
| D-H | **Preço** (ver COMPARATIVO seção 6): Técnico **vitalício R$ 149**? | **Sim** — é o golpe mais forte contra as assinaturas em dólar dos concorrentes. |

## Fases (ordem por impacto × esforço; segue a seção 9 do seu pedido)

### Fase 0 — Fundação de qualidade (rápida, sem quebrar nada) — ✅ CONCLUÍDA (b5)
- ✅ Quarentena em **zip com senha `infected`** + Cryptodome (dívida 5 — antivírus para de apagar prova).
- ✅ **SHA-256 + allowlist de host** em todo download (dívida 7); scrcpy 4.1 com hash fixado.
- ✅ Segredos no **keyring** do sistema, com migração e fallback (dívida 10).
- ✅ Detecção de **driver USB do fabricante** no Windows + link do driver na tela Conectar (dívida 6).
- **Testado:** 90 testes (pytest) + build da interface. 🔬 **Falta confirmar no Windows real** (keyring
  no Gerenciador de Credenciais, aviso de driver com celular de verdade).

### Fase 1 — Motor sólido (prioridade 1 do seu pedido)
- Migrar `core/adb.py` para **adbutils** (conexão persistente) + **asyncio** por aparelho (dívida 1).
- **Motor de plugins**: cada verificação vira plugin com manifesto (id, plataforma, coleta, parser,
  regras, ações, desfazer). `core/analise/acoes` atuais viram os primeiros plugins.
- **Pacotes de regras/IOCs versionados** e atualizáveis (dívida 11); parsear os **domínios** dos
  IOCs do MVT (dívida 4).
- Cache de assinatura/hash cobrindo **todos** os apps (dívida 2).
- **Meta de desempenho:** 200 apps em ≤ 90 s. **Risco:** médio (refator grande, mas com testes).

### Fase 2 — Interface: temas, layouts e Tauri
- **Design system** com tokens + catálogo de componentes; acessibilidade AA.
- **Temas**: Bancada, Noite, Terminal, Alto contraste, Minha Loja (cores do logo).
- **Layouts**: Assistente, Painel técnico, Balcão (kanban), Modo cliente (2ª tela).
- **Visualizações**: Raio-X (bolhas), Linha do tempo, Medidor com decomposição.
- Migrar o empacotamento para **Tauri 2** (motor Python como sidecar) + **auto-update** + assinatura.

### Fase 3 — Nomes/ícones + Agente Android + Segurança avançada
- **Agente Android (Kotlin)** instalado por adb e removido no fim: nome/ícone em lote, uso, rede,
  VPN/certificados. Fallback: Play Store.
- **Segurança**: análise estática de APK (manifesto/strings/URLs + YARA + domínios IOC); apps que
  imitam o sistema; ícone escondido pós-instalação; reputação na Play; **modo vítima** de
  stalkerware (documentar antes de remover, contatos de apoio — Ligue 180).

### Fase 4 — Balcão, laudos e negócio
- Ordem de serviço, pacotes de serviço (1 clique), painel da loja (CSV).
- Modelos de laudo: Clássico, Moderno, Resumido, Técnico, **Seminovo**.
- Estrutura de **licença Ed25519 offline** + planos (preços configuráveis).

### Fase 5 — Demais funções
- Sensores, consumo em 2º plano (wakelocks/batterystats), rede (VPN/DNS), modo profundo
  (AndroidQF+MVT), apps esquecidos, lote, transferência entre aparelhos (essencial), tendência de
  bateria/armazenamento, teste de desempenho (am start -W, dd).

### Fase 6 — Nuvem e IA (opcionais, com consentimento)
- Verificação de laudo por QR (hash assinado, sem dado pessoal); painel multiloja; distribuição de
  regras/IOCs; explicação por IA (chave do usuário, só metadados) e automações YAML.

## Riscos principais
- **Refator do adb (Fase 1)** pode regredir a coleta → mitigo com os testes atuais + fixtures reais.
- **Agente Android** adiciona build Gradle no CI e superfície de segurança → assinado, removido no fim, sem internet.
- **Tauri** muda todo o empacotamento → só depois do motor estável; mantenho pywebview até validar.
- **Assinatura de código e Nuvem** têm **custo seu** → paro e pergunto (D-D, D-E).
- **Aparelho real**: eu não testo daqui; cada fase depende de você rodar e mandar as saídas.

---

# CelScan v3 — Plano de implementação (já executado — histórico)

> **Plano aprovado em 30/09/2026.** Decisões registradas abaixo, em "Decisões tomadas".

## Decisões tomadas (30/09/2026)

| # | Decisão | Resposta |
|---|---|---|
| 1 | Nome/destino | **CelScan é o produto.** O v0.2 é substituído quando a Etapa A ficar pronta |
| 2 | Testes em aparelho real | **Sim**: você roda `celscan fixtures` em 3 marcas e os testes guiados ao fim de cada etapa |
| 3 | Interface | **FastAPI + React + pywebview** |
| 4 | PDF | **reportlab + qrcode** |
| 5 | Certificados dos bancos | **Sim**: comando que extrai os certificados dos apps de banco do seu celular (junto com o item B1) |
| 6 | Assinatura digital do `.exe` | **Adiada.** ⏰ **Lembrete:** perguntar de novo no fim da Etapa A (A3, instalador novo) e antes da D7 (atualização automática) |
| 7 | Repositório público/privado | Continua como está. Mudar a visibilidade é com você, nas configurações do GitHub |
| 8 | Modo balcão grátis/pago | Em aberto; só afeta a D4 (modo balcão) |

## Beta 3.0.0b4 (30/09/2026): correções do aparelho real + novas funções

Testado no Redmi (24090RA29G) do dono: conectou por USB, laudo saiu. Ajustes:

| Item | Situação |
|---|---|
| **Conexão "Reconectando..."** | ✅ o status agora reflete o polling (fica verde mesmo se o WebSocket não subir); a lib `websockets` passou a ser empacotada de verdade no `.exe` |
| **Falsos positivos no laudo** | ✅ apps de sistema atualizados pela loja não são mais acusados de "escondido/fora da loja" (usa `pm list packages -s`); GetApps `com.xiaomi.discover` reconhecida; SMS padrão "null" ignorado; apps de consumo conhecidos na lista de confiáveis |
| **Diagnóstico completo** | ✅ saúde real da bateria (capacidade vs projeto, ciclos), situação, identificação e IMEI (via `service call`), espaço, RAM, pastas grandes — CLI, API e tela nova |
| **Limpeza** | ✅ cache + lixo seguro (miniaturas, temporários, cache do Telegram), medindo o quanto libera; nunca apaga mídia pessoal (irreversível) |
| **Recuperação de sobras** | ✅ lixeira da galeria, miniaturas e mídia deixada nos apps; aviso honesto: sem root não há undelete real nem recuperação de WhatsApp apagado |
| **Espelho: streaming travando/preto** | ✅ "modo compatível" (resolução/taxa menores + buffer); aviso de que DRM aparece preto de propósito; atalhos que abrem direto as telas de ajuste no celular |
| **iPhone: ver por USB** | ✅ nome, modelo, iOS, IMEI e saúde da bateria (precisa do libimobiledevice); varredura completa (backup+MVT) continua no `celscan ios` |
| **Interface** | ✅ novas seções Diagnóstico, Recuperar; painéis de iPhone e atalhos |

**Recusado (e por quê):** função de "espionagem" de celular/redes sociais — é stalkerware,
é crime e contradiz o produto, que existe para detectar e remover exatamente isso.

**Não testado em aparelho real ainda:** limpeza, recuperação, diagnóstico de bateria/IMEI
(varia por fabricante), iPhone (precisa de Mac/Windows com libimobiledevice).

## Extra pedido em 30/09/2026: tela quebrada (beta 3.0.0b2)

| Item | Situação |
|---|---|
| **D1 Espelhamento (antecipado)** | ✅ scrcpy embutido: ver e controlar, só ver, desligar a tela do celular, gravar em vídeo; botão "Ver a tela" também no resultado |
| **Modo mouse sem depuração (OTG)** | ✅ toque quebrado: o mouse/teclado do PC controla o celular sem depuração USB, para ligar a depuração e tocar em Permitir; o CelScan pausa o adb enquanto isso |
| **Cópia dos dados (parte do item 13)** | ✅ por categoria, só leitura, datas preservadas, conferência de tamanho (SHA-256 opcional), retomada, relatório e LEIA-ME com aviso de LGPD, lista de apps |
| **Guia por situação** | ✅ autorizado / toque quebrado / sem imagem / não liga, com os limites reais explicados |

**Ainda falta do item 13 (D6):** contatos, SMS e registro de chamadas (o Android bloqueia pelo
adb sem um app auxiliar), prévia com imagens e escolha de pasta pela janela do Windows.
**Não testado em aparelho real:** tudo isso. O modo mouse (OTG) no Windows depende do driver
USB do celular; se falhar, o guia oferece o mouse USB com adaptador OTG.

## Etapa A: concluída em 30/09/2026 (beta 3.0.0b1)

| Item | Situação | Como foi testado |
|---|---|---|
| A1 Backend | ✅ FastAPI + WebSocket, track-devices, tarefas canceláveis, Wi-Fi com QR, token por sessão | 11 testes de API com o ADB simulado |
| A2 Interface | ✅ Conectar (passo a passo por marca, Wi-Fi), Modo, Varredura, Resultado, Desfazer em 10 s, Histórico, Configurações; tema claro/escuro | Chromium (Playwright) com o ADB simulado, sem erros de console |
| A3 Empacotamento | ✅ CelScan.exe + celscan-cli.exe com adb e scrcpy; instalador que remove o v0.2 | Build no Windows (GitHub Actions) + `celscan-cli.exe --help/bases`; binário completo testado no Linux |
| A4 Laudo PDF | ✅ Cliente e técnico, QR + código de verificação | Testes de texto do PDF e verificação |

**Não testado ainda (depende de você):**
- aparelho real;
- a janela no Windows (pywebview/WebView2);
- o instalador de verdade (instalar, atualizar sobre o v0.2, desinstalar);
- o pareamento Wi-Fi com celular de verdade.

**Pendências da Etapa A:**
- imagens no passo a passo por marca (hoje é só texto);
- a marca não é detectada antes de o celular autorizar o computador (o usuário escolhe).

⏰ **Lembrete (decisão 6): assinatura digital do `.exe`.** O instalador novo está pronto e ainda
sai sem assinatura. Pergunto de novo antes da D7 (atualização automática).

## Onde estamos (antes da Etapa A)

A **Fase 0 está concluída**: 10 commits, todos já no GitHub (branch `ccr-b3fdeeb6-jqhbn5`).
O CI roda **ruff + 44 testes** no Windows e no Linux, com Python 3.9 e 3.12, e está todo verde.

| Item da Fase 0 | Situação |
|---|---|
| Rodar `android` e `otimizar` e corrigir falhas | ✅ só com o **ADB simulado** (veja o aviso abaixo). Corrigido: travamento sem teclado (EOFError); remoção não tirava o app de administrador; animações sem desfazer; janela de console no Windows; linha de erro do appops lida como válida |
| Pacote `core/ analise/ acoes/ ios/ relatorio/ api/ cli.py` | ✅ `python celscan.py android` continua funcionando; também `python -m celscan` |
| Coleta separada da análise; `regras.yaml` | ✅ peso + título + "o que significa" + "o que fazer" em cada regra; `~/.celscan/regras.yaml` sobrescreve |
| Log de comandos adb com tempos | ✅ `~/.celscan/logs/celscan.log` |
| ruff + type hints + pytest | ✅ leitores com 94% de cobertura; teste de ponta a ponta com `fake_adb.py` |
| SQLite (aparelhos, varreduras, ações, clientes) | ✅ + comando `celscan historico`; clientes só com consentimento e com exclusão (LGPD) |
| Bases em segundo plano + modo offline | ✅ indicadores, UAD e certificados; `--offline`; comando `celscan bases` |
| Parsers tolerantes com aviso visível | ✅ "Verificação de X não disponível neste aparelho" na tela, no laudo e no JSON |

**⚠️ Aviso sobre o teste em aparelho real.** O plano diz que há um celular conectado, mas eu rodo
num servidor na nuvem e **não tenho acesso a nenhum celular**. Tudo foi testado com o ADB simulado
e com fixtures **sintéticas** (marcadas como tal em `testes/fixtures/LEIAME.md`).

Para resolver, criei o comando `python celscan.py fixtures`. Ele grava a saída real de cada comando
(inclusive os que a Fase 3 vai usar) e anonimiza serial, IMEI, e-mails, MACs, redes Wi-Fi e IPs.
**Preciso que você rode esse comando em 3 marcas** (ex.: Samsung, Motorola e Xiaomi) e mande as
pastas geradas. Até lá, nenhuma funcionalidade pode ser declarada "testada no aparelho real".

## Ordem final (ajustada pelo COMPARATIVO.md)

**Como ler a coluna "Esforço":** estimativa do **meu** tempo de implementação, com testes
automáticos, em dias de trabalho. Não inclui as rodadas de teste no seu aparelho.

**Mudanças em relação ao plano original, vindas da pesquisa:**
- A proteção Pix ganhou a detecção de **captura de tela** e de **imitação de nome**, porque é
  assim que o PixRevolution (2026) funciona.
- **Nome e ícone reais** subiram de prioridade: sem eles, nenhuma tela é legível para leigo.
- **Laudo PDF** veio para o começo, porque todas as funcionalidades escrevem nele.
- **Backup completo** e **atualização automática** desceram. A atualização automática depende
  da assinatura digital do programa (decisão 6).

### Etapa A: base da interface (Fase 2)

| # | Item | Esforço |
|---|---|---|
| A1 | Backend FastAPI reaproveitando os módulos; WebSocket com progresso por etapa; tarefas canceláveis; cabo desconectado encerra a tarefa limpo | 2 d |
| A2 | Frontend React/TypeScript/Tailwind com identidade "bancada técnica", tema claro/escuro e navegação por teclado; telas: Conectar (detecção automática do cabo, passo a passo por marca, Wi-Fi com QR), Modo, Varredura, Resultado (nota + cards), Ações com "Desfazer" por 10 s | 4 d |
| A3 | Empacotamento: um `.exe` com pywebview + adb + scrcpy; build reproduzível no GitHub Actions; substitui o instalador atual | 1,5 d |
| A4 | Laudo **PDF** nativo (resumido e técnico) com QR code + hash de autenticidade (item 18) | 1,5 d |

### Etapa B: segurança (Fase 3, prioridade máxima)

| # | Item do plano | O que muda depois da pesquisa | Esforço |
|---|---|---|---|
| B1 | **1. Proteção Pix e bancos** | Acessibilidade + sobreposição + **captura de tela (PROJECT_MEDIA)** + app bancário no mesmo aparelho; certificado oficial; typosquatting (`com.whatsaap`, "Correios", "Sicredi"...) | 2,5 d |
| B2 | **8. Nome e ícone reais** | Cache por hash; lê só o necessário do APK | 2 d |
| B3 | **6. Gerenciador de permissões** | Revogar/tirar sobreposição/tirar acessibilidade em 1 clique, com desfazer | 1,5 d |
| B4 | **7. Histórico e diferenças** | Usa os "retratos" do banco (já existem) | 1,5 d |
| B5 | **2. Painel de sensores** | Últimos acessos pelo `appops`; destaca app sem ícone ou fora da loja | 1,5 d |
| B6 | **4. Análise de rede** | VPN, VPN sempre ativa, DNS privado, proxy global e de APN | 1 d |
| B7 | **3. Consumo em segundo plano** | `netstats`/`batterystats`; formato varia muito entre marcas, **depende das fixtures reais** | 2 d |
| B8 | **5. Modo Profundo** | Baixa o AndroidQF, roda `mvt-android check-androidqf`, traduz o resultado; análise de bugreport | 2 d |

### Etapa C: otimização e armazenamento

| # | Item | Esforço |
|---|---|---|
| C1 | **11. Debloat no nível do UAD**: 4 níveis traduzidos ("Inseguro" escondido por padrão), filtro por marca, perfis salvos e aplicáveis em lote, multiusuário/perfil de trabalho, sempre **desativar** antes de desinstalar | 2 d |
| C2 | **12. Otimização mensurável**: antes/depois de espaço, cache, `am start -W` de 3 apps e apps em segundo plano | 1,5 d |
| C3 | **10. Apps esquecidos** (`usagestats`) | 1 d |
| C4 | **9. Limpeza guiada de armazenamento**: grandes, duplicados por hash, APKs em Download, mídia do WhatsApp, miniaturas; prévia com imagens; "copiar para o PC antes" | 2,5 d |

### Etapa D: praticidade

| # | Item | Esforço |
|---|---|---|
| D1 | **15. Espelhamento de tela** (scrcpy embutido) | 1 d |
| D2 | **14. Gerenciador de apps em lote** (APK/XAPK/APKM, extrair, parar, limpar, congelar) | 1,5 d |
| D3 | **16. Checklist de hardware + laudo de seminovo** | 2 d |
| D4 | **17. Modo balcão** (vários aparelhos, cliente, OS, logo, WhatsApp/e-mail, LGPD) | 3 d |
| D5 | **19. iPhone mais completo** (apps, perfis/MDM, crash logs, bateria, backups) | 2,5 d |
| D6 | **13. Backup antes de formatar** (hash, retomada, relatório) | 3 d |
| D7 | **20. Atualização automática** do programa e das bases, com changelog | 1,5 d |

### Etapa E: qualidade e entrega (Fase 4)

Fixtures de 3 fabricantes, meta de desempenho (200 apps em até 2 min, medida no log), robustez
com o cabo desconectado, `README.md` com imagens e `DESENVOLVIMENTO.md`: **3 d**.

**Total estimado: ~51 dias de trabalho**, sem contar as rodadas de teste no seu aparelho.
Ao fim de cada etapa entrego um resumo com: o que foi feito, o que foi testado no aparelho real,
o que ficou pendente e o que você precisa decidir.

## Decisões que eu precisava de você (texto original)

1. **Nome e destino do produto.** Proposta:
   - o CelScan vira o produto principal;
   - o "Removedor de Vírus Android" v0.2 (janela simples, já publicado na página Releases)
     continua disponível até a nova interface (Etapa A) ficar pronta, e aí é substituído;
   - o repositório pode continuar o mesmo ou ser renomeado.
2. **Testes em aparelho real.** Você topa rodar `python celscan.py fixtures` em 3 marcas e
   fazer os testes guiados no fim de cada etapa?
3. **Tecnologia da interface.** FastAPI + React + pywebview, como no seu plano:
   - o `.exe` deve ficar em torno de 60–90 MB com adb e scrcpy (estimativa);
   - o build passa a precisar de Node, o que o CI resolve.

   Confirma? A alternativa é manter a janela Tkinter, que é mais leve e mais simples.
4. **PDF.** Recomendo `reportlab` + `qrcode` (Python puro, sem instalar nada extra no Windows).
   O WeasyPrint deixaria o laudo mais bonito, mas exige GTK.
5. **Certificados dos bancos.** A lista precisa ser conferida em aparelho real. Posso criar um
   comando que extrai os certificados dos apps de banco instalados pela Play Store no seu celular
   e os adiciona à lista. Você tem acesso a vários apps de banco para isso?
6. **Assinatura digital do `.exe`** (certificado de code signing, custo anual). Sem ela:
   - o Windows mostra "editor desconhecido";
   - antivírus tendem a marcar o programa como suspeito (irônico para um antivírus);
   - a atualização automática (D7) fica menos confiável.

   Você pretende comprar?
7. **Repositório público ou privado.** Hoje ele é público. Com modo balcão, logo de loja e
   possível venda, talvez faça sentido torná-lo privado.
8. **Modo balcão grátis ou pago?** Isso muda se vamos precisar de licença/ativação.
