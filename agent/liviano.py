"""Imágenes livianas: convierte JPG/PNG de la biblioteca a WebP y, si la copia quedó bien, elimina el original.

Seguridad (nunca se borra nada sin comprobar):
  1. Se crea <nombre>.webp en la misma carpeta (calidad alta, lado máx. 3000 px, sin agrandar).
  2. Se comprueba que la copia abre, tiene las mismas proporciones y se parece al original
     (diferencia media de color menor a 4 de 255), y que pesa al menos 20 % menos.
  3. Se vuelve a descargar de la nube y se comprueba que lo guardado es idéntico.
  4. Solo entonces se borra el original. Si algo falla, el original queda intacto.
Si no se ahorra espacio, el archivo se deja como está y se anota para no revisarlo otra vez.

Variables: LIVIANO_MAX (archivos por corrida, 60), LIVIANO_MIN (minutos por corrida, 12), LIVIANO_BORRAR=false
(deja ambos), DRY_RUN=true (no escribe ni borra: solo estima el ahorro).
"""
import datetime as dt
import io
import json
import os
import re
import time

from PIL import Image, ImageChops, ImageOps, ImageStat

import clouds

CONVERTIR = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
SKIP_DIR = re.compile(r"^(_|\.|libreto liviano)", re.I)
AG = "_agente3d"
LADO_MAX = 3000
CALIDAD = 90
MIN_AHORRO = 0.20
MAX_DIFF = 4.0
MIN_BYTES = 120 * 1024       # no vale la pena convertir lo que ya es chico


def _now():
    return dt.datetime.now(dt.timezone.utc)


def caminar(cloud, path, depth=0, out=None):
    out = [] if out is None else out
    if depth > 8:
        return out
    items = cloud.list(path)
    out.append((path, [n for n, d in items if not d]))
    for n, d in items:
        if d and not SKIP_DIR.match(n):
            caminar(cloud, f"{path}/{n}", depth + 1, out)
    return out


def _convertir(data):
    im = Image.open(io.BytesIO(data))
    if getattr(im, "is_animated", False):
        return None, None, "animada"
    im = ImageOps.exif_transpose(im)
    tiene_alfa = im.mode in ("RGBA", "LA") or "transparency" in im.info
    im = im.convert("RGBA" if tiene_alfa else "RGB")
    orig = im.copy()
    if max(im.size) > LADO_MAX:
        im.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "WEBP", quality=CALIDAD, method=6)
    return orig, b.getvalue(), None


def _verificar(orig, nuevo_bytes):
    """True si la copia abre, conserva proporciones y se parece al original."""
    try:
        nuevo = Image.open(io.BytesIO(nuevo_bytes))
        nuevo.load()
        if abs(nuevo.width / nuevo.height - orig.width / orig.height) > 0.01:
            return False, "proporciones distintas"
        a = orig.convert("RGB").resize((256, 256), Image.LANCZOS)
        b = nuevo.convert("RGB").resize((256, 256), Image.LANCZOS)
        diff = ImageStat.Stat(ImageChops.difference(a, b)).mean
        if max(diff) > MAX_DIFF:
            return False, f"se ve distinta ({max(diff):.1f})"
        return True, ""
    except Exception as e:
        return False, f"no abre ({str(e)[:40]})"


def run(cfg, dry):
    maxn = int(os.environ.get("LIVIANO_MAX") or 60)
    limite = int(os.environ.get("LIVIANO_MIN") or 12) * 60
    borrar = os.environ.get("LIVIANO_BORRAR", "true") != "false"
    cloud = clouds.make(cfg)
    root = "/" + cfg.get("folder", "").strip("/") if cfg.get("folder") else ""
    sp = f"{AG}/liviano.json"
    try:
        st = json.loads(cloud.get(sp)) if cloud.exists(sp) else {}
    except Exception:
        st = {}
    hecho, omitido = st.get("hecho", {}), st.get("omitido", {})
    t0, n = time.time(), 0
    ahora = []
    carpetas = caminar(cloud, root)
    pend = 0
    for path, files in carpetas:
        fs = set(files)
        for f in files:
            if not f.lower().endswith(CONVERTIR):
                continue
            rel = f"{path[len(root):].strip('/')}/{f}"
            if rel in hecho or rel in omitido:
                continue
            if n >= maxn or time.time() - t0 > limite:
                pend += 1
                continue
            try:
                data = cloud.get(f"{path}/{f}")
                n += 1
                if len(data) < MIN_BYTES:
                    omitido[rel] = "ya es chico"
                    continue
                orig, nuevo, motivo = _convertir(data)
                if motivo:
                    omitido[rel] = motivo
                    continue
                if len(nuevo) > len(data) * (1 - MIN_AHORRO):
                    omitido[rel] = f"no ahorra ({len(data) // 1024} → {len(nuevo) // 1024} KB)"
                    continue
                ok, why = _verificar(orig, nuevo)
                if not ok:
                    omitido[rel] = why
                    continue
                destino = re.sub(r"\.[^.]+$", ".webp", f)
                if destino in fs:
                    omitido[rel] = "ya existe un .webp con ese nombre"
                    continue
                kb0, kb1 = len(data) // 1024, len(nuevo) // 1024
                if dry:
                    ahora.append((rel, kb0, kb1, "simulado"))
                    continue
                if not cloud.put(f"{path}/{destino}", nuevo, "image/webp", overwrite=False):
                    omitido[rel] = "no se pudo guardar la copia"
                    continue
                if cloud.get(f"{path}/{destino}") != nuevo:
                    cloud.delete(f"{path}/{destino}")
                    omitido[rel] = "la copia guardada no coincide"
                    continue
                if borrar and cloud.delete(f"{path}/{f}"):
                    hecho[rel] = [kb0, kb1]
                    ahora.append((rel, kb0, kb1, "original eliminado"))
                else:
                    hecho[rel] = [kb0, kb1]
                    ahora.append((rel, kb0, kb1, "copia creada (original conservado)"))
            except Exception as e:
                omitido[rel] = f"error: {str(e)[:60]}"
    ahorro = sum(v[0] - v[1] for v in hecho.values())
    L = ["# Imágenes livianas", "",
         f"Actualizado: {_now().strftime('%Y-%m-%d %H:%M')} UTC" + (" · SIMULACIÓN (no se tocó nada)" if dry else ""), "",
         f"- Convertidas en total: {len(hecho)} · espacio liberado: {ahorro / 1024:.1f} MB",
         f"- Ahora: {len(ahora)} · pendientes por revisar: {pend}",
         f"- Omitidas (ya chicas, no ahorran o no pasaron la comprobación): {len(omitido)}", ""]
    if ahora:
        L += ["## Esta corrida", ""] + [f"- {r}: {a} → {b} KB · {e}" for r, a, b, e in ahora] + [""]
    if omitido:
        L += ["## Omitidas", ""] + [f"- {k}: {v}" for k, v in list(omitido.items())[-80:]] + [""]
    md = "\n".join(L)
    print(md)
    if not dry:
        cloud.put(sp, json.dumps({"hecho": hecho, "omitido": omitido}, ensure_ascii=False).encode(), "application/json", overwrite=True)
        cloud.put(f"{AG}/liviano.md", md.encode("utf-8"), "text/markdown", overwrite=True)
    sm = os.environ.get("GITHUB_STEP_SUMMARY")
    if sm:
        open(sm, "a", encoding="utf-8").write("\n" + md)
