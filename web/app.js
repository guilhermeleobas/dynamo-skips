"use strict";

const STATUS = {
  P: { name: "PASSED", label: "Passed", key: "passed", color: "--app-passed" },
  S: { name: "SKIPPED", label: "Skipped", key: "skipped", color: "--app-skipped" },
  F: { name: "FAILED", label: "Failed", key: "failed", color: "--app-failed" },
  E: { name: "ERROR", label: "Error", key: "error", color: "--app-error" },
};
const PYTORCH_COMMIT_URL = "https://github.com/pytorch/pytorch/commit/";

const $ = (sel) => document.querySelector(sel);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmt = (n) => (n ?? 0).toLocaleString("en-US");
const pct = (n, d = 1) => `${(n ?? 0).toFixed(d)}%`;
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const passRate = (r) => (r.total ? (r.passed / r.total) * 100 : 0);
const skipRate = (r) => (r.total ? (r.skipped / r.total) * 100 : 0);
const chip = (code) => `<span class="chip" style="--c:var(${STATUS[code].color})">${STATUS[code].name}</span>`;
const commitLink = (c) =>
  /^[0-9a-f]{7,40}$/.test(c) ? `<a href="${PYTORCH_COMMIT_URL}${c}" target="_blank" rel="noopener"><code>${esc(c)}</code></a>` : `<code>${esc(c)}</code>`;

/** Pass/skip/fail(/error) proportions as a thin stacked bar. */
function stackbar(s, cls = "") {
  const seg = (k, c) => (s[k] ? `<span class="s-${k}" style="flex:${s[k]}" title="${STATUS[c].label}: ${fmt(s[k])}"></span>` : "");
  return `<div class="stackbar ${cls}">${seg("passed", "P")}${seg("skipped", "S")}${seg("failed", "F")}${seg("error", "E")}</div>`;
}

const state = { view: "run", run: null, tab: "overview", module: "", search: "" };
let index = null;
const runCache = new Map();
const tables = {};

// ---------- URL state (shareable links) ----------
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.view = p.get("view") === "all" ? "all" : "run";
  state.run = p.get("run");
  state.tab = ["overview", "breaks", "details"].includes(p.get("tab")) ? p.get("tab") : "overview";
  state.module = p.get("module") || "";
}
function writeHash() {
  const p = new URLSearchParams({ view: state.view });
  if (state.view === "run") {
    p.set("run", state.run);
    p.set("tab", state.tab);
    if (state.tab === "details" && state.module) p.set("module", state.module);
  }
  history.replaceState(null, "", `#${p}`);
}

// ---------- KPI tiles ----------
/** delta: {value, unit, goodWhenUp} compared with the previous run. */
function deltaHtml(d) {
  if (!d || !isFinite(d.value)) return "";
  if (Math.abs(d.value) < 1e-9) return `<span class="text-body-secondary">no change</span> vs previous run`;
  const up = d.value > 0;
  const good = up === d.goodWhenUp;
  const v = d.unit === "pp" ? `${Math.abs(d.value).toFixed(1)} pp` : fmt(Math.abs(d.value));
  return `<span class="${good ? "delta-up" : "delta-down"}"><i class="bi bi-arrow-${up ? "up" : "down"}-right"></i> ${v}</span> vs previous run`;
}
function kpis(el, items) {
  el.innerHTML = items
    .map(
      (m) => `<div class="col-6 col-lg"><div class="app-card kpi">
        <div class="kpi-head"><span>${esc(m.label)}</span>${m.icon ? `<span class="kpi-icon" style="--c:${m.color ?? "var(--bs-primary)"}"><i class="bi bi-${m.icon}"></i></span>` : ""}</div>
        <div class="kpi-value${m.text ? " text-value" : ""}" title="${esc(m.title ?? m.value)}">${esc(m.value)}</div>
        ${m.extra ?? ""}
        ${m.delta ? `<div class="kpi-sub">${deltaHtml(m.delta)}</div>` : m.sub ? `<div class="kpi-sub">${m.sub}</div>` : ""}
      </div></div>`,
    )
    .join("");
}

// ---------- DataTables ----------
/** Create the DataTable on first use, then just swap its rows. */
function dataTable(id, rows, options) {
  if (!tables[id]) {
    tables[id] = new DataTable(`#${id}`, { data: rows, deferRender: true, ...options });
    if (options.onRow) {
      $(`#${id}`).classList.add("clickable");
      $(`#${id} tbody`).addEventListener("click", (e) => {
        const tr = e.target.closest("tr");
        if (!tr || e.target.closest("summary, a")) return;
        const data = tables[id].row(tr).data();
        if (data) options.onRow(data);
      });
    }
  } else {
    tables[id].clear().rows.add(rows).draw();
  }
  return tables[id];
}
const num = (title, data, render = fmt) => ({
  title,
  data,
  className: "dt-right",
  render: (d, type) => (type === "display" ? render(d) : d),
});

async function loadRun(id) {
  if (!runCache.has(id)) {
    runCache.set(
      id,
      fetch(`data/runs/${encodeURIComponent(id)}.json`).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} loading run ${id}`);
        return r.json();
      }),
    );
  }
  return runCache.get(id);
}
const currentRun = () => index.runs.find((r) => r.id === state.run);
/** The parsed run immediately before `run` (index.runs is newest first). */
const previousRun = (run) => index.runs.slice(index.runs.indexOf(run) + 1).find((r) => r.parse_ok);

// ---------- Plotly ----------
function layout(extra = {}) {
  const ink = css("--bs-body-color"), ink2 = css("--bs-secondary-color"), grid = css("--bs-border-color");
  const ax = { gridcolor: grid, linecolor: grid, zerolinecolor: grid, automargin: true, tickfont: { size: 11 } };
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: css("--bs-body-font-family"), color: ink2, size: 12 },
    margin: { t: 32, r: 12, b: 8, l: 48 },
    height: 420,
    bargap: 0.18,
    barcornerradius: 3,
    legend: { orientation: "h", y: 1.02, yanchor: "bottom", x: 0, traceorder: "normal", font: { size: 12 } },
    hoverlabel: { bgcolor: css("--app-surface"), bordercolor: grid, font: { color: ink, family: css("--bs-body-font-family") } },
    ...extra,
    xaxis: { ...ax, ...(extra.xaxis ?? {}) },
    yaxis: { ...ax, ...(extra.yaxis ?? {}) },
  };
}
function plot(id, data, lay) {
  // With responsive: true Plotly fills its container, so the container needs the height.
  document.getElementById(id).style.height = `${lay.height}px`;
  Plotly.react(id, data, lay, { responsive: true, displayModeBar: false });
}
const statusTraces = (x, rows, valueFor, hover) =>
  ["P", "S", "F"].map((code) => ({
    type: "bar",
    name: STATUS[code].label,
    x,
    y: rows.map((r) => valueFor(r, code)),
    customdata: rows.map((r) => r[STATUS[code].key]),
    marker: { color: css(STATUS[code].color), line: { color: css("--app-surface"), width: 0.5 } },
    hovertemplate: hover(STATUS[code].label),
  }));

// ---------- Individual run: Overview ----------
function renderOverview(run) {
  const rows = Object.entries(run.modules).map(([name, s]) => ({ name, ...s, skipPct: skipRate(s), passPct: passRate(s) }));
  const byRate = rows.slice().sort((a, b) => b.skipPct - a.skipPct || b.total - a.total);
  const x = byRate.map((r) => r.name.replace(/^test_/, ""));

  plot(
    "chart-module-pct",
    statusTraces(
      x,
      byRate,
      (r, code) => (r.total ? (r[STATUS[code].key] / r.total) * 100 : 0),
      (label) => `<b>test_%{x}</b><br>${label}: %{y:.1f}% · %{customdata:,} tests<extra></extra>`,
    ),
    layout({
      barmode: "stack",
      bargap: 0.12,
      barcornerradius: 2,
      height: 400,
      xaxis: { tickangle: -60, tickfont: { size: 10 } },
      yaxis: { range: [0, 100], ticksuffix: "%" },
    }),
  );

  const top = rows.slice().sort((a, b) => b.skipped - a.skipped).slice(0, 20).reverse();
  plot(
    "chart-module-skip",
    [
      {
        type: "bar",
        orientation: "h",
        y: top.map((r) => r.name),
        x: top.map((r) => r.skipped),
        customdata: top.map((r) => [r.total, r.skipPct]),
        marker: { color: css("--app-skipped") },
        text: top.map((r) => `${fmt(r.skipped)} / ${fmt(r.total)}`),
        textposition: "outside",
        cliponaxis: false,
        textfont: { size: 10, color: css("--bs-secondary-color") },
        hovertemplate: "<b>%{y}</b><br>%{x:,} of %{customdata[0]:,} tests skipped (%{customdata[1]:.1f}%)<extra></extra>",
      },
    ],
    layout({ height: 560, margin: { t: 8, r: 64, b: 8, l: 8 }, showlegend: false, yaxis: { tickfont: { size: 11 } } }),
  );

  const footer = [
    "TOTAL", fmt(run.total), fmt(run.passed), fmt(run.skipped), fmt(run.failed), stackbar(run, "thin"), pct(skipRate(run), 1),
  ];
  $("#module-table tfoot tr").innerHTML = footer.map((v, i) => `<th class="${i && i !== 5 ? "dt-right" : ""}">${v}</th>`).join("");
  dataTable("module-table", rows, {
    columns: [
      { title: "Module", data: "name" },
      num("Tests", "total"),
      num("Pass", "passed"),
      num("Skip", "skipped"),
      num("Fail", "failed"),
      { title: "Breakdown", data: "passPct", render: (d, type, r) => (type === "display" ? stackbar(r, "thin") : d) },
      num("Skip %", "skipPct", (d) => pct(d, 1)),
    ],
    order: [[6, "desc"]],
    paging: false,
    scrollY: "430px",
    scrollCollapse: true,
    language: { search: "", searchPlaceholder: "Filter modules…" },
    onRow: (r) => {
      state.module = r.name;
      state.search = "";
      showTab("details");
    },
  });
}

// ---------- Individual run: Graph breaks ----------
function renderBreaks(run) {
  const gb = run.graph_breaks ?? [];
  const total = gb.reduce((s, [, c]) => s + c, 0);
  $("#breaks-empty").hidden = total > 0;
  $("#breaks-body").hidden = total === 0;
  if (!total) return;

  const [topReason, topCount] = gb[0];
  kpis($("#breaks-metrics"), [
    { label: "Categorized skips", value: fmt(total), icon: "tags", color: "var(--app-skipped)" },
    { label: "Distinct keys", value: fmt(gb.length), icon: "diagram-3" },
    { label: "Top issue", value: topReason, text: true, icon: "trophy", color: "var(--app-failed)" },
    { label: "Top issue share", value: pct((topCount / total) * 100), sub: `${fmt(topCount)} tests`, icon: "pie-chart" },
  ]);

  const top = gb.slice(0, 15).reverse();
  plot(
    "chart-breaks",
    [
      {
        type: "bar",
        orientation: "h",
        y: top.map(([r]) => (r.length > 70 ? `${r.slice(0, 69)}…` : r)),
        x: top.map(([, c]) => c),
        customdata: top.map(([r, c]) => [r, (c / total) * 100]),
        text: top.map(([, c]) => `${fmt(c)}  ·  ${pct((c / total) * 100)}`),
        textposition: "outside",
        cliponaxis: false,
        textfont: { size: 11, color: css("--bs-secondary-color") },
        marker: { color: css("--bs-primary") },
        hovertemplate: "%{customdata[0]}<br><b>%{x:,}</b> tests (%{customdata[1]:.1f}%)<extra></extra>",
      },
    ],
    layout({ height: Math.max(320, top.length * 30 + 40), margin: { t: 8, r: 110, b: 8, l: 8 }, showlegend: false }),
  );

  dataTable(
    "breaks-table",
    gb.map(([reason, count]) => ({ reason, count, percent: (count / total) * 100 })),
    {
      columns: [
        { title: "Reason", data: "reason" },
        num("Tests", "count"),
        {
          title: "Share",
          data: "percent",
          className: "dt-right",
          width: "180px",
          render: (d, type) =>
            type === "display"
              ? `<div class="d-flex align-items-center gap-2 justify-content-end"><div class="progress flex-grow-1" style="height:6px;max-width:110px"><div class="progress-bar" style="width:${(d / ((gb[0][1] / total) * 100)) * 100}%"></div></div><span style="min-width:3.5em">${pct(d, 1)}</span></div>`
              : d,
        },
      ],
      order: [[1, "desc"]],
      pageLength: 25,
      language: { search: "", searchPlaceholder: "Filter keys…" },
      onRow: (r) => {
        state.module = "";
        state.search = r.reason;
        showTab("details");
      },
    },
  );
}

// ---------- Individual run: Module details ----------
function reasonCell(reason, type) {
  if (type !== "display") return reason;
  const text = reason.replace(/\\n/g, "\n").trim();
  if (!text) return "";
  const [first, ...rest] = text.split("\n");
  return rest.length
    ? `<details><summary>${esc(first)}</summary><pre>${esc(rest.join("\n"))}</pre></details>`
    : esc(first);
}

function applyDetailFilters() {
  const dt = tables["detail-table"];
  if (!dt) return;
  const statuses = [...document.querySelectorAll("#status-filter input:checked")].map((i) => STATUS[i.value].name);
  dt.column(0).visible(!state.module);
  dt.column(0).search(state.module ? `^${DataTable.util.escapeRegex(state.module)}$` : "", true, false);
  dt.column(2).search(statuses.length ? `^(${statuses.join("|")})$` : "^$", true, false);
  dt.draw();
}

async function renderDetails(run) {
  const modules = Object.keys(run.modules).sort();
  if (!modules.includes(state.module)) state.module = "";
  const sel = $("#module-select");
  sel.innerHTML = `<option value="">All modules</option>${modules.map((m) => `<option>${esc(m)}</option>`).join("")}`;
  sel.value = state.module;

  const s = state.module ? run.modules[state.module] : run;
  kpis($("#module-metrics"), [
    { label: "Tests", value: fmt(s.total), icon: "collection" },
    { label: "Passed", value: fmt(s.passed), icon: "check2-circle", color: "var(--app-passed)" },
    { label: "Skipped", value: fmt(s.skipped), icon: "skip-forward-circle", color: "var(--app-skipped)" },
    { label: "Failed", value: fmt(s.failed), icon: "x-circle", color: "var(--app-failed)" },
    { label: "Error", value: fmt(s.error), icon: "exclamation-octagon", color: "var(--app-error)" },
  ]);

  const data = await loadRun(run.id);
  if (state.run !== run.id) return; // switched runs while loading
  const rows = data.tests.map(([mi, name, st, ri]) => [data.modules[mi], name, STATUS[st].name, data.reasons[ri]]);
  const dt = dataTable("detail-table", rows, {
    columns: [
      { title: "Module" },
      { title: "Test", render: (d, type) => (type === "display" ? `<span class="font-monospace small">${esc(d)}</span>` : d) },
      { title: "Status", render: (d, type) => (type === "display" ? chip(d[0]) : d) },
      { title: "Reason", className: "reason", orderable: false, render: reasonCell, width: "50%" },
    ],
    autoWidth: false,
    order: [[0, "asc"], [1, "asc"]],
    pageLength: 50,
    language: { search: "", searchPlaceholder: "Search test name or reason…" },
  });
  if (state.search !== null) {
    dt.search(state.search);
    state.search = null; // only applied once; afterwards the search box owns it
  }
  applyDetailFilters();
}

// ---------- All runs summary ----------
function renderAll() {
  const runs = index.runs;
  const parsed = runs.filter((r) => r.parse_ok);
  const first = parsed.at(-1), last = parsed[0];
  kpis($("#top-metrics"), [
    { label: "Saved runs", value: fmt(runs.length), icon: "archive", sub: `${fmt(parsed.length)} parsed` },
    { label: "Date range", value: `${first?.date ?? "–"} → ${last?.date ?? "–"}`, text: true, icon: "calendar-range" },
    {
      label: "Latest pass rate",
      value: pct(passRate(last)),
      icon: "speedometer2",
      color: "var(--app-passed)",
      sub: first ? deltaHtml({ value: passRate(last) - passRate(first), unit: "pp", goodWhenUp: true }).replace("vs previous run", "since first run") : "",
    },
    {
      label: "Avg pass rate",
      value: pct(parsed.length ? parsed.reduce((s, r) => s + passRate(r), 0) / parsed.length : 0),
      icon: "bar-chart-line",
      sub: `${fmt(parsed.reduce((s, r) => s + r.total, 0))} tests across all runs`,
    },
  ]);

  const trend = parsed.slice().reverse(); // oldest -> newest
  const x = trend.map((r) => r.date);
  const primary = css("--bs-primary");
  plot(
    "chart-trend",
    [
      {
        type: "scatter",
        mode: "lines+markers",
        x,
        y: trend.map(passRate),
        customdata: trend.map((r) => [r.passed, r.total, r.commit]),
        fill: "tozeroy",
        fillcolor: `rgba(${css("--bs-primary-rgb")}, 0.12)`,
        line: { color: primary, width: 2.5, shape: "spline", smoothing: 0.4 },
        marker: { size: 6, color: primary },
        hovertemplate: "<b>%{x|%b %d, %Y}</b> · %{customdata[2]}<br>Pass rate: <b>%{y:.1f}%</b><br>%{customdata[0]:,} of %{customdata[1]:,} tests<extra></extra>",
      },
    ],
    layout({ showlegend: false, xaxis: { type: "date" }, yaxis: { range: [0, 100], ticksuffix: "%" } }),
  );
  plot(
    "chart-counts",
    statusTraces(x, trend, (r, code) => r[STATUS[code].key], (label) => `${label}: %{y:,}<extra></extra>`),
    layout({ barmode: "stack", hovermode: "x unified", xaxis: { type: "date" }, yaxis: { title: { text: "Tests" } } }),
  );

  const rate = (d, type, r) => (type === "display" ? (r.parse_ok ? pct(d, 1) : "") : d);
  dataTable(
    "run-table",
    runs.map((r) => ({ ...r, passRate: passRate(r), skipRate: skipRate(r) })),
    {
      columns: [
        { title: "Date", data: "date", render: (d, type) => (type === "display" ? `<span class="fw-medium">${esc(d)}</span>` : d) },
        { title: "Commit", data: "commit", render: (d, type) => (type === "display" ? commitLink(d) : d) },
        num("Tests", "total"),
        num("Passed", "passed"),
        num("Skipped", "skipped"),
        num("Failed", "failed"),
        { title: "Breakdown", data: "passRate", orderable: false, render: (d, type, r) => (type === "display" && r.parse_ok ? stackbar(r, "thin") : "") },
        { title: "Pass rate", data: "passRate", className: "dt-right", render: rate },
        { title: "Skip rate", data: "skipRate", className: "dt-right", render: rate },
        { title: "Parsed", data: "parse_ok", className: "dt-center", render: (d) => (d ? '<i class="bi bi-check-circle-fill delta-up"></i>' : '<i class="bi bi-x-circle-fill delta-down"></i>') },
      ],
      order: [[0, "desc"], [1, "desc"]],
      pageLength: 25,
      language: { search: "", searchPlaceholder: "Filter runs…" },
      onRow: (r) => {
        if (!r.parse_ok) return;
        state.view = "run";
        state.run = r.id;
        state.tab = "overview";
        render();
        scrollTo({ top: 0 });
      },
    },
  );
}

// ---------- Orchestration ----------
function renderTab() {
  writeHash();
  const run = currentRun();
  if (!run?.parse_ok) return showError(`Could not parse results from ${run?.file ?? state.run}.`);
  $("#error").hidden = true;
  if (state.tab === "overview") renderOverview(run);
  else if (state.tab === "breaks") renderBreaks(run);
  else renderDetails(run).catch((e) => showError(e.message));
}

/** Switch tab; Bootstrap fires shown.bs.tab (-> renderTab) unless it is already active. */
function showTab(tab) {
  const btn = $(`.nav-link[data-tab="${tab}"]`);
  if (btn.classList.contains("active")) {
    state.tab = tab;
    renderTab();
  } else bootstrap.Tab.getOrCreateInstance(btn).show();
}

function renderRunHeader(run) {
  const prev = previousRun(run);
  $("#page-title").textContent = `Run of ${run.date}`;
  $("#page-subtitle").innerHTML = `PyTorch ${commitLink(run.commit)} · CPython test suite with <code>PYTORCH_TEST_WITH_DYNAMO=1</code>`;
  if (!run.parse_ok) return;
  const d = (k, goodWhenUp) => (prev ? { value: run[k] - prev[k], goodWhenUp } : null);
  kpis($("#top-metrics"), [
    { label: "Total tests", value: fmt(run.total), icon: "collection", delta: d("total", true) },
    { label: "Passing", value: fmt(run.passed), icon: "check2-circle", color: "var(--app-passed)", delta: d("passed", true) },
    { label: "Skipped", value: fmt(run.skipped), icon: "skip-forward-circle", color: "var(--app-skipped)", delta: d("skipped", false) },
    {
      label: "Pass rate",
      value: pct(passRate(run)),
      icon: "speedometer2",
      color: "var(--app-passed)",
      extra: `<div class="mt-2">${stackbar(run)}</div>`,
      delta: prev ? { value: passRate(run) - passRate(prev), unit: "pp", goodWhenUp: true } : null,
    },
  ]);
}

function render() {
  writeHash();
  $(`#view-btn-${state.view}`).checked = true;
  $("#view-run").hidden = state.view !== "run";
  $("#view-all").hidden = state.view !== "all";
  $("#run-picker").hidden = state.view !== "run";
  $("#run-select").value = state.run;

  const run = state.view === "run" ? currentRun() : null;
  $("#footer-run").innerHTML = run ? `File: <code>${esc(run.file)}</code>` : `${fmt(index.runs.length)} report files in <code>data/</code>`;

  if (state.view === "all") {
    $("#page-title").textContent = "All runs";
    $("#page-subtitle").textContent = "How Dynamo's CPython test coverage evolves over time";
    renderAll();
  } else {
    renderRunHeader(run);
    showTab(state.tab);
  }
}

function showError(msg) {
  $("#error").textContent = msg;
  $("#error").hidden = false;
}

async function init() {
  try {
    const res = await fetch("data/runs.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    index = await res.json();
  } catch (e) {
    return showError(`Could not load data/runs.json (${e.message}). Run build_site.py first.`);
  }
  if (!index.runs.length) return showError("No test output found under data/. Add runs and rebuild.");
  $("#generated").textContent = `updated ${new Date(index.generated).toLocaleString()}`;

  readHash();
  if (!index.runs.some((r) => r.id === state.run)) state.run = (index.runs.find((r) => r.parse_ok) ?? index.runs[0]).id;
  state.search = "";

  $("#run-select").innerHTML = index.runs
    .map((r) => `<option value="${esc(r.id)}">${esc(r.date)} · ${esc(r.commit)}${r.parse_ok ? "" : " (unparsed)"}</option>`)
    .join("");
  $("#status-filter").innerHTML = Object.keys(STATUS)
    .map(
      (code) => `<span class="status-toggle"><input class="btn-check" type="checkbox" id="st-${code}" value="${code}" checked autocomplete="off">
        <label for="st-${code}">${chip(code)}</label></span>`,
    )
    .join("");

  document.querySelectorAll('input[name="view"]').forEach((i) =>
    i.addEventListener("change", () => {
      state.view = i.value;
      render();
    }),
  );
  document.querySelectorAll(".nav-link[data-tab]").forEach((b) =>
    b.addEventListener("shown.bs.tab", () => {
      state.tab = b.dataset.tab;
      renderTab();
    }),
  );
  $("#run-select").addEventListener("change", (e) => {
    state.run = e.target.value;
    render();
  });
  $("#module-select").addEventListener("change", (e) => {
    state.module = e.target.value;
    renderTab();
  });
  $("#status-filter").addEventListener("change", applyDetailFilters);
  // Re-theme charts when the OS color scheme flips (index.html updates data-bs-theme first).
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);

  render();
}

init();
