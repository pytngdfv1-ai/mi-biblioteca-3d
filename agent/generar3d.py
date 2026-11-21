"""Agente 3D de Mi Biblioteca. Gratis: corre en GitHub Actions (repo público = minutos ilimitados).
Por cada álbum de la nube genera hojas de cuadros girando (LP 12", vinilo 7", cassette), cerrado y abierto,
y las deja en la carpeta del álbum. Nunca borra nada; solo escribe sus propios archivos objeto3d-*.

Reglas:
  · Álbum con contraportada en su carpeta  -> LP + 7" + cassette
  · Álbum sin contraportada                -> solo cassette (trasera generada) y queda en «esperan contraportada»
  · Tema suelto (pocos temas)              -> 7" + cassette, con trasera generada
  · Salta lo ya hecho (huella en objeto3d.json); rehace si cambió la portada, la trasera, el sello o los datos.

Variables: CLOUDS | KOOFR_EMAIL/KOOFR_APP_PASSWORD/KOOFR_FOLDER, MAX_ALBUMS, FORCE=true, DRY_RUN=true, DEMO=true
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time

import clouds
import imagen
import liviano
from render import Renderer, data_url, webp

AUDIO = (".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aac")
IMG = (".jpg", ".jpeg", ".png", ".webp")
FRONT = re.compile(r"^(cover|folder|front|album|artwork|portada|car[aá]tula)(\s*(\d+|hd))?\.", re.I)
BACK = re.compile(r"^(back|contraportada|contra\s*portada|trasera)(\s*\d+)?\.", re.I)
SELLO = re.compile(r"^sello\.", re.I)
CASSETTE = re.compile(r"^cassette\.", re.I)
SINGLES = re.compile(r"(sueltos?|singles?)", re.I)
AG = "_agente3d"
VERSION = "2"            # súbela para rehacer todo (cambió el diseño de los objetos)
MAX_DEPTH = 6
MAX_SINGLE_TRACKS = 3
FRAMES, COLS = 16, 4
LIMITE_MIN = 45


def now():
    return dt.datetime.now(dt.timezone.utc)


def load_configs():
    raw = os.environ.get("CLOUDS", "").strip()
    if raw:
        return json.loads(raw)
    user = os.environ.get("KOOFR_EMAIL", "")
    if not user:
        sys.exit("Falta KOOFR_EMAIL / KOOFR_APP_PASSWORD (o CLOUDS).")
    return [{
        "name": "koofr", "type": "webdav",
        "url": os.environ.get("KOOFR_URL", "https://app.koofr.net/dav/Koofr"),
        "user": user, "password": os.environ["KOOFR_APP_PASSWORD"],
        "folder": os.environ.get("KOOFR_FOLDER") or "Música",
    }]


def scan(cloud, path, depth=0, out=None):
    out = [] if out is None else out
    if depth > MAX_DEPTH:
        return out
    items = cloud.list(path)
    files = [n for n, d in items if not d]
    if any(f.lower().endswith(AUDIO) for f in files):
        out.append((path, files))
    for n, d in items:
        if d and not n.startswith(("_", ".")):
            scan(cloud, f"{path}/{n}", depth + 1, out)
    return out


def names(path, root):
    parts = [p for p in path[len(root):].split("/") if p]
    return (parts[-2] if len(parts) >= 2 else ""), (parts[-1] if parts else "")


def clean_album(a):
    return re.sub(r"^\s*(\(?\d{4}\)?\s*[-–.]\s*)", "", a).strip()


def track_name(f):
    n = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", f)
    n = re.sub(r"^\s*\d{1,3}\s*[-–._)]*\s*", "", n)
    return n.strip() or f


def pick_front(files):
    cands = [f for f in files if f.lower().endswith(IMG) and FRONT.match(f)]
    hd = [f for f in cands if "hd" in f.lower()]
    return (hd or cands or [None])[0]


def first(files, rx):
    return next((f for f in files if f.lower().endswith(IMG) and rx.match(f)), None)


def sha(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
    return h.hexdigest()[:16]


class Salida:
    """Dónde se guardan los archivos: la nube o, en prueba, una carpeta local."""

    def __init__(self, cloud, dry):
        self.cloud, self.dry = cloud, dry
        os.makedirs("salida", exist_ok=True)

    def put(self, path, data, ctype):
        if self.dry:
            local = os.path.join("salida", path.strip("/").replace("/", "__"))
            open(local, "wb").write(data)
            return True
        return self.cloud.put(path, data, ctype, overwrite=True)


def _buscar_trasera(cloud, path, artista, titulo, estado_cov):
    """Si Coveralia tiene la trasera, la guarda como Contraportada.jpg en la carpeta del álbum."""
    import coveralia
    cov = estado_cov.setdefault("coveralia2", {})
    hoy = dt.date.today()
    ult = cov.get(path)
    if ult and (hoy - dt.date.fromisoformat(ult)).days < 14:
        return None                      # ya se buscó hace poco: no insistir
    b, info = coveralia.trasera(artista, titulo)
    cov[path] = hoy.isoformat()
    if not b:
        print(f"    Coveralia: {info}")
        return None
    if cloud.put(f"{path}/Contraportada.jpg", b, "image/jpeg", overwrite=False):
        print(f"    Coveralia: trasera guardada ({info})")
        cov.pop(path, None)
        return "Contraportada.jpg"
    return None


def hacer_album(r, out, cloud, path, files, root, st):
    """Devuelve (estado, detalle). estado: hecho | salta | espera | error | sin_portada"""
    artista, album = names(path, root)
    album = clean_album(album)
    audio = [f for f in files if f.lower().endswith(AUDIO)]
    nombre_front = pick_front(files)
    if not nombre_front:
        return "sin_portada", "sin portada en la carpeta"
    nombre_back = first(files, BACK)
    nombre_sello, nombre_shell = first(files, SELLO), first(files, CASSETTE)
    single = len(audio) <= MAX_SINGLE_TRACKS or bool(SINGLES.search(path))

    meta = {}
    if "album.json" in files:
        try:
            meta = json.loads(cloud.get(f"{path}/album.json"))
        except Exception:
            meta = {}
    titulo = meta.get("titulo") or album
    artista = meta.get("artista") or artista
    anio = meta.get("año") or None
    sello_nom = meta.get("sello") or None
    temas = [t.get("titulo") for t in (meta.get("temas") or []) if t.get("titulo")] or [track_name(f) for f in sorted(audio)]

    if nombre_back is None and not single and not os.environ.get("DRY_RUN") == "true" and not os.environ.get("DEMO") == "true":
        nombre_back = _buscar_trasera(cloud, path, artista, titulo, estado_cov=st)
        if nombre_back:
            files = list(files) + [nombre_back]
    tiene_back = nombre_back is not None
    if single:
        objetos = ["7", "k7"]
    elif tiene_back:
        objetos = ["lp", "7", "k7"]
    else:
        objetos = ["k7"]

    front_b = cloud.get(f"{path}/{nombre_front}")
    back_b = cloud.get(f"{path}/{nombre_back}") if tiene_back else b""
    sello_b = cloud.get(f"{path}/{nombre_sello}") if nombre_sello else b""
    shell_b = cloud.get(f"{path}/{nombre_shell}") if nombre_shell else b""
    huella = sha(VERSION, imagen.huella_img(imagen.abrir(front_b, 256)), imagen.huella_img(imagen.abrir(back_b, 256)) if back_b else b"", imagen.huella_img(imagen.abrir(sello_b, 256)) if sello_b else b"", imagen.huella_img(imagen.abrir(shell_b, 256)) if shell_b else b"", titulo, artista, anio or "", "|".join(temas), ",".join(objetos))

    man_path = f"{path}/objeto3d.json"
    if not os.environ.get("FORCE") == "true" and "objeto3d.json" in files:
        try:
            old = json.loads(cloud.get(man_path))
            if old.get("huella") == huella:
                espera = (not tiene_back and not single)
                return ("espera" if espera else "salta"), "ya estaba hecho"
        except Exception:
            pass

    front = imagen.abrir(front_b)
    accent = imagen.dominante(front)
    if tiene_back:
        back = imagen.abrir(back_b)
    else:
        back = imagen.trasera(front, artista, titulo, temas, anio, sello_nom)
    f_url, b_url = data_url(imagen.jpeg(front)), data_url(imagen.jpeg(back))
    label_url = data_url(imagen.jpeg(imagen.abrir(sello_b, 600))) if sello_b else None
    shell_url = data_url(imagen.jpeg(imagen.abrir(shell_b, 900))) if shell_b else None

    manifest = {"version": int(VERSION), "huella": huella, "generado": now().isoformat(), "cuadros": FRAMES,
                "columnas": COLS, "tamano": 300, "trasera_generada": not tiene_back, "objetos": {}}
    for obj in objetos:
        for estado in ("cerrado", "abierto"):
            sh = r.sheet(kind=obj, state=estado, front=f_url, back=b_url, label=label_url, shell=shell_url,
                         accent=accent, title=titulo, frames=FRAMES, cols=COLS)
            nombre = f"objeto3d-{'cassette' if obj == 'k7' else obj}-{estado}.webp"
            out.put(f"{path}/{nombre}", webp(sh), "image/webp")
            manifest["objetos"].setdefault("cassette" if obj == "k7" else obj, {})[estado] = nombre
    out.put(man_path, json.dumps(manifest, ensure_ascii=False, indent=1).encode(), "application/json")
    espera = (not tiene_back and not single)
    return ("espera" if espera else "hecho"), ", ".join(objetos) + f" · {len(audio)} temas" + (" · suelto" if single else "") + (" · con contraportada" if tiene_back else "")


def informe(res, total, t0):
    c = {}
    for _, (e, _) in res.items():
        c[e] = c.get(e, 0) + 1
    L = ["# Objetos 3D creados", "",
         f"Actualizado: {now().strftime('%Y-%m-%d %H:%M')} UTC · {total} álbumes en la nube · {int((time.time() - t0) / 60)} min", "",
         f"- Hechos ahora: {c.get('hecho', 0)}",
         f"- Ya estaban hechos: {c.get('salta', 0)}",
         f"- Esperan contraportada (solo cassette hecho): {c.get('espera', 0)}",
         f"- Sin portada: {c.get('sin_portada', 0)}",
         f"- Con error: {c.get('error', 0)}",
         f"- Pendientes de procesar: {c.get('pendiente', 0)}", ""]
    for titulo, clave in (("Creados ahora", "hecho"), ("Ya hechos", "salta"), ("Esperan contraportada (agrégala y se rehacen LP y 7\")", "espera"),
                          ("Sin portada", "sin_portada"), ("Errores", "error")):
        items = [(p, d) for p, (e, d) in sorted(res.items()) if e == clave]
        if items:
            L += [f"## {titulo} ({len(items)})", ""] + [f"- {p} — {d}" for p, d in items] + [""]
    return "\n".join(L)


def run_cloud(cfg, maxn, dry, r):
    cloud = clouds.make(cfg)
    root = "/" + cfg.get("folder", "").strip("/") if cfg.get("folder") else ""
    global AG
    AG = f"{root}/_agente3d"   # dentro de la carpeta de música, donde la app lo busca
    out = Salida(cloud, dry)
    albums = scan(cloud, root)
    print(f"[{cfg['name']}] {len(albums)} álbumes")
    estado_p = f"{AG}/estado.json"
    try:
        estado = json.loads(cloud.get(estado_p)) if cloud.exists(estado_p) else {}
    except Exception:
        estado = {}
    prev = estado.get("albums", {})
    res = {}
    t0 = time.time()
    hechos = 0
    # Primero los que nunca se hicieron; luego los demás (para revisar cambios).
    orden = sorted(albums, key=lambda a: (a[0] in prev and prev[a[0]].get("estado") in ("hecho", "salta"), a[0]))
    for p, files in orden:
        rel = p[len(root):].strip("/")
        if time.time() - t0 > LIMITE_MIN * 60 or hechos >= maxn:
            e = prev.get(p, {}).get("estado") or "pendiente"
            res[rel] = (e if e != "pendiente" else "pendiente", prev.get(p, {}).get("detalle", "queda para la próxima corrida"))
            continue
        try:
            e, d = hacer_album(r, out, cloud, p, files, root, estado)
            if e in ("hecho", "espera") and "ya estaba" not in d:
                hechos += 1
            print(f"  {rel}: {e} ({d})")
        except Exception as ex:
            e, d = "error", str(ex)[:160]
            print(f"  {rel}: ERROR {d}")
        res[rel] = (e, d)
    estado["albums"] = {root + "/" + k: {"estado": v[0], "detalle": v[1]} for k, v in res.items()}
    estado["actualizado"] = now().isoformat()
    md = informe(res, len(albums), t0)
    out.put(estado_p, json.dumps(estado, ensure_ascii=False, indent=1).encode(), "application/json")
    out.put(f"{AG}/objetos.md", md.encode("utf-8"), "text/markdown")
    out.put(f"{AG}/objetos.json", json.dumps({k: {"estado": v[0], "detalle": v[1]} for k, v in res.items()}, ensure_ascii=False, indent=1).encode(), "application/json")
    sm = os.environ.get("GITHUB_STEP_SUMMARY")
    if sm:
        open(sm, "a", encoding="utf-8").write(md)
    print(md)


def demo(r):
    """Sin nube: genera álbumes de muestra y deja las hojas en salida/ para revisarlas."""
    from PIL import Image, ImageDraw
    os.makedirs("salida", exist_ok=True)
    muestras = [("Artista de Prueba", "Disco Demo", (200, 60, 50)), ("Otro Artista", "Noche Azul", (40, 90, 200))]
    for art, alb, col in muestras:
        im = Image.new("RGB", (1000, 1000), col)
        d = ImageDraw.Draw(im)
        for i in range(0, 1000, 40):
            d.ellipse((500 - i, 500 - i, 500 + i, 500 + i), outline=tuple(min(255, c + 40) for c in col), width=6)
        d.text((60, 60), art.upper(), font=imagen.font(60, True), fill="white")
        d.text((60, 900), alb, font=imagen.font(80, True), fill="white")
        back = imagen.trasera(im, art, alb, [f"Tema número {i}" for i in range(1, 11)], 1991, "Sello Demo")
        f_url, b_url = data_url(imagen.jpeg(im)), data_url(imagen.jpeg(back))
        accent = imagen.dominante(im)
        for obj in ("lp", "7", "k7"):
            for estado in ("cerrado", "abierto"):
                sh = r.sheet(kind=obj, state=estado, front=f_url, back=b_url, label=None, shell=None, accent=accent,
                             title=alb, frames=FRAMES, cols=COLS)
                n = f"salida/demo-{alb.replace(' ', '_')}-{obj}-{estado}"
                open(n + ".webp", "wb").write(webp(sh))
                print(n, len(webp(sh)) // 1024, "KB")


def main():
    r = Renderer()
    try:
        if os.environ.get("DEMO") == "true":
            return demo(r)
        maxn = int(os.environ.get("MAX_ALBUMS") or 60)
        dry = (os.environ.get("DRY_RUN", "") or "").lower() in ("1", "true", "yes")
        for cfg in load_configs():
            run_cloud(cfg, maxn, dry, r)
            if os.environ.get("LIVIANO", "true") != "false":
                liviano.run(cfg, dry)
    finally:
        r.close()


if __name__ == "__main__":
    main()
