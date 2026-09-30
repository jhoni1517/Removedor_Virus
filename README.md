# CelScan

Segurança, diagnóstico e otimização de celulares Android pelo cabo USB, no Windows.
O CelScan substitui o antigo "Removedor de Vírus Android".

> **Versão 3.0 beta 1.** A interface nova ainda não foi testada num celular real. Se algo der
> errado, mande o arquivo `celscan.log` da pasta `%USERPROFILE%\.celscan\logs`.

## Download e instalação

1. Abra a página **[Releases](https://github.com/jhoni1517/Removedor_Virus/releases)** e baixe `CelScan-Setup-X.Y.Z.exe`.
2. Execute o instalador:
   - não pede senha de administrador;
   - remove o "Removedor de Vírus Android" antigo, se ele estiver instalado.
3. Abra o **CelScan** pelo menu Iniciar.

Não precisa instalar Python, ADB nem nada mais: vem tudo junto. Também existe a versão portátil
(`CelScan-Portatil-X.Y.Z.zip`), que não precisa instalar.

> O Windows pode avisar "editor desconhecido", porque o programa ainda não tem assinatura digital.
> Clique em **Mais informações > Executar assim mesmo**.

## Como usar

1. **Conectar.** Ligue o celular no cabo e ele aparece sozinho. A tela mostra o passo a passo
   para ligar a Depuração USB na sua marca (Samsung, Motorola, Xiaomi, OPPO/Realme, vivo...).
   Também dá para conectar pelo Wi-Fi lendo um código QR (Android 11 ou mais novo).
2. **Escolher o tipo:**
   - **Rápido** (1–2 min): apps, permissões, assinaturas e ameaças conhecidas;
   - **Completo**: tudo do rápido e mais a opinião de mais de 70 antivírus (VirusTotal).
     Precisa de uma chave gratuita, que você cadastra em Configurações.
3. **Resultado.** O programa mostra uma nota de 0 a 100. Cada problema vem com
   **"o que isso significa"** e **"o que fazer"**. Dá para filtrar por nível e remover apps
   um a um ou em lote.
4. **Desfazer.** Toda remoção guarda uma cópia do app na quarentena e registra as configurações
   alteradas. O botão "Desfazer" aparece por 10 segundos e continua disponível no **Histórico**.
5. **Laudo.** Gere o laudo em PDF: versão para o cliente ou versão técnica. Cada laudo tem um
   **código de verificação** e um QR code, que você confere em Histórico > Verificar laudo.

## O que o CelScan verifica

- **Ameaças conhecidas:** listas públicas de spyware e stalkerware da Amnesty/MVT e da Echap.
  Compara nome do pacote, certificado e impressão digital do arquivo.
- **Sinais de golpe:**
  - serviço de acessibilidade ativo (usado por trojans bancários que roubam Pix);
  - app administrador do aparelho;
  - leitor de notificações;
  - app sem ícone;
  - app instalado fora da loja;
  - telas por cima de outros apps;
  - SMS, áudio e localização em segundo plano;
  - certificado de teste.
- **Aparelho:** atualização de segurança antiga, proxy, root e bootloader desbloqueado.
- **VirusTotal**, no modo Completo.

As regras e os textos ficam em `celscan/dados/regras.yaml` e podem ser ajustados sem mexer no código.

## Linha de comando

A instalação inclui o `celscan-cli.exe`. Quem usa Python pode rodar `python celscan.py`:

```
celscan-cli android [--modo rapido|completo] [--remover]   varredura + laudo
celscan-cli otimizar                                       cache, compilação, animações, bloatware
celscan-cli historico | quarentena listar | quarentena restaurar ID
celscan-cli laudo ID [--versao tecnico] | verificar CÓDIGO
celscan-cli bases [--atualizar]   (e --offline em qualquer comando)
celscan-cli fixtures              grava as saídas do celular para os testes
celscan-cli interface [--navegador]
```

## Para desenvolvedores

```
pip install -r requirements-dev.txt
cd celscan/web && npm ci && npm run build && cd ../..
python celscan.py interface --navegador      # interface
python -m pytest && ruff check celscan testes celscan.py
```

- **Sem celular:** `CELSCAN_ADB=testes/fake_adb.py`, com as fixtures em `testes/fixtures/`.
- **Teste da interface no navegador:** `testes/e2e_interface.py`, que usa o Playwright.
- **Instalador:** o GitHub Actions gera a cada push (Actions > artefatos). Para publicar em
  Releases, use **Actions > Instalador Windows > Run workflow**, que cria a tag `v<versão>`
  de `celscan/__init__.py`.
- **Estrutura:**
  - `celscan/core` (adb, coleta, parsers, banco);
  - `celscan/analise` (regras, ameaças, VirusTotal);
  - `celscan/acoes` (remoção, quarentena, otimização);
  - `celscan/api` (backend da interface);
  - `celscan/web` (React);
  - `celscan/relatorio` (laudos).
- **Planejamento:** [`PLANO.md`](PLANO.md) (etapas e decisões) e
  [`COMPARATIVO.md`](COMPARATIVO.md) (concorrentes).
