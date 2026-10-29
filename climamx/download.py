"""Descarga y selección de estaciones GHCN-Daily para México.

Flujo:
    1. Bajar el catálogo (ghcnd-stations.txt) y el inventario (ghcnd-inventory.txt).
    2. Filtrar estaciones con ID que empieza con "MX".
    3. Elegir, por ciudad, las estaciones cercanas con series largas de TMAX/TMIN.
    4. Bajar los registros diarios de cada estación (CSV de AWS o .dly de NCEI).
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def fetch(url: str, dest: Path, overwrite: bool = False) -> Path:
    """Descarga `url` a `dest` si no existe ya (idempotente)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": "ClimaMX/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


# ---------------------------------------------------------------------------
# Catálogo e inventario (archivos de ancho fijo, formato documentado en readme.txt)
# ---------------------------------------------------------------------------
def read_stations(path: Path) -> pd.DataFrame:
    cols = [(0, 11), (12, 20), (21, 30), (31, 37), (38, 40), (41, 71), (72, 75), (76, 79), (80, 85)]
    names = ["station", "lat", "lon", "elev", "state", "name", "gsn", "hcn_crn", "wmo"]
    df = pd.read_fwf(path, colspecs=cols, names=names, dtype={"wmo": str})
    df["name"] = df["name"].str.strip()
    return df


def read_inventory(path: Path) -> pd.DataFrame:
    cols = [(0, 11), (12, 20), (21, 30), (31, 35), (36, 40), (41, 45)]
    names = ["station", "lat", "lon", "element", "first_year", "last_year"]
    return pd.read_fwf(path, colspecs=cols, names=names)


def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia en km entre dos puntos (vectorizada)."""
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def select_stations(stations: pd.DataFrame, inventory: pd.DataFrame,
                    cities: dict = C.CITIES, radius_km: float = C.RADIUS_KM,
                    min_years: int = C.MIN_YEARS, start: int = C.START_YEAR,
                    end: int = C.END_YEAR, per_city: int = C.MAX_STATIONS_PER_CITY) -> pd.DataFrame:
    """Devuelve las estaciones elegidas con su ciudad asignada.

    Criterio: prefijo MX, TMAX y TMIN disponibles, ≥ `min_years` de traslape
    con el periodo [start, end], y a ≤ `radius_km` de la ciudad. Se toman las
    `per_city` con más años de cobertura.
    """
    mx = stations[stations["station"].str.startswith("MX")].copy()
    inv = inventory[inventory["station"].str.startswith("MX")]
    temp = (inv[inv["element"].isin(["TMAX", "TMIN"])]
            .groupby("station").agg(first_year=("first_year", "max"), last_year=("last_year", "min"),
                                    n_elem=("element", "nunique")))
    temp = temp[temp["n_elem"] == 2]
    temp["overlap"] = (np.minimum(temp["last_year"], end) - np.maximum(temp["first_year"], start) + 1)
    temp = temp[temp["overlap"] >= min_years]
    mx = mx.merge(temp[["first_year", "last_year", "overlap"]], left_on="station", right_index=True)

    rows = []
    for city, (lat, lon) in cities.items():
        d = haversine_km(mx["lat"].values, mx["lon"].values, lat, lon)
        cand = mx.assign(city=city, dist_km=d)
        cand = cand[cand["dist_km"] <= radius_km].sort_values(["overlap", "dist_km"], ascending=[False, True])
        rows.append(cand.head(per_city))
    sel = pd.concat(rows, ignore_index=True)
    return sel[["station", "name", "city", "lat", "lon", "elev", "dist_km", "first_year", "last_year", "overlap"]]


# ---------------------------------------------------------------------------
# Datos diarios por estación
# ---------------------------------------------------------------------------
def download_station(sid: str, raw_dir: Path = C.RAW_DIR) -> Path:
    """Baja el archivo de una estación: primero el CSV de AWS, si falla el .dly de NCEI."""
    csv = raw_dir / f"{sid}.csv"
    dly = raw_dir / f"{sid}.dly"
    if csv.exists():
        return csv
    if dly.exists():
        return dly
    try:
        return fetch(C.BY_STATION_CSV_URL.format(sid=sid), csv)
    except Exception as e:  # noqa: BLE001 - cualquier fallo de red cae al .dly
        print(f"  CSV no disponible para {sid} ({e}); intentando .dly")
        return fetch(C.DLY_URL.format(sid=sid), dly)


def download_catalog(raw_dir: Path = C.RAW_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    st = read_stations(fetch(C.STATIONS_URL, raw_dir / "ghcnd-stations.txt"))
    inv = read_inventory(fetch(C.INVENTORY_URL, raw_dir / "ghcnd-inventory.txt"))
    return st, inv
