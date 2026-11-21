import re, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; MiBibliotecaAgente/1.0)"}
def g(u):
    try:
        r = requests.get(u, headers=H, timeout=30)
        print("\n##", u, r.status_code, len(r.text)); return r
    except Exception as e:
        print("\n##", u, "ERROR", e)
r = g("https://www.coveralia.com/")
for f in re.findall(r"<form[^>]*>.*?</form>", r.text, re.S)[:3]:
    print(f[:700])
r = g("https://www.coveralia.com/discos/nirvana-nevermind.php")
t = r.text
print(sorted(set(re.findall(r'href="(/caratulas/[^"]+)"', t)))[:20])
print(sorted(set(re.findall(r'(?:src|href)="([^"]*images\.coveralia[^"]*)"', t)))[:12])
for u in ["https://www.coveralia.com/caratulas/Nirvana-Nevermind-Trasera.php","https://www.coveralia.com/caratulas/Nirvana-Nevermind-Frontal.php"]:
    r = g(u)
    if r:
        print(sorted(set(re.findall(r'(?:src|href|content)="([^"]*\.(?:jpg|jpeg|png)[^"]*)"', r.text)))[:12])
for q in ["https://www.coveralia.com/buscar/?q=nirvana+nevermind","https://www.coveralia.com/buscador/?q=nirvana+nevermind","https://www.coveralia.com/search.php?q=nirvana+nevermind"]:
    r = g(q)
    if r and r.status_code == 200: print(re.findall(r'href="(/discos/[^"]+)"', r.text)[:8])
