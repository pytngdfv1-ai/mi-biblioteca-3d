"""Corrige nombres de temas: quita el nombre del artista ("Artista - Tema" o "Tema - Artista" -> "Tema").

Modo (variable NOMBRES): prueba (solo informa, no toca nada) · aplicar · revertir (deshace lo aplicado).
Seguridad: solo quita un segmento que coincide EXACTO con el artista de la carpeta; nunca pisa un archivo
existente; copia, comprueba y recién entonces borra el viejo; todo queda en _agente3d/nombres.json para revertir.
También renombra la letra (Letras/<nombre>.lrc|.txt) para que siga emparejada."""
import datetime as dt
import json
import os
import re
import unicodedata

import clouds
import generar3d as g

SEP = re.compile(r"\s+[-–—]\s+")
NUM = re.compile(r"^(\s*\d{1,3}\s*[-–._)]*\s*)")
LETRAS = (".lrc", ".txt")


def _n(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^the ", "", s.strip())
    return re.sub(r"[^a-z0-9]", "", s)


def nuevo_stem(stem, artista):
    m = NUM.match(stem)
    pre = m.group(1) if m else ""
    resto = stem[len(pre):] if m else stem
    partes = SEP.split(resto)
    if len(partes) < 2 or not _n(artista):
        return None
    a = _n(artista)
    if _n(partes[0]) == a:
        partes = partes[1:]
    elif _n(partes[-1]) == a:
        partes = partes[:-1]
    else:
        return None
    t = " - ".join(partes).strip()
    return (pre + t).strip() if t else None


def _mover(cloud, src, dst):
    if cloud.exists(dst) or not cloud.copy(src, dst):
        return False
    if not cloud.exists(dst):
        return False
    return cloud.delete(src)


def carpetas_con_espacios(cloud, path, depth=0, out=None):
    """Carpetas cuyo nombre empieza o termina con espacio. Devuelve de más profunda a menos."""
    out = [] if out is None else out
    if depth > g.MAX_DEPTH:
        return out
    for n, d in cloud.list(path):
        if d and not n.startswith(("_", ".")):
            carpetas_con_espacios(cloud, f"{path}/{n}", depth + 1, out)
            if n != n.strip() and n.strip():
                out.append((path, n))
    return out


def run(cfg, modo):
    cloud = clouds.make(cfg)
    root = "/" + cfg.get("folder", "").strip("/") if cfg.get("folder") else ""
    ag = f"{root}/_agente3d"
    lp = f"{ag}/nombres.json"
    try:
        reg = json.loads(cloud.get(lp)) if cloud.exists(lp) else {}
    except Exception:
        reg = {}
    cambios = reg.get("cambios", [])
    L = [f"# Nombres de temas ({modo}) – {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC", ""]
    carp = reg.get("carpetas", [])
    if modo == "revertir":
        for c in list(carp):
            if cloud.move(c["a"], c["de"]):
                carp.remove(c)
                L.append(f"- carpeta revertida: {c['a']} → {c['de']}")
        n = 0
        for c in list(cambios):
            ok = _mover(cloud, f"{c['carpeta']}/{c['a']}", f"{c['carpeta']}/{c['de']}")
            for de, a in c.get("letras", []):
                _mover(cloud, f"{c['carpeta']}/Letras/{a}", f"{c['carpeta']}/Letras/{de}")
            if ok:
                cambios.remove(c)
                n += 1
                L.append(f"- revertido: {c['a']} → {c['de']}")
        L.insert(2, f"Revertidos: {n}\n")
    else:
        hechos = 0
        for padre, n in carpetas_con_espacios(cloud, root):
            de, a = f"{padre}/{n}", f"{padre}/{n.strip()}"
            if modo == "aplicar":
                if cloud.exists(a):
                    L.append(f"- carpeta NO renombrada (ya existe otra igual): {de[len(root):]}")
                    continue
                if not cloud.move(de, a):
                    L.append(f"- carpeta NO se pudo renombrar: {de[len(root):]}")
                    continue
                carp.append({"de": de, "a": a})
            hechos += 1
            L.append(f"- carpeta: `{n}` → `{n.strip()}` en {padre[len(root):] or '/'}")
        for p, files in g.scan(cloud, root):
            artista, _ = g.names(p, root)
            usados = {f.lower() for f in files}
            for f in sorted(files):
                if not f.lower().endswith(g.AUDIO):
                    continue
                stem, ext = os.path.splitext(f)
                ns = nuevo_stem(stem, artista)
                if not ns and stem != stem.strip():
                    ns = stem.strip()
                if not ns or (ns + ext).lower() in usados:
                    continue
                nuevo = ns + ext
                c = {"carpeta": p, "de": f, "a": nuevo, "letras": []}
                if modo == "aplicar":
                    if not _mover(cloud, f"{p}/{f}", f"{p}/{nuevo}"):
                        L.append(f"- NO se pudo: {p[len(root):]}/{f}")
                        continue
                    try:
                        for ln in [n for n, d in cloud.list(f"{p}/Letras") if not d]:
                            s2, e2 = os.path.splitext(ln)
                            if s2 == stem and e2.lower() in LETRAS and _mover(cloud, f"{p}/Letras/{ln}", f"{p}/Letras/{ns}{e2}"):
                                c["letras"].append([ln, ns + e2])
                    except Exception:
                        pass
                    cambios.append(c)
                usados.add(nuevo.lower())
                hechos += 1
                L.append(f"- {p[len(root):]}: `{f}` → `{nuevo}`")
        L.insert(2, f"{'Cambiados' if modo == 'aplicar' else 'Se cambiarían'}: {hechos}\n")
    txt = "\n".join(L)
    print(txt)
    if modo != "prueba":
        cloud.put(lp, json.dumps({"cambios": cambios, "carpetas": carp}, ensure_ascii=False, indent=1).encode(), "application/json", overwrite=True)
    cloud.put(f"{ag}/nombres.md", txt.encode("utf-8"), "text/markdown", overwrite=True)
    sm = os.environ.get("GITHUB_STEP_SUMMARY")
    if sm:
        open(sm, "a", encoding="utf-8").write(txt)


if __name__ == "__main__":
    modo = (os.environ.get("NOMBRES") or "prueba").strip()
    for cfg in g.load_configs():
        run(cfg, modo)
