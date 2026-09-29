"""Leitura do certificado de assinatura (esquemas v2/v3) sem baixar o APK inteiro."""
import hashlib
import shlex
import struct

MAGIC = b"APK Sig Block 42"
V2, V3, V31 = 0x7109871A, 0xF05368C0, 0x1B93AD61


def _lp(buf, pos=0):
    n = struct.unpack_from("<I", buf, pos)[0]
    return buf[pos + 4:pos + 4 + n], pos + 4 + n


def certificado_der(ler, tamanho):
    """ler(offset, n) -> bytes. Retorna o DER do certificado ou None (só assinatura v1)."""
    n = min(tamanho, 65557)
    fim = ler(tamanho - n, n)
    i = fim.rfind(b"PK\x05\x06")
    if i < 0 or i + 20 > len(fim):
        return None
    cd = struct.unpack_from("<I", fim, i + 16)[0]
    if cd < 32:
        return None
    cab = ler(cd - 24, 24)
    if len(cab) < 24 or cab[8:] != MAGIC:
        return None
    tam = struct.unpack_from("<Q", cab, 0)[0]
    if not 32 <= tam <= 50_000_000 or tam + 8 > cd:
        return None
    bloco = ler(cd - tam - 8, tam + 8)
    pos, limite, blocos = 8, len(bloco) - 24, {}
    while pos + 12 <= limite:
        n, ident = struct.unpack_from("<QI", bloco, pos)
        blocos[ident] = bloco[pos + 12:pos + 8 + n]
        pos += 8 + n
    for ident in (V2, V3, V31):  # v2 tem o signatário original (bate com IOCs)
        if ident in blocos:
            try:
                seq, _ = _lp(blocos[ident])
                signer, _ = _lp(seq)
                dados, _ = _lp(signer)
                _, p = _lp(dados)          # digests
                certs, _ = _lp(dados, p)
                der, _ = _lp(certs)
                if der:
                    return der
            except struct.error:
                continue
    return None


def resumo(der):
    return {
        "sha1": hashlib.sha1(der).hexdigest().upper(),
        "sha256": hashlib.sha256(der).hexdigest().upper(),
        "debug": b"Android Debug" in der,
    }


def ler_local(caminho):
    with open(caminho, "rb") as f:
        f.seek(0, 2)
        tam = f.tell()

        def ler(off, n):
            f.seek(off)
            return f.read(n)
        der = certificado_der(ler, tam)
    return resumo(der) if der else None


def ler_remoto(aparelho, caminho, tamanho):
    q = shlex.quote(caminho)

    def ler(off, n, bs=4096):
        ini, fim = off // bs, (off + n + bs - 1) // bs
        dados = aparelho.bytes(f"dd if={q} bs={bs} skip={ini} count={fim - ini} 2>/dev/null")
        d = off - ini * bs
        return dados[d:d + n]
    der = certificado_der(ler, tamanho)
    return resumo(der) if der else None
