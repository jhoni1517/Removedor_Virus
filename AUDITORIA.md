# AUDITORIA — CelScan antes do salto para o Studio (v4)

Data: 30/09/2026 · Branch `ccr-b3fdeeb6-jqhbn5` · Versão `3.0.0b4`.

> **Aviso honesto sobre ambiente.** Esta auditoria foi feita num servidor na nuvem, **sem celular
> conectado** (`adb` não está nem instalado aqui; `adb devices` não lista nada). Portanto a
> execução em aparelho real (seção 0 do pedido) **não pôde ser feita por mim** — ela depende de
> você rodar na sua máquina com o Redmi/Samsung/Motorola no cabo. O que eu validei aqui: leitura
> de todo o código, a suíte de testes automatizados e o ADB simulado. Onde digo "funciona", quero
> dizer "passa nos testes com ADB simulado"; onde depende do aparelho, está marcado 🔬 **a
> confirmar no real**.

## 1. O que o repositório é hoje

Já **não é** a v2 (CLI simples): o `PROMPT_CELSCAN_V3.md` foi executado. O estado atual é uma **v3
madura, quase completa da Etapa A + parte da B**, com correções do primeiro teste em aparelho real
(beta b3/b4).

- **Python** ~5.6 mil linhas (`celscan/`), **interface** ~2,1 mil linhas (React/TS em `celscan/web/`).
- **82–83 testes** pytest passando (4 skips), **ruff** limpo, **build** da interface OK.
- Arquitetura: `core` (adb, coleta, parsers, db, bases) → `analise` (pontuacao, iocs, pix,
  certificados, apksig, rotulos, virustotal) → `acoes` (quarentena, remocao, otimizacao, backup,
  permissoes, espelho, navegacao, recuperacao) → `api` (FastAPI + WebSocket) e `cli` (rich).
- Empacotamento: PyInstaller (`CelScan.spec`) + Inno Setup + GitHub Actions (Windows).

## 2. O que funciona

| Área | Situação | Como validei |
|---|---|---|
| Varredura (coleta + pontuação + regras YAML) | ✅ | `test_coleta_pontuacao`, ADB simulado |
| IOCs stalkerware (MVT + Echap: pacotes, certs, hashes) | ✅ | `test_*`; **mas veja dívida 4** |
| Assinatura v2/v3 do APK sem baixar o app (dd por faixa) | ✅ diferencial real | `test_apksig` |
| Nome e ícone reais dos apps (lê o APK remoto, cache por sha256) | ✅ (resolve a dor da v2) | `test_rotulos` |
| Proteção Pix (acessibilidade + overlay + PROJECT_MEDIA + banco) | ✅ | `test_pix` |
| Quarentena e desfazer (settings/appops/permissão) | ✅ | `test_quarentena` |
| Laudo PDF cliente/técnico com QR + código de verificação | ✅ | `test_pdf` |
| Backend FastAPI + WebSocket + tarefas canceláveis | ✅ | `test_api`, `test_resgate` |
| Interface React (Conectar, Varredura, Resultado, Histórico, Config) | ✅ compila | build Vite, sem erro TS |
| Diagnóstico (bateria, saúde, IMEI, RAM, espaço) — b4 | ✅ | `test_*` + parsers |
| Limpeza segura (cache + lixo rebuildável) — b4 | ✅ | `test_api_limpeza` |
| Recuperação de sobras (lixeira, miniaturas, status) — b4 | ✅ | `test_api_recuperacao` |
| Espelho scrcpy (ver/controlar/OTG/compatível) + atalhos de ajuste — b4 | ✅ monta comando | `test_resgate` |
| iPhone: ver info + backup/MVT — b4 | ✅ código; 🔬 precisa libimobiledevice | leitura |
| Wi-Fi (QR de pareamento Android 11+) | ✅ código | `test_api` |

## 3. O que ainda NÃO foi validado (depende de você, no aparelho real) 🔬

- Conexão real por USB e por Wi-Fi (o b3 travava em "Reconectando…"; corrigido no b4, **não
  reconfirmado**).
- Janela no Windows (pywebview/WebView2), instalador (instalar sobre o antigo, atualizar,
  desinstalar), driver USB do fabricante.
- Diagnóstico de **saúde da bateria e IMEI** varia muito por fabricante (caminhos em `/sys` e
  `service call` podem falhar) — precisa de amostras Samsung/Motorola/Xiaomi.
- Limpeza, recuperação e espelho **nunca rodaram em aparelho de verdade**.
- iPhone: precisa de Windows/Mac com libimobiledevice instalado.

## 4. Dívidas técnicas (confirmadas no código)

| # | Dívida | Onde | Impacto | Correção proposta (v4) |
|---|---|---|---|---|
| 1 | **Um processo `adb` por comando** (sem conexão persistente, sem paralelismo real) | `core/adb.py` (subprocess) | lento com muitos apps; trava com vários aparelhos | migrar para **adbutils** (fala com o servidor adb) + asyncio por aparelho |
| 2 | **Assinatura/VirusTotal só para candidatos** | `analise/pontuacao.py` | app malicioso fora do filtro passa | cache de cert/hash por sha256 cobrindo todos, em 2º plano |
| 3 | **Nome/ícone**: já resolvido lendo o APK, mas é I/O pesado | `analise/rotulos.py` | lento sem cache quente | o **Agente Android** (v4) resolve em lote; manter fallback Play Store |
| 4 | **6,6 mil domínios dos IOCs do MVT não são usados** | `analise/iocs.py` (regex só pega `app:id`, `app:cert`, `file:hashes`) | perde sinal de rede | parsear `domain-name:value`/`url:value` e cruzar com DNS/rede (Agente) |
| 5 | **Quarentena guarda o APK solto** | `acoes/quarentena.py` (`pull` para pasta) | o antivírus do Windows apaga | **zip com senha `infected`** + manifesto (padrão da área) |
| 6 | **Driver USB do fabricante não é tratado** | — | principal causa de "aparelho não aparece" no Windows | detectar e oferecer instalação (Google USB Driver / OEM) |
| 7 | **Download sem conferência de hash** | `instalador/baixar_dependencias.py` (`urlopen`, sem checksum) | risco de supply-chain | verificar SHA-256 de todo download (platform-tools, scrcpy) |
| 8 | **QR do laudo sem endereço que verifique** | laudo + `db.verificar_laudo` (só local) | QR não abre nada | **CelScan Nuvem** com hash assinado (seção 3 do pedido) |
| 9 | **Sem proteção à vítima de stalkerware** | remoção direta | remover pode alertar o agressor | **modo vítima** (documentar antes de remover, contatos de apoio) |
| 10 | Segredos (chave VirusTotal, IA) — conferir se vão para o **keyring** | `core/preferencias.py` | segredo em texto puro | mover para o cofre do sistema (keyring) |
| 11 | Regras/IOCs embutidos, não versionados como pacote atualizável | `dados/*.yaml` | atualizar exige nova versão do programa | **pacotes de regras versionados** com changelog |

## 5. Status do plano v3 (o que já foi feito × o que falta)

**Etapa A (interface + empacotamento): concluída** (b1). **Extra tela quebrada** (b2) e
**correções do real + diagnóstico/limpeza/recuperação/iPhone** (b3/b4): feitos.

**Etapa B (segurança, 20 funções do plano) — parcial:**

- ✅ Proteção Pix/bancos (base), nomes e ícones, permissões com desfazer, limpeza de
  armazenamento, otimização medida (cache), espelhamento, backup essencial, laudo PDF, iPhone
  (ver + MVT), diagnóstico de bateria/saúde.
- 🟡 Certificados oficiais de bancos (mecanismo pronto, **lista vazia** — precisa conferir no real);
  histórico (banco guarda retratos, **falta a tela de diferenças**); debloat (só "Recommended",
  falta os níveis do UAD).
- ❌ Painel de sensores; consumo em 2º plano (wakelocks/batterystats); análise de rede (VPN/DNS);
  modo profundo (AndroidQF+MVT); apps esquecidos; apps em lote; checklist de hardware/seminovo;
  modo balcão (OS/kanban); atualização automática; transferência entre aparelhos.

## 6. Conclusão da auditoria

A base v3 é **sólida, testada e honesta** — reaproveitável quase inteira. O salto para o **Studio
(v4)** é principalmente de **arquitetura** (motor com plugins + adbutils/asyncio; front Tauri;
Agente Android; Nuvem) e de **cobertura de funções** (as ❌ acima). Não recomendo jogar fora o que
existe: o `core/analise/acoes` viram os **plugins do motor**; a interface React migra de pywebview
para **Tauri** reaproveitando as telas.

As dívidas 1, 5, 6, 7 e 9 são as de maior risco imediato (desempenho, antivírus apagando
quarentena, "não conecta" no Windows, supply-chain e segurança da vítima) — proponho atacá-las
já na Fase 1 do PLANO. Detalhes e ordem no `PLANO.md`.
