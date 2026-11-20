# Mi Biblioteca 3D

Agente gratuito (GitHub Actions) que genera **objetos 3D** para la app *Mi Biblioteca* y los deja en la carpeta
de cada álbum en tu nube. La app solo los muestra; no dibuja nada en el teléfono.

Repo público = minutos de Actions ilimitados. Tus claves van como *secrets* (no se ven). Aquí no hay música, solo código.

## Qué genera por álbum

| Caso | Objetos |
|---|---|
| Álbum **con contraportada** en su carpeta | LP 12", vinilo 7" y cassette |
| Álbum **sin contraportada** | Solo cassette (trasera generada con la lista de temas). Queda en «Esperan contraportada» |
| **Tema suelto** (hasta 3 temas o carpeta «sueltos/singles») | Vinilo 7" y cassette, con trasera generada |

Cada objeto en dos vistas, como hoja de 16 cuadros girando (4×4, 300 px cada uno):

- `objeto3d-lp-cerrado.webp` · `objeto3d-lp-abierto.webp`
- `objeto3d-7-cerrado.webp` · `objeto3d-7-abierto.webp`
- `objeto3d-cassette-cerrado.webp` · `objeto3d-cassette-abierto.webp`
- `objeto3d.json` (manifiesto: cuadros, columnas, huella, si la trasera es generada)

**Cerrado:** funda con portada y contraportada (disco dentro) / estuche transparente con la portada.
**Abierto:** el disco (o el cassette) fuera, descansando junto a la funda o el estuche.

Usa de la carpeta del álbum: portada (`cover`, `folder`, `front`, `portada`…, prefiere `hd`), contraportada
(`back`, `contraportada`, `trasera`), `sello.*` (foto del sello del disco) y `cassette.*` (foto del cassette),
estos últimos los deja el otro agente. También lee `album.json`.

## Qué salta y qué rehace

Guarda una huella (portada, trasera, sello, cassette, datos del álbum, versión del diseño) en `objeto3d.json`.
Si coincide, lo salta («ya hecho»). Si cambió algo, lo rehace. Cuando agregas la contraportada a un álbum que
esperaba, la próxima corrida le hace el LP y el 7".

## Informe

`_agente3d/objetos.md` en tu nube: creados, ya hechos, esperan contraportada, sin portada, errores y pendientes.

## Configuración

Secrets del repo (Settings → Secrets and variables → Actions): `KOOFR_EMAIL`, `KOOFR_APP_PASSWORD`,
`KOOFR_FOLDER` (o `CLOUDS` con varias nubes, igual que el otro agente).

Corre 4 veces al día (cron). Manualmente: *Actions → Objetos 3D → Run workflow*:

- `demo=true`: genera dos álbumes de muestra sin tocar tu nube (sin secretos). Descarga el artefacto `salida`.
- `dry_run=true`: procesa tu nube pero deja los archivos en el artefacto y no escribe nada.
- `force=true`: rehace todo.

Si cambias el diseño de los objetos, sube `VERSION` en `agent/generar3d.py` para rehacer todos.

## Créditos

Los objetos se construyen por código con [three.js](https://threejs.org) (MIT), sin modelos de terceros.
Los modelos 3D con licencia CC que usa la app (créditos completos en su pantalla *Acerca de*) no se usan aquí.
