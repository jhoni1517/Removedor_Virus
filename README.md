# Removedor de Vírus Android (USB)

Programa para Windows que detecta e remove vírus e **adware** (apps que enchem o celular de anúncios) de celulares Android conectados por cabo USB. Não precisa de root.

## O que ele faz

- **Escaneia** todos os apps instalados pelo usuário e dá uma nota de risco para cada um (ALTO / MÉDIO / BAIXO / LIMPO), explicando o motivo:
  - app escondido (sem ícone na tela inicial);
  - permissão para exibir janelas sobre outros apps (anúncios em tela cheia);
  - administrador do dispositivo (impede a desinstalação);
  - serviço de acessibilidade ativo (controla a tela);
  - instalado fora da loja oficial (APK baixado da internet);
  - nome típico de adware ("cleaner", "booster", "lanterna"…), permissões perigosas e instalação recente;
  - lista de malware conhecido (`removedor_virus/dados/assinaturas.json`).
- **Remove** com segurança:
  1. faz backup do APK na pasta `quarentena/`;
  2. para o app e tira os "poderes" dele (sobreposição, acessibilidade e administrador);
  3. desinstala. Se não conseguir, remove só do usuário; em último caso, desativa o app.
- **Restaura** da quarentena, caso algo tenha sido removido por engano.
- **DNS bloqueador de anúncios** (AdGuard DNS), que bloqueia anúncios no celular todo (Android 9+).
- Salva um **relatório JSON** em `relatorios/`.

Apps do sistema nunca são tocados.

## Como usar

1. Instale o [Python 3.9+](https://www.python.org/downloads/) e marque **"Add to PATH"**.
2. No celular, ative a **Depuração USB**:
   - Configurações > Sobre o telefone > toque 7× em **Número da versão**;
   - Configurações > Sistema > **Opções do desenvolvedor** > **Depuração USB**.
3. Conecte o cabo USB e toque em **Permitir** no aviso do celular.
4. Dê dois cliques em **`iniciar.bat`**. Se o ADB não estiver instalado, o programa oferece baixar a versão oficial do Google.

> Samsung: se o celular não aparecer, instale o [driver USB da Samsung](https://developer.samsung.com/android-usb-driver).

### Linha de comando

```
python -m removedor_virus                      # menu interativo
python -m removedor_virus escanear [--todos]
python -m removedor_virus limpar [--nivel medio] [--sim] [--sem-backup]
python -m removedor_virus remover com.app.suspeito [--sim]
python -m removedor_virus restaurar
python -m removedor_virus dns ativar|desativar
python -m removedor_virus baixar-adb
```

## Dicas contra anúncios

- Anúncios que chegam como **notificação do navegador** não vêm de vírus. Desative em Chrome > Configurações > Configurações do site > Notificações.
- Depois de limpar, rode `dns ativar` para bloquear anúncios em todos os apps.

## Testes

```
python -m unittest discover -s tests
```

## Roadmap

- [x] v0.1: versão para PC via USB (ADB)
- [ ] Atualização automática da lista de assinaturas
- [ ] Verificação de apps pré-instalados (bloatware/adware de fábrica)
- [ ] Interface gráfica para Windows
- [ ] App Android instalável (sem PC)
