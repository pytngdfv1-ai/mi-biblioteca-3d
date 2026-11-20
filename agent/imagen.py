"""Utilidades de imagen: portada trasera generada, color dominante, redimensionado."""
import io
import colorsys

from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/"]


def font(size, bold=False):
    for d in FONT_DIRS:
        for n in (["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"] if bold else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf"]):
            try:
                return ImageFont.truetype(d + n, size)
            except Exception:
                pass
    return ImageFont.load_default()


def abrir(data, max_side=1024):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    return im


def jpeg(im, q=86):
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=q, optimize=True)
    return b.getvalue()


def dominante(im):
    """Color vivo dominante (hex) para etiquetas y fondos."""
    p = im.copy().resize((48, 48)).quantize(8).convert("RGB")
    best, score = (90, 90, 110), -1
    for n, c in sorted(p.getcolors(), reverse=True):
        h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
        sc = n * (0.3 + s) * (0.4 + min(v, 0.9))
        if sc > score:
            best, score = c, sc
    return "#%02x%02x%02x" % best


def _ajustar(draw, texto, ancho, size, bold):
    f = font(size, bold)
    while size > 14 and draw.textlength(texto, font=f) > ancho:
        size -= 2
        f = font(size, bold)
    return f


def trasera(front, artista, album, temas, anio=None, sello=None, size=1024):
    """Contraportada generada: fondo con la portada desenfocada, título y lista de temas."""
    bg = front.copy().resize((size, size), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    ov = Image.new("RGB", (size, size), (8, 8, 10))
    bg = Image.blend(bg, ov, 0.68)
    d = ImageDraw.Draw(bg)
    m = int(size * 0.07)
    w = size - 2 * m
    f = _ajustar(d, (artista or "").upper(), w, int(size * 0.045), True)
    d.text((m, m), (artista or "").upper(), font=f, fill=(255, 255, 255))
    f = _ajustar(d, album or "", w, int(size * 0.075), True)
    d.text((m, m + int(size * 0.07)), album or "", font=f, fill=(240, 240, 240))
    y = m + int(size * 0.19)
    d.line((m, y, size - m, y), fill=(255, 255, 255), width=2)
    y += int(size * 0.03)
    temas = temas or []
    n = len(temas)
    fs = int(size * (0.04 if n <= 10 else 0.032 if n <= 14 else 0.026 if n <= 20 else 0.02))
    paso = int(fs * 1.45)
    ft = font(fs)
    maxn = max(1, (size - y - int(size * 0.12)) // paso)
    for i, t in enumerate(temas[:maxn]):
        d.text((m, y), f"{i + 1:02d}", font=ft, fill=(190, 190, 190))
        txt = t
        while d.textlength(txt, font=ft) > w - fs * 2.5 and len(txt) > 4:
            txt = txt[:-2]
        d.text((m + fs * 2.4, y), txt + ("…" if txt != t else ""), font=ft, fill=(245, 245, 245))
        y += paso
    pie = " · ".join(x for x in (sello, str(anio) if anio else None) if x)
    if pie:
        d.text((m, size - m - int(size * 0.03)), pie, font=font(int(size * 0.028)), fill=(170, 170, 170))
    return bg
