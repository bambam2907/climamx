"""Preprocesamiento (fase KDD de limpieza).

Reglas, en orden:
    1. Descartar registros con Q_FLAG (no pasaron el control de calidad de NOAA).
    2. Quedarse con TMAX, TMIN y PRCP; convertir décimas → °C y mm.
    3. Pivotear a formato ancho: una fila por estación-día.
    4. Anular valores fuera de rango físico y pares con TMIN > TMAX.
    5. Rellenar el calendario completo (los días sin fila cuentan como faltantes).
    6. Interpolar huecos cortos (≤ MAX_GAP_DAYS) sólo en temperatura.
Devuelve además un reporte de limpieza por estación.
"""
from __future__ import annotations

import pandas as pd

from . import config as C


def clean_daily(long: pd.DataFrame, start: int = C.START_YEAR, end: int = C.END_YEAR):
    """Convierte el formato largo crudo en un DataFrame ancho limpio.

    Regresa (daily, report) donde `daily` tiene columnas
    station, date, TMAX, TMIN, PRCP y `report` resume cuánto se descartó.
    """
    df = long[long["element"].isin(C.ELEMENTS)].copy()
    n_total = len(df)

    # 1. Control de calidad de NOAA
    flagged = df["qflag"].notna()
    n_qflag = int(flagged.sum())
    df = df[~flagged]

    # 2. Periodo y unidades
    df = df[(df["date"].dt.year >= start) & (df["date"].dt.year <= end)]
    df["value"] = df["value"] / 10.0

    # 3. Ancho
    wide = (df.pivot_table(index=["station", "date"], columns="element", values="value", aggfunc="first")
              .reset_index())
    for e in C.ELEMENTS:
        if e not in wide:
            wide[e] = float("nan")

    # 4. Rango físico y coherencia
    lo, hi = C.TEMP_RANGE
    bad_range = 0
    for e in ("TMAX", "TMIN"):
        m = (wide[e] < lo) | (wide[e] > hi)
        bad_range += int(m.sum())
        wide.loc[m, e] = float("nan")
    m = (wide["PRCP"] < C.PRCP_RANGE[0]) | (wide["PRCP"] > C.PRCP_RANGE[1])
    bad_range += int(m.sum())
    wide.loc[m, "PRCP"] = float("nan")
    inverted = wide["TMIN"] > wide["TMAX"]
    n_inverted = int(inverted.sum())
    wide.loc[inverted, ["TMAX", "TMIN"]] = float("nan")

    # 5. Calendario completo por estación + 6. interpolación de huecos cortos
    full = pd.date_range(f"{start}-01-01", f"{end}-12-31", freq="D")
    out, rows = [], []
    for sid, g in wide.groupby("station"):
        g = g.set_index("date").reindex(full)
        g["station"] = sid
        n_missing_before = int(g[["TMAX", "TMIN"]].isna().any(axis=1).sum())
        for e in ("TMAX", "TMIN"):
            g[e] = g[e].interpolate(method="linear", limit=C.MAX_GAP_DAYS, limit_area="inside")
        n_missing_after = int(g[["TMAX", "TMIN"]].isna().any(axis=1).sum())
        first = g["TMAX"].first_valid_index()
        last = g["TMAX"].last_valid_index()
        rows.append({"station": sid,
                     "primer_dia": first.date() if first is not None else None,
                     "ultimo_dia": last.date() if last is not None else None,
                     "dias_faltantes_temp": n_missing_before,
                     "dias_interpolados": n_missing_before - n_missing_after,
                     "completitud_temp": round(1 - n_missing_after / len(full), 3)})
        out.append(g.rename_axis("date").reset_index())
    daily = pd.concat(out, ignore_index=True)[["station", "date", "TMAX", "TMIN", "PRCP"]]

    report = pd.DataFrame(rows)
    report.attrs["resumen"] = {"registros_entrada": n_total, "descartados_qflag": n_qflag,
                               "fuera_de_rango": bad_range, "tmin_mayor_que_tmax": n_inverted}
    return daily, report
