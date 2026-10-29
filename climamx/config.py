"""Configuración central del pipeline ClimaMX.

Todo lo que el equipo pueda querer ajustar (ciudades, periodo, umbrales de
limpieza, rutas) vive aquí para no tocar el resto del código.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Ciudades de estudio (lat, lon). 12 ciudades que cubren las regiones
# climáticas del país: norte árido, altiplano, costas y sureste tropical.
# ---------------------------------------------------------------------------
CITIES = {
    "Ciudad de México": (19.43, -99.13),
    "Guadalajara": (20.67, -103.35),
    "Monterrey": (25.67, -100.31),
    "Mérida": (20.97, -89.62),
    "Hermosillo": (29.07, -110.96),
    "Chihuahua": (28.63, -106.08),
    "Mexicali": (32.63, -115.45),
    "Culiacán": (24.80, -107.39),
    "San Luis Potosí": (22.15, -100.98),
    "Veracruz": (19.19, -96.14),
    "Oaxaca": (17.07, -96.72),
    "Acapulco": (16.86, -99.88),
}

# Periodo de análisis y climatología base para anomalías
START_YEAR = 1971
END_YEAR = 2024
BASELINE = (1971, 2000)

# Selección de estaciones
RADIUS_KM = 40            # distancia máxima estación-ciudad
MIN_YEARS = 30            # años mínimos de registro de TMAX/TMIN
MAX_STATIONS_PER_CITY = 3

# Limpieza
ELEMENTS = ["TMAX", "TMIN", "PRCP"]
TEMP_RANGE = (-30.0, 55.0)      # °C físicamente plausibles en México
PRCP_RANGE = (0.0, 500.0)       # mm/día
MAX_GAP_DAYS = 3                # huecos ≤ 3 días se interpolan (solo temperatura)
MIN_MONTH_FRAC = 0.80           # un mes vale si tiene ≥ 80 % de días válidos
MIN_MONTHS_PER_YEAR = 11        # un año vale si tiene ≥ 11 meses válidos
MIN_BASELINE_YEARS = 15         # años mínimos en la climatología base por mes

# Fuentes de datos
STATIONS_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"
INVENTORY_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt"
BY_STATION_CSV_URL = "https://noaa-ghcn-pds.s3.amazonaws.com/csv/by_station/{sid}.csv"
DLY_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{sid}.dly"

# Rutas
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STORE_PATH = DATA_DIR / "climamx.sqlite"
OUTPUT_DIR = ROOT / "output"
FIG_DIR = OUTPUT_DIR / "figuras"

SEASONS = {12: "DEF", 1: "DEF", 2: "DEF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
SEASON_ORDER = ["DEF", "MAM", "JJA", "SON"]
