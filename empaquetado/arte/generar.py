"""Arte geométrico del asistente; opcional para rediseñar, requiere Pillow.

Los PNG generados viajan en Git; construir el instalador no necesita Pillow.
"""
from pathlib import Path

from PIL import Image, ImageDraw

DESTINO = Path(__file__).resolve().parent


def calendario(lado=256):
    s = lado / 256
    imagen = Image.new('RGBA', (lado, lado))
    d = ImageDraw.Draw(imagen)

    def caja(coords, fill, radius=0):
        coords = tuple(round(c*s) for c in coords)
        d.rounded_rectangle(coords, radius=round(radius*s), fill=fill)

    caja((20, 38, 236, 231), '#ddd9ff', 28)
    caja((20, 38, 236, 101), '#7b67e9', 28)
    caja((20, 78, 236, 103), '#7b67e9')
    for x in (72, 184):
        caja((x-7, 21, x+7, 63), '#bdb2ff', 7)
    for y in (125, 163, 201):
        for x in (63, 106, 149, 192):
            caja((x-9, y-9, x+9, y+9), '#ffffff' if x != 149 else '#7b67e9', 6)
    return imagen


if __name__ == '__main__':
    # Relación 164:314 de Inno Setup, a 4x para pantallas de alta densidad.
    ancho, alto = 656, 1256
    imagen = Image.new('RGB', (ancho, alto))
    d = ImageDraw.Draw(imagen)
    for y in range(alto):
        t = y / alto
        d.line((0, y, ancho, y), fill=(int(35+18*t), int(30+11*t), int(76+35*t)))
    for box in [(-280, -210, 580, 650), (175, 925, 970, 1720)]:
        d.ellipse(box, outline='#50488c', width=2)
    d.rounded_rectangle((81, 208, 575, 899), radius=36, fill='#3d356e')
    icono = calendario(370)
    imagen.paste(icono, (143, 257), icono)
    # Vista abstracta de una semana; sin textos rasterizados.
    for row in range(3):
        for col in range(5):
            x, y = 124+col*83, 706+row*48
            d.rounded_rectangle((x,y,x+60,y+24),radius=10,
                                fill='#aa9bee' if (col+row)%3 else '#695793')
    imagen.save(DESTINO/'bienvenida.png')
    calendario(128).save(DESTINO/'calendario.png')
