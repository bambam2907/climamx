#!/usr/bin/env python3
"""Exporta los resultados del pipeline a un JSON compacto para la página web.

    python export_web.py                       # escribe output/web_data.json
    python export_web.py --inject docs/index.html   # además lo incrusta en la página

La página lee el bloque <script id="climamx-data" type="application/json">…</script>;
`--inject` reemplaza ese bloque con los datos nuevos, así la página queda
autocontenida (no necesita servidor ni fetch).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path

import pandas as pd

from climamx import config as C


def r(x, nd=2):
    return None if pd.isna(x) else round(float(x), nd)


def build(demo: bool | None = None) -> dict:
    con = sqlite3.connect(C.STORE_PATH)
    stations = pd.read_sql("SELECT * FROM estaciones", con)
    annual = pd.read_sql("SELECT city, year, TMEAN_anom, TMAX_anom, TMIN_anom, TMEAN, TMAX, TMIN FROM ciudad_anual ORDER BY city, year", con)
    monthly = pd.read_sql("SELECT city, year, month, TMEAN_anom FROM ciudad_mensual ORDER BY city, year, month", con)
    trends = pd.read_sql("SELECT * FROM tendencias", con)
    decades = pd.read_sql("SELECT * FROM comparacion_decadas", con)
    hot = pd.read_sql("SELECT city, year, hot_days FROM dias_calidos ORDER BY city, year", con)
    n_dias = int(con.execute("SELECT COUNT(*) FROM diario WHERE TMAX IS NOT NULL AND TMIN IS NOT NULL").fetchone()[0])
    if demo is None:
        demo = bool(stations["station"].str.startswith("MXDEMO").all())

    years = sorted(annual["year"].unique().tolist())
    cities = {}
    for city, g in stations.groupby("city"):
        a = annual[annual["city"] == city].set_index("year").reindex(years)
        m = monthly[monthly["city"] == city]
        heat = []
        for y in years:
            row = m[m["year"] == y].set_index("month")["TMEAN_anom"].reindex(range(1, 13))
            heat.append([r(v) for v in row.values])
        t = {}
        for _, tr in trends[trends["ciudad"] == city].iterrows():
            t[tr["variable"]] = {"sen": r(tr["sen_dec"]), "sen_lo": r(tr["sen_lo"]), "sen_hi": r(tr["sen_hi"]),
                                 "slope": r(tr["slope_dec"]), "ci_lo": r(tr["ci_lo"]), "ci_hi": r(tr["ci_hi"]),
                                 "p_mk": r(tr["p_mk"], 4), "tendencia": tr["tendencia"], "n": int(tr["n"])}
        d = {}
        for _, dr in decades[decades["ciudad"] == city].iterrows():
            d[dr["estacion"]] = {"delta": r(dr["delta"]), "p": r(dr["p_welch"], 4),
                                 "inicio": r(dr["media_inicio"]), "fin": r(dr["media_fin"])}
        h = hot[hot["city"] == city].set_index("year")["hot_days"].reindex(years)
        cities[city] = {
            "lat": r(g["lat"].mean(), 3), "lon": r(g["lon"].mean(), 3),
            "estaciones": g[["station", "name"]].to_dict("records"),
            "anual": {k: [r(v) for v in a[f"{k}_anom"].values] for k in ("TMEAN", "TMAX", "TMIN")},
            "absoluto": {k: [r(v, 1) for v in a[k].values] for k in ("TMEAN", "TMAX", "TMIN")},
            "heatmap": heat,
            "dias_calidos": [r(v, 1) for v in h.values],
            "tendencias": t,
            "decenios": d,
        }
    first = (years[0], years[0] + 9)
    last = (years[-1] - 9, years[-1])
    return {"generado": time.strftime("%Y-%m-%d"), "demo": demo, "years": years,
            "baseline": list(C.BASELINE), "decenio_inicio": list(first), "decenio_fin": list(last),
            "n_estaciones": int(len(stations)), "n_dias": n_dias, "ciudades": cities}


# ----------------------------------------------------------------------------- fragmentos estáticos
# La página también se lee sin JavaScript: el hero, el enunciado, el diagrama y las cifras
# se pre-renderizan aquí con la ciudad por defecto; el script sólo los vuelve a dibujar.
NEG, MID, POS = (47, 95, 208), (236, 238, 234), (226, 35, 26)


def _mix(a, b, t):
    return "rgb(%d,%d,%d)" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def diverging(v, vmax):
    if v is None:
        return "var(--mid)"
    t = max(-1.0, min(1.0, v / (vmax or 1)))
    return _mix(MID, NEG, -t) if t < 0 else _mix(MID, POS, t)


def _fmt(v, nd=2, sign=True):
    if v is None:
        return "—"
    s = f"{v:.{nd}f}".replace(".", ",")
    return ("+" if sign and v > 0 else "") + s


def stripes_svg(values, years, label, titles=True, hidden=False):
    vmax = max([abs(v) for v in values if v is not None] or [1])
    out = [f'<svg viewBox="0 0 {len(values)} 10" preserveAspectRatio="none" role="img" aria-label="{label}"{" aria-hidden=\"true\"" if hidden else ""}>']
    for i, v in enumerate(values):
        t = f"<title>{years[i]}: {_fmt(v)} °C</title>" if titles else ""
        out.append(f'<rect x="{i}" y="0" width="1.02" height="10" fill="{diverging(v, vmax)}" style="animation-delay:{i*12}ms">{t}</rect>')
    return "".join(out) + "</svg>"


def diagram_svg(seed: int = 3) -> str:
    """«Muchos en uno»: 150 rectángulos (el motivo) dispersos → comprimidos en una cinta → ordenados en filas."""
    import random
    rng = random.Random(seed)
    W, H, n = 1200, 270, 150
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Diagrama: muchos registros dispersos se comprimen en una cinta y salen ordenados en filas">']
    third = W / 3
    for i in range(n):
        if i < n // 3:                                   # dispersos, dos tonos pálidos
            x, y = rng.uniform(10, third - 30), rng.uniform(10, H - 24)
            out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="12" height="12" fill="{"var(--cold-soft)" if i % 2 else "var(--mid)"}"/>')
        elif i < 2 * n // 3:                             # cinta de tres filas
            k = i - n // 3; col, row = k // 3, k % 3
            out.append(f'<rect x="{third + 40 + col*17:.0f}" y="{H/2 - 20 + row*14:.0f}" width="12" height="12" fill="var(--ink)"/>')
        else:                                            # filas ordenadas, acento
            k = i - 2 * n // 3; col, row = k % 10, k // 10
            out.append(f'<rect x="{2*third + 40 + col*34:.0f}" y="{30 + row*44:.0f}" width="12" height="12" fill="var(--accent)"/>')
    return "".join(out) + "</svg>"


def static_fragments(data: dict, city: str | None = None) -> dict:
    cities = sorted(data["ciudades"], key=lambda c: c.casefold())
    city = city or cities[0]
    c = data["ciudades"][city]
    years = data["years"]
    t = c["tendencias"].get("TMEAN", {})
    sen = t.get("sen")
    sens = [data["ciudades"][k]["tendencias"].get("TMEAN", {}).get("sen") for k in cities]
    valid = [v for v in sens if v is not None]
    avg = sum(valid) / len(valid) if valid else None
    n_sig = sum(1 for k in cities if (data["ciudades"][k]["tendencias"].get("TMEAN", {}).get("p_mk") or 1) < 0.05 and (data["ciudades"][k]["tendencias"].get("TMEAN", {}).get("sen") or 0) > 0)
    thumbs = "".join(f'<span class="thumb">{stripes_svg(data["ciudades"][k]["anual"]["TMEAN"], years, k, titles=False, hidden=True)}</span>' for k in cities[:3])
    p = t.get("p_mk")
    n_dias_txt = f"{data['n_dias']:,}".replace(",", " ")
    return {
        "notice": ('<div class="notice"><p>Estás viendo datos de demostración, generados por el pipeline con series sintéticas: muestran cómo funciona la página, no el clima real de México. Para cargar los datos de NOAA: <code>python pipeline.py --download</code> y luego <code>python export_web.py --inject docs/index.html</code>.</p></div>' if data.get("demo") else ""),
        "herotitle": f"{city}<br>{_fmt(sen)}\u00a0°C/década" if sen is not None else f"{city}<br>sin datos suficientes",
        "herolead": f"Tendencia de la temperatura media por década desde {years[0]}, medida con registros diarios de NOAA. " + (("Significativa" if p < 0.05 else "No significativa") + f" (Mann-Kendall, p {'menor que 0,001' if p < 0.001 else _fmt(p, 3, False)})." if p is not None else ""),
        "options": "".join(f'<option value="{k}"{" selected" if k == city else ""}>{k}</option>' for k in cities),
        "hero": stripes_svg(c["anual"]["TMEAN"], years, f"{city}: una franja por año, {years[0]}–{years[-1]}, anomalía de la temperatura media"),
        "statement": f"{n_dias_txt} días medidos: cuánto se calentó cada una de {len(cities)} ciudades {thumbs} desde {years[0]}, en qué estación y con qué certeza.",
        "diagram": diagram_svg(),
        "stats": (f'<h2 id="statsTitle">Las cifras del proyecto, {years[0]}–{years[-1]}</h2>'
                  f'<div class="tile a"><b>{_fmt(avg)} °C</b><span>por década: el calentamiento promedio de la temperatura media en las {len(cities)} ciudades, según la pendiente de Sen.</span></div>'
                  f'<div class="tile b"><b>{n_sig} de {len(cities)}</b><span>ciudades con una tendencia creciente significativa (Mann-Kendall, p menor que 0,05).</span></div>'
                  f'<div class="tile c"><b>{round(data["n_dias"]/1000)} mil</b><span>días con temperatura válida tras la limpieza, de {data["n_estaciones"]} estaciones.</span></div>'),
    }


FIGURES = [
    ("tendencia_tmean_ciudades.png", "Anomalía anual de la temperatura media en las 12 ciudades, con la pendiente de Sen en rojo."),
    ("mapa_tendencias.png", "Mapa de tendencias: tamaño y color del punto según los grados por década."),
    ("cambio_por_estacion.png", "Cambio por estación del año entre el primer y el último decenio, ciudad por ciudad."),
    ("dias_calidos.png", "Días cálidos por año y ciudad, media móvil de cinco años."),
]


def figures_html(fig_dir: Path = C.FIG_DIR, max_width: int = 1100) -> str:
    """Incrusta como data URI las figuras PNG que generó el pipeline (reducidas para que la página pese poco)."""
    import base64
    import io
    try:
        from PIL import Image
    except ImportError:  # sin Pillow se usa el PNG tal cual
        Image = None
    out = []
    for name, caption in FIGURES:
        path = fig_dir / name
        if not path.exists():
            continue
        raw = path.read_bytes()
        w = h = None
        if Image is not None:
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            if im.width > max_width:
                im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
            buf = io.BytesIO(); im.save(buf, "PNG", optimize=True); raw = buf.getvalue(); w, h = im.size
        uri = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        dims = f' width="{w}" height="{h}"' if w else ""
        out.append(f'<figure><img src="{uri}" alt="{caption}" loading="lazy"{dims}><figcaption>{caption}</figcaption></figure>')
    return "".join(out)


def inject(html_path: Path, data: dict) -> None:
    html = html_path.read_text(encoding="utf-8")
    block = f'<script id="climamx-data" type="application/json">{json.dumps(data, ensure_ascii=False, separators=(",", ":"))}</script>'
    new, n = re.subn(r'<script id="climamx-data" type="application/json">.*?</script>', lambda _m: block, html, flags=re.S)
    if n != 1:
        raise SystemExit(f"No encontré el bloque climamx-data en {html_path}")
    frags = static_fragments(data)
    frags["figures"] = figures_html()
    for key, frag in frags.items():
        new, k = re.subn(rf"<!--static:{key}-->.*?<!--/static:{key}-->", lambda _m, f=frag, key=key: f"<!--static:{key}-->{f}<!--/static:{key}-->", new, flags=re.S)
        if k != 1:
            raise SystemExit(f"No encontré el marcador static:{key} en {html_path}")
    html_path.write_text(new, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(C.OUTPUT_DIR / "web_data.json"))
    ap.add_argument("--inject", help="ruta del index.html donde incrustar los datos")
    args = ap.parse_args()
    data = build()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"JSON en {args.out} ({Path(args.out).stat().st_size/1024:.0f} KB, demo={data['demo']})")
    if args.inject:
        inject(Path(args.inject), data)
        print(f"Datos incrustados en {args.inject}")


if __name__ == "__main__":
    main()
