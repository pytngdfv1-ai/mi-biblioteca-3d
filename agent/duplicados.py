"""Artistas duplicados (p. ej. «R.E.M.» y «R E M»): detecta carpetas de artista con el mismo nombre normalizado
dentro de un mismo idioma, compara su contenido (temas e imágenes) y marca cuál es la correcta.
Por defecto SOLO informa (_agente3d/duplicados-artistas.md). Con DUPLICADOS=aplicar mueve la sobrante, si todo su
contenido ya está en la correcta, a <Música>/_duplicados/ (reversible; nunca borra). DUPLICADOS=revertir la devuelve.
Correcta = la que se llama igual que el artista en MusicBrainz, luego la que tiene más temas, luego la de nombre más limpio."""
import datetime as dt
import json
import os
import re

import clouds
import discografia as dg

AUDIO = (".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aac")
IMG = (".jpg", ".jpeg", ".png", ".webp")
MAX_GRUPOS = 6      # grupos revisados por corrida (poco a poco)


def clave(nombre):
    return re.sub(r"[^a-z0-9]", "", dg.norm(nombre))


def stem(f):
    b = f.rsplit(".", 1)[0]
    b = re.sub(r"^\s*\d{1,3}\s*[-.)_]*\s*", "", b)
    return re.sub(r"[^a-z0-9]", "", dg.norm(b))


def inventario(cloud, ruta, depth=0, out=None):
    out = {"temas": set(), "imgs": set(), "n": 0} if out is None else out
    if depth > 3:
        return out
    for n, d in cloud.list(ruta):
        if d:
            if not n.startswith(("_", ".")):
                inventario(cloud, f"{ruta}/{n}", depth + 1, out)
        elif n.lower().endswith(AUDIO):
            out["temas"].add(stem(n))
            out["n"] += 1
        elif n.lower().endswith(IMG):
            out["imgs"].add(re.sub(r"[^a-z0-9]", "", n.lower().rsplit(".", 1)[0]))
    return out


def elegir(cands, canon):
    def punt(c):
        limpio = bool(re.fullmatch(r"[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ' &\-!]+", c["nombre"]))
        return (c["nombre"] == canon, c["inv"]["n"], limpio, -len(c["nombre"]))
    return max(cands, key=punt)


def run(cfg, dry):
    modo = (os.environ.get("DUPLICADOS") or "").strip().lower()
    cloud = clouds.make(cfg)
    root = "/" + cfg.get("folder", "").strip("/") if cfg.get("folder") else ""
    ag = f"{root}/_agente3d"
    sp = f"{ag}/duplicados-artistas.json"
    try:
        st = json.loads(cloud.get(sp)) if cloud.exists(sp) else {}
    except Exception:
        st = {}
    movidos = st.setdefault("movidos", [])
    if modo == "revertir":
        for m in list(movidos):
            if cloud.move(m["a"], m["de"]):
                movidos.remove(m)
                print("  devuelto:", m["de"])
        cloud.put(sp, json.dumps(st, ensure_ascii=False, indent=1).encode(), "application/json", overwrite=True)
        return
    arts = dg.artistas(cloud, root)
    try:
        dst = json.loads(cloud.get(f"{ag}/discografia-estado.json")).get("artistas", {})
    except Exception:
        dst = {}
    grupos = {}
    for ruta in arts:
        lang = ruta[len(root):].strip("/").split("/")[0]
        grupos.setdefault((lang, clave(arts[ruta]["nombre"])), []).append(ruta)
    dup = sorted(k for k, v in grupos.items() if len(v) > 1 and k[1])
    hechos = st.setdefault("grupos", {})
    pend = [k for k in dup if f"{k[0]}/{k[1]}" not in hechos or hechos[f"{k[0]}/{k[1]}"].get("modo") != modo][:MAX_GRUPOS]
    print(f"[duplicados] {len(dup)} grupos de artistas repetidos; reviso {len(pend)}")
    for k in pend:
        cands = []
        for ruta in grupos[k]:
            nombre = ruta.rsplit("/", 1)[-1]
            cands.append({"ruta": ruta, "nombre": nombre, "inv": inventario(cloud, ruta)})
        canon = next((dst[c["ruta"]].get("nombre") for c in cands if (dst.get(c["ruta"]) or {}).get("nombre")), None)
        bueno = elegir(cands, canon)
        info = {"correcta": bueno["ruta"], "otras": [], "modo": modo}
        for c in cands:
            if c is bueno:
                continue
            a, b = c["inv"], bueno["inv"]
            comunes = len(a["temas"] & b["temas"])
            contenida = a["temas"] <= b["temas"] and a["imgs"] <= b["imgs"]
            o = {"ruta": c["ruta"], "temas": a["n"], "comparte": f"{comunes}/{len(a['temas'])}", "contenida": contenida, "movida": False}
            if modo == "aplicar" and contenida and not dry:
                destino = f"{root}/_duplicados/{k[0]}/{c['nombre']}"
                if cloud.move(c["ruta"], destino):
                    movidos.append({"de": c["ruta"], "a": destino, "fecha": dt.date.today().isoformat()})
                    o["movida"] = True
            info["otras"].append(o)
        hechos[f"{k[0]}/{k[1]}"] = info
        print("  grupo", k, "->", info["correcta"].rsplit("/", 1)[-1])
    if not dry:
        cloud.put(sp, json.dumps(st, ensure_ascii=False, indent=1).encode(), "application/json", overwrite=True)
        L = ["# Artistas duplicados", "", "Correcta = ✓. «Contenida» = todo lo de la sobrante ya está en la correcta (se puede mover sin perder nada).", ""]
        for g, i in sorted(hechos.items()):
            L.append(f"## {g.split('/')[0]} · {i['correcta'].rsplit('/', 1)[-1]} ✓")
            for o in i["otras"]:
                L.append(f"- Sobra: `{o['ruta'].rsplit('/', 1)[-1]}` · {o['temas']} temas · comparte {o['comparte']}"
                         + (" · contenida" if o["contenida"] else " · tiene cosas que la correcta no tiene (revisar)")
                         + (" · **movida a _duplicados**" if o["movida"] else ""))
            L.append("")
        if not hechos:
            L.append("No hay artistas duplicados.")
        cloud.put(f"{ag}/duplicados-artistas.md", "\n".join(L).encode("utf-8"), "text/markdown", overwrite=True)
