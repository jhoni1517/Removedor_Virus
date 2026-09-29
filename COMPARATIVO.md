# CelScan — Comparativo com concorrentes (setembro/2026)

Pesquisa feita na web em 29/09/2026. Onde as fontes públicas eram rasas (páginas de produto
sem detalhes, sites de download de terceiros), o texto diz **"não confirmado"**. Nesses casos,
vale conferir com uso real antes de copiar a ideia. As fontes estão no fim do documento.

## Resumo de cada ferramenta

| Ferramenta | O que é hoje (2026) | Pontos fortes para copiar |
|---|---|---|
| **UAD-ng** (Universal Android Debloater NG) | GUI em Rust, código aberto, remove apps de sistema via ADB sem root | Níveis de remoção com definição clara (*Recommended / Advanced / Expert / Unsafe*); listas por fabricante e operadora; diferencia **desativar** (mais seguro) de **desinstalar**; reversível. A própria equipe avisa que "Recommended" não quer dizer "recomendado remover" |
| **ADB AppControl** | App para Windows (e versão para Android/TV) com modo pago | Ações em lote com **presets**, instalar APK/APKS, salvar APK, gerenciador de permissões, processos, logs, busca de bloatware, console com destaque de sintaxe |
| **scrcpy** | Espelhamento e controle da tela via USB/Wi-Fi, código aberto (v4.1, jul/2026) | Latência baixa, sem instalar nada no celular, câmera e áudio; licença Apache 2.0 (pode ser embutido) |
| **MVT + AndroidQF** (Amnesty) | AndroidQF: binário portátil que coleta backup, bugreport, logs, processos, pacotes/APKs, arquivos, módulos Magisk, com saída criptografada (age). MVT analisa com indicadores de spyware | Coleta forense completa sem instalar nada; indicadores atualizados; saída criptografada. Mas é técnico demais para leigo |
| **iMazing** | Gerenciador de iPhone com Spyware Analyzer gratuito (3.5.2, abr/2026) | Tudo local (nada sobe para servidor); análise a partir do backup; UX de backup muito boa |
| **3uTools** | Gerenciador de iPhone para Windows | **Relatório de verificação**: compara peças com as originais (tela, bateria trocadas), saúde e ciclos da bateria, status de ativação/jailbreak. Só iOS (Android não confirmado) |
| **Dr.Fone / DroidKit / Tenorshare / iMyFone** | Suítes pagas (DroidKit ~US$ 40/ano) | Assistentes de 1 clique, transferência de dados entre aparelhos (inclusive WhatsApp), backup, recuperação. Detalhes de 2026 não confirmados |
| **TinyCheck** (Kaspersky) / **PiRogue Tool Suite** | Raspberry Pi como ponto de acesso Wi-Fi; analisa para onde o celular se conecta (não lê conteúdo). PTS adiciona caso/evidências (Colander) e planeja VPN WireGuard | Detecta stalkerware **pela rede**, o que o ADB sozinho não vê |
| **Antivírus mobile** (Kaspersky, ESET, Malwarebytes, Avast) | Apps residentes no celular | Detecção alta (teste AV-Comparatives 2025: Malwarebytes 100% dos stalkerwares; ESET e Kaspersky todos menos um); ESET Premium tem "Proteção de pagamento" para apps financeiros e antiphishing. Rodam o tempo todo, o que uma ferramenta via USB não faz |

## Contexto de ameaça que muda prioridades

- **Trojans bancários são 53% dos instaladores maliciosos de Android no 1º tri/2026** (Testing
  Ground Labs). Eles usam **telas falsas por cima (overlay)** e roubam senhas e códigos.
- **PixRevolution** (Zimperium, mar/2026), feito para o Brasil:
  - se passa por Correios, Sicredi, Expedia e AVG em páginas falsas da Play Store;
  - pede **acessibilidade**, transmite a tela com **MediaProjection** e cobre tudo com "Aguarde…";
  - troca a chave Pix no momento da transferência.

  **Consequência para o CelScan:** além de acessibilidade e sobreposição, precisa ver quem usa
  **captura de tela** (appop `PROJECT_MEDIA`) e quem imita nome de marca conhecida.

## Tabela de funcionalidades

Legenda da coluna "CelScan tem?": ✅ tem · 🟡 parcial · ❌ não tem.

| Funcionalidade | Quem tem | Como fazem bem | CelScan tem? | Decisão |
|---|---|---|---|---|
| Detecção por indicadores de spyware/stalkerware | MVT, iMazing, antivírus | Bases públicas atualizadas | ✅ (MVT + Echap, 4.634 indicadores) | **Manter** |
| Assinatura do APK sem baixar o app inteiro | — (MVT baixa o APK) | — | ✅ | **Manter** (diferencial) |
| Heurística em linguagem leiga ("o que significa / o que fazer") | Antivírus (parcial) | Categorias de ameaça e explicação | ✅ (regras.yaml) | **Melhorar**: categorias (trojan bancário, stalkerware, adware) |
| Detecção de captura de tela (MediaProjection) | Antivírus (não confirmado) | — | ❌ | **Copiar** (Fase 3 item 1, prioridade máxima) |
| Certificado oficial de bancos (app falso com mesmo nome) | ESET "Proteção de pagamento" (parcial, dentro do celular) | Protege o app bancário | 🟡 (base criada, vazia) | **Melhorar**: lista brasileira conferida + typosquatting |
| Níveis de segurança no debloat | UAD-ng | 4 níveis com definição clara; desativar ≠ desinstalar | 🟡 (só "Recommended") | **Copiar** e traduzir; nunca mostrar "Unsafe" para leigo |
| Perfis de debloat / presets em lote | UAD-ng, ADB AppControl | Exportar/importar seleção | ❌ | **Copiar** (perfis por marca, aplicar em vários aparelhos) |
| Multiusuário / perfil de trabalho | UAD-ng | Seleciona o usuário | ❌ | **Copiar** (Fase 3 item 11) |
| Nome e ícone reais dos apps | ADB AppControl | Lista legível | ❌ | **Copiar** (item 8; essencial para leigo) |
| Instalar APK/APKS/XAPK, extrair APK, lote | ADB AppControl | Arrastar e soltar, presets | 🟡 (restaurar reinstala APK) | **Copiar** (item 14) |
| Gerenciar permissões | ADB AppControl | Conceder/revogar | ❌ | **Melhorar**: revogar em 1 clique **com desfazer** (item 6) |
| Espelhar a tela | scrcpy | Baixa latência, sem instalar app | ❌ | **Embutir o scrcpy** (item 15), não reinventar |
| Coleta forense completa / bugreport | AndroidQF + MVT | Portátil, criptografado | ❌ | **Integrar** AndroidQF + MVT no modo Profundo (item 5), com tradução do resultado |
| Análise de rede (DNS, VPN, proxy) | TinyCheck, PiRogue | Tráfego real num Raspberry Pi | 🟡 (proxy global) | **Melhorar** via ADB: VPN, VPN sempre ativa, DNS privado, proxy de APN (item 4). **Ignorar** captura de tráfego (exige hardware) |
| Relatório de peças/bateria (seminovo) | 3uTools (iOS) | Compara peças com as de fábrica | 🟡 (bateria) | **Copiar** para Android dentro do possível (item 16) |
| Backup antes de formatar | Dr.Fone, iMazing, DroidKit | Assistente, progresso, retomada | ❌ | **Copiar** o essencial (item 13); **ignorar** recuperação de dados apagados |
| Transferência entre aparelhos (WhatsApp etc.) | Dr.Fone, DroidKit, iMyFone | 1 clique | ❌ | **Ignorar** (fora do foco, arriscado, exige reengenharia) |
| "Reparo do sistema" / desbloqueio de tela | Dr.Fone, DroidKit | — | ❌ | **Ignorar** (fora do foco, risco jurídico) |
| Assistente de 1 clique | Dr.Fone, DroidKit | Fluxo guiado | 🟡 (CLI com perguntas) | **Copiar** (Fase 2) |
| Laudo profissional | 3uTools (relatório), iMazing (exporta) | — | 🟡 (HTML imprimível) | **Melhorar**: PDF nativo com QR de autenticidade (item 18) |
| Histórico / diferenças entre varreduras | — | — | 🟡 (banco guarda os retratos) | **Fazer** (item 7), diferencial |
| Modo balcão (vários aparelhos, cliente, OS) | — (3uTools parcial) | — | 🟡 (tabela de clientes com LGPD) | **Fazer** (item 17), diferencial |
| iPhone: spyware + bateria | iMazing, 3uTools, MVT | Backup local | 🟡 (MVT + bateria) | **Melhorar** (item 19) |
| Proteção em tempo real | Antivírus | Residente | ❌ | **Ignorar** no PC. Fica para o app Android futuro |
| Otimização honesta (antes/depois) | Ninguém mede de verdade | — | 🟡 (cache medido) | **Fazer** (item 12), diferencial |

## (a) O que nenhum concorrente faz e o CelScan fará

1. **Proteção Pix em uma varredura via USB**, em linguagem leiga. O CelScan vai cruzar:
   acessibilidade, sobreposição, captura de tela, certificado oficial dos bancos e imitação de nome.
   Hoje isso está espalhado entre antivírus residentes (que o usuário infectado muitas vezes
   não tem) e ferramentas forenses (técnicas demais).
2. **Varredura + debloat + otimização medida + laudo num só lugar**, para leigo e para balcão de assistência técnica.
3. **Laudo com antes/depois real** (espaço, tempo de abertura de apps) e QR code verificável.
4. **Histórico do aparelho**: o que mudou desde a última visita, como apps novos, permissões novas e certificado trocado.
5. **Tudo reversível**: quarentena com APK, registro de desfazer para toda configuração alterada.
6. **Modo balcão com LGPD de verdade**: consentimento, dado mínimo e exclusão do cliente.

## (b) Lacunas que continuarão depois da v3

- **Sem proteção em tempo real.** A ferramenta vê o aparelho só enquanto está no cabo; isso fica para o app Android.
- **Sem análise do tráfego de rede real.** Só a configuração (VPN, DNS, proxy) é lida; ver o tráfego exige algo como TinyCheck/PiRogue.
- **Sem root**, alguns dados ficam inacessíveis: dados privados dos apps e histórico de navegador, por exemplo.
- **Verificação de peças no Android** é muito limitada comparada ao 3uTools no iPhone.
- **iPhone continua dependendo do backup + MVT.** Remover spyware do iPhone continua sendo restaurar o aparelho.
- **Heurística tem falso positivo.** Gerenciadores de senha usam acessibilidade, por exemplo. O mitigador é a lista de permitidos, que precisa de manutenção.
- **A lista de certificados oficiais depende de conferência manual** em aparelhos reais.

## Como isso muda as prioridades

- **Sobe:** proteção Pix, agora incluindo **captura de tela** e **imitação de nome**; nome e ícone reais; gerenciador de permissões com desfazer.
- **Mantém:** histórico/diferenças, debloat no nível do UAD, laudo PDF.
- **Desce:** backup completo antes de formatar (concorrentes pagos fazem bem; aqui entra só o essencial) e atualização automática do programa, que depende da assinatura digital.
- **Fora do escopo:** transferência de WhatsApp, reparo de sistema, desbloqueio de tela, captura de tráfego.

## Fontes

- UAD-ng: [README](https://cdn.jsdelivr.net/gh/universal-debloater-alliance/universal-android-debloater-next-generation@main/README.md), [FAQ](https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation/wiki/FAQ), [Debloat Lists](https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation/wiki/Debloat-Lists)
- ADB AppControl: [site oficial](https://adbappcontrol.com/en/)
- scrcpy: [4.1 (UbuntuHandbook, jul/2026)](https://ubuntuhandbook.org/index.php/2026/07/android-screen-mirroring-app-scrcpy-4-1-added-vp8-vp9-encoders-support/), [Wikipedia](https://en.wikipedia.org/wiki/Scrcpy)
- AndroidQF/MVT: [androidqf](https://github.com/mvt-project/androidqf), [metodologia MVT](https://docs.mvt.re/en/latest/android/methodology/), [dicionário SocialTIC](https://forensics.socialtic.org/en/references/01-reference-androidqf-dictionary/)
- iMazing: [3.5.2 (abr/2026)](https://imazing.com/blog/imazing-3-5-2-release), [Spyware Analyzer](https://imazing.com/guides/detect-pegasus-and-other-spyware-on-iphone)
- 3uTools: [Apple Discussions](https://discussions.apple.com/thread/255413905), [SourceForge](https://sourceforge.net/app/3tools/mac/)
- Suítes pagas: [DroidKit](https://gizmodo.com/download/droidkit), [Dr.Fone](https://gizmodo.com/download/dr-fone)
- TinyCheck/PiRogue: [Kaspersky](https://www.kaspersky.com/blog/tinycheck-detects-spyware-stalkerware/38030/), [PortSwigger](https://portswigger.net/daily-swig/tinycheck-open-source-privacy-project-turns-your-raspberry-pi-into-a-stalkerware-detection-unit), [OTF PiRogue](https://www.opentech.fund/projects-we-support/supported-projects/pirogue-tool-suite/)
- Antivírus: [EFF + AV-Comparatives 2025](https://www.eff.org/deeplinks/2025/11/eff-teams-av-comparatives-test-android-stalkerware-detection-major-antivirus-apps), [Malwarebytes 100%](https://www.malwarebytes.com/blog/news/2025/11/malwarebytes-scores-100-in-av-comparatives-stalkerware-test-2025), [Testing Ground Labs jun/2026](https://www.testingground.io/report/android/tgl_android_malware_detection_202606_consumer_en.html), [ESET Mobile Security](https://eset.com/ch-en/home/mobile-security-android)
- PixRevolution: [Zimperium (mar/2026)](https://zimperium.com/blog/pixrevolution-the-agent-operated-android-trojan-hijacking-brazils-pix-payments-in-real-time), [TecMundo](https://www.tecmundo.com.br/seguranca/411537-malware-pixrevolution-sequestra-transferencias-pix-no-android.htm), [Dark Reading](https://www.darkreading.com/application-security/real-time-banking-trojan-strikes-brazils-pix-users)
