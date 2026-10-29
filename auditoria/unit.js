// Extrae el script de docs/index.html, lo ejecuta con un DOM mínimo y prueba las funciones puras
// y los renders con casos límite (nulos, series vacías, p-valores raros).
const fs = require("fs");
const path = require("path");
const html = fs.readFileSync(path.join(__dirname, "..", "docs", "index.html"), "utf8");
const json = html.match(/<script id="climamx-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
let js = html.match(/<script>\n([\s\S]*?)<\/script>\n<\/body>/)[1];
// exponer las funciones internas para probarlas
js = js.replace("renderTiles();\n  render();", "renderTiles();\n  render();\n  globalThis.__t = { fmt, fmtP, diverging, mean, maxAbs, senLine, stripesSVG, seriesChart, seasonChart, heatmap, hotChart, mapChart, summary, cityDesc, rows };");

const elems = {};
const mk = (id) => elems[id] || (elems[id] = {
  id, innerHTML: "", textContent: "", value: "", dataset: {}, attrs: {}, listeners: {}, classList: { add() {}, remove() {}, contains() { return false; } }, style: {}, open: false,
  setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; }, removeAttribute(k) { delete this.attrs[k]; },
  addEventListener(t, f) { this.listeners[t] = f; }, querySelector() { return null; }, querySelectorAll() { return []; }, insertAdjacentHTML(_p, h) { this.innerHTML = h + this.innerHTML; },
});
const document = { getElementById: (id) => (id === "climamx-data" ? { textContent: json } : mk(id)), querySelectorAll: () => [], querySelector: () => null, documentElement: mk("html") };
const localStorage = { getItem() { return null; }, setItem() {} };
const window = { matchMedia: () => ({ matches: false }), addEventListener() {} };
const location = { hash: "" }, history = { replaceState() {} };
new Function("document", "localStorage", "window", "location", "history", "setTimeout", js)(document, localStorage, window, location, history, () => {});
const t = globalThis.__t;
const DATA = JSON.parse(json);

let pass = 0, fail = 0;
function check(name, cond, extra) { if (cond) pass++; else { fail++; console.log("FAIL " + name + (extra !== undefined ? " → " + JSON.stringify(extra) : "")); } }

// formato
check("fmt redondea y usa coma", t.fmt(0.255, 2) === "0,26" || t.fmt(0.255, 2) === "0,25");
check("fmt signo", t.fmt(0.3, 1, true) === "+0,3" && t.fmt(-0.3, 1, true) === "-0,3" && t.fmt(0, 1, true) === "0,0");
check("fmt nulos", t.fmt(null) === "—" && t.fmt(undefined) === "—" && t.fmt(NaN) === "—");
check("fmtP", t.fmtP(0.0004) === "menor que 0,001" && t.fmtP(0.011) === "0,011" && t.fmtP(null) === "—");
// color divergente
check("diverging 0 = tono medio", t.diverging(0, 1) === "rgb(236,238,234)");
check("diverging positivo rojo", t.diverging(1, 1) === "rgb(226,35,26)");
check("diverging negativo azul", t.diverging(-1, 1) === "rgb(47,95,208)");
check("diverging satura fuera de rango", t.diverging(5, 1) === t.diverging(1, 1));
check("diverging nulo", t.diverging(null, 1) === "var(--mid)");
check("diverging vmax 0 no divide por cero", typeof t.diverging(0.5, 0) === "string");
// estadísticos
check("mean ignora nulos", t.mean([1, null, 3, NaN]) === 2);
check("mean vacío NaN", isNaN(t.mean([])));
check("maxAbs", t.maxAbs([-3, 2, null]) === 3 && t.maxAbs([]) === 1);
// línea de Sen: pasa por la media y tiene la pendiente pedida
const ln = t.senLine([2000, 2001, 2002, 2003], [0, 1, 2, 3], 10);
check("senLine pendiente", ln && Math.abs((ln.y1 - ln.y0) / (ln.x1 - ln.x0) - 1) < 1e-9, ln);
check("senLine sin datos", t.senLine([2000], [null], 1) === null && t.senLine([2000, 2001], [1, 2], null) === null);
// renders con casos límite
check("stripes con nulos", /<svg/.test(t.stripesSVG([null, null], { label: "x" })));
check("series toda nula no truena", /<svg/.test(t.seriesChart(DATA.years, DATA.years.map(() => null), {}, "TMEAN", "X")));
check("series sin tendencia", /<svg/.test(t.seriesChart(DATA.years, DATA.years.map((_, i) => i * 0.01), null, "TMEAN", "X")));
check("season con decenios vacíos", /<svg/.test(t.seasonChart({}, "X")));
check("heatmap vacío", /<svg/.test(t.heatmap(DATA.years, [], "X")));
check("hot sin valores", /<svg/.test(t.hotChart(DATA.years, DATA.years.map(() => null), "X")));
check("escape en nombres", !/<script/.test(t.mapChart("TMEAN", "<script>")));
const S = t.summary();
check("summary promedio coherente", S.avg > -5 && S.avg < 5 && S.nSig >= 0 && S.nSig <= Object.keys(DATA.ciudades).length, S);
const r = t.rows("TMEAN");
check("ranking ordenado desc", r.every((o, i) => i === 0 || (r[i - 1].sen ?? -99) >= (o.sen ?? -99)));
check("cityDesc texto", /por década/.test(t.cityDesc(Object.keys(DATA.ciudades)[0], "TMEAN")));
// render completo sin NaN
const all = Object.values(elems).map((e) => e.innerHTML + " " + e.textContent).join(" ");
check("sin NaN/undefined en el render inicial", !/NaN|undefined/.test(all));
console.log(`${pass} pruebas pasaron, ${fail} fallaron`);
process.exit(fail ? 1 : 0);
