#!/usr/bin/env python3
"""ClimaMX — pipeline completo en un solo comando.

    python pipeline.py --demo                 # datos sintéticos, sin internet (prueba de punta a punta)
    python pipeline.py --download             # descarga GHCN-Daily (México) y corre todo
    python pipeline.py --download --start 1981 --end 2024 --per-city 2

Fases (ciclo KDD):
    1 selección → 2 preprocesamiento → 3 transformación → 4 carga al almacén
    → 5 análisis → 6 visualización → 7 reporte
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from climamx import analysis, clean, config as C, demo, download, parse, store, transform, visualize


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def md_table(df: pd.DataFrame, floatfmt: str = "{:.2f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append("" if pd.isna(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--demo", action="store_true", help="usa datos sintéticos (no descarga nada)")
    src.add_argument("--download", action="store_true", help="descarga GHCN-Daily para las ciudades configuradas")
    ap.add_argument("--start", type=int, default=C.START_YEAR)
    ap.add_argument("--end", type=int, default=C.END_YEAR)
    ap.add_argument("--per-city", type=int, default=C.MAX_STATIONS_PER_CITY, help="estaciones por ciudad")
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    C.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ 1. Selección
    if args.demo:
        log("Modo DEMO: generando estaciones y registros sintéticos")
        stations = demo.demo_stations()
        long = demo.demo_long(stations, args.start, args.end)
    else:
        log("Descargando catálogo e inventario de GHCN-Daily")
        st, inv = download.download_catalog()
        stations = download.select_stations(st, inv, start=args.start, end=args.end, per_city=args.per_city)
        if stations.empty:
            log("No se encontraron estaciones MX con los criterios; relaja RADIUS_KM o MIN_YEARS en config.py")
            return 1
        log(f"{len(stations)} estaciones seleccionadas en {stations['city'].nunique()} ciudades")
        parts = []
        for sid in stations["station"]:
            log(f"  descargando {sid}")
            parts.append(parse.read_any(download.download_station(sid)))
        long = pd.concat(parts, ignore_index=True)
    stations.to_csv(C.PROCESSED_DIR / "estaciones.csv", index=False)
    log(f"Registros crudos (formato largo): {len(long):,}")

    # ------------------------------------------------------------------ 2. Preprocesamiento
    daily, report = clean.clean_daily(long, args.start, args.end)
    res = report.attrs["resumen"]
    log(f"Limpieza: {res['descartados_qflag']} con Q_FLAG, {res['fuera_de_rango']} fuera de rango, "
        f"{res['tmin_mayor_que_tmax']} con TMIN>TMAX")
    report.to_csv(C.PROCESSED_DIR / "reporte_limpieza.csv", index=False)

    # ------------------------------------------------------------------ 3. Transformación
    daily = transform.add_features(daily)
    mon = transform.monthly(daily)
    clim = transform.climatology(mon)
    anom = transform.anomalies(mon, clim)
    cm = transform.city_monthly(anom, stations)
    ann = transform.annual(cm)
    sea = transform.seasonal(cm)
    hd = transform.hot_days(daily, stations)
    log(f"Diario: {len(daily):,} filas · mensual: {len(mon):,} · ciudades-año: {len(ann):,}")
    for name, df in {"diario": daily, "mensual": anom, "ciudad_mensual": cm, "ciudad_anual": ann,
                     "ciudad_estacional": sea, "dias_calidos": hd}.items():
        df.to_csv(C.PROCESSED_DIR / f"{name}.csv", index=False)

    # ------------------------------------------------------------------ 5. Análisis
    tt = analysis.trend_table(ann)
    first = (args.start, args.start + 9)
    last = (args.end - 9, args.end)
    dc = analysis.decade_comparison(sea, first, last, "TMEAN")
    rk_season = analysis.season_ranking(dc)
    rk_city = analysis.city_ranking(tt, "TMEAN")
    hd_tt = analysis.trend_table(hd.rename(columns={"hot_days": "HOT"}), variables=("HOT",), use_anom=False)

    # ------------------------------------------------------------------ 4. Carga al almacén
    con = store.connect()
    for name, df in {"estaciones": stations, "diario": daily, "mensual": anom, "ciudad_mensual": cm,
                     "ciudad_anual": ann, "ciudad_estacional": sea, "dias_calidos": hd,
                     "tendencias": tt, "comparacion_decadas": dc}.items():
        n = store.save(con, name, df)
        log(f"  almacén ← {name}: {n:,} filas")
    log(f"Almacén en {C.STORE_PATH}")

    # ------------------------------------------------------------------ 6. Visualización
    if not args.no_figures:
        visualize.city_series_grid(ann, tt, "TMEAN", C.FIG_DIR / "tendencia_tmean_ciudades.png")
        visualize.city_series_grid(ann, tt, "TMIN", C.FIG_DIR / "tendencia_tmin_ciudades.png")
        visualize.season_decade_bars(dc, first, last, C.FIG_DIR / "cambio_por_estacion.png")
        visualize.anomaly_map(stations, tt, "TMEAN", C.FIG_DIR / "mapa_tendencias.png")
        visualize.hot_days_plot(hd, C.FIG_DIR / "dias_calidos.png")
        for city in stations["city"].unique():
            slug = city.lower().replace(" ", "_").replace("é", "e").replace("á", "a").replace("í", "i")
            visualize.anomaly_heatmap(cm, city, "TMEAN", C.FIG_DIR / f"heatmap_{slug}.png")
        log(f"Figuras en {C.FIG_DIR}")

    # ------------------------------------------------------------------ 7. Reporte
    cols = ["ciudad", "variable", "slope_dec", "ci_lo", "ci_hi", "sen_dec", "p_mk", "tendencia", "n"]
    rep = [f"# ClimaMX — resultados ({'DEMO sintético' if args.demo else 'GHCN-Daily'})",
           f"Periodo {args.start}–{args.end}; climatología base {C.BASELINE[0]}–{C.BASELINE[1]}; "
           f"{len(stations)} estaciones en {stations['city'].nunique()} ciudades; "
           f"{len(daily):,} registros diarios procesados en {time.time()-t0:.0f} s.",
           "", "## Tendencia por ciudad (°C/década; slope = regresión lineal con IC 95 %, sen = pendiente de Sen, p = Mann-Kendall)",
           md_table(tt[cols]),
           "", "## Ranking de ciudades por calentamiento de la temperatura media (Sen)", md_table(rk_city),
           "", f"## ¿Qué estación cambia más? Δ TMEAN {last[0]}–{last[1]} vs {first[0]}–{first[1]}", md_table(rk_season),
           "", "## Comparación de decenios por ciudad y estación del año", md_table(dc.drop(columns=["n_inicio", "n_fin"])),
           "", "## Días cálidos (TMAX > p90): tendencia en días/década", md_table(hd_tt[["ciudad", "slope_dec", "ci_lo", "ci_hi", "p_mk", "tendencia"]]),
           "", "## Limpieza", f"Entrada: {res['registros_entrada']:,} registros · Q_FLAG: {res['descartados_qflag']} · "
           f"fuera de rango: {res['fuera_de_rango']} · TMIN>TMAX: {res['tmin_mayor_que_tmax']}",
           md_table(report)]
    out = C.OUTPUT_DIR / "reporte.md"
    out.write_text("\n".join(rep), encoding="utf-8")
    log(f"Reporte en {out}")
    print("\n" + md_table(rk_city))
    return 0


if __name__ == "__main__":
    sys.exit(main())
