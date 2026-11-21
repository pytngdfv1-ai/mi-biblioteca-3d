"""Busca la contraportada de un álbum en coveralia.com (robots.txt lo permite; se usa poco y con pausa).
Página del disco: /discos/<artista>-<album>.php ; trasera: images.coveralia.com/audio/n/<Artista>-<Album>-Trasera.jpg"""
import re
import time
import unicodedata

import requests

H = {"User-Agent": "Mozilla/5.0 (compatible; MiBibliotecaAgente/1.0)", "Referer": "https://www.coveralia.com/"}
_last = [0.0]


def _slug(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _get(url):
    d = 1.5 - (time.time() - _last[0])
    if d > 0:
        time.sleep(d)
    _last[0] = time.time()
    return requests.get(url, headers=H, timeout=30)


def _variantes(album):
    a = album
    out = [a]
    out.append(re.sub(r"\s*[\(\[].*?[\)\]]", "", a).strip())                       # sin (Deluxe), [Remastered]…
    out.append(re.sub(r"\s*[-–]\s*(deluxe|remaster|remastered|bonus|expanded|anniversary).*$", "", out[-1], flags=re.I).strip())
    vistos = []
    for v in out:
        if v and v not in vistos:
            vistos.append(v)
    return vistos


def trasera(artista, album):
    """-> (bytes, url) o (None, motivo)."""
    arts = [artista]
    if artista.lower().startswith("the "):
        arts.append(artista[4:])
    for ar in arts:
        for al in _variantes(album):
            url = f"https://www.coveralia.com/discos/{_slug(ar)}-{_slug(al)}.php"
            try:
                r = _get(url)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            m = re.search(r'href="/caratulas/([^"]+-Trasera)\.php"', r.text)
            if not m:
                return None, "el disco está en Coveralia pero sin trasera"
            mf = re.search(r'href="/caratulas/([^"]+-Frontal)\.php"', r.text)
            img = None
            if mf:   # la página de la frontal muestra la ruta real (audio/<letra>/Artista_Album-Frontal.jpg)
                try:
                    rf = _get(f"https://www.coveralia.com/caratulas/{mf.group(1)}.php")
                    mi = re.search(r'(https?://images\.coveralia\.com/audio/[a-z0-9]/[^"\']+-Frontal\.jpg)', rf.text)
                    if mi:
                        img = mi.group(1)[:-len("Frontal.jpg")] + "Trasera.jpg"
                except Exception:
                    pass
            for cand in [img, f"https://images.coveralia.com/audio/n/{m.group(1)}.jpg"]:
                if not cand:
                    continue
                try:
                    ri = _get(cand)
                except Exception:
                    continue
                if ri.status_code == 200 and ri.content[:3] == b"\xff\xd8\xff" and len(ri.content) > 20_000:
                    return ri.content, cand
            return None, "imagen no disponible"
    return None, "no está en Coveralia"
