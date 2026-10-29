"""Visualización (Semana 5): series con tendencia, estaciones por década, heatmap y mapa de anomalías.

Reglas de honestidad visual que seguimos:
    - Ejes completos y la misma escala para todas las ciudades cuando se comparan.
    - Escala de color divergente centrada en 0 para anomalías.
    - La línea de tendencia se dibuja con la pendiente de Sen (robusta) y se anota en °C/década.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config as C  # noqa: E402

plt.rcParams.update({"figure.dpi": 120, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def city_series_grid(annual_df: pd.DataFrame, tt: pd.DataFrame, variable: str, out: Path) -> Path:
    """Una cuadrícula con la serie anual de anomalías por ciudad y su tendencia (Sen)."""
    cities = list(annual_df["city"].unique())
    ncol = 4
    nrow = int(np.ceil(len(cities) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(14, 2.8 * nrow), sharex=True, sharey=True)
    col = f"{variable}_anom"
    ymax = np.nanmax(np.abs(annual_df[col].values)) * 1.1 if annual_df[col].notna().any() else 1
    for ax, city in zip(axes.flat, cities):
        g = annual_df[annual_df["city"] == city]
        ax.axhline(0, color="#999", lw=0.8)
        ax.plot(g["year"], g[col], color="#1e2a6b", lw=1.2)
        ax.fill_between(g["year"], 0, g[col], where=g[col] >= 0, color="#e2231a", alpha=0.25, interpolate=True)
        ax.fill_between(g["year"], 0, g[col], where=g[col] < 0, color="#1e2a6b", alpha=0.25, interpolate=True)
        r = tt[(tt["ciudad"] == city) & (tt["variable"] == variable)]
        if len(r) and not np.isnan(r["sen_dec"].iloc[0]):
            s = r["sen_dec"].iloc[0] / 10
            valid = g.dropna(subset=[col])
            t0 = valid["year"].mean()
            x0 = valid[col].mean()
            xs = np.array([valid["year"].min(), valid["year"].max()])
            ax.plot(xs, x0 + s * (xs - t0), color="#e2231a", lw=2)
            sig = "*" if r["p_mk"].iloc[0] < 0.05 else ""
            ax.set_title(f"{city}: {r['sen_dec'].iloc[0]:+.2f} °C/década{sig}", fontsize=9)
        else:
            ax.set_title(city, fontsize=9)
        ax.set_ylim(-ymax, ymax)
    for ax in axes.flat[len(cities):]:
        ax.axis("off")
    fig.suptitle(f"Anomalía anual de {variable} respecto a {C.BASELINE[0]}–{C.BASELINE[1]} (línea roja: pendiente de Sen; * = p<0.05)")
    fig.supylabel("°C")
    fig.tight_layout()
    return _save(fig, out)


def season_decade_bars(dc: pd.DataFrame, first: tuple, last: tuple, out: Path) -> Path:
    """Δ de temperatura media por estación del año (último − primer decenio) para cada ciudad."""
    piv = dc.pivot(index="ciudad", columns="estacion", values="delta")[C.SEASON_ORDER]
    sig = dc.pivot(index="ciudad", columns="estacion", values="significativa")[C.SEASON_ORDER]
    fig, ax = plt.subplots(figsize=(13, 5))
    x = np.arange(len(piv))
    w = 0.2
    colors = {"DEF": "#1e2a6b", "MAM": "#5b8def", "JJA": "#e2231a", "SON": "#f29d3a"}
    for i, s in enumerate(C.SEASON_ORDER):
        vals = piv[s].values
        bars = ax.bar(x + (i - 1.5) * w, vals, w, label=s, color=colors[s])
        for b, ok in zip(bars, sig[s].values):
            if ok is not True:
                b.set_alpha(0.35)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(piv.index, rotation=30, ha="right")
    ax.set_ylabel("Δ temperatura media (°C)")
    ax.set_title(f"Cambio por estación del año: {last[0]}–{last[1]} vs {first[0]}–{first[1]} (barras tenues: no significativo, p≥0.05)")
    ax.legend(title="Estación", ncol=4)
    fig.tight_layout()
    return _save(fig, out)


def anomaly_heatmap(cm: pd.DataFrame, city: str, variable: str, out: Path) -> Path:
    """Año × mes de anomalías para una ciudad: deja ver de golpe qué meses y décadas se calientan."""
    g = cm[cm["city"] == city]
    piv = g.pivot(index="year", columns="month", values=f"{variable}_anom").reindex(columns=range(1, 13))
    vmax = np.nanmax(np.abs(piv.values)) if piv.notna().any().any() else 1
    fig, ax = plt.subplots(figsize=(7, 0.16 * len(piv) + 1.5))
    im = ax.imshow(piv.values, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(12))
    ax.set_xticklabels(["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    step = max(1, len(piv) // 12)
    ax.set_yticks(range(0, len(piv), step))
    ax.set_yticklabels(piv.index[::step])
    ax.set_title(f"{city}: anomalía mensual de {variable} (°C)")
    fig.colorbar(im, ax=ax, label="°C")
    fig.tight_layout()
    return _save(fig, out)


def anomaly_map(stations: pd.DataFrame, tt: pd.DataFrame, variable: str, out: Path) -> Path:
    """Mapa de puntos: pendiente de calentamiento por ciudad (tamaño y color = °C/década)."""
    r = tt[tt["variable"] == variable].merge(
        stations.groupby("city")[["lat", "lon"]].mean().reset_index(), left_on="ciudad", right_on="city")
    vmax = np.nanmax(np.abs(r["sen_dec"])) if r["sen_dec"].notna().any() else 1
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.set_facecolor("#f4f4f4")
    sc = ax.scatter(r["lon"], r["lat"], c=r["sen_dec"], cmap="RdBu_r", vmin=-vmax, vmax=vmax,
                    s=80 + 600 * np.abs(r["sen_dec"]) / vmax, edgecolor="#333", lw=0.6, zorder=3)
    for _, row in r.iterrows():
        sig = "*" if row["p_mk"] < 0.05 else ""
        ax.annotate(f"{row['ciudad']}\n{row['sen_dec']:+.2f}{sig}", (row["lon"], row["lat"]),
                    textcoords="offset points", xytext=(8, 6), fontsize=8)
    ax.set_xlim(-118, -86)
    ax.set_ylim(14, 34)
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.set_title(f"Tendencia de {variable} por ciudad (°C/década, pendiente de Sen; * = p<0.05)")
    ax.grid(True, color="#ddd", lw=0.5)
    fig.colorbar(sc, ax=ax, label="°C/década")
    fig.tight_layout()
    return _save(fig, out)


def hot_days_plot(hd: pd.DataFrame, out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for city, g in hd.groupby("city"):
        ax.plot(g["year"], g["hot_days"].rolling(5, center=True, min_periods=3).mean(), lw=1.2, label=city)
    ax.set_ylabel("días con TMAX > p90 (media móvil 5 años)")
    ax.set_title("Días cálidos por año y ciudad")
    ax.legend(ncol=4, fontsize=7, frameon=False)
    fig.tight_layout()
    return _save(fig, out)


def _save(fig, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out
