"""Servidor adb falso (protocolo real do adb sobre TCP) para testar a conexão direta."""

from __future__ import annotations

import socket
import struct
import threading


class ServidorAdb:
    def __init__(self, respostas: dict[str, bytes], seriais=("ABC123",)):
        self.respostas, self.seriais = respostas, set(seriais)
        self.recebidos: list[str] = []
        self.arquivos: dict[str, bytes] = {}
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.porta = self.sock.getsockname()[1]
        self._parar = False
        threading.Thread(target=self._aceitar, daemon=True).start()

    def fechar(self):
        self._parar = True
        self.sock.close()

    def _aceitar(self):
        while not self._parar:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._atender, args=(c,), daemon=True).start()

    @staticmethod
    def _ler(c, n):
        b = b""
        while len(b) < n:
            p = c.recv(n - len(b))
            if not p:
                raise ConnectionError
            b += p
        return b

    def _cmd(self, c):
        return self._ler(c, int(self._ler(c, 4), 16)).decode()

    def _atender(self, c):
        try:
            cmd = self._cmd(c)
            self.recebidos.append(cmd)
            if cmd == "host:version":
                c.sendall(b"OKAY0004" + b"0029")
                return
            if cmd.startswith(("host:tport:serial:", "host:transport:")):
                serial = cmd.split(":")[-1]
                if serial not in self.seriais:
                    msg = b"device not found"
                    c.sendall(b"FAIL" + b"%04x" % len(msg) + msg)
                    return
                c.sendall(b"OKAY" + (b"\0" * 8 if "tport" in cmd else b""))
                cmd = self._cmd(c)
                self.recebidos.append(cmd)
            if cmd.startswith(("shell:", "exec:")):
                c.sendall(b"OKAY")
                corpo = cmd.split(":", 1)[1]
                for chave, resp in self.respostas.items():
                    if chave in corpo:
                        c.sendall(resp)
                        break
            elif cmd == "sync:":
                c.sendall(b"OKAY")
                self._sync(c)
        except (ConnectionError, OSError):
            pass
        finally:
            c.close()

    def _sync(self, c):
        caminho, dados = None, b""
        while True:
            ident, n = self._ler(c, 4), struct.unpack("<I", self._ler(c, 4))[0]
            if ident == b"SEND":
                caminho = self._ler(c, n).decode().split(",")[0]
            elif ident == b"DATA":
                dados += self._ler(c, n)
            elif ident == b"DONE":
                self.arquivos[caminho] = dados
                c.sendall(b"OKAY" + b"\0" * 4)
            elif ident == b"STAT":
                alvo = self._ler(c, n).decode()
                tam = len(self.arquivos.get(alvo, b""))
                c.sendall(b"STAT" + struct.pack("<III", 0o100644, tam, 0))
            elif ident == b"QUIT":
                return
