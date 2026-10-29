"""Almacén de series temporales (Semanas 6–7).

Usamos SQLite porque no requiere servidor y cualquiera del equipo lo abre con
`sqlite3` o DB Browser. Las tablas se indexan por (clave, fecha) para que las
consultas por serie sean rápidas. Si el proyecto crece, el mismo código
funciona con PostgreSQL/TimescaleDB cambiando la URL en `connect()`.

Tablas:
    estaciones       catálogo de estaciones seleccionadas y su ciudad
    diario           registros diarios limpios (estación, fecha, TMAX, TMIN, PRCP, TMEAN, DTR)
    mensual          agregados mensuales por estación con anomalías
    ciudad_mensual   promedio por ciudad, mes a mes
    ciudad_anual     promedio por ciudad, año a año
    ciudad_estacional promedio por ciudad, estación del año y año
    tendencias       resultados estadísticos por ciudad y variable
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from . import config as C

INDEXES = {
    "diario": ["station", "date"],
    "mensual": ["station", "year", "month"],
    "ciudad_mensual": ["city", "year", "month"],
    "ciudad_anual": ["city", "year"],
    "ciudad_estacional": ["city", "season", "season_year"],
}


def connect(path: Path = C.STORE_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def save(con: sqlite3.Connection, name: str, df: pd.DataFrame) -> int:
    """Reemplaza la tabla `name` con `df` y crea su índice. Devuelve filas escritas."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%d")
        elif out[c].dtype == object:
            out[c] = out[c].astype(str)
        elif str(out[c].dtype) == "category":
            out[c] = out[c].astype(str)
    out.to_sql(name, con, if_exists="replace", index=False, chunksize=50_000)
    if name in INDEXES:
        cols = ", ".join(INDEXES[name])
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{name} ON {name} ({cols})")
    con.commit()
    return len(out)


def load(con: sqlite3.Connection, name: str, parse_dates=None) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {name}", con, parse_dates=parse_dates)


def summary(con: sqlite3.Connection) -> pd.DataFrame:
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    rows = [{"tabla": n, "filas": con.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]} for n in names]
    return pd.DataFrame(rows)
