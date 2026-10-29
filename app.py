#!/usr/bin/env python3
"""ClimaMX — app interactiva (Streamlit).

    streamlit run app.py

Lee el almacén SQLite que genera `pipeline.py` (data/climamx.sqlite) y permite
explorar, ciudad por ciudad, la tendencia de calentamiento, el cambio por
estación del año, el heatmap de anomalías, los días cálidos, el ranking y el
mapa. Si todavía no hay almacén, ofrece generar los datos de demostración.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from climamx import config as C  # noqa: E402

# ----------------------------------------------------------------------------- estilo
NAVY, RED, BLUE, GRAY = "#1E2A6B", "#E2231A", "#2F5FD0", "#6A7179"
VARLBL = {"TMEAN": "temperatura media", "TMAX": "temperatura máxima (días)", "TMIN": "temperatura mínima (noches)"}
SEASON_NAME = {"DEF": "invierno", "MAM": "primavera", "JJA": "verano", "SON": "otoño"}
MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
LAYOUT = dict(margin=dict(l=40, r=20, t=40, b=40), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
              font=dict(family="IBM Plex Sans, Segoe UI, sans-serif"), hovermode="x unified")

st.set_page_config(page_title="ClimaMX", page_icon="🌡️", layout="wide")


# ----------------------------------------------------------------------------- datos
TABLES = ["estaciones", "ciudad_anual", "ciudad_mensual", "ciudad_estacional", "tendencias", "comparacion_decadas", "dias_calidos"]


@st.cache_data(show_spinner="Cargando el almacén…")
def load_store(db_path: str, mtime: float) -> dict[str, pd.DataFrame]:
    """Lee todas las tablas del SQLite. `mtime` sólo sirve para invalidar la caché cuando el pipeline vuelve a correr."""
    con = sqlite3.connect(db_path)
    data = {t: pd.read_sql(f"SELECT * FROM {t}", con) for t in TABLES}
    con.close()
    return data


def run_demo_pipeline() -> None:
    """Corre `pipeline.py --demo --no-figures` dentro de la app (datos sintéticos)."""
    import pipeline  # noqa: WPS433 - import tardío a propósito
    pipeline.main(["--demo", "--no-figures"])


def fmt(v, nd=2, sign=True) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def fmt_p(p) -> str:
    if p is None or np.isnan(p):
        return "—"
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


# ----------------------------------------------------------------------------- gráficas
def fig_series(ann: pd.DataFrame, trend: pd.Series, var: str, show_linear: bool) -> go.Figure:
    col = f"{var}_anom"
    y = ann[col]
    fig = go.Figure()
    fig.add_bar(x=ann["year"], y=y, marker_color=np.where(y >= 0, RED, BLUE), opacity=0.55, name="Anomalía anual",
                hovertemplate="%{y:+.2f} °C<extra>anomalía</extra>")
    fig.add_scatter(x=ann["year"], y=y, mode="lines", line=dict(color=NAVY, width=1.3), name="Serie", hoverinfo="skip")
    valid = ann.dropna(subset=[col])
    if len(valid) and not np.isnan(trend.get("sen_dec", np.nan)):
        t0, v0 = valid["year"].mean(), valid[col].mean()
        xs = np.array([valid["year"].min(), valid["year"].max()])
        fig.add_scatter(x=xs, y=v0 + trend["sen_dec"] / 10 * (xs - t0), mode="lines", line=dict(color=RED, width=3),
                        name=f"Sen: {trend['sen_dec']:+.2f} °C/década", hoverinfo="skip")
        if show_linear:
            fig.add_scatter(x=xs, y=v0 + trend["slope_dec"] / 10 * (xs - t0), mode="lines",
                            line=dict(color=NAVY, width=2, dash="dash"), name=f"Regresión: {trend['slope_dec']:+.2f} °C/década", hoverinfo="skip")
    vmax = max(0.5, float(np.nanmax(np.abs(y))) * 1.15) if y.notna().any() else 1
    fig.update_layout(**LAYOUT, height=380, yaxis=dict(title=f"°C respecto a {C.BASELINE[0]}–{C.BASELINE[1]}", range=[-vmax, vmax], zeroline=True, zerolinecolor=GRAY),
                      xaxis=dict(title=None), legend=dict(orientation="h", y=1.12, x=0), bargap=0.15)
    return fig


def fig_seasons(dc: pd.DataFrame, first: tuple, last: tuple) -> go.Figure:
    dc = dc.set_index("estacion").reindex(C.SEASON_ORDER).reset_index()
    sig = dc["p_welch"] < 0.05
    fig = go.Figure(go.Bar(
        x=[f"{k}<br>{SEASON_NAME[k]}" for k in dc["estacion"]], y=dc["delta"],
        marker_color=np.where(dc["delta"] >= 0, RED, BLUE), marker_opacity=np.where(sig, 0.95, 0.3),
        text=[f"{d:+.2f}" + ("" if s else " ns") for d, s in zip(dc["delta"], sig)], textposition="outside",
        customdata=np.stack([dc["media_inicio"], dc["media_fin"], dc["p_welch"]], axis=1),
        hovertemplate="%{customdata[0]:.1f} → %{customdata[1]:.1f} °C<br>Δ %{y:+.2f} °C · p = %{customdata[2]:.3f}<extra></extra>"))
    vmax = max(0.5, float(np.nanmax(np.abs(dc["delta"]))) * 1.3)
    fig.update_layout(**LAYOUT, height=360, yaxis=dict(title=f"Δ temperatura media (°C), {last[0]}–{last[1]} vs {first[0]}–{first[1]}", range=[-vmax, vmax], zeroline=True, zerolinecolor=GRAY))
    return fig


def fig_heatmap(cm: pd.DataFrame, var: str) -> go.Figure:
    piv = cm.pivot(index="month", columns="year", values=f"{var}_anom").reindex(range(1, 13))
    vmax = max(0.5, float(np.nanmax(np.abs(piv.values))))
    fig = go.Figure(go.Heatmap(z=piv.values, x=piv.columns, y=MONTHS, colorscale="RdBu_r", zmid=0, zmin=-vmax, zmax=vmax,
                               colorbar=dict(title="°C"), hovertemplate="%{y} %{x}: %{z:+.2f} °C<extra></extra>"))
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=380, yaxis=dict(autorange="reversed"))
    return fig


def fig_hot_days(hd: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=hd["year"], y=hd["hot_days"], mode="lines", line=dict(color=GRAY, width=1), name="Días cálidos", hovertemplate="%{y:.0f} días<extra></extra>")
    fig.add_scatter(x=hd["year"], y=hd["hot_days"].rolling(5, center=True, min_periods=3).mean(), mode="lines",
                    line=dict(color=RED, width=3), name="Media móvil 5 años", hovertemplate="%{y:.1f} días<extra>media móvil</extra>")
    fig.update_layout(**LAYOUT, height=360, yaxis=dict(title="días con TMAX > p90", rangemode="tozero"), legend=dict(orientation="h", y=1.12, x=0))
    return fig


def fig_ranking(tt: pd.DataFrame, var: str, selected: str) -> go.Figure:
    r = tt[tt["variable"] == var].sort_values("sen_dec")
    fig = go.Figure(go.Bar(
        x=r["sen_dec"], y=r["ciudad"], orientation="h",
        marker_color=np.where(r["sen_dec"] >= 0, RED, BLUE), marker_opacity=np.where(r["ciudad"] == selected, 1.0, 0.6),
        text=[f"{v:+.2f}" + ("*" if p < 0.05 else "") for v, p in zip(r["sen_dec"], r["p_mk"])], textposition="outside", cliponaxis=False,
        customdata=np.stack([r["sen_lo"], r["sen_hi"], r["p_mk"]], axis=1),
        hovertemplate="%{y}: %{x:+.2f} °C/década<br>IC 95 %%: %{customdata[0]:+.2f} a %{customdata[1]:+.2f} · p = %{customdata[2]:.3f}<extra></extra>"))
    xmax = max(0.1, float(np.nanmax(np.abs(r["sen_dec"]))) * 1.3)
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=30 * len(r) + 80,
                      xaxis=dict(title="°C por década (pendiente de Sen); * = p < 0.05", range=[min(0, -xmax) if (r["sen_dec"] < 0).any() else 0, xmax]))
    return fig


# Contorno simplificado de México (lon, lat) para un mapa esquemático que no necesita internet.
OUTLINE = [(-117.1, 32.5), (-114.7, 32.7), (-111.0, 31.3), (-108.2, 31.3), (-106.5, 31.8), (-104.4, 29.6), (-103.0, 29.0), (-101.4, 29.8),
           (-100.5, 28.7), (-99.5, 27.5), (-98.3, 26.1), (-97.4, 25.9), (-97.7, 24.3), (-97.9, 22.2), (-97.4, 20.9), (-96.4, 19.6), (-95.9, 18.8),
           (-94.4, 18.1), (-92.7, 18.5), (-91.5, 18.6), (-90.5, 19.8), (-90.3, 21.0), (-89.0, 21.4), (-87.1, 21.6), (-86.8, 21.0), (-87.5, 19.9),
           (-87.6, 18.9), (-88.3, 18.5), (-89.1, 17.8), (-90.9, 17.8), (-91.0, 17.2), (-91.4, 16.1), (-92.2, 15.3), (-92.3, 14.6), (-93.9, 15.9),
           (-95.2, 16.2), (-97.1, 15.9), (-98.6, 16.4), (-99.9, 16.8), (-101.6, 17.6), (-102.2, 17.9), (-103.5, 18.3), (-104.3, 19.1), (-105.3, 20.4),
           (-105.5, 21.6), (-106.4, 23.2), (-107.9, 24.6), (-109.1, 25.6), (-109.5, 26.8), (-110.9, 27.9), (-112.2, 29.2), (-113.5, 31.3), (-114.8, 31.8),
           (-114.8, 31.0), (-114.4, 30.0), (-113.1, 28.6), (-112.3, 27.3), (-111.3, 26.0), (-110.3, 24.1), (-109.9, 22.9), (-110.9, 23.6), (-112.1, 24.6),
           (-112.3, 26.1), (-113.8, 26.9), (-114.4, 27.6), (-114.1, 28.0), (-115.7, 30.1), (-116.6, 31.9), (-117.1, 32.5)]


def fig_map(stations: pd.DataFrame, tt: pd.DataFrame, var: str, selected: str) -> go.Figure:
    r = tt[tt["variable"] == var].merge(stations.groupby("city")[["lat", "lon"]].mean().reset_index(), left_on="ciudad", right_on="city")
    vmax = max(0.1, float(np.nanmax(np.abs(r["sen_dec"]))))
    fig = go.Figure()
    fig.add_scatter(x=[p[0] for p in OUTLINE], y=[p[1] for p in OUTLINE], fill="toself", fillcolor="rgba(30,42,107,0.08)",
                    line=dict(color="#9AA3BF", width=1), mode="lines", hoverinfo="skip", showlegend=False)
    fig.add_scatter(
        x=r["lon"], y=r["lat"], text=r["ciudad"], mode="markers+text", textposition="top center", textfont=dict(color=NAVY, size=12),
        marker=dict(size=12 + 26 * np.abs(r["sen_dec"]) / vmax, color=r["sen_dec"], colorscale="RdBu_r", cmid=0, cmin=-vmax, cmax=vmax,
                    line=dict(width=np.where(r["ciudad"] == selected, 3, 1), color=NAVY), colorbar=dict(title="°C/década")),
        customdata=np.stack([r["sen_dec"], r["p_mk"]], axis=1), showlegend=False,
        hovertemplate="%{text}: %{customdata[0]:+.2f} °C/década · p = %{customdata[1]:.3f}<extra></extra>")
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=460,
                      xaxis=dict(range=[-118, -86], title="Longitud", showgrid=False, zeroline=False),
                      yaxis=dict(range=[14, 33.5], title="Latitud", showgrid=False, zeroline=False))
    return fig


# ----------------------------------------------------------------------------- app
def main() -> None:
    db = C.STORE_PATH
    if not db.exists():
        st.title("🌡️ ClimaMX")
        st.warning("Todavía no hay almacén de datos (`data/climamx.sqlite`). Corre el pipeline primero.")
        st.code("python pipeline.py --download    # datos reales de NOAA GHCN-Daily\npython pipeline.py --demo        # datos sintéticos para probar", language="bash")
        if st.button("Generar datos de demostración ahora (sintéticos, ~20 s)", type="primary"):
            with st.spinner("Corriendo el pipeline en modo demo…"):
                run_demo_pipeline()
            st.rerun()
        return

    data = load_store(str(db), db.stat().st_mtime)
    stations, ann, cm, tt, dc, hd = (data[k] for k in ["estaciones", "ciudad_anual", "ciudad_mensual", "tendencias", "comparacion_decadas", "dias_calidos"])
    demo = bool(stations["station"].str.startswith("MXDEMO").all())
    cities = sorted(stations["city"].unique(), key=str.casefold)
    years = sorted(ann["year"].unique())
    first, last = (years[0], years[0] + 9), (years[-1] - 9, years[-1])

    # --- barra lateral ---------------------------------------------------------
    with st.sidebar:
        st.markdown(f"<h2 style='color:{NAVY};margin-bottom:0'>🌡️ ClimaMX</h2><p style='color:{GRAY};margin-top:0'>Tendencias de calentamiento y cambio estacional en ciudades de México</p>", unsafe_allow_html=True)
        city = st.selectbox("Ciudad", cities, index=cities.index(st.session_state.get("city", cities[0])) if st.session_state.get("city") in cities else 0)
        st.session_state["city"] = city
        var = st.radio("Variable", list(VARLBL), format_func=lambda k: VARLBL[k].capitalize())
        show_linear = st.checkbox("Mostrar también la regresión lineal", value=False)
        st.caption(f"Periodo {years[0]}–{years[-1]} · climatología base {C.BASELINE[0]}–{C.BASELINE[1]} · {len(stations)} estaciones en {len(cities)} ciudades")
        if demo:
            st.warning("Datos de demostración (sintéticos). Corre `python pipeline.py --download` para usar NOAA GHCN-Daily.")
        st.caption("UNE · Optativa III: Ciencia de Datos · Juan Pablo Rodríguez, Alfredo Santos, Bryan Salazar")

    # --- datos de la ciudad -----------------------------------------------------
    ann_c = ann[ann["city"] == city].sort_values("year")
    cm_c = cm[cm["city"] == city]
    dc_c = dc[dc["ciudad"] == city]
    hd_c = hd[hd["city"] == city].sort_values("year")
    t = tt[(tt["ciudad"] == city) & (tt["variable"] == var)].iloc[0] if len(tt[(tt["ciudad"] == city) & (tt["variable"] == var)]) else pd.Series(dtype=float)
    best = dc_c.sort_values("delta", ascending=False).iloc[0] if len(dc_c) else None
    st_c = stations[stations["city"] == city]

    st.title(f"{city} · {VARLBL[var]}")
    if demo:
        st.info("Estás viendo **datos sintéticos** generados por `pipeline.py --demo`: sirven para probar la app, no son resultados reales de México.", icon="⚠️")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Tendencia Sen (°C/década)", fmt(t.get("sen_dec")))
    k1.caption(f"IC 95 %: {fmt(t.get('sen_lo'))} a {fmt(t.get('sen_hi'))}")
    k2.metric("Regresión lineal (°C/década)", fmt(t.get("slope_dec")))
    k2.caption(f"IC 95 %: {fmt(t.get('ci_lo'))} a {fmt(t.get('ci_hi'))}")
    k3.metric("Mann-Kendall (p-valor)", fmt_p(t.get("p_mk")))
    k3.caption(str(t.get("tendencia", "—")).capitalize() + f" · {int(t.get('n', 0)) if not np.isnan(t.get('n', np.nan)) else 0} años válidos")
    k4.metric("Estación que más cambia", SEASON_NAME.get(best["estacion"], "—").capitalize() if best is not None else "—")
    k4.caption(f"{fmt(best['delta'])} °C entre decenios (p {fmt_p(best['p_welch'])})" if best is not None else "")
    k5.metric("Estaciones usadas", len(st_c))
    k5.caption(", ".join(st_c["station"]))

    tab_s, tab_e, tab_h, tab_d, tab_r, tab_t = st.tabs(["Serie anual", "Estaciones del año", "Heatmap", "Días cálidos", "Ranking y mapa", "Tablas y datos"])

    with tab_s:
        st.plotly_chart(fig_series(ann_c, t, var, show_linear), use_container_width=True)
        st.caption("Barras: anomalía de cada año respecto a la climatología base de cada estación (rojo = más cálido, azul = más frío). Línea roja: pendiente de Sen, robusta a años extremos.")

    with tab_e:
        if len(dc_c):
            st.plotly_chart(fig_seasons(dc_c, first, last), use_container_width=True)
            st.caption("Diferencia de la temperatura media por estación del año entre el último y el primer decenio. Barras tenues: no significativa (t de Welch, p ≥ 0.05).")
        else:
            st.info("No hay suficientes años en ambos decenios para comparar esta ciudad.")

    with tab_h:
        st.plotly_chart(fig_heatmap(cm_c, var), use_container_width=True)
        st.caption("Cada celda es un mes. Deja ver de un vistazo qué meses y qué décadas concentran el calentamiento.")

    with tab_d:
        st.plotly_chart(fig_hot_days(hd_c), use_container_width=True)
        st.caption("Días por año con TMAX por encima del percentil 90 de la climatología base, promedio de las estaciones de la ciudad.")

    with tab_r:
        c1, c2 = st.columns([1, 1.3])
        with c1:
            st.plotly_chart(fig_ranking(tt, var, city), use_container_width=True)
        with c2:
            st.plotly_chart(fig_map(stations, tt, var, city), use_container_width=True)
        st.caption("Tamaño y color = pendiente de Sen de la variable elegida. Las barras de error del ranking son el IC 95 % de la pendiente.")

    with tab_t:
        st.subheader("Tendencias por ciudad y variable")
        show = tt[["ciudad", "variable", "sen_dec", "sen_lo", "sen_hi", "slope_dec", "ci_lo", "ci_hi", "p_mk", "tendencia", "n"]].rename(columns={
            "sen_dec": "Sen °C/déc", "sen_lo": "Sen IC lo", "sen_hi": "Sen IC hi", "slope_dec": "Regr. °C/déc", "ci_lo": "Regr. IC lo", "ci_hi": "Regr. IC hi", "p_mk": "p (MK)", "n": "años"})
        st.dataframe(show.sort_values(["variable", "Sen °C/déc"], ascending=[True, False]), use_container_width=True, hide_index=True)
        st.download_button("Descargar tendencias (CSV)", tt.to_csv(index=False).encode("utf-8"), "tendencias.csv", "text/csv")
        st.subheader(f"Comparación de decenios · {city}")
        st.dataframe(dc_c[["estacion", "media_inicio", "media_fin", "delta", "p_welch", "significativa"]], use_container_width=True, hide_index=True)
        st.subheader("Estaciones de la ciudad")
        st.dataframe(st_c[["station", "name", "lat", "lon", "elev", "dist_km", "first_year", "last_year"]], use_container_width=True, hide_index=True)
        st.download_button("Descargar serie anual de la ciudad (CSV)", ann_c.to_csv(index=False).encode("utf-8"), f"anual_{city}.csv", "text/csv")

    with st.expander("¿Cómo se calculó esto? (método en corto)"):
        st.markdown(f"""
- **Anomalías, no absolutos.** Cada estación se compara contra su propia climatología {C.BASELINE[0]}–{C.BASELINE[1]} mes a mes; así se promedian varias estaciones por ciudad sin sesgos.
- **Completitud.** Un mes vale con ≥ {int(C.MIN_MONTH_FRAC*100)} % de días válidos y un año con ≥ {C.MIN_MONTHS_PER_YEAR} meses; sólo se interpolan huecos de ≤ {C.MAX_GAP_DAYS} días y sólo en temperatura.
- **Pendiente de Sen + Mann-Kendall.** Sen es la mediana de todas las pendientes entre pares de años (robusta a atípicos); Mann-Kendall prueba si la serie sube de forma monótona sin suponer normalidad. La regresión lineal se reporta como comparación.
- **t de Welch entre decenios.** Para cada estación del año se comparan las medias del primer decenio ({first[0]}–{first[1]}) y del último ({last[0]}–{last[1]}) sin suponer varianzas iguales.
- **Fuente.** NOAA NCEI, GHCN-Daily (estaciones con prefijo MX). El código de todo el proceso está en `climamx/` y se ejecuta con `python pipeline.py`.
""")


if __name__ == "__main__":
    main()
