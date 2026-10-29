"""Datos sintéticos para probar el pipeline de punta a punta sin descargar nada.

Imita el formato largo crudo de GHCN-Daily (décimas de °C / mm, banderas) y
mete a propósito los problemas que la limpieza debe resolver: días faltantes,
meses enteros perdidos, estaciones que arrancan tarde o cierran antes,
registros con Q_FLAG, TMIN > TMAX y errores de captura ×10.

Cada ciudad recibe una tendencia conocida (°C/década) para poder verificar
que el análisis la recupera. NO son datos reales de México.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

# (temperatura media anual, amplitud estacional, rango diurno, tendencia °C/década en TMIN, en TMAX)
CITY_PARAMS = {
    "Ciudad de México": (16.5, 3.0, 13.0, 0.35, 0.20),
    "Guadalajara": (20.5, 4.0, 15.0, 0.30, 0.22),
    "Monterrey": (22.5, 7.5, 11.0, 0.40, 0.30),
    "Mérida": (26.5, 3.5, 11.0, 0.25, 0.15),
    "Hermosillo": (25.0, 9.5, 14.0, 0.45, 0.35),
    "Chihuahua": (18.5, 9.0, 14.0, 0.30, 0.25),
    "Mexicali": (23.0, 11.0, 15.0, 0.50, 0.40),
    "Culiacán": (25.0, 5.0, 13.0, 0.28, 0.18),
    "San Luis Potosí": (18.0, 5.0, 14.0, 0.22, 0.15),
    "Veracruz": (25.5, 4.0, 7.0, 0.20, 0.12),
    "Oaxaca": (20.5, 2.5, 14.0, 0.15, 0.10),
    "Acapulco": (27.5, 1.5, 8.0, 0.10, 0.05),
}


def demo_stations(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i, (city, (lat, lon)) in enumerate(C.CITIES.items()):
        for k in range(2):
            rows.append({"station": f"MXDEMO{i:02d}{k}", "name": f"{city.upper()} DEMO {k+1}",
                         "city": city, "lat": lat + rng.normal(0, 0.1), "lon": lon + rng.normal(0, 0.1),
                         "elev": float(rng.integers(0, 2300)), "dist_km": float(rng.uniform(2, 30)),
                         "first_year": C.START_YEAR, "last_year": C.END_YEAR,
                         "overlap": C.END_YEAR - C.START_YEAR + 1})
    return pd.DataFrame(rows)


def demo_long(stations: pd.DataFrame, start: int = C.START_YEAR, end: int = C.END_YEAR, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(f"{start}-01-01", f"{end}-12-31", freq="D")
    doy = dates.dayofyear.values
    yrs = (dates.year.values - start) / 10.0
    frames = []
    for _, st in stations.iterrows():
        tmean, amp, dtr, tr_min, tr_max = CITY_PARAMS[st["city"]]
        season = amp * np.cos(2 * np.pi * (doy - 200) / 365.25)
        noise = _ar1(len(dates), 0.7, 1.6, rng)
        tmax = tmean + dtr / 2 + season + tr_max * yrs + noise + rng.normal(0, 0.5)
        tmin = tmean - dtr / 2 + 0.8 * season + tr_min * yrs + noise * 0.8 + rng.normal(0, 0.5)
        wet = np.isin(dates.month.values, [6, 7, 8, 9])
        rain_p = np.where(wet, 0.45, 0.06)
        prcp = np.where(rng.random(len(dates)) < rain_p, rng.exponential(9, len(dates)), 0.0)

        d = pd.DataFrame({"date": dates, "TMAX": tmax, "TMIN": tmin, "PRCP": prcp})
        # --- suciedad deliberada ---------------------------------------------------
        d.loc[rng.random(len(d)) < 0.03, ["TMAX", "TMIN"]] = np.nan             # días sueltos
        for _ in range(rng.integers(2, 6)):                                       # meses enteros
            y, m = rng.integers(start, end + 1), rng.integers(1, 13)
            d.loc[(d["date"].dt.year == y) & (d["date"].dt.month == m), ["TMAX", "TMIN", "PRCP"]] = np.nan
        if st["station"].endswith("1") and rng.random() < 0.5:                   # cierra o abre tarde
            cut = rng.integers(start + 35, end - 3)
            if rng.random() < 0.5:
                d.loc[d["date"].dt.year > cut, ["TMAX", "TMIN", "PRCP"]] = np.nan
            else:
                d.loc[d["date"].dt.year < start + 12, ["TMAX", "TMIN", "PRCP"]] = np.nan
        inv = rng.random(len(d)) < 0.002                                          # TMIN > TMAX
        d.loc[inv, ["TMAX", "TMIN"]] = d.loc[inv, ["TMIN", "TMAX"]].values
        x10 = rng.random(len(d)) < 0.0005                                         # error de captura ×10
        d.loc[x10, "TMAX"] = d.loc[x10, "TMAX"] * 10

        long = d.melt(id_vars="date", var_name="element", value_name="value").dropna()
        long["value"] = np.round(long["value"] * 10).astype(int)                  # décimas, como NOAA
        long["station"] = st["station"]
        long["mflag"] = np.nan
        long["qflag"] = pd.Series(np.where(rng.random(len(long)) < 0.002, "X", None),
                                  index=long.index, dtype=object)              # falló control de calidad
        long["sflag"] = "N"
        frames.append(long)
    out = pd.concat(frames, ignore_index=True)
    return out[["station", "date", "element", "value", "mflag", "qflag", "sflag"]]


def _ar1(n: int, phi: float, sigma: float, rng) -> np.ndarray:
    e = rng.normal(0, sigma, n)
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x
