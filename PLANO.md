# CelScan v3 — Plano de implementação

> **Aguardando sua aprovação.** Nada da Fase 2 em diante começa antes disso.

## Onde estamos

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

## Decisões que preciso de você

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
