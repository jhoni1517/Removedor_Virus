#!/usr/bin/env bash
# Compila o CelScan Agente só com as ferramentas do Android SDK (sem Gradle):
#   javac -> d8 -> aapt2 -> zipalign -> apksigner
# Uso: ANDROID_HOME=/caminho/do/sdk agente/construir.sh   (gera agente/build/celscan-agente.apk)
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_HOME:?defina ANDROID_HOME}"
# Usa as versões pedidas ou as mais novas instaladas (o CI do GitHub já traz várias).
BT="$SDK/build-tools/${BUILD_TOOLS:-$(ls "$SDK/build-tools" | sort -V | tail -1)}"
PLAT="${PLATAFORMA:-$(ls "$SDK/platforms" | sed 's/android-//' | grep -E '^[0-9]+$' | sort -n | tail -1)}"
JAR="$SDK/platforms/android-$PLAT/android.jar"
echo "build-tools: $BT | plataforma: android-$PLAT"
OUT="$AQUI/build"

rm -rf "$OUT"
mkdir -p "$OUT/classes" "$OUT/dex"

javac -source 8 -target 8 -bootclasspath "$JAR" -classpath "$JAR" -Xlint:-options \
      -d "$OUT/classes" $(find "$AQUI/src" -name '*.java')
"$BT/d8" --min-api 21 --lib "$JAR" --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')
"$BT/aapt2" link -o "$OUT/sem_dex.apk" --manifest "$AQUI/AndroidManifest.xml" -I "$JAR"
cp "$OUT/sem_dex.apk" "$OUT/com_dex.apk"
python3 - "$OUT/com_dex.apk" "$OUT/dex/classes.dex" <<'PY' || python - "$OUT/com_dex.apk" "$OUT/dex/classes.dex" <<'PY2'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "a", zipfile.ZIP_DEFLATED) as z:
    z.write(sys.argv[2], "classes.dex")
PY
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "a", zipfile.ZIP_DEFLATED) as z:
    z.write(sys.argv[2], "classes.dex")
PY2
"$BT/zipalign" -f -p 4 "$OUT/com_dex.apk" "$OUT/alinhado.apk"

# Chave descartável: o Agente é instalado e removido a cada uso, não precisa de chave fixa.
CHAVE="$OUT/chave.jks"
keytool -genkeypair -keystore "$CHAVE" -storepass celscan -keypass celscan -alias agente \
        -keyalg RSA -keysize 2048 -validity 3650 -dname "CN=CelScan Agente" >/dev/null 2>&1
"$BT/apksigner" sign --ks "$CHAVE" --ks-pass pass:celscan --key-pass pass:celscan \
        --out "$OUT/celscan-agente.apk" "$OUT/alinhado.apk"
"$BT/apksigner" verify "$OUT/celscan-agente.apk"
rm -f "$OUT/sem_dex.apk" "$OUT/com_dex.apk" "$OUT/alinhado.apk" "$CHAVE"
echo "OK: $OUT/celscan-agente.apk ($(du -h "$OUT/celscan-agente.apk" | cut -f1))"
