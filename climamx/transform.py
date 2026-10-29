"""Transformación (fase KDD): variables derivadas y agregación diario → mensual → anual.

Pasos:
    1. TMEAN, rango diurno, año, mes, estación del año, década.
    2. Agregado mensual por estación (un mes vale con ≥ 80 % de días válidos).
    3. Climatología base 1971–2000 por estación y mes → anomalías.
    4. Promedio por ciudad (varias estaciones) y agregados anual y estacional.
    5. Días cálidos: TMAX > percentil 90 de la climatología base.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

VARS = ["TMAX", "TMIN", "TMEAN", "DTR"]


def add_features(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["TMEAN"] = (d["TMAX"] + d["TMIN"]) / 2
    d["DTR"] = d["TMAX"] - d["TMIN"]
    d["year"] = d["date"].dt.year
    d["month"] = d["date"].dt.month
    d["season"] = d["month"].map(C.SEASONS)
    d["season_year"] = d["year"] + (d["month"] == 12).astype(int)   # diciembre cuenta para el invierno siguiente
    d["decade"] = (d["year"] // 10) * 10
    return d


def monthly(daily_feat: pd.DataFrame, min_frac: float = C.MIN_MONTH_FRAC) -> pd.DataFrame:
    g = daily_feat.groupby(["station", "year", "month"])
    m = g[VARS].mean()
    m["n_valid"] = g["TMEAN"].count()
    m["n_days"] = g["date"].count()
    m["valid"] = m["n_valid"] >= min_frac * m["n_days"]
    m.loc[~m["valid"], VARS] = np.nan
    n_prcp = g["PRCP"].count()
    m["PRCP"] = g["PRCP"].sum(min_count=1).where(n_prcp >= min_frac * m["n_days"])
    return m.reset_index()


def climatology(monthly_df: pd.DataFrame, baseline=C.BASELINE,
                min_years: int = C.MIN_BASELINE_YEARS) -> pd.DataFrame:
    b = monthly_df[(monthly_df["year"] >= baseline[0]) & (monthly_df["year"] <= baseline[1]) & monthly_df["valid"]]
    g = b.groupby(["station", "month"])
    clim = g[VARS].mean()
    clim["n_years"] = g["year"].count()
    clim = clim[clim["n_years"] >= min_years]
    return clim.rename(columns={v: f"{v}_clim" for v in VARS}).reset_index()


def anomalies(monthly_df: pd.DataFrame, clim: pd.DataFrame) -> pd.DataFrame:
    """Anomalía = valor mensual − climatología del mismo mes en la misma estación."""
    a = monthly_df.merge(clim, on=["station", "month"], how="inner")
    for v in VARS:
        a[f"{v}_anom"] = a[v] - a[f"{v}_clim"]
    return a


def city_monthly(anom: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Promedia las estaciones de cada ciudad, mes a mes (absolutos y anomalías)."""
    cols = VARS + [f"{v}_anom" for v in VARS] + ["PRCP"]
    df = anom.merge(stations[["station", "city"]], on="station")
    g = df.groupby(["city", "year", "month"])
    cm = g[cols].mean()
    cm["n_stations"] = g["TMEAN"].count()
    cm = cm[cm["n_stations"] > 0].reset_index()
    cm["season"] = cm["month"].map(C.SEASONS)
    cm["season_year"] = cm["year"] + (cm["month"] == 12).astype(int)
    return cm


def annual(cm: pd.DataFrame, min_months: int = C.MIN_MONTHS_PER_YEAR) -> pd.DataFrame:
    cols = VARS + [f"{v}_anom" for v in VARS]
    g = cm.groupby(["city", "year"])
    a = g[cols].mean()
    a["n_months"] = g["month"].count()
    a["PRCP"] = g["PRCP"].sum(min_count=12)          # lluvia anual sólo con los 12 meses
    a.loc[a["n_months"] < min_months, cols] = np.nan
    return a.reset_index()


def seasonal(cm: pd.DataFrame) -> pd.DataFrame:
    cols = VARS + [f"{v}_anom" for v in VARS]
    g = cm.groupby(["city", "season", "season_year"])
    s = g[cols].mean()
    s["n_months"] = g["month"].count()
    s.loc[s["n_months"] < 3, cols] = np.nan
    s["decade"] = (s.index.get_level_values("season_year") // 10) * 10
    return s.reset_index()


def hot_days(daily_feat: pd.DataFrame, stations: pd.DataFrame, baseline=C.BASELINE) -> pd.DataFrame:
    """Días por año con TMAX por encima del percentil 90 de la climatología base, promedio por ciudad."""
    base = daily_feat[(daily_feat["year"] >= baseline[0]) & (daily_feat["year"] <= baseline[1])]
    p90 = base.groupby("station")["TMAX"].quantile(0.90).rename("p90")
    d = daily_feat.merge(p90, on="station")
    d["hot"] = d["TMAX"] > d["p90"]
    y = d.groupby(["station", "year"]).agg(hot_days=("hot", "sum"), n_valid=("TMAX", "count"))
    y = y[y["n_valid"] >= 0.8 * 365].reset_index()
    y = y.merge(stations[["station", "city"]], on="station")
    return y.groupby(["city", "year"])["hot_days"].mean().reset_index()
