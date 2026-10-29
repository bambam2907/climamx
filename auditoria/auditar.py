"""Tres auditores sobre docs/index.html. Cada uno escribe sus hallazgos en auditoria/reporte.json.

    python auditoria/auditar.py

1. Auditor visual y responsivo: desbordes, objetivos táctiles, textos cortados, capturas por viewport y tema.
2. Auditor de accesibilidad: axe-core (WCAG 2.x A/AA), orden de encabezados, foco visible, etiquetas, reduced-motion.
3. Auditor de lógica: integridad JSON vs SQLite, consistencia estático/dinámico, interacciones y estado (ciudad, variable,
   vista, preview, deep link, localStorage, tema), textos sin NaN/undefined, sin errores de consola.
"""
from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "index.html").resolve().as_uri()
OUT = ROOT / "auditoria"
CAP = OUT / "capturas"
CAP.mkdir(parents=True, exist_ok=True)
AXE = pathlib.Path("/home/claude/a11y/node_modules/axe-core/axe.min.js").read_text(encoding="utf-8")
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
DATA = json.loads(re.search(r'<script id="climamx-data" type="application/json">(.*?)</script>', HTML, re.S).group(1))
report = {"visual": [], "a11y": [], "logica": [], "capturas": []}


def finding(section, sev, title, detail=""):
    report[section].append({"sev": sev, "title": title, "detail": detail})


def new_page(b, w, h, **kw):
    pg = b.new_page(viewport={"width": w, "height": h}, **kw)
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console." + m.type + ": " + m.text) if m.type in ("error", "warning") and "fonts.googleapis" not in m.text and "ERR_NAME_NOT_RESOLVED" not in m.text else None)
    pg.goto(PAGE)
    pg.wait_for_timeout(700)
    return pg, errs


# ----------------------------------------------------------------------------- 1. visual y responsivo
def auditor_visual(b):
    for w, h, name in [(1440, 900, "desktop"), (1024, 768, "laptop"), (768, 1024, "tablet"), (390, 844, "movil"), (320, 568, "movil-chico")]:
        pg, errs = new_page(b, w, h)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        if sw > w:
            finding("visual", "P1", f"Desborde horizontal a {w}px", f"scrollWidth {sw} > viewport {w}")
        # objetivos táctiles en viewports táctiles
        if w <= 768:
            small = pg.evaluate("""() => Array.from(document.querySelectorAll('a,button,select,summary,[role=button]')).map(el => {
                const r = el.getBoundingClientRect(); return {t: (el.innerText||el.getAttribute('aria-label')||el.tagName).trim().slice(0,30), w: Math.round(r.width), h: Math.round(r.height), vis: r.width>0 && r.height>0}; })
                .filter(o => o.vis && (o.w < 44 || o.h < 44))""")
            for o in small:
                finding("visual", "P2", f"Objetivo táctil menor a 44px a {w}px", f"{o['t']!r}: {o['w']}×{o['h']}px")
        # textos recortados (overflow con texto escondido)
        clipped = pg.evaluate("""() => Array.from(document.querySelectorAll('h1,h2,h3,p,button,a,span,td,th,figcaption')).filter(el => {
            const cs = getComputedStyle(el); if (el.closest('svg') || cs.overflow === 'visible' && el.tagName !== 'BUTTON') return false;
            return el.scrollWidth > el.clientWidth + 2 && cs.overflowX !== 'auto' && cs.overflowX !== 'scroll'; }).map(el => el.tagName + ': ' + (el.innerText||'').trim().slice(0,40))""")
        for c in clipped:
            finding("visual", "P2", f"Texto recortado a {w}px", c)
        # líneas de titulares (h1/h2 a ≤ 2 líneas)
        lines = pg.evaluate("""() => Array.from(document.querySelectorAll('h1,h2')).map(el => { const lh = parseFloat(getComputedStyle(el).lineHeight); return {t: el.innerText.trim().slice(0,40), lines: Math.round(el.getBoundingClientRect().height / lh)}; }).filter(o => o.lines > 2)""")
        for o in lines:
            finding("visual", "P2", f"Titular a {o['lines']} líneas a {w}px", o["t"])
        # el plato pegajoso no debe tapar la columna (escritorio)
        if w >= 1024:
            pg.evaluate("window.scrollTo(0, document.getElementById('explorador').offsetTop + 400)")
            pg.wait_for_timeout(200)
            ov = pg.evaluate("""() => { const a = document.querySelector('.plate').getBoundingClientRect(), b = document.querySelector('.col').getBoundingClientRect();
                return a.right > b.left + 2; }""")
            if ov:
                finding("visual", "P1", f"El plato pegajoso se encima a la columna a {w}px")
            pg.evaluate("window.scrollTo(0,0)")
        pg.screenshot(path=str(CAP / f"{name}-fold.png"))
        report["capturas"].append(f"{name}-fold.png")
        if name in ("desktop", "movil"):
            pg.screenshot(path=str(CAP / f"{name}-completa.png"), full_page=True)
            report["capturas"].append(f"{name}-completa.png")
        for e in errs:
            finding("visual", "P1", f"Error de consola a {w}px", e)
        pg.close()
    # tema oscuro: capturas y contraste lo revisa axe en el auditor 2
    pg, errs = new_page(b, 1440, 900, color_scheme="dark")
    pg.screenshot(path=str(CAP / "desktop-oscuro.png"))
    report["capturas"].append("desktop-oscuro.png")
    pg.close()
    # fuentes: ¿qué familia renderiza realmente el h1?
    pg, _ = new_page(b, 1440, 900)
    fam = pg.evaluate("getComputedStyle(document.querySelector('h1')).fontFamily")
    finding("visual", "info", "Familia tipográfica del h1 (en este entorno sin red carga el respaldo)", fam)
    pg.close()


# ----------------------------------------------------------------------------- 2. accesibilidad
def run_axe(pg):
    pg.add_script_tag(content=AXE)
    return pg.evaluate("""async () => { const r = await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}});
        return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0,4).map(n => n.target.join(' ') + ' — ' + (n.failureSummary||'').split('\\n')[1]) , count: v.nodes.length})); }""")


def auditor_a11y(b):
    for w, h, scheme in [(1440, 900, "light"), (390, 844, "light"), (1440, 900, "dark")]:
        pg, errs = new_page(b, w, h, color_scheme=scheme)
        pg.evaluate("document.getElementById('dataDetails').open = true")  # auditar también la tabla
        pg.wait_for_timeout(300)
        for v in run_axe(pg):
            sev = {"critical": "P0", "serious": "P1", "moderate": "P2", "minor": "P3"}.get(v["impact"], "P3")
            finding("a11y", sev, f"axe {v['id']} ({v['count']} nodos, {w}px {scheme}): {v['help']}", "; ".join(v["nodes"]))
        pg.close()
    pg, _ = new_page(b, 1440, 900)
    # orden de encabezados y landmarks
    heads = pg.evaluate("Array.from(document.querySelectorAll('h1,h2,h3')).map(h => h.tagName + ' ' + h.innerText.trim().slice(0,50))")
    levels = [int(x[1]) for x in heads]
    if levels.count(1) != 1:
        finding("a11y", "P1", "Debe haber exactamente un h1", str(levels.count(1)))
    for i in range(1, len(levels)):
        if levels[i] - levels[i - 1] > 1:
            finding("a11y", "P2", "Salto de nivel de encabezado", f"{heads[i-1]} → {heads[i]}")
    lands = pg.evaluate("['header','nav','main','footer'].map(t => t + ':' + document.querySelectorAll(t).length).join(' ')")
    finding("a11y", "info", "Landmarks", lands)
    # foco visible y orden de tabulación en los primeros 40 elementos
    seq, no_ring = [], []
    for _ in range(40):
        pg.keyboard.press("Tab")
        info = pg.evaluate("""() => { const el = document.activeElement; if (!el || el === document.body) return null; const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect(); return {tag: el.tagName, text: (el.innerText||el.getAttribute('aria-label')||el.value||'').trim().slice(0,30), outline: cs.outlineStyle + ' ' + cs.outlineWidth, w: r.width, h: r.height}; }""")
        if not info:
            break
        seq.append(info["tag"] + ":" + info["text"])
        if info["outline"].startswith("none") or info["outline"].endswith("0px"):
            no_ring.append(info["tag"] + ":" + info["text"])
    finding("a11y", "info", "Orden de tabulación (primeros elementos)", " → ".join(seq[:14]))
    for n in no_ring:
        finding("a11y", "P1", "Elemento enfocable sin anillo de foco visible", n)
    # etiqueta del select y estados aria
    lbl = pg.evaluate("!!document.querySelector('label[for=citySelect]')")
    if not lbl:
        finding("a11y", "P1", "El select de ciudad no tiene label asociado")
    pressed = pg.evaluate("document.querySelectorAll('#viewTabs [aria-pressed=true]').length + document.querySelectorAll('#varTabs [aria-pressed=true]').length")
    if pressed != 2:
        finding("a11y", "P2", "Los grupos de pestañas deben tener exactamente un botón presionado cada uno", str(pressed))
    svgs = pg.evaluate("Array.from(document.querySelectorAll('svg')).filter(s => !s.getAttribute('aria-label') && !s.getAttribute('aria-hidden')).length")
    if svgs:
        finding("a11y", "P2", "SVG sin aria-label ni aria-hidden", str(svgs))
    imgs = pg.evaluate("Array.from(document.querySelectorAll('img')).filter(i => !i.alt).length")
    if imgs:
        finding("a11y", "P1", "Imágenes sin alt", str(imgs))
    pg.close()
    # reduced motion: nada debe animarse ni quedar oculto
    pg, _ = new_page(b, 1440, 900, reduced_motion="reduce")
    hidden = pg.evaluate("Array.from(document.querySelectorAll('[data-reveal]')).filter(el => getComputedStyle(el).opacity !== '1').length")
    anim = pg.evaluate("getComputedStyle(document.querySelector('.stripes rect')).animationName")
    if hidden:
        finding("a11y", "P1", "Con reduced-motion hay bloques con opacidad < 1", str(hidden))
    if anim != "none":
        finding("a11y", "P2", "Con reduced-motion las franjas siguen animadas", anim)
    pg.close()
    # zoom de texto: 200 % no debe producir desborde horizontal
    pg, _ = new_page(b, 1280, 800)
    pg.evaluate("document.documentElement.style.fontSize = '200%'")
    pg.wait_for_timeout(300)
    sw = pg.evaluate("document.documentElement.scrollWidth")
    if sw > 1280:
        finding("a11y", "P2", "Con texto al 200 % aparece desborde horizontal", str(sw))
    pg.close()


# ----------------------------------------------------------------------------- 3. lógica
def auditor_logica(b):
    # 3a. integridad del JSON contra el almacén
    con = sqlite3.connect(ROOT / "data" / "climamx.sqlite")
    tt = {(r[0], r[1]): r[2] for r in con.execute("SELECT ciudad, variable, sen_dec FROM tendencias")}
    cities = DATA["ciudades"]
    if len(cities) != len({r[0] for r in con.execute("SELECT DISTINCT city FROM estaciones")}):
        finding("logica", "P1", "El JSON no tiene todas las ciudades del almacén")
    for c, d in cities.items():
        for v in ("TMEAN", "TMAX", "TMIN"):
            j = d["tendencias"].get(v, {}).get("sen")
            if j is None or abs(j - round(tt[(c, v)], 2)) > 0.005:
                finding("logica", "P1", f"Sen de {c}/{v} difiere entre JSON y SQLite", f"{j} vs {tt[(c, v)]}")
            if len(d["anual"][v]) != len(DATA["years"]):
                finding("logica", "P1", f"Serie anual de {c}/{v} con longitud distinta a years")
        if len(d["heatmap"]) != len(DATA["years"]) or any(len(r) != 12 for r in d["heatmap"]):
            finding("logica", "P1", f"Heatmap de {c} no es años × 12")
        # la anomalía promedio en el periodo base debe ser ≈ 0 (validación del cálculo de climatología)
        b0, b1 = DATA["baseline"]
        base = [a for y, a in zip(DATA["years"], d["anual"]["TMEAN"]) if b0 <= y <= b1 and a is not None]
        m = sum(base) / len(base) if base else None
        if m is None or abs(m) > 0.1:
            finding("logica", "P2", f"Anomalía media en el periodo base no es ≈ 0 para {c}", f"{m}")
        for k in ("DEF", "MAM", "JJA", "SON"):
            if k not in d["decenios"]:
                finding("logica", "P2", f"Falta la estación {k} en decenios de {c}")
    # 3b. consistencia entre el HTML estático y lo que dibuja el script
    static_title = re.sub(r"<[^>]+>", " ", re.search(r"<!--static:herotitle-->(.*?)<!--/static:herotitle-->", HTML, re.S).group(1))
    pg, errs = new_page(b, 1440, 900)
    pg.evaluate("localStorage.clear()")
    pg.reload(); pg.wait_for_timeout(600)
    live_title = pg.inner_text("#heroTitle")
    norm = lambda s: re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip()
    if norm(static_title) != norm(live_title):
        finding("logica", "P2", "El titular estático (sin JS) y el dinámico no coinciden", f"{norm(static_title)!r} vs {norm(live_title)!r}")
    # 3c. interacciones: todas las ciudades × variables
    bad = []
    for city in sorted(cities):
        pg.select_option("#citySelect", city); pg.wait_for_timeout(120)
        for var, btn in [("TMEAN", "Temperatura media"), ("TMAX", "Máxima, los días"), ("TMIN", "Mínima, las noches")]:
            pg.click(f"#varTabs >> text={btn}"); pg.wait_for_timeout(80)
            sen = cities[city]["tendencias"][var]["sen"]
            expected = (("+" if sen > 0 else "") + f"{sen:.2f}".replace(".", ","))
            h1 = pg.inner_text("#heroTitle")
            fig = pg.inner_text("#figures")
            cur = pg.get_attribute("#rankList [aria-current=true]", "data-city")
            if city not in h1 or expected not in h1 or expected not in fig or cur != city:
                bad.append(f"{city}/{var}: h1={h1!r} cur={cur}")
            body = pg.inner_text("main")
            if re.search(r"\bNaN\b|undefined|null", body):
                bad.append(f"{city}/{var}: NaN/undefined en el texto")
    for x in bad:
        finding("logica", "P1", "Inconsistencia al cambiar ciudad/variable", x)
    # vistas del plato
    for view in ["Estaciones del año", "Mes a mes", "Días cálidos", "Serie anual"]:
        pg.click(f"#viewTabs >> text={view}"); pg.wait_for_timeout(120)
        vis = pg.evaluate("document.querySelectorAll('.frame > div:not(.ghost) svg').length")
        if vis != 1:
            finding("logica", "P1", f"La vista '{view}' no muestra exactamente una gráfica visible", str(vis))
    # preview con hover y foco, restauración al salir
    pg.select_option("#citySelect", "Acapulco"); pg.wait_for_timeout(120)
    pg.hover("#rankList [data-city='Mexicali']"); pg.wait_for_timeout(150)
    cap = pg.inner_text("#plateCaption")
    if "Mexicali (vista previa)" not in cap:
        finding("logica", "P1", "El hover sobre una ciudad no muestra la vista previa", cap[:60])
    if pg.inner_text("#heroTitle").split("\n")[0] != "Acapulco":
        finding("logica", "P1", "La vista previa cambió la selección (no debía)")
    pg.mouse.move(5, 5); pg.wait_for_timeout(150)
    if "vista previa" in pg.inner_text("#plateCaption"):
        finding("logica", "P1", "Al salir de la lista no se restaura la gráfica de la ciudad elegida")
    pg.focus("#rankList [data-city='Monterrey']"); pg.wait_for_timeout(120)
    if "Monterrey (vista previa)" not in pg.inner_text("#plateCaption"):
        finding("logica", "P1", "El foco con teclado no muestra la vista previa")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(150)
    if pg.inner_text("#heroTitle").split("\n")[0] != "Monterrey":
        finding("logica", "P1", "Enter sobre una fila no selecciona la ciudad")
    # mapa con teclado
    pg.focus("#map [data-city='Mérida']"); pg.keyboard.press("Enter"); pg.wait_for_timeout(150)
    if pg.inner_text("#heroTitle").split("\n")[0] != "Mérida":
        finding("logica", "P1", "Enter sobre una ciudad del mapa no la selecciona")
    # tabla perezosa
    pg.click("#dataDetails summary"); pg.wait_for_timeout(150)
    n = pg.evaluate("document.querySelectorAll('#dataTable tr').length")
    if n != len(DATA["years"]) + 1:
        finding("logica", "P1", "La tabla de datos no tiene una fila por año", str(n))
    # deep link y persistencia
    pg.goto(PAGE + "#ciudad=Hermosillo"); pg.wait_for_timeout(500)
    if pg.inner_text("#heroTitle").split("\n")[0] != "Hermosillo":
        finding("logica", "P1", "El deep link #ciudad= no selecciona la ciudad")
    pg.goto(PAGE); pg.wait_for_timeout(500)
    if pg.inner_text("#heroTitle").split("\n")[0] != "Hermosillo":
        finding("logica", "P2", "La última ciudad no persiste entre visitas (localStorage)")
    # tema
    pg.click("#themeBtn"); pg.wait_for_timeout(100)
    th = pg.get_attribute("html", "data-theme")
    if th not in ("dark", "light"):
        finding("logica", "P2", "El botón de tema no cambia data-theme", str(th))
    for e in errs:
        finding("logica", "P1", "Error de consola durante las interacciones", e)
    pg.close()
    # 3d. pruebas unitarias de las funciones puras del script (en node)
    import subprocess
    r = subprocess.run(["node", str(OUT / "unit.js")], capture_output=True, text=True)
    for line in r.stdout.strip().splitlines():
        if line.startswith("FAIL"):
            finding("logica", "P1", "Prueba unitaria fallida", line)
    finding("logica", "info", "Pruebas unitarias", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])


with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--no-sandbox"])
    auditor_visual(b)
    auditor_a11y(b)
    auditor_logica(b)
    b.close()

(OUT / "reporte.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
for sec in ("visual", "a11y", "logica"):
    print(f"\n== {sec.upper()} ==")
    for f in report[sec]:
        print(f"[{f['sev']}] {f['title']}" + (f"\n      {f['detail'][:300]}" if f["detail"] else ""))
