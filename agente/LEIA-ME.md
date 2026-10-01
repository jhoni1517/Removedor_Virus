# CelScan Agente

App auxiliar Android **temporário**: o CelScan instala pelo adb, lê e remove no fim.

- Só leitura: nome, ícone, datas de instalação e tempo de uso dos apps. Nenhum conteúdo pessoal.
- Sem ícone na tela, sem acesso à internet.
- Só o shell do adb consegue consultar (permissão `DUMP` + conferência do UID em `Dados.java`).
- Estatísticas de uso liberadas pelo próprio CelScan (`appops set ... GET_USAGE_STATS allow`).

Compilar (sem Gradle): `ANDROID_HOME=/caminho/do/sdk bash agente/construir.sh` → `agente/build/celscan-agente.apk`.
No CI, o job `agente` compila no Linux e o instalador Windows embute o APK em `celscan/dados/agente/`.
