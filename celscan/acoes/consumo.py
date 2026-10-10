"""Consumo de internet por app desde a última recarga completa da bateria (estatísticas do Android).

Lê `dumpsys batterystats --checkin` (formato estável desde o Android 5): linhas "uid" ligam o número
do app ao pacote e linhas "nt" trazem os bytes de dados móveis e Wi-Fi. Só leitura.
"""

from __future__ import annotations

from typing import Any

from celscan.core.adb import Aparelho

CMD = "dumpsys batterystats --checkin 2>/dev/null | grep -E '^9,[0-9]+,(i,uid|l,nt),'"


def parse(txt: str) -> dict[str, dict[str, float]]:
    """{pacote: {'movel_mb', 'wifi_mb'}} somando todos os pacotes que dividem o mesmo uid."""
    pacotes: dict[str, list[str]] = {}
    rede: dict[str, tuple[int, int, int, int]] = {}
    for linha in txt.splitlines():
        p = linha.strip().split(",")
        if len(p) >= 6 and p[2] == "i" and p[3] == "uid":
            pacotes.setdefault(p[4], []).append(p[5])
        elif len(p) >= 8 and p[2] == "l" and p[3] == "nt":
            try:
                rx_m, tx_m, rx_w, tx_w = (int(x) for x in p[4:8])
            except ValueError:
                continue
            a = rede.get(p[1], (0, 0, 0, 0))
            rede[p[1]] = (a[0] + rx_m, a[1] + tx_m, a[2] + rx_w, a[3] + tx_w)
    res: dict[str, dict[str, float]] = {}
    for uid, (rx_m, tx_m, rx_w, tx_w) in rede.items():
        for pkg in pacotes.get(uid, []):
            res[pkg] = {"movel_mb": round((rx_m + tx_m) / 1048576, 1), "wifi_mb": round((rx_w + tx_w) / 1048576, 1),
                        "enviado_mb": round((tx_m + tx_w) / 1048576, 1)}
    return res


def ler(ap: Aparelho) -> dict[str, Any]:
    dados = parse(ap.sh(CMD, timeout=120) or "")
    ranking = sorted(({"pacote": k, **v, "total_mb": round(v["movel_mb"] + v["wifi_mb"], 1)} for k, v in dados.items()),
                     key=lambda x: -x["total_mb"])
    return {"disponivel": bool(dados), "apps": [r for r in ranking if r["total_mb"] > 0][:40],
            "observacao": "Desde a última carga completa. Alguns fabricantes zeram as estatísticas ao reiniciar."}
