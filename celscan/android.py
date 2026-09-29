"""Varredura de Android via ADB — coleta em lote, IOCs, assinatura e pontuação."""
import re
import shlex
from datetime import datetime

import apksig
import quarentena
from adb import AdbErro
from config import LOJAS, PASTAS_SISTEMA, SMS_CONHECIDOS, permitidos

PERMISSOES = {
    "android.permission.READ_SMS": (20, "lê SMS"),
    "android.permission.RECEIVE_SMS": (15, "intercepta SMS"),
    "android.permission.SEND_SMS": (15, "envia SMS"),
    "android.permission.READ_CALL_LOG": (10, "lê registro de chamadas"),
    "android.permission.RECORD_AUDIO": (10, "grava áudio"),
    "android.permission.ACCESS_BACKGROUND_LOCATION": (10, "localização em 2º plano"),
    "android.permission.CAMERA": (5, "usa câmera"),
    "android.permission.READ_CONTACTS": (5, "lê contatos"),
    "android.permission.ACCESS_FINE_LOCATION": (5, "localização precisa"),
}
APPOPS = {
    "SYSTEM_ALERT_WINDOW": (15, "desenha sobre outros apps"),
    "REQUEST_INSTALL_PACKAGES": (15, "pode instalar outros apps"),
}

COLETA = r"""
sec(){ echo "@@SEC $1"; }
sec props; getprop
sec pkgs; pm list packages -f -i {F}
sec desativados; pm list packages -d
sec acess; settings get secure enabled_accessibility_services
sec notif; settings get secure enabled_notification_listeners
sec sms; settings get secure sms_default_application
sec proxy; settings get global http_proxy
sec owners; dpm list-owners 2>&1
sec admins; dumpsys device_policy 2>&1
sec launcher; cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER 2>&1
sec idle; dumpsys deviceidle whitelist 2>&1
sec su; for f in /system/bin/su /system/xbin/su /sbin/su /su/bin/su /debug_ramdisk/su; do [ -e "$f" ] && echo "$f"; done
sec pkgdump; dumpsys package packages 2>&1
sec appops
for p in $(pm list packages {F} | sed 's/^package://'); do
  echo "@@PKG $p"
  for op in SYSTEM_ALERT_WINDOW REQUEST_INSTALL_PACKAGES; do
    cmd appops get $p $op 2>/dev/null || appops get $p $op 2>/dev/null
  done
done
sec fim
"""

HASHES = ("pm list packages -f {F} | sed 's/^package://; s/=[^=]*$//' | while read f; do "
          "printf '@@H\\t%s\\t%s\\t%s\\n' \"$(stat -c %s \"$f\" 2>/dev/null)\" "
          "\"$(sha256sum \"$f\" 2>/dev/null | cut -d' ' -f1)\" \"$f\"; done")


def nivel(score):
    if score >= 60:
        return "ALTO"
    if score >= 30:
        return "MÉDIO"
    return "BAIXO" if score > 0 else "OK"


def _componentes(v):
    if not v or v == "null":
        return set()
    return {c.split("/")[0] for c in v.split(":") if "/" in c}


def _data(txt):
    try:
        return datetime.strptime(txt.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def parse_pkgdump(txt):
    pkgs, cur = {}, None
    for linha in txt.splitlines():
        m = re.match(r"^\s{2}Package \[([\w.]+)\] \(", linha)
        if m:
            cur = pkgs.setdefault(m.group(1), {"perms": set(), "versao": None, "instalado": None})
            continue
        if cur is None:
            continue
        s = linha.strip()
        if s.startswith("versionName="):
            cur["versao"] = s.split("=", 1)[1]
        elif s.startswith("firstInstallTime="):
            cur["instalado"] = _data(s.split("=", 1)[1])
        else:
            m = re.match(r"(android\.permission\.[A-Z0-9_]+): granted=true", s)
            if m:
                cur["perms"].add(m.group(1))
    return pkgs


def parse_admins(txt):
    admins = set(re.findall(r"ComponentInfo\{([\w.]+)/", txt))
    dentro = False
    for linha in txt.splitlines():  # formato Android 10+
        if "Enabled Device Admins" in linha:
            dentro = True
            continue
        if dentro:
            m = re.match(r"^\s{4}([\w.]+)/[\w.$]+:\s*$", linha)
            if m:
                admins.add(m.group(1))
            elif linha.strip() and not linha.startswith("      "):
                dentro = False
    return admins


class AndroidScanner:
    def __init__(self, aparelho, vt=None, iocs=None, sistema=False):
        self.ap, self.vt, self.iocs, self.sistema = aparelho, vt, iocs, sistema
        self.filtro = "-e" if sistema else "-3"
        self.apps, self.avisos = {}, []
        self.permitidos = permitidos()

    # ---------- coleta ----------
    def coletar(self):
        s = self.ap.script(COLETA.replace("{F}", self.filtro), timeout=900)
        if "fim" not in s:
            raise AdbErro("Coleta interrompida — resultado incompleto. Reconecte o cabo e tente de novo.")
        self.props = dict(re.findall(r"^\[(.+?)\]: \[(.*)\]$", s.get("props", ""), re.M))
        dump = parse_pkgdump(s.get("pkgdump", ""))
        rx = re.compile(r"^package:(.+\.apk)=([\w.]+)(?:\s+installer=(\S+))?")
        for linha in s.get("pkgs", "").splitlines():
            m = rx.match(linha.strip())
            if not m:
                continue
            caminho, pkg, inst = m.groups()
            d = dump.get(pkg, {})
            self.apps[pkg] = {
                "apk": caminho, "instalador": None if inst in (None, "null") else inst,
                "sistema": caminho.startswith(PASTAS_SISTEMA), "perms": d.get("perms", set()),
                "versao": d.get("versao"), "instalado": d.get("instalado"),
                "appops": set(), "sha256": None, "tamanho": None, "cert": None, "vt": None,
            }
        if not self.apps:
            raise AdbErro("Nenhum app listado — o 'pm list packages' falhou.")
        atual = None
        for linha in s.get("appops", "").splitlines():
            if linha.startswith("@@PKG "):
                atual = self.apps.get(linha[6:].strip())
            elif atual is not None:
                m = re.match(r"^\s*(\w+): allow", linha)
                if m and m.group(1) in APPOPS:
                    atual["appops"].add(m.group(1))

        self.desativados = set(re.findall(r"^package:([\w.]+)", s.get("desativados", ""), re.M))
        self.acess = _componentes(s.get("acess"))
        self.notif = _componentes(s.get("notif"))
        self.admins = parse_admins(s.get("admins", ""))
        self.owners = set(re.findall(r"admin=([\w.]+)/", s.get("owners", "")))
        self.sms = (s.get("sms") or "").strip()
        self.proxy = (s.get("proxy") or "").strip()
        self.su = [l for l in s.get("su", "").splitlines() if l.strip()]
        self.sempre_ativo = set(re.findall(r"^user,([\w.]+),", s.get("idle", ""), re.M))
        lanc = s.get("launcher", "")
        icones = set(re.findall(r"^\s*([\w.]+)/", lanc, re.M))
        self.icones = icones or None
        if self.icones is None:
            self.avisos.append("Não foi possível listar ícones (Android antigo): critério ignorado.")
        if not s.get("admins"):
            self.avisos.append("Lista de administradores vazia/indisponível.")

    def info(self):
        g = self.props.get
        return {
            "fabricante": g("ro.product.manufacturer", "?"), "modelo": g("ro.product.model", "?"),
            "android": g("ro.build.version.release", "?"), "sdk": g("ro.build.version.sdk", "?"),
            "patch_seguranca": g("ro.build.version.security_patch", "?"), "serial": self.ap.serial,
        }

    def calcular_hashes(self):
        """Gerador: devolve cada pacote conforme o hash sai do aparelho."""
        por_caminho = {d["apk"]: p for p, d in self.apps.items()}
        for linha in self.ap.linhas(HASHES.replace("{F}", self.filtro)):
            partes = linha.split("\t")
            if len(partes) != 4 or partes[0] != "@@H":
                continue
            pkg = por_caminho.get(partes[3])
            if not pkg:
                continue
            d = self.apps[pkg]
            d["tamanho"] = int(partes[1]) if partes[1].isdigit() else None
            d["sha256"] = partes[2] if re.fullmatch(r"[0-9a-f]{64}", partes[2]) else None
            yield pkg

    def candidatos(self, minimo=20, todos=False):
        res = {r["pacote"]: r["score"] for r in self.pontuar()[1]}
        return [p for p, d in self.apps.items() if not d["sistema"]
                and (todos or res[p] >= minimo or d["instalador"] not in LOJAS)]

    def ler_certificado(self, pkg):
        d = self.apps[pkg]
        if d["tamanho"]:
            try:
                d["cert"] = apksig.ler_remoto(self.ap, d["apk"], d["tamanho"])
            except Exception:
                d["cert"] = None

    def consultar_vt(self, pkg):
        d = self.apps[pkg]
        if self.vt and d["sha256"]:
            try:
                d["vt"] = self.vt.consultar(d["sha256"])
            except Exception as e:
                d["vt"] = {"erro": str(e)}

    # ---------- análise ----------
    def achados_aparelho(self):
        a, i = [], self.info()
        try:
            patch = datetime.strptime(i["patch_seguranca"], "%Y-%m-%d")
            meses = (datetime.now() - patch).days // 30
            if meses >= 24:
                a.append(("ALTO", f"Atualização de segurança de {meses} meses atrás"))
            elif meses >= 12:
                a.append(("MÉDIO", f"Atualização de segurança de {meses} meses atrás"))
        except ValueError:
            pass
        if self.proxy and self.proxy not in ("null", ":0"):
            a.append(("ALTO", f"Proxy global ativo ({self.proxy}): o tráfego pode estar sendo interceptado"))
        if self.su:
            a.append(("ALTO", "Root detectado (" + ", ".join(self.su) + ")"))
        if self.props.get("ro.boot.verifiedbootstate") == "orange" or self.props.get("ro.boot.flash.locked") == "0":
            a.append(("MÉDIO", "Bootloader desbloqueado"))
        for o in self.owners:
            a.append(("MÉDIO", f"Aparelho gerenciado por {o} (normal se for celular corporativo)"))
        if self.sms and self.sms not in SMS_CONHECIDOS:
            a.append(("MÉDIO", f"App de SMS padrão incomum: {self.sms}"))
        return a

    def pontuar(self):
        resultados = []
        agora = datetime.now()
        for pkg, d in self.apps.items():
            a = []
            ioc = self.iocs.checar(pkg, d["cert"], d["sha256"]) if self.iocs else None
            if ioc:
                a.append((100, f"AMEAÇA CONHECIDA: {ioc}"))
            loja = LOJAS.get(d["instalador"])
            if pkg in self.acess:
                a.append((40, "serviço de acessibilidade ativo (pode ler e controlar a tela)"))
            if pkg in self.admins:
                a.append((30, "administrador do dispositivo (dificulta a remoção)"))
            if pkg in self.owners:
                a.append((30, "controla o aparelho (device owner)"))
            if pkg in self.notif:
                a.append((20, "lê todas as notificações"))
            if not d["sistema"]:
                if self.icones is not None and pkg not in self.icones:
                    a.append((20, "sem ícone na tela inicial"))
                if not loja:
                    a.append((15, f"instalado fora da loja ({d['instalador'] or 'desconhecido'})"))
            if pkg == self.sms and pkg not in SMS_CONHECIDOS:
                a.append((20, "definido como app de SMS padrão"))
            a += [PERMISSOES[p] for p in d["perms"] if p in PERMISSOES]
            a += [APPOPS[o] for o in d["appops"]]
            if d["cert"] and d["cert"]["debug"]:
                a.append((25, "assinado com certificado de teste (debug)"))
            vt = d["vt"] or {}
            if vt.get("malicioso"):
                a.append((60, f"VirusTotal: {vt['malicioso']} antivírus detectaram ({vt.get('rotulo') or 'sem rótulo'})"))
            elif vt.get("conhecido") is False and not loja and not d["sistema"]:
                a.append((10, "APK nunca visto pelo VirusTotal"))
            if pkg in self.sempre_ativo:
                a.append((5, "liberado da economia de bateria (roda sempre)"))
            if d["instalado"] and (agora - d["instalado"]).days < 7:
                a.append((5, f"instalado há {(agora - d['instalado']).days} dia(s)"))

            score = min(100, sum(p for p, _ in a))
            permitido = pkg in self.permitidos and bool(loja) and not ioc
            if permitido:
                score = min(score, 10)
            resultados.append({
                "pacote": pkg, "score": score, "nivel": "PERMITIDO" if permitido else nivel(score),
                "motivos": [m for _, m in sorted(a, reverse=True)], "ameaca": ioc,
                "instalador": d["instalador"], "loja": loja, "sistema": d["sistema"],
                "desativado": pkg in self.desativados, "versao": d["versao"],
                "instalado": d["instalado"].isoformat() if d["instalado"] else None,
                "sha256": d["sha256"], "cert": d["cert"], "virustotal": d["vt"],
            })
        resultados.sort(key=lambda r: r["score"], reverse=True)
        return self.achados_aparelho(), resultados

    # ---------- remoção ----------
    def remover(self, r):
        pkg = r["pacote"]
        pasta = quarentena.criar(self.ap, pkg, r, copiar_apk=True)
        self.ap.sh(f"am force-stop {pkg}")
        for chave in ("enabled_accessibility_services", "enabled_notification_listeners"):
            atual = self.ap.sh(f"settings get secure {chave}")
            if atual and atual != "null" and pkg + "/" in atual:
                novo = ":".join(c for c in atual.split(":") if not c.startswith(pkg + "/"))
                self.ap.sh(f"settings put secure {chave} {shlex.quote(novo)}" if novo else f"settings delete secure {chave}")

        out = self.ap.adb("uninstall", pkg, erro=True, timeout=180)
        if "Success" in out:
            quarentena.registrar(pasta, "removido")
            return True, "removido (cópia na quarentena)"
        out2 = self.ap.sh(f"pm uninstall --user 0 {pkg}", erro=True)
        if "Success" in out2:
            quarentena.registrar(pasta, "removido_usuario0")
            return True, "removido para o usuário (reversível)"
        if "DEVICE_POLICY" in out + out2:
            self.ap.sh("am start -a android.settings.SECURITY_SETTINGS")
            return False, ("bloqueado por ser administrador. Abri as Configurações de Segurança no celular: "
                           "desative o app em 'Apps de administrador' e rode de novo.")
        out3 = self.ap.sh(f"pm disable-user --user 0 {pkg}", erro=True)
        if "disabled" in out3:
            quarentena.registrar(pasta, "desativado")
            return True, "desativado (não foi possível desinstalar)"
        return False, f"falhou: {out or out2 or out3}"


def nota(achados, resultados):
    n = 100
    n -= sum(25 if nv == "ALTO" else 10 for nv, _ in achados)
    n -= sum(30 if r["nivel"] == "ALTO" else 8 if r["nivel"] == "MÉDIO" else 0 for r in resultados)
    n = max(0, n)
    if any(r.get("ameaca") for r in resultados):
        n = min(n, 20)  # ameaça conhecida = crítico, sempre
    rot = "Excelente" if n >= 90 else "Bom" if n >= 70 else "Atenção" if n >= 50 else "Crítico"
    return n, rot
