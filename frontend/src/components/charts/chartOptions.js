// Pure helpers for the incident metric charts (MetricChart.jsx): values, states and the ECharts option. No DOM and
// no ECharts import here, so everything is unit-tested in Node. Ported from the ui-graphs prototype (chartCard,
// renderCharts, focusWindow). Data: GET /api/v1/incidents/{id}/metrics (docs/API-FOR-UI.md, item 11):
//   { from, to, incident_from, incident_to, events: [{at, kind, label}],
//     series: [{ key, title, unit, max, fired, kind, thresholds: {warning, critical, direction} | null,
//                detector_threshold, baseline: {p50, p95} | null, points: [[time, value | null]] }] }
// Every field past `points` is optional: a missing one just draws less.

const ms = (t) => (typeof t === "number" ? t : Date.parse(t));
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// 0.000022 cores, 7.32 %, 59.3 MiB, 1235: enough digits to read the value, never a long float.
export function fmtNumber(v) {
  if (v == null) return "—";
  if (Number.isInteger(v)) return String(v);
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  if (a >= 1) return v.toFixed(2);
  return String(Number(v.toPrecision(2)));
}
export const fmtValue = (v, unit) => (v == null ? "—" : `${fmtNumber(v)}${unit ? ` ${unit}` : ""}`);

// Which side of the warning / critical lines a value is on. `direction: "below"` means lower is worse (e.g. memory
// available 25 / 10 %).
export function thresholdState(value, thresholds) {
  if (value == null) return "no_data";
  if (!thresholds) return "no_threshold";
  const worse = thresholds.direction === "below" ? (v, line) => v <= line : (v, line) => v >= line;
  if (thresholds.critical != null && worse(value, thresholds.critical)) return "critical";
  if (thresholds.warning != null && worse(value, thresholds.warning)) return "warning";
  return "normal";
}

const lastValue = (series) => {
  for (let i = (series.points ?? []).length - 1; i >= 0; i -= 1) {
    const v = num(series.points[i][1]);
    if (v != null) return v;
  }
  return null;
};

// One state per chart, for its badge: the detector's own signal says "Fired"; otherwise the latest reading against
// the thresholds.
export function seriesState(series) {
  const last = lastValue(series);
  if (series.fired) return { state: "fired", last };
  return { state: thresholdState(last, series.thresholds), last };
}

// Badge text, tone (ui.jsx Pill tones) and the explanation shown on hover.
export const STATE_META = {
  fired: { label: "Fired", tone: "red", help: "The detector crossed its configured threshold and opened an alert." },
  critical: { label: "Above alert", tone: "red", help: "The latest reading is past the alert (critical) line set for this signal." },
  warning: { label: "Warning", tone: "amber", help: "The latest reading is past the warning line but not the alert line yet." },
  normal: { label: "Normal", tone: "green", help: "The latest reading is inside the limits set for this signal." },
  no_threshold: { label: "No limit set", tone: "neutral", help: "This signal has no warning or alert line, so it shows context only." },
  no_data: { label: "No data", tone: "neutral", help: "No fresh samples in this window. A gap is a missing sample, never zero." },
};

// The line at which Argus opens the incident (the detector's), else the critical threshold.
export const alertLine = (series) => num(series.detector_threshold) ?? num(series.thresholds?.critical) ?? null;

// "Focus incident": 4 minutes before the incident to 2 minutes after it (at least 5 minutes), inside the data window.
export function focusWindow(metrics) {
  if (!metrics.incident_from) return null;
  const from = ms(metrics.from), to = ms(metrics.to), start0 = ms(metrics.incident_from);
  const end0 = metrics.incident_to ? ms(metrics.incident_to) : to;
  const start = Math.max(from, start0 - 4 * 60_000);
  const end = Math.min(to, Math.max(end0 + 2 * 60_000, start + 5 * 60_000));
  return { start, end };
}

// Event markers on the lane under each chart. Tones are keys of the colours object.
export const MARKERS = {
  oom_kill: { symbol: "triangle", rotate: 180, tone: "critical", label: "OOM kill" },
  restart: { symbol: "circle", hollow: true, tone: "warning", label: "Restart" },
  deploy: { symbol: "diamond", tone: "accent", label: "Deploy" },
  alert_fired: { symbol: "triangle", tone: "critical", label: "Alert fired" },
  alert_resolved: { symbol: "circle", tone: "ok", label: "Alert resolved" },
  link_broken: { symbol: "rect", tone: "critical", label: "Link broken" },
  link_slow: { symbol: "rect", tone: "warning", label: "Link slow" },
  link_recovered: { symbol: "rect", tone: "ok", label: "Link recovered" },
};
const marker = (kind) => MARKERS[kind] ?? { symbol: "circle", tone: "muted", label: kind };

// "#rrggbb" or "rgb(r, g, b)" with an alpha.
export function alpha(color, a) {
  const hex = /^#([0-9a-f]{6})$/i.exec(color ?? "");
  if (hex) {
    const n = parseInt(hex[1], 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }
  const rgb = /^rgba?\(([^,]+),([^,]+),([^,)]+)/.exec(color ?? "");
  return rgb ? `rgba(${rgb[1].trim()}, ${rgb[2].trim()}, ${rgb[3].trim()}, ${a})` : color;
}
const fade = (c, top) => ({ type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: alpha(c, top) }, { offset: 1, color: alpha(c, 0) }] });

const ZONE_TEXT = {
  above: { critical: "Above alert", warning: "Above warning" },
  below: { critical: "Below alert", warning: "Below warning" },
};

// The ECharts option for one chart. `variant`: "hero" (the big chart, with a slider) or "compact". `view`: the
// initial zoom ({start, end} in ms) or null for the whole window. `formatTime(ms)` gives the clock in the browser's
// zone and `zone` its name; `formatAxis(ms)` is the shorter clock under the time axis. The incident band is set here in time; MetricChart widens it to >= 8 px after drawing.
export function buildChartOption({ series, metrics, colors, variant = "compact", view = null, reducedMotion = false, formatTime, formatAxis = formatTime, zone }) {
  const hero = variant === "hero";
  const from = ms(metrics.from), to = ms(metrics.to);
  const data = (series.points ?? []).map(([t, v]) => [ms(t), num(v)]);
  const t = series.thresholds ?? null;
  const alert = alertLine(series);
  const split = metrics.incident_from ? ms(metrics.incident_from) : null;
  const events = (metrics.events ?? []).map((e) => ({ ...e, t: ms(e.at) })).filter((e) => e.t >= from && e.t <= to);
  const toneColor = (tone) => colors[tone] ?? colors.muted;

  const lines = [
    ...(alert != null ? [{ name: "Alert", yAxis: alert, lineStyle: { color: alpha(colors.critical, 0.7), type: [5, 4], width: 1 }, label: { show: false } }] : []),
    ...(num(t?.warning) != null ? [{ name: "Warning", yAxis: t.warning, lineStyle: { color: alpha(colors.warning, 0.55), type: [2, 4], width: 1 }, label: { show: false } }] : []),
    ...(split != null ? [{ name: "Incident start", xAxis: split, lineStyle: { color: alpha(colors.critical, 0.6), type: [3, 3], width: 1 }, label: { show: false } }] : []),
    ...events.map((e) => ({ name: e.label, xAxis: e.t, lineStyle: { color: alpha(toneColor(marker(e.kind).tone), 0.16), type: [2, 3], width: 1 }, label: { show: false } })),
  ];
  const baseline = series.baseline && num(series.baseline.p50) != null && num(series.baseline.p95) != null
    ? [[{ name: "Normal range", yAxis: series.baseline.p50, itemStyle: { color: alpha(colors.muted, 0.12) }, label: { show: false } }, { yAxis: series.baseline.p95 }]]
    : [];

  // y axis: the API's max when it gives one; otherwise room above the peak and the alert / warning lines.
  const lineValues = [alert, num(t?.warning)].filter((v) => v != null);
  const yMax = num(series.max) ?? ((v) => Math.max(v.max, ...lineValues) * 1.15 || 1);

  const extra = [];
  const quiet = { silent: true, showSymbol: false, connectNulls: false, tooltip: { show: false }, emphasis: { disabled: true } };
  if (series.fired && split != null) {
    extra.push({ ...quiet, name: "Before the incident", type: "line", z: 1, lineStyle: { width: 0 }, areaStyle: { color: fade(colors.accent, hero ? 0.28 : 0.2) }, data: data.map(([x, v]) => [x, x <= split ? v : null]) });
    extra.push({ ...quiet, name: "During the incident area", type: "line", z: 1, lineStyle: { width: 0 }, areaStyle: { color: fade(colors.critical, hero ? 0.3 : 0.22) }, data: data.map(([x, v]) => [x, x >= split ? v : null]) });
    extra.push({ ...quiet, name: "During the incident", type: "line", z: 4, lineStyle: { width: 1.6, color: colors.critical }, data: data.map(([x, v]) => [x, x >= split ? v : null]) });
  } else {
    extra.push({ ...quiet, name: "Reading area", type: "line", z: 1, lineStyle: { width: 0 }, areaStyle: { color: fade(colors.accent, hero ? 0.24 : 0.18) }, data });
  }

  const zoomRange = view ? { startValue: view.start, endValue: view.end } : {};
  const tooltipTime = (x) => `${formatTime(x)} ${zone}`;
  const near = (x) => events.filter((e) => Math.abs(e.t - x) <= Math.max(30_000, (to - from) / 120));

  return {
    animation: !reducedMotion,
    animationDuration: 300,
    aria: { enabled: true },
    textStyle: { fontFamily: "Inter Variable, Inter, system-ui, sans-serif" },
    grid: [
      { left: 44, right: 14, top: hero ? 26 : 18, bottom: hero ? 86 : 46 },
      { left: 44, right: 14, height: 12, bottom: hero ? 52 : 24 },
    ],
    axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: alpha(colors.axis, 0.6), type: "dashed" } },
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: colors.surface,
      borderColor: colors.border,
      textStyle: { color: colors.ink, fontSize: 12 },
      extraCssText: "box-shadow:0 8px 24px -10px rgba(0,0,0,.45);border-radius:10px;",
      formatter: (params) => {
        const p = (Array.isArray(params) ? params : [params]).find((x) => x.seriesName === series.title);
        if (!p) return "";
        const [x, v] = p.value;
        const st = thresholdState(num(v), t);
        const where = st === "no_data" ? "No data" : st === "no_threshold" ? "No limit set" : st === "normal" ? "Normal" : ZONE_TEXT[t.direction === "below" ? "below" : "above"][st];
        const reading = st === "no_data" ? "No sample (a gap, not zero)" : `${fmtValue(num(v), series.unit)} · ${where}`;
        return `<strong>${esc(series.title)}</strong><br>${esc(tooltipTime(x))}<br>${esc(reading)}`
          + near(x).map((e) => `<br><span style="color:${toneColor(marker(e.kind).tone)}">●</span> ${esc(e.label)} · ${esc(formatTime(e.t))}`).join("");
      },
    },
    xAxis: [
      { type: "time", gridIndex: 0, min: from, max: to, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false } },
      { type: "time", gridIndex: 1, min: from, max: to, splitNumber: hero ? 6 : 3, axisLine: { show: true, lineStyle: { color: colors.grid } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { color: colors.axis, fontSize: 11, hideOverlap: true, margin: 10, formatter: (x) => formatAxis(x) } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, min: 0, max: yMax, splitNumber: hero ? 4 : 2, axisLabel: { color: colors.axis, fontSize: 11, showMaxLabel: false, margin: 8, formatter: (v) => fmtNumber(v) }, splitLine: { lineStyle: { color: colors.grid } } },
      { type: "category", gridIndex: 1, data: ["events"], show: false },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], filterMode: "none", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false, moveOnMouseMove: true, minValueSpan: 2 * 60_000, ...zoomRange },
      ...(hero ? [{
        type: "slider", xAxisIndex: [0, 1], filterMode: "none", height: 16, bottom: 8, left: 44, right: 14, minValueSpan: 2 * 60_000, showDetail: false,
        borderColor: colors.grid, backgroundColor: "transparent", fillerColor: alpha(colors.accent, 0.12),
        dataBackground: { lineStyle: { color: alpha(colors.muted, 0.5), width: 1 }, areaStyle: { color: alpha(colors.muted, 0.08) } },
        selectedDataBackground: { lineStyle: { color: alpha(colors.accent, 0.8), width: 1 }, areaStyle: { color: alpha(colors.accent, 0.14) } },
        handleStyle: { color: colors.surface, borderColor: alpha(colors.accent, 0.8) }, moveHandleSize: 0, ...zoomRange,
      }] : []),
    ],
    series: [
      {
        name: series.title, type: "line", xAxisIndex: 0, yAxisIndex: 0, z: 3, data, connectNulls: false, showSymbol: false,
        lineStyle: { width: 1.6, color: colors.accent }, itemStyle: { color: series.fired ? colors.critical : colors.accent }, emphasis: { disabled: true },
        markArea: { silent: true, data: baseline },
        markLine: { symbol: ["none", "none"], silent: true, data: lines },
      },
      {
        name: "Incident window", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: [],
        markArea: {
          silent: true, itemStyle: { color: alpha(colors.critical, 0.08) },
          label: { show: true, position: "insideTop", distance: 4, formatter: "Incident", color: colors.critical, fontSize: 11, fontWeight: 600 },
          data: split != null ? [[{ xAxis: split }, { xAxis: metrics.incident_to ? ms(metrics.incident_to) : to }]] : [],
        },
      },
      {
        name: "Events", type: "scatter", xAxisIndex: 1, yAxisIndex: 1, z: 5,
        tooltip: { trigger: "item", formatter: (p) => `${esc(p.name)}<br>${esc(tooltipTime(p.value[0]))}` },
        data: events.map((e) => {
          const m = marker(e.kind), c = toneColor(m.tone);
          return { name: e.label, value: [e.t, "events"], symbol: m.symbol, symbolSize: m.hollow ? 7 : 9, symbolRotate: m.rotate ?? 0, itemStyle: { color: m.hollow ? colors.surface : c, borderColor: c, borderWidth: m.hollow ? 1.5 : 0 } };
        }),
      },
      ...extra,
    ],
  };
}
