import coveralia as c, re
r = c._get("https://www.coveralia.com/discos/fito_paez-no_se_si_es_baires_o_madrid.php")
t = r.text; i = t.find("-Trasera.php"); print(t[i-250:i+350])
m = re.search(r'/caratulas/([^"]+-Trasera)\.php"[^>]*>\s*<img[^>]+src="([^"]+)"', t); print(m and m.groups())
for u in ["https://images.coveralia.com/audio/f/Fito-Paez-No-Se-Si-Es-Baires-O-Madrid-Trasera.jpg",
          "https://images.coveralia.com/audio/n/Fito-Paez-No-Se-Si-Es-Baires-O-Madrid-Frontal.jpg",
          "https://images.coveralia.com/audio/n/Fito-Paez-No-Se-Si-Es-Baires-O-Madrid-Trasera.jpg"]:
    ri = c._get(u); print(u, ri.status_code, len(ri.content))
r = c._get("https://www.coveralia.com/caratulas/Fito-Paez-No-Se-Si-Es-Baires-O-Madrid-Frontal.php"); print(r.status_code, re.findall(r'(https?:[^"\']*images\.coveralia[^"\']*)', r.text)[:6], "Fatal" in r.text)
