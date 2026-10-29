# ClimaMX — tendencias de calentamiento y cambio estacional en ciudades de México

Pipeline en Python del proyecto integrador (Optativa III: Ciencia de Datos, UNE).
Descarga registros diarios de **NOAA GHCN-Daily** para 12 ciudades mexicanas, los limpia,
los agrega a series mensuales y anuales, los carga a un almacén de series temporales
(SQLite) y calcula la tendencia de calentamiento (°C/década) y el cambio por estación del año.

Equipo: Juan Pablo Rodríguez Torres · Alfredo Santos Gutiérrez · Bryan Salazar


**Página en línea:** https://bambam2907.github.io/climamx/ (GitHub Pages sirve la carpeta `docs/`)

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso (un solo comando)

```bash
python pipeline.py --demo        # datos sintéticos, sin internet: prueba todo el flujo en ~20 s
python pipeline.py --download    # datos reales de GHCN-Daily (tarda según la red)
python pipeline.py --download --start 1981 --end 2024 --per-city 2
streamlit run app.py             # app interactiva sobre los resultados
```

Salidas:

| Ruta | Qué contiene |
|---|---|
| `data/raw/` | catálogo, inventario y archivos crudos por estación (CSV de AWS o `.dly` de NCEI) |
| `data/processed/*.csv` | estaciones elegidas, reporte de limpieza, diario, mensual, por ciudad (mensual/anual/estacional), días cálidos |
| `data/climamx.sqlite` | almacén de series temporales (tablas `diario`, `mensual`, `ciudad_anual`, `tendencias`, …) |
| `output/reporte.md` | tablas de tendencias, ranking de ciudades, estación que más cambia, comparación de decenios |
| `output/figuras/` | series con tendencia, barras por estación, mapa de tendencias, días cálidos, heatmaps por ciudad |

Consultar el almacén:

```bash
sqlite3 data/climamx.sqlite "SELECT ciudad, variable, ROUND(sen_dec,2) AS c_por_decada, ROUND(p_mk,3) AS p FROM tendencias WHERE variable='TMEAN' ORDER BY sen_dec DESC;"
```

## App interactiva (Streamlit)

```bash
streamlit run app.py
```

Abre `http://localhost:8501` con un explorador por ciudad y variable: serie anual con pendiente de
Sen, cambio por estación del año, heatmap de anomalías, días cálidos, ranking, mapa y tablas
descargables. Lee `data/climamx.sqlite`; si no existe, la app ofrece generar los datos de
demostración con un botón. Si vuelves a correr el pipeline, la app recarga sola los datos.

## Página web interactiva

`docs/index.html` es una página autocontenida (sin servidor) con el explorador de resultados:
series anuales con tendencia, cambio por estación, heatmap, días cálidos, ranking y mapa.
Los datos van incrustados en el HTML; después de correr el pipeline se actualizan con:

```bash
python export_web.py --inject docs/index.html
```

## Auditoría de la página

`auditoria/auditar.py` corre tres auditores sobre `docs/index.html` (visual y responsivo, accesibilidad con
axe-core, lógica e interacción) y `auditoria/unit.js` prueba las funciones puras del script. Necesitan
Playwright con Chromium y `axe-core` (npm). El reporte de diseño está en `docs/DISENO.md`.

## Cómo mapea al ciclo KDD

| Fase (semana) | Módulo | Qué hace |
|---|---|---|
| Selección (1) | `download.py` | filtra estaciones `MX*` con TMAX/TMIN y ≥30 años; elige las más cercanas a cada ciudad |
| Preprocesamiento (4) | `parse.py`, `clean.py` | lee CSV/.dly; descarta `Q_FLAG`; décimas → °C/mm; rango físico; TMIN>TMAX; huecos ≤3 días |
| Transformación (4·6) | `transform.py` | TMEAN, rango diurno, estación del año; mensual → anual; climatología 1971–2000 y anomalías; días cálidos |
| Carga (6·7) | `store.py` | SQLite indexado por serie y fecha |
| Análisis (2·3·5) | `analysis.py` | regresión lineal (IC 95 %), Mann-Kendall, pendiente de Sen, t de Welch entre decenios |
| Visualización (5) | `visualize.py` | series con tendencia, barras por estación, heatmap año×mes, mapa de tendencias |

Los parámetros (ciudades, periodo, umbrales) están en `climamx/config.py`.

## Decisiones metodológicas

- **Anomalías, no absolutos, para la tendencia.** Cada estación se compara contra su propia
  climatología 1971–2000 por mes; así se pueden promediar varias estaciones por ciudad sin que
  una estación más alta o más fría sesgue la serie.
- **Un mes vale si tiene ≥80 % de días; un año si tiene ≥11 meses.** Los meses incompletos se
  marcan como faltantes en vez de rellenarlos.
- **Sen + Mann-Kendall como resultado principal.** Son robustos a atípicos y no suponen
  normalidad; la regresión lineal se reporta como comparación.
- **Primer vs último decenio por estación del año** con t de Welch (varianzas distintas).

## Estado

- Probado de punta a punta en modo `--demo` (datos sintéticos con tendencia conocida; el análisis
  la recupera). El modo `--download` usa los formatos documentados de NOAA, pero conviene correrlo
  y revisar `data/processed/reporte_limpieza.csv` para ajustar `RADIUS_KM`, `MIN_YEARS` o
  `MAX_STATIONS_PER_CITY` según la cobertura real de cada ciudad.
- Pendiente: validar cruzando con Berkeley Earth (Kaggle) y, si se quiere, mapa con contorno del
  país usando `geopandas`.


## Publicar en GitHub Pages

La página es `docs/index.html`: un solo archivo con los datos incrustados, sin servidor.

1. Sube este repositorio a GitHub (público).
2. En el repo: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, rama `main`, carpeta `/docs`, **Save**.
3. En uno o dos minutos queda en `https://bambam2907.github.io/climamx/`.

Para actualizarla con datos reales: `python pipeline.py --download`, luego
`python export_web.py --inject docs/index.html`, y haz commit y push de `docs/index.html`.
