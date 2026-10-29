"""Análisis (fase KDD): estadística de tendencias y comparación entre décadas.

Métodos:
    - Regresión lineal temporal (pendiente en °C/década con IC 95 %).
    - Prueba de Mann-Kendall (no paramétrica, ¿hay tendencia monótona?).
    - Pendiente de Sen (estimador robusto de la tendencia, con IC 95 %).
    - Prueba t de Welch para comparar el primer y el último decenio por estación del año.
Todo está implementado con numpy/scipy para no depender de paquetes extra.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

from . import config as C


# ---------------------------------------------------------------------------
# Tendencia de una serie anual
# ---------------------------------------------------------------------------
def linear_trend(years, values) -> dict:
    t, x = _drop_nan(years, values)
    if len(x) < 10:
        return {"slope_dec": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p_lineal": np.nan, "r2": np.nan, "n": len(x)}
    res = stats.linregress(t, x)
    tcrit = stats.t.ppf(0.975, len(x) - 2)
    return {"slope_dec": res.slope * 10, "ci_lo": (res.slope - tcrit * res.stderr) * 10,
            "ci_hi": (res.slope + tcrit * res.stderr) * 10, "p_lineal": res.pvalue,
            "r2": res.rvalue ** 2, "n": len(x)}


def mann_kendall(values, alpha: float = 0.05) -> dict:
    """Prueba de Mann-Kendall con corrección por empates (aproximación normal)."""
    x = np.asarray(values, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 10:
        return {"mk_s": np.nan, "mk_z": np.nan, "p_mk": np.nan, "tau": np.nan, "tendencia": "datos insuficientes"}
    s = sum(np.sign(x[k + 1:] - x[k]).sum() for k in range(n - 1))
    _, counts = np.unique(x, return_counts=True)
    ties = counts[counts > 1]
    var_s = (n * (n - 1) * (2 * n + 5) - np.sum(ties * (ties - 1) * (2 * ties + 5))) / 18.0
    z = 0.0 if s == 0 else (s - np.sign(s)) / np.sqrt(var_s)
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    tau = s / (n * (n - 1) / 2)
    if p < alpha:
        trend = "creciente" if s > 0 else "decreciente"
    else:
        trend = "sin tendencia"
    return {"mk_s": s, "mk_z": z, "p_mk": p, "tau": tau, "tendencia": trend}


def sens_slope(years, values, alpha: float = 0.05) -> dict:
    """Pendiente de Sen (mediana de todas las pendientes pareadas) con IC 95 % (Gilbert, 1987)."""
    t, x = _drop_nan(years, values)
    n = len(x)
    if n < 10:
        return {"sen_dec": np.nan, "sen_lo": np.nan, "sen_hi": np.nan}
    slopes = np.array([(x[j] - x[i]) / (t[j] - t[i]) for i, j in combinations(range(n), 2)])
    slopes.sort()
    N = len(slopes)
    _, counts = np.unique(x, return_counts=True)
    ties = counts[counts > 1]
    var_s = (n * (n - 1) * (2 * n + 5) - np.sum(ties * (ties - 1) * (2 * ties + 5))) / 18.0
    c = stats.norm.ppf(1 - alpha / 2) * np.sqrt(var_s)
    lo_i = int(np.clip(np.floor((N - c) / 2), 0, N - 1))
    hi_i = int(np.clip(np.ceil((N + c) / 2), 0, N - 1))
    return {"sen_dec": np.median(slopes) * 10, "sen_lo": slopes[lo_i] * 10, "sen_hi": slopes[hi_i] * 10}


def trend_table(annual_df: pd.DataFrame, variables=("TMAX", "TMIN", "TMEAN"), use_anom: bool = True) -> pd.DataFrame:
    """Una fila por ciudad y variable con regresión, Mann-Kendall y Sen."""
    rows = []
    for city, g in annual_df.groupby("city"):
        for v in variables:
            col = f"{v}_anom" if use_anom else v
            row = {"ciudad": city, "variable": v}
            row.update(linear_trend(g["year"], g[col]))
            row.update(mann_kendall(g[col].values))
            row.update(sens_slope(g["year"], g[col]))
            rows.append(row)
    tt = pd.DataFrame(rows)
    tt["significativa"] = tt["p_mk"] < 0.05
    return tt.sort_values(["variable", "slope_dec"], ascending=[True, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Comparación entre decenios por estación del año
# ---------------------------------------------------------------------------
def decade_comparison(seasonal_df: pd.DataFrame, first: tuple, last: tuple, variable: str = "TMEAN") -> pd.DataFrame:
    """Diferencia de medias (último − primer decenio) por ciudad y estación, con t de Welch."""
    rows = []
    for (city, season), g in seasonal_df.groupby(["city", "season"]):
        a = g[(g["season_year"] >= first[0]) & (g["season_year"] <= first[1])][variable].dropna()
        b = g[(g["season_year"] >= last[0]) & (g["season_year"] <= last[1])][variable].dropna()
        if len(a) < 5 or len(b) < 5:
            rows.append({"ciudad": city, "estacion": season, "media_inicio": a.mean(), "media_fin": b.mean(),
                         "delta": np.nan, "p_welch": np.nan, "n_inicio": len(a), "n_fin": len(b)})
            continue
        t = stats.ttest_ind(b, a, equal_var=False)
        rows.append({"ciudad": city, "estacion": season, "media_inicio": a.mean(), "media_fin": b.mean(),
                     "delta": b.mean() - a.mean(), "p_welch": t.pvalue, "n_inicio": len(a), "n_fin": len(b)})
    out = pd.DataFrame(rows)
    out["estacion"] = pd.Categorical(out["estacion"], C.SEASON_ORDER, ordered=True)
    out["significativa"] = out["p_welch"] < 0.05
    return out.sort_values(["ciudad", "estacion"]).reset_index(drop=True)


def season_ranking(dc: pd.DataFrame) -> pd.DataFrame:
    """Qué estación del año cambia más (promedio del Δ entre ciudades)."""
    return (dc.groupby("estacion", observed=True)
              .agg(delta_promedio=("delta", "mean"), ciudades_significativas=("significativa", "sum"), n=("delta", "count"))
              .reset_index().sort_values("delta_promedio", ascending=False))


def city_ranking(tt: pd.DataFrame, variable: str = "TMEAN") -> pd.DataFrame:
    """Ciudades ordenadas de mayor a menor calentamiento (°C/década, Sen)."""
    r = tt[tt["variable"] == variable][["ciudad", "sen_dec", "sen_lo", "sen_hi", "p_mk", "tendencia"]]
    return r.sort_values("sen_dec", ascending=False).reset_index(drop=True)


def _drop_nan(t, x):
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    m = ~np.isnan(x)
    return t[m], x[m]
