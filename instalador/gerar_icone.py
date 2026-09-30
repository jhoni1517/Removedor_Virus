"""Gera assets/celscan.ico (celular com linha de varredura). Requer Pillow: pip install pillow"""

from pathlib import Path

from PIL import Image, ImageDraw

TAMANHO = 256
DESTINO = Path(__file__).resolve().parent.parent / "assets" / "celscan.ico"
FUNDO, TINTA, DESTAQUE = (23, 25, 27), (240, 238, 233), (127, 178, 229)


def desenhar() -> Image.Image:
    e = 4  # desenha grande e reduz, para bordas suaves
    t = TAMANHO * e
    img = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, t - 1, t - 1], radius=int(t * 0.22), fill=FUNDO)
    # celular
    w, h = t * 0.40, t * 0.66
    x0, y0 = (t - w) / 2, (t - h) / 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=int(t * 0.07), outline=TINTA, width=int(t * 0.045))
    # cantos de mira
    m, c, g = t * 0.14, t * 0.12, int(t * 0.035)
    for (x, y, dx, dy) in ((m, m, 1, 1), (t - m, m, -1, 1), (m, t - m, 1, -1), (t - m, t - m, -1, -1)):
        d.line([(x, y + dy * c), (x, y), (x + dx * c, y)], fill=DESTAQUE, width=g, joint="curve")
    # linha de varredura
    y = t * 0.5
    d.rounded_rectangle([t * 0.18, y - t * 0.025, t * 0.82, y + t * 0.025], radius=int(t * 0.025), fill=DESTAQUE)
    return img.resize((TAMANHO, TAMANHO), Image.LANCZOS)


if __name__ == "__main__":
    DESTINO.parent.mkdir(exist_ok=True)
    desenhar().save(DESTINO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Ícone salvo em", DESTINO)
