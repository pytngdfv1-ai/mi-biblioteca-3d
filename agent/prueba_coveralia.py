import re, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; MiBibliotecaAgente/1.0)"}
def g(u):
    try:
        r = requests.get(u, headers=H, timeout=30)
        print("\n##", u, r.status_code, len(r.text)); return r
    except Exception as e:
        print("\n##", u, "ERROR", e)
r = g("https://www.coveralia.com/robots.txt")
if r: print(r.text[:1500])
for u in ["https://www.coveralia.com/discos/the_weeknd-dawn_fm.php",
          "https://www.coveralia.com/buscador.php?texto=metallica+black&tipo=discos",
          "https://www.coveralia.com/buscar.php?q=metallica+black"]:
    r = g(u)
    if r:
        t = r.text
        print([m for m in re.findall(r'href="([^"]+)"', t) if any(k in m.lower() for k in ("trasera","back","caratula","cd","discos/"))][:25])
        print(re.findall(r'<img[^>]+src="([^"]+)"', t)[:15])
        i = t.lower().find("trasera"); print(t[max(0,i-300):i+300] if i>=0 else "sin 'trasera'")
