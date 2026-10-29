"""Lectura de los formatos crudos de GHCN-Daily.

Ambos lectores devuelven el mismo "formato largo":
    station | date | element | value | mflag | qflag | sflag
con `value` en las unidades crudas (décimas de °C o décimas de mm).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

LONG_COLS = ["station", "date", "element", "value", "mflag", "qflag", "sflag"]
CSV_COLS = ["station", "date", "element", "value", "mflag", "qflag", "sflag", "obs_time"]


def read_station_csv(path: Path) -> pd.DataFrame:
    """CSV por estación del bucket noaa-ghcn-pds (ID,DATE,ELEMENT,DATA_VALUE,M_FLAG,Q_FLAG,S_FLAG,OBS_TIME).

    El archivo puede o no traer encabezado, así que se detecta.
    """
    df = pd.read_csv(path, header=None, names=CSV_COLS, dtype=str, keep_default_na=False)
    if df.iloc[0]["station"].upper() == "ID":
        df = df.iloc[1:]
    df["date"] = pd.to_datetime(df["date"].str.replace("-", ""), format="%Y%m%d", errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    for c in ("mflag", "qflag", "sflag"):
        df[c] = df[c].str.strip().replace("", np.nan)
    return df[LONG_COLS].dropna(subset=["date"]).reset_index(drop=True)


def read_dly(path: Path) -> pd.DataFrame:
    """Formato .dly de NCEI: una fila por estación-año-mes-elemento con 31 columnas de día."""
    specs = [(0, 11), (11, 15), (15, 17), (17, 21)]
    names = ["station", "year", "month", "element"]
    for d in range(31):
        base = 21 + 8 * d
        specs += [(base, base + 5), (base + 5, base + 6), (base + 6, base + 7), (base + 7, base + 8)]
        names += [f"v{d+1}", f"m{d+1}", f"q{d+1}", f"s{d+1}"]
    raw = pd.read_fwf(path, colspecs=specs, names=names, dtype=str, keep_default_na=False)

    frames = []
    for d in range(1, 32):
        part = raw[["station", "year", "month", "element", f"v{d}", f"m{d}", f"q{d}", f"s{d}"]].copy()
        part.columns = ["station", "year", "month", "element", "value", "mflag", "qflag", "sflag"]
        part["day"] = d
        frames.append(part)
    long = pd.concat(frames, ignore_index=True)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long[long["value"] != -9999]                       # -9999 = faltante
    long["date"] = pd.to_datetime(dict(year=long["year"].astype(int), month=long["month"].astype(int),
                                       day=long["day"]), errors="coerce")  # días inexistentes (30 feb) → NaT
    long = long.dropna(subset=["date"])
    for c in ("mflag", "qflag", "sflag"):
        long[c] = long[c].str.strip().replace("", np.nan)
    return long[LONG_COLS].sort_values(["station", "element", "date"]).reset_index(drop=True)


def read_any(path: Path) -> pd.DataFrame:
    return read_dly(path) if path.suffix == ".dly" else read_station_csv(path)
