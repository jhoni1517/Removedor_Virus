"""Configurações, pastas e listas fixas do CelScan."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from celscan import __version__

VERSAO = __version__
PACOTE = Path(__file__).resolve().parent
DADOS = PACOTE / "dados"
DIR = Path(os.getenv("CELSCAN_HOME") or Path.home() / ".celscan")
DIR.mkdir(parents=True, exist_ok=True)
# Modo offline: nunca acessa a internet; usa só as cópias locais das bases (--offline liga em tempo de execução).
OFFLINE = os.getenv("CELSCAN_OFFLINE", "").lower() in ("1", "sim", "true")


def recursos() -> Path:
    """Pasta dos arquivos que vão junto com o programa (ex.: adb embutido no .exe)."""
    return Path(getattr(sys, "_MEIPASS", PACOTE.parent))


LOJAS = {
    "com.android.vending": "Google Play",
    "com.google.android.feedback": "Google Play",  # instalações antigas da Play
    "com.sec.android.app.samsungapps": "Galaxy Store",
    "com.huawei.appmarket": "AppGallery",
    "com.xiaomi.market": "GetApps",
    "com.xiaomi.mipicks": "GetApps",
    "com.xiaomi.discover": "GetApps (recomendados MIUI)",
    "com.heytap.market": "App Market (OPPO/Realme)",
    "com.oppo.market": "App Market (OPPO)",
    "com.vivo.appstore": "V-Appstore",
    "com.hihonor.appmarket": "Honor AppMarket",
    "com.amazon.venezia": "Amazon Appstore",
}

# Lojas alternativas confiáveis (verificam ou compilam os apps): contam como origem conhecida, com peso menor
LOJAS_ALTERNATIVAS = {
    "org.fdroid.fdroid": "F-Droid", "org.fdroid.basic": "F-Droid", "com.aurora.store": "Aurora Store (Play)",
    "com.looker.droidify": "Droid-ify (F-Droid)", "dev.imranr.obtainium": "Obtainium",
}

# Apps de transferência entre celulares: copiam os apps do aparelho antigo. Não é "loja", mas também não é
# "arquivo baixado da internet"; antes todo app passado por Smart Switch aparecia como "fora da loja".
TRANSFERENCIA = {
    "com.sec.android.easyMover": "Smart Switch (Samsung)", "com.google.android.apps.restore": "restauração do Google",
    "com.miui.backup": "Backup Xiaomi", "com.xiaomi.mi_connect_service": "Mi Mover",
    "com.motorola.migrate": "Migração Motorola", "com.coloros.backuprestore": "Clone Phone (OPPO/Realme)",
    "com.hihonor.phoneclone": "Phone Clone (Honor)", "com.huawei.KoBackup": "Phone Clone (Huawei)",
    "com.vivo.easyshare": "EasyShare (vivo)",
}

# Pacotes do próprio CelScan: nunca entram na análise como suspeitos
PROPRIOS = {"com.celscan.agente": "CelScan Agente (ferramenta desta análise)"}

SMS_CONHECIDOS = {
    "com.google.android.apps.messaging", "com.samsung.android.messaging",
    "com.android.mms", "com.android.messaging", "com.motorola.messaging",
    "com.oneplus.mms", "com.coloros.mms", "com.miui.mms", "com.huawei.message",
    "org.thoughtcrime.securesms", "com.textra", "com.microsoft.android.smsorganizer",
}

PASTAS_SISTEMA = ("/system/", "/product/", "/vendor/", "/system_ext/", "/apex/", "/odm/")


def permitidos() -> set[str]:
    """Apps confiáveis: dados/permitidos.txt do programa + ~/.celscan/permitidos.txt do usuário."""
    pacotes: set[str] = set()
    for arq in (DADOS / "permitidos.txt", DIR / "permitidos.txt"):
        if arq.exists():
            for linha in arq.read_text(encoding="utf-8").splitlines():
                linha = linha.split("#")[0].strip()
                if linha:
                    pacotes.add(linha)
    return pacotes
