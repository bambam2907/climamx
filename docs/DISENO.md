# ClimaMX — reporte de diseño y auditoría de la página

## Skills aplicadas

| Skill | Qué se usó | Qué no se pudo correr |
|---|---|---|
| **design-taste-frontend (tasteskill v2)** | `draw.mjs` repartió la dirección; se construyó con sus reglas de casa; `lint.mjs` e `inspect.mjs` (1440/768/390) como gate; crítica con `critique.md` | `assets.mjs` (colecciones abiertas de imágenes) no tiene red en este entorno: la página no usa fotografías |
| **impeccable** | `craft-floor.md` (piso de calidad, bans), `audit.md` (dimensiones y severidades P0–P3), modo Persuade/Read | El lanzador `scripts/impeccable` descarga un binario; no se ejecutó. Se leyeron las referencias directamente |
| **ui-ux-pro-max** | `search.py --design-system` y la tabla de prioridades (contraste 4.5:1, 44 px, sin scroll horizontal, reduced-motion, gráficas con leyenda y tooltips) | El sistema sugerido (verde biofílico, Exo/Roboto Mono) se descartó: la marca ya fija navy/rojo y las reglas de casa prohíben monospace fuera de código |

## Dirección repartida

- **Dirección:** `one-motif` (One motif), semilla 1579200300, sector education, tono technical, `--keep palette,type`.
- **Idea:** *En esta página, las 54 anomalías anuales de cada ciudad (los datos mismos) se vuelven el motivo: la franja.* Es la pared del hero, las miniaturas dentro del enunciado, cada fila del ranking, el diagrama «muchos en uno», las tejas de cifras y la marca del pie construida con bloques.
- **Lo vivo:** elegir tu ciudad en la primera pantalla; cambia el titular, la pared de franjas, la gráfica, el ranking y el mapa. Funciona con pulgar (select nativo), con teclado y sin JavaScript (la ciudad por defecto se pre-renderiza con `export_web.py`).
- **Hero:** la hoja repartió «Tabbed folder stack»; se construyó con la composición propia de la dirección (el motivo a escala enorme, recortado por el viewport) porque la precedencia de la hoja pone la dirección por encima del blueprint del hero y la pila de folders metía un segundo motivo.
- **Secciones y palabra de layout:** hero=pared · enunciado=statement con miniaturas · explorador=split con índice y vista previa · cómo se hizo=banda con diagrama · salidas=cuadrícula asimétrica de figuras reales · cifras=tejas escalonadas · método=panel inset con el mapa dibujado · equipo=banda · pie=marca construida.
- **Movimiento:** firma «índice con vista previa» (240 ms); entradas por sección escalonadas 80 ms; las franjas del hero suben al cargar y al cambiar de ciudad; todo sólo transform/opacity y apagado con `prefers-reduced-motion`.
- **Imágenes:** 4 figuras raster reales que genera el pipeline (en modo demo, con datos sintéticos; al correr `--download` se regeneran con datos reales). No hay fotografías ni video: no existe un clip honesto del sujeto y las colecciones abiertas no se pudieron consultar.

## Gate (tasteskill)

| | Antes (página anterior) | Después |
|---|---|---|
| `lint.mjs` | 14 FAIL, 9 WARN | 0 FAIL, 0 WARN |
| `inspect.mjs` | 7 FAIL, 10 WARN | 0 FAIL, 1 WARN (`no-footage`, defendido arriba) |

## Crítica (ronda final)

```
ROUND 3
Seen in one second: una pared de franjas rojas y azules bajo un nombre de ciudad y una cifra.
Idea: los datos de cada ciudad son el motivo de toda la página.
Live thing: elegir tu ciudad y ver su pared, su cifra y su gráfica.
Layout words by section: hero=pared / enunciado=statement / explorador=split+índice / cómo=banda / salidas=grid / cifras=tejas / método=panel / equipo=banda / pie=marca
Scores: design 7.5 · usability 8 · creativity 7.5 · content 8 → overall 7.7
Caps applied: fewer than four photographs (design ≤ 6.5 si se cuentan sólo fotos; las cuatro figuras son salida real del producto, no fotos).
Top three problems:
1. La pared del hero en móvil queda corta cuando está el aviso de datos demo (mobile-fold). Desaparece con datos reales.
2. Las figuras del pipeline traen su propio estilo (fondo blanco, tipografía de matplotlib); valdría exportarlas con la paleta de la página.
3. El mapa en 320 px es pequeño; las zonas de toque sí cumplen 44 px pero las etiquetas se encogen.
```

## Auditoría con tres roles (`auditoria/auditar.py`, `auditoria/unit.js`)

| Auditor | Qué revisa | Resultado final |
|---|---|---|
| Visual y responsivo | desborde horizontal a 320/390/768/1024/1440, objetivos táctiles ≥ 44 px, texto recortado, titulares ≤ 2 líneas, plato pegajoso sin encimarse, capturas claro/oscuro | 0 hallazgos (se corrigieron 41: zonas de toque del mapa, marca de 44 px, dos titulares largos) |
| Accesibilidad | axe-core WCAG 2.x A/AA en 1440/390 y tema oscuro, un solo h1 y orden de niveles, landmarks, orden de tabulación y anillo de foco en 40 elementos, label del select, estados `aria-pressed`/`aria-current`, SVG con `aria-label`, `alt` en imágenes, reduced-motion, texto al 200 % | 0 hallazgos (se corrigió: el aviso quedaba fuera de los landmarks) |
| Lógica | JSON vs SQLite (Sen por ciudad y variable, longitudes, heatmap 54×12, anomalía base ≈ 0), estático vs dinámico, 12 ciudades × 3 variables, 4 vistas, vista previa con hover/foco y restauración, Enter en filas y mapa, tabla perezosa, deep link `#ciudad=`, localStorage, tema, sin NaN/undefined, sin errores de consola; 26 pruebas unitarias | 0 hallazgos (se corrigió un bug real: la significancia leía `t.p` en vez de `t.p_mk`) |

## Pendientes antes de entregar

- Correr `python pipeline.py --download` y `python export_web.py --inject docs/index.html` para sustituir los datos sintéticos; el aviso amarillo desaparece solo.
- Las fuentes se cargan de Google Fonts; sin red se usa el respaldo (Segoe UI/Arial).
