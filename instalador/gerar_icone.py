"""Gera assets/icone.ico (escudo verde com check). Requer Pillow: pip install pillow"""

from pathlib import Path

from PIL import Image, ImageDraw

TAMANHO = 256
DESTINO = Path(__file__).resolve().parent.parent / "assets" / "icone.ico"


def desenhar() -> Image.Image:
    escala = 4  # desenha grande e reduz, para bordas suaves
    t = TAMANHO * escala
    img = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = t * 0.08
    topo, base = m, t - m
    esquerda, direita = m * 1.4, t - m * 1.4
    meio = t / 2
    escudo = [
        (meio, topo),
        (direita, topo + t * 0.14),
        (direita, t * 0.50),
        (meio + t * 0.20, base - t * 0.12),
        (meio, base),
        (meio - t * 0.20, base - t * 0.12),
        (esquerda, t * 0.50),
        (esquerda, topo + t * 0.14),
    ]
    d.polygon(escudo, fill=(22, 128, 61))
    interno = [(meio + (x - meio) * 0.86, t * 0.52 + (y - t * 0.52) * 0.86) for x, y in escudo]
    d.polygon(interno, fill=(34, 197, 94))
    largura = int(t * 0.085)
    d.line([(t * 0.33, t * 0.52), (t * 0.46, t * 0.65), (t * 0.69, t * 0.38)],
           fill="white", width=largura, joint="curve")
    for x, y in ((t * 0.33, t * 0.52), (t * 0.69, t * 0.38)):
        d.ellipse([x - largura / 2, y - largura / 2, x + largura / 2, y + largura / 2], fill="white")
    return img.resize((TAMANHO, TAMANHO), Image.LANCZOS)


if __name__ == "__main__":
    DESTINO.parent.mkdir(exist_ok=True)
    desenhar().save(DESTINO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Ícone salvo em", DESTINO)
