import re, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; MiBibliotecaAgente/1.0)", "Referer": "https://www.coveralia.com/"}
def g(u, **k):
    try:
        r = requests.get(u, headers=H, timeout=30, **k)
        print("\n##", u, r.status_code, len(r.content), r.headers.get("content-type")); return r
    except Exception as e:
        print("\n##", u, "ERROR", e)
r = g("https://www.coveralia.com/mostrar.php?bus=metallica+black&Boton=")
if r:
    print(re.findall(r'href="(/discos/[^"]+)"', r.text)[:10]); print(re.findall(r'href="(/[a-z-]+/[^"]+\.php)"', r.text)[:15])
r = g("https://www.coveralia.com/caratulas/Nirvana-Nevermind-Trasera.php"); print(r.text[:1800])
r = g("https://images.coveralia.com/audio/n/Nirvana-Nevermind-Trasera.jpg"); print(r.content[:4])
r = g("https://www.coveralia.com/discos/metallica-metallica_black_album.php"); 
r = g("https://www.coveralia.com/discos/metallica-metallica.php")
if r and r.status_code==200: print(re.findall(r'href="(/caratulas/[^"]+)"', r.text)[:10])
