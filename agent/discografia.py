"""Discografía de cada artista (MusicBrainz, gratis): <Idioma>/<Artista>/discografia.json y discografia.md
con todos sus álbumes y EPs (año, tipo, temas) y marca cuáles tienes (✓) y cuáles te faltan.
Va poco a poco: cada corrida usa DISCO_MIN minutos (por defecto 12) y sigue donde quedó.
Nunca borra ni toca tu música; solo escribe esos dos archivos. Estructura: Música/Idioma/Artista/Álbum/Tema.
Variables: DISCO_MIN, DISCO_INCLUIR=vivo,recopilatorio,single (por defecto solo álbumes y EPs de estudio), DISCOGRAFIA=false."""
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import time
import unicodedata

import requests

import clouds

IDIOMAS = {"ingles", "espanol", "english", "spanish"}
UA = "MiBibliotecaAgente3D/1.0 (https://github.com/pytngdfv1-ai/mi-biblioteca-3d)"
S = requests.Session()
S.headers["User-Agent"] = UA
_ultimo = [0.0]


def norm(s):
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"^(the|los|las|el|la) ", "", re.sub(r"\s+", " ", s).strip())
    return s.strip()


def similar(a, b):
    a, b = norm(a), norm(b)
    return bool(a and b) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= .86)


def mb(ruta, params):
    espera = 1.15 - (time.time() - _ultimo[0])
    if espera > 0:
        time.sleep(espera)
    p = dict(params, fmt="json")
    for _ in range(2):
        try:
            r = S.get("https://musicbrainz.org/ws/2/" + ruta, params=p, timeout=25)
            _ultimo[0] = time.time()
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503):
                time.sleep(5)
                continue
            return None
        except Exception:
            _ultimo[0] = time.time()
    return None


def buscar_artista(nombre):
    d = mb("artist", {"query": f'artist:"{nombre}"', "limit": 5})
    c = [a for a in (d or {}).get("artists", []) if a.get("score", 0) >= 95 and similar(a.get("name"), nombre)]
    if not c:
        return None
    return {"mbid": c[0]["id"], "nombre": c[0]["name"], "ambiguo": len(c) > 1}


def discos(mbid, incluir):
    """Álbumes y EPs de estudio (sin en vivo, recopilatorios, etc. salvo que se pidan)."""
    out, off = [], 0
    while off < 400:
        d = mb("release-group", {"artist": mbid, "type": "album|ep" + ("|single" if "single" in incluir else ""), "limit": 100, "offset": off})
        gs = (d or {}).get("release-groups", [])
        for g in gs:
            sec = {x.lower() for x in g.get("secondary-types", [])}
            ok = {"live": "vivo", "compilation": "recopilatorio"}
            if any(k in sec and v not in incluir for k, v in ok.items()):
                continue
            if sec - {"live", "compilation"} - ({"soundtrack"} if "soundtrack" in incluir else set()):
                continue   # remix, demo, mixtape, etc.
            f = g.get("first-release-date") or ""
            out.append({"id": g["id"], "titulo": g["title"], "año": int(f[:4]) if f[:4].isdigit() else None,
                        "tipo": (g.get("primary-type") or "").lower()})
        if len(gs) < 100:
            break
        off += 100
    out.sort(key=lambda x: (x["año"] or 9999, x["titulo"]))
    return out


def temas(rgid):
    d = mb("release", {"release-group": rgid, "inc": "recordings", "status": "official", "limit": 5})
    rel = sorted((d or {}).get("releases", []), key=lambda r: (r.get("date") or "9999"))
    for r in rel:
        t = [tr.get("title") for m in r.get("media", []) for tr in m.get("tracks", []) if tr.get("title")]
        if t:
            return t
    return []


def discogs(nombre):
    """Segunda fuente (solo si hay DISCOGS_TOKEN, gratis en discogs.com/settings/developers): álbumes principales del artista."""
    tok = os.environ.get("DISCOGS_TOKEN")
    if not tok:
        return None
    h = {"Authorization": f"Discogs token={tok}", "User-Agent": UA}
    try:
        time.sleep(1.1)
        d = S.get("https://api.discogs.com/database/search", params={"q": nombre, "type": "artist", "per_page": 5}, headers=h, timeout=25).json()
        a = next((r for r in d.get("results", []) if similar(r.get("title"), nombre)), None)
        if not a:
            return None
        out, pag = [], 1
        while pag <= 4:
            time.sleep(1.1)
            r = S.get(f"https://api.discogs.com/artists/{a['id']}/releases", params={"per_page": 100, "page": pag, "sort": "year"}, headers=h, timeout=25).json()
            for x in r.get("releases", []):
                if x.get("type") == "master" and x.get("role") == "Main":
                    out.append({"id": f"d{x['id']}", "titulo": x["title"], "año": x.get("year") or None, "tipo": "album"})
            if pag >= (r.get("pagination", {}).get("pages") or 1):
                break
            pag += 1
        return {"mbid": f"discogs:{a['id']}", "nombre": a.get("title", nombre), "lista": out} if out else None
    except Exception:
        return None


def artistas(cloud, root):
    """{ruta carpeta artista: {nombre, albums:set(nombres)}} según Música/Idioma/Artista/Álbum."""
    out = {}
    for lang, d in cloud.list(root):
        if not d or norm(lang) not in IDIOMAS:
            continue
        for art, d2 in cloud.list(f"{root}/{lang}"):
            if not d2 or art.startswith(("_", ".")):
                continue
            ruta = f"{root}/{lang}/{art}"
            albs = {a for a, d3 in cloud.list(ruta) if d3 and not a.startswith(("_", "."))}
            out[ruta] = {"nombre": art.strip(), "albums": albs}
    return out


def _limpio(a):
    return re.sub(r"^\s*(\(?\d{4}\)?\s*[-–.]\s*)", "", a).strip()


def armar(nombre, info, lista, tem, mis):
    mis_n = [_limpio(a) for a in mis]
    albumes = []
    for g in lista:
        tengo = any(similar(g["titulo"], a) for a in mis_n)
        albumes.append({"titulo": g["titulo"], "año": g["año"], "tipo": g["tipo"], "tengo": tengo, "temas": tem.get(g["id"], [])})
    return {"artista": info["nombre"] or nombre, "mbid": info["mbid"], "fuente": "MusicBrainz",
            "actualizado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
            "tienes": sum(a["tengo"] for a in albumes), "total": len(albumes), "albumes": albumes}


def a_md(d):
    L = [f"# Discografía: {d['artista']}", "", f"Tienes {d['tienes']} de {d['total']} (✓ lo tienes · ✗ te falta). Fuente: MusicBrainz, {d['actualizado']}.", ""]
    for a in d["albumes"]:
        L.append(f"## {'✓' if a['tengo'] else '✗'} {a['titulo']}" + (f" ({a['año']})" if a["año"] else "") + f" · {a['tipo']}")
        L += [f"{i}. {t}" for i, t in enumerate(a["temas"], 1)]
        L.append("")
    return "\n".join(L)


def run(cfg, dry):
    if os.environ.get("DISCOGRAFIA", "true") == "false":
        return
    incluir = {x.strip() for x in (os.environ.get("DISCO_INCLUIR") or "").lower().split(",") if x.strip()}
    limite = int(os.environ.get("DISCO_MIN") or 12) * 60
    cloud = clouds.make(cfg)
    root = "/" + cfg.get("folder", "").strip("/") if cfg.get("folder") else ""
    sp = f"{root}/_agente3d/discografia-estado.json"
    try:
        st = json.loads(cloud.get(sp)) if cloud.exists(sp) else {}
    except Exception:
        st = {}
    st.setdefault("artistas", {})
    arts = artistas(cloud, root)
    print(f"[discografía] {len(arts)} artistas")
    t0 = time.time()
    tocados = 0
    # primero los que nunca se hicieron
    for ruta in sorted(arts, key=lambda r: (r in st["artistas"] and st["artistas"][r].get("hecho", False), r)):
        a = arts[ruta]
        e = st["artistas"].setdefault(ruta, {})
        if time.time() - t0 > limite:
            break
        if e.get("sin"):       # no se encontró con seguridad: no se adivina
            continue
        if "mbid" not in e:
            info = buscar_artista(a["nombre"])
            alt = None if info else discogs(a["nombre"])
            if alt:
                e.update({"mbid": alt["mbid"], "nombre": alt["nombre"], "lista": alt["lista"], "temas": {}, "fuente": "Discogs"})
                info = e
            if not info:
                e["sin"] = True
                print("  sin coincidencia segura:", a["nombre"])
                continue
            if info is not e:
                e.update(info)
        if "lista" not in e:
            e["lista"] = discos(e["mbid"], incluir)
            e["temas"] = {}
        for g in e["lista"]:
            if g["id"] in e["temas"]:
                continue
            if time.time() - t0 > limite:
                break
            e["temas"][g["id"]] = temas(g["id"]) if not str(g["id"]).startswith("d") else []
        e["hecho"] = all(g["id"] in e["temas"] for g in e["lista"])
        d = armar(a["nombre"], e, e["lista"], e["temas"], a["albums"])
        huella = hashlib.sha1(json.dumps([x["tengo"] for x in d["albumes"]] + [len(e["temas"])]).encode()).hexdigest()
        if huella != e.get("huella") and not dry:
            ok1 = cloud.put(f"{ruta}/discografia.json", json.dumps(d, ensure_ascii=False, indent=1).encode(), "application/json", overwrite=True)
            ok2 = cloud.put(f"{ruta}/discografia.md", a_md(d).encode("utf-8"), "text/markdown", overwrite=True)
            if ok1 and ok2:
                e["huella"] = huella
                tocados += 1
                print(f"  {a['nombre']}: {d['tienes']}/{d['total']}" + ("" if e["hecho"] else " (parcial)"))
    if not dry:
        cloud.put(sp, json.dumps(st, ensure_ascii=False).encode(), "application/json", overwrite=True)
        todos = []
        for ruta, a in arts.items():
            e = st["artistas"].get(ruta) or {}
            if not e.get("lista"):
                continue
            d = armar(a["nombre"], e, e["lista"], e.get("temas", {}), a["albums"])
            d["parcial"] = not e.get("hecho", False)
            d.pop("mbid", None)
            todos.append(d)
        cloud.put(f"{root}/_agente3d/discografias.json", json.dumps({"actualizado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"), "artistas": todos},
                                                                  ensure_ascii=False).encode(), "application/json", overwrite=True)
    print(f"[discografía] archivos escritos esta corrida: {tocados}")
