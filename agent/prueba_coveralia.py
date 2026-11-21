import coveralia as c
for a, al in [("Fito Páez","No Sé Si Es Baires O Madrid"),("No Te Va Gustar","Otras Canciones"),("Nirvana","Nevermind"),("Los Redonditos de Ricota","La mosca y la sopa")]:
    b, i = c.trasera(a, al); print(a, al, "->", len(b) if b else None, i)
