import coveralia as c, re
for a, al in [("Fito Páez","No Sé Si Es Baires O Madrid"),("Los Redonditos de Ricota","La mosca y la sopa"),("No Te Va Gustar","Otras Canciones"),("Nirvana","Nevermind")]:
    for ar in [a]:
        for v in c._variantes(al):
            url = f"https://www.coveralia.com/discos/{c._slug(ar)}-{c._slug(v)}.php"
            r = c._get(url); print(url, r.status_code)
            if r.status_code == 200:
                m = re.search(r'href="/caratulas/([^"]+-Trasera)\.php"', r.text); print(" link:", m and m.group(1))
                if m:
                    img = f"https://images.coveralia.com/audio/n/{m.group(1)}.jpg"
                    ri = c._get(img); print(" img", ri.status_code, len(ri.content), ri.headers.get("content-type"), ri.content[:4])
                break
