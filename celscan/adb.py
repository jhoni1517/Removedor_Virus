"""Camada de acesso ao ADB: localização, download, execução e coleta em lote."""
import io
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

from config import BASE, DIR

URL_PT = "https://dl.google.com/android/repository/platform-tools-latest-{}.zip"
SO = {"Windows": "windows", "Darwin": "darwin", "Linux": "linux"}
EXE = "adb.exe" if os.name == "nt" else "adb"
_ADB = None


class AdbErro(Exception):
    pass


class AdbAusente(AdbErro):
    pass


def localizar():
    cands = [os.getenv("CELSCAN_ADB"), shutil.which("adb"),
             BASE / "platform-tools" / EXE, DIR / "platform-tools" / EXE]
    for c in cands:
        if c and os.path.isfile(c):
            return str(c)
    return None


def instalar_platform_tools():
    """Baixa o Android Platform Tools oficial para ~/.celscan."""
    import requests
    url = URL_PT.format(SO.get(platform.system(), "linux"))
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    zipfile.ZipFile(io.BytesIO(r.content)).extractall(DIR)
    adb = DIR / "platform-tools" / EXE
    if os.name != "nt":
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
    global _ADB
    _ADB = str(adb)
    return _ADB


def binario():
    global _ADB
    if not _ADB:
        _ADB = localizar()
    if not _ADB:
        raise AdbAusente("ADB não encontrado.")
    return _ADB


def run(args, timeout=120, entrada=None):
    try:
        return subprocess.run([binario(), *args], capture_output=True, encoding="utf-8",
                              errors="replace", timeout=timeout, input=entrada)
    except subprocess.TimeoutExpired:
        raise AdbErro(f"'adb {' '.join(map(str, args[:4]))}' excedeu {timeout}s")


def dispositivos():
    run(["start-server"], timeout=30)
    res = []
    for linha in run(["devices"]).stdout.splitlines():
        m = re.match(r"^(\S+)\s+(device|unauthorized|offline|recovery|sideload|"
                     r"bootloader|no permissions.*)$", linha.strip())
        if m:
            res.append((m.group(1), m.group(2)))
    return res


def parear(endereco, codigo):
    return (run(["pair", endereco, codigo], timeout=60).stdout or "").strip()


def conectar(endereco):
    return (run(["connect", endereco], timeout=30).stdout or "").strip()


def secoes(texto):
    """Divide a saída de um script em seções marcadas com '@@SEC nome'."""
    sec, nome, buf = {}, None, []
    for linha in texto.replace("\r\n", "\n").split("\n"):
        if linha.startswith("@@SEC "):
            if nome:
                sec[nome] = "\n".join(buf).strip()
            nome, buf = linha[6:].strip(), []
        else:
            buf.append(linha)
    if nome:
        sec[nome] = "\n".join(buf).strip()
    return sec


class Aparelho:
    def __init__(self, serial):
        self.serial = serial

    def adb(self, *args, timeout=120, erro=False):
        r = run(["-s", self.serial, *args], timeout=timeout)
        return ((r.stdout or "") + ((r.stderr or "") if erro else "")).strip()

    def sh(self, comando, timeout=120, erro=False):
        return self.adb("shell", comando, timeout=timeout, erro=erro)

    def bytes(self, comando, timeout=60):
        """Saída binária sem conversão de quebra de linha (exec-out)."""
        try:
            return subprocess.run([binario(), "-s", self.serial, "exec-out", comando],
                                  capture_output=True, timeout=timeout).stdout
        except subprocess.TimeoutExpired:
            raise AdbErro(f"leitura binária excedeu {timeout}s")

    def script(self, texto, timeout=600):
        """Envia um script shell, executa numa única chamada e devolve as seções."""
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         encoding="utf-8", newline="\n") as f:
            f.write(texto)
            local = f.name
        remoto = "/data/local/tmp/celscan.sh"
        try:
            r = run(["-s", self.serial, "push", local, remoto], timeout=60)
            if r.returncode != 0:
                raise AdbErro(f"falha ao enviar script: {r.stderr.strip()}")
            saida = self.sh(f"sh {remoto}", timeout=timeout)
            self.sh(f"rm -f {remoto}")
        finally:
            os.unlink(local)
        return secoes(saida)

    def linhas(self, comando):
        """Executa e entrega a saída linha a linha (para barra de progresso)."""
        p = subprocess.Popen([binario(), "-s", self.serial, "shell", comando],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             encoding="utf-8", errors="replace")
        try:
            for linha in p.stdout:
                yield linha.rstrip("\r\n")
        finally:
            p.stdout.close()
            p.wait()
