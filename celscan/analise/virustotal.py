"""Consulta ao VirusTotal (API v3) com cache local e respeito ao limite gratuito."""
import json
import sqlite3
import time

import requests

from celscan.config import DIR

URL = "https://www.virustotal.com/api/v3/files/{}"
VALIDADE = 7 * 86400


class VTErro(Exception):
    pass


class VirusTotal:
    def __init__(self, chave, intervalo=15.5):
        self.chave, self.intervalo, self._ultima = chave, intervalo, 0.0
        self.db = sqlite3.connect(DIR / "cache.db")
        self.db.execute("CREATE TABLE IF NOT EXISTS vt (sha TEXT PRIMARY KEY, ts REAL, dados TEXT)")

    def em_cache(self, sha):
        row = self.db.execute("SELECT ts, dados FROM vt WHERE sha=?", (sha,)).fetchone()
        if row and time.time() - row[0] < VALIDADE:
            return json.loads(row[1])
        return None

    def consultar(self, sha):
        cache = self.em_cache(sha)
        if cache is not None:
            return cache
        for _tentativa in range(3):
            espera = self.intervalo - (time.time() - self._ultima)
            if espera > 0:
                time.sleep(espera)
            self._ultima = time.time()
            r = requests.get(URL.format(sha), headers={"x-apikey": self.chave}, timeout=30)
            if r.status_code == 429:
                time.sleep(60)
                continue
            if r.status_code == 401:
                raise VTErro("chave do VirusTotal inválida")
            if r.status_code == 404:
                res = {"conhecido": False}
                break
            r.raise_for_status()
            a = r.json()["data"]["attributes"]
            st = a.get("last_analysis_stats", {})
            res = {
                "conhecido": True,
                "malicioso": st.get("malicious", 0),
                "suspeito": st.get("suspicious", 0),
                "rotulo": a.get("popular_threat_classification", {}).get("suggested_threat_label"),
            }
            break
        else:
            raise VTErro("limite de consultas do VirusTotal atingido")
        self.db.execute("INSERT OR REPLACE INTO vt VALUES (?,?,?)", (sha, time.time(), json.dumps(res)))
        self.db.commit()
        return res
