# Removedor de Vírus Android

Programa para Windows que detecta e remove vírus e **adware** (apps que enchem o celular de anúncios) de celulares Android conectados por cabo USB. Não precisa de root.

## Download e instalação

1. Abra a página **[Releases](https://github.com/jhoni1517/Removedor_Virus/releases)** e baixe `RemovedorVirus-Setup-X.Y.Z.exe`.
2. Execute o instalador. Ele não pede senha de administrador e cria atalhos no menu Iniciar e, se quiser, na área de trabalho.
3. Abra o **Removedor de Vírus Android**.

Não precisa instalar Python nem ADB: tudo já vem no instalador. Também existe a versão portátil (`RemovedorVirus-Portatil-X.Y.Z.zip`), que não precisa instalar.

> O Windows SmartScreen pode avisar "editor desconhecido", porque o programa ainda não tem assinatura digital. Clique em **Mais informações > Executar assim mesmo**.

## Como usar

1. No celular, ative a **Depuração USB**:
   - Configurações > Sobre o telefone > toque 7× em **Número da versão**;
   - Configurações > Sistema > **Opções do desenvolvedor** > **Depuração USB**.
2. Conecte o cabo USB e toque em **Permitir** no aviso do celular.
3. No programa: **Conectar** > **Escanear**.
4. Clique em um app para ver por que ele é suspeito. Depois use **Remover selecionados** ou **Limpeza rápida**, que remove todos os apps de risco alto.

> Samsung: se o celular não aparecer, instale o [driver USB da Samsung](https://developer.samsung.com/android-usb-driver).

## O que ele detecta

Cada app instalado pelo usuário recebe uma pontuação (Alto ≥ 60, Médio ≥ 30):

| Sinal | Pontos |
|---|---|
| Malware conhecido (lista de assinaturas) | 100 |
| VirusTotal: 3 ou mais antivírus detectam / 1 ou 2 detectam | 100 / 30 |
| Administrador do dispositivo (bloqueia a desinstalação) | 40 |
| Serviço de acessibilidade ativo | 30 |
| Sem ícone na tela inicial (app escondido) | 30 |
| Pode exibir janelas sobre outros apps (anúncios) | 25 |
| Lê todas as notificações | 20 |
| Instalado fora da loja oficial | 15 |
| SMS, chamadas, áudio, localização em segundo plano (concedidos) | 3–15 |
| Nome típico de adware, permissões de instalar apps / iniciar sozinho | 3–10 |

Apps do sistema nunca são tocados. Apps conhecidos (WhatsApp, Google…) instalados pela loja oficial são ignorados, a não ser que o VirusTotal os acuse.

### VirusTotal (opcional)

Em **Opções > Chave do VirusTotal**, cole uma chave gratuita de [virustotal.com](https://www.virustotal.com/gui/join-us). Assim o programa confere os apps suspeitos em mais de 70 antivírus. O plano gratuito permite 4 consultas por minuto.

## Como a remoção funciona

1. Faz uma cópia do app na **quarentena**, para poder restaurar depois.
2. Para o app e tira os "poderes" dele: sobreposição, acessibilidade e administrador.
3. Desinstala. Se não conseguir, remove só do usuário; em último caso, desativa o app.

Além disso:
- **Restaurar...** reinstala um app da quarentena.
- **Bloquear anúncios (DNS)** ativa o DNS Privado AdGuard, que bloqueia anúncios no celular todo (Android 9+).

Os relatórios e a quarentena ficam em `%LOCALAPPDATA%\RemovedorVirus`, acessível pelo menu **Arquivo**.

> Anúncios que chegam como notificação do Chrome vêm de sites, não de vírus. Desative em Chrome > Configurações > Configurações do site > Notificações.

## Para desenvolvedores

```
python -m removedor_virus                 # abre a janela
python -m removedor_virus menu            # menu no terminal
python -m removedor_virus escanear | limpar | remover PACOTE | restaurar | dns ativar | virustotal CHAVE
python -m unittest discover -s tests      # testes
```

### Gerar o instalador

Cada push gera o instalador pelo GitHub Actions (`.github/workflows/windows.yml`); ele aparece em **Actions > artefatos**. Para publicar na página de Releases, use um destes caminhos:
- no GitHub: **Actions > Instalador Windows > Run workflow** (cria a tag `v<versão>` automaticamente);
- ou envie uma tag: `git tag v0.2.0 && git push origin v0.2.0`.

Antes de publicar uma versão nova, atualize `__version__` em `removedor_virus/__init__.py`.

Para gerar manualmente no Windows (Python 3.9+, PyInstaller e [Inno Setup 6](https://jrsoftware.org/isdl.php)):

```
pip install pyinstaller
python -m removedor_virus baixar-adb --destino .
pyinstaller --noconfirm instalador\RemovedorVirus.spec
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.2.0 instalador\RemovedorVirus.iss
```

O instalador fica em `dist\`.

## Roadmap

- [x] v0.1: versão para PC via USB (linha de comando)
- [x] v0.2: programa Windows com janela e instalador, VirusTotal
- [ ] Atualização automática da lista de assinaturas
- [ ] Verificação de apps pré-instalados (adware de fábrica)
- [ ] Assinatura digital do instalador
- [ ] iPhone (análise de spyware via backup + MVT)
- [ ] App Android instalável (sem PC)
