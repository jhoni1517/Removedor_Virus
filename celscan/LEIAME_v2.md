# CelScan 2.0

Segurança e otimização de celulares via USB, com laudo em HTML/PDF.

## Instalação
```bash
pip install -r requirements.txt
```
O **adb** é baixado automaticamente na primeira execução se não estiver instalado.
Opcional: chave gratuita do VirusTotal em `VT_API_KEY` (`set VT_API_KEY=...` no Windows).

## Comandos
```bash
python celscan.py android                    # varredura + laudo (abre no navegador)
python celscan.py android --loja "Minha Loja" # laudo com o nome da loja
python celscan.py android --sistema          # inclui apps pré-instalados
python celscan.py android --remover          # vai direto para a remoção
python celscan.py otimizar                   # diagnóstico + cache, compilação, animações, bloatware
python celscan.py otimizar --tudo            # sem perguntas (exceto bloatware)
python celscan.py quarentena listar          # tudo o que foi removido/desativado
python celscan.py quarentena restaurar ID    # desfaz
python celscan.py parear 192.168.0.10:37123 123456   # Wi-Fi (Android 11+)
python celscan.py conectar 192.168.0.10:41234
python celscan.py ios                        # backup + MVT
python celscan.py ios --listar-backups       # usa backups do iTunes/Apple Devices
python celscan.py iocs                       # força atualização dos indicadores
```
Para PDF: abra o laudo no navegador e use Imprimir → Salvar como PDF.

## Como detecta
- **Indicadores públicos** (atualizados a cada 24 h): stalkerware da Echap e spyware do MVT/Amnesty
  (nome de pacote, certificado de assinatura e hash do APK). Correspondência = risco 100.
- **Assinatura**: lê o certificado direto do aparelho (sem baixar o APK) e marca assinatura de teste.
- **Heurística**: acessibilidade, administrador, device owner, leitor de notificações, sem ícone,
  fora da loja, SMS/áudio/localização, sobreposição, instalação de apps, bateria liberada, instalação recente.
- **Aparelho**: patch antigo, proxy global, root, bootloader desbloqueado, SMS padrão incomum.
- **VirusTotal** (com cache de 7 dias) para os apps suspeitos.
- `permitidos.txt`: apps legítimos que usam acessibilidade etc. (só valem se vierem de loja oficial).
  Adicione os seus em `~/.celscan/permitidos.txt`.

## Segurança das ações
- Toda remoção guarda o APK em `~/.celscan/quarentena` (extensão `.quarentena`; o antivírus do PC
  pode apagá-lo — isso não afeta o celular).
- Bloatware é **desativado**, não apagado. Tudo é reversível com `quarentena restaurar`.

## Testar sem celular
```bash
set CELSCAN_ADB=testes\fake_adb.py      # Linux/Mac: export CELSCAN_ADB=testes/fake_adb.py
set APK_TESTE=caminho\de\qualquer.apk
python celscan.py android --nao-abrir
```

## Limitações
- Heurística pode gerar falso positivo; nenhuma ferramenta garante 100%.
- iPhone: detecta indicadores conhecidos; a remoção é manual (restauração de fábrica).
