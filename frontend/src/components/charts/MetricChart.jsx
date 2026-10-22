import { useEffect, useRef, useState } from "react";
import { clock, clockHM, zoneLabel } from "../../utils/format.js";
import { Hint, Pill } from "../ui.jsx";
import { alertLine, buildChartOption, fmtNumber, fmtValue, seriesState, STATE_META } from "./chartOptions.js";
import { init } from "./echarts.js";

// One metric chart (ECharts, SVG). The option comes from chartOptions.js; this component owns the instance: created
// once per mount, redrawn when the data, the variant or the theme colours change (keeping the current zoom while the
// time window is the same), resized with its box, and disposed on unmount. `register` adds the instance to its
// ChartGrid, which links the charts' zoom and crosshair and drives Focus / Reset.
const ms = (t) => (typeof t === "number" ? t : Date.parse(t));
const reducedMotion = () => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
const DELTA_TONE = { red: "text-red-300", amber: "text-amber-300", green: "text-emerald-300", neutral: "text-muted" };

// The line under the big number: how the latest reading compares with the normal range, else with the alert line.
function deltaOf(series, last) {
  if (last == null) return null;
  const b = series.baseline;
  if (b && b.p95 > 0 && last > b.p95 * 1.1) return { text: `+${Math.round(((last - b.p95) / b.p95) * 100)}% over normal`, tone: series.fired ? "red" : "amber" };
  if (b && b.p50 > 0 && last < b.p50 * 0.9) return { text: `${Math.round(((b.p50 - last) / b.p50) * 100)}% under normal`, tone: "amber" };
  if (b) return { text: "Within normal range", tone: "green" };
  const alert = alertLine(series);
  return alert != null ? { text: `Alert at ${fmtValue(alert, series.unit)}`, tone: "neutral" } : null;
}

export default function MetricChart({ series, metrics, variant = "compact", colors, group, view, register }) {
  const el = useRef(null);
  const chartRef = useRef(null);
  const latest = useRef({});
  latest.current = { series, metrics, view };
  const drawn = useRef(null);
  const drawRef = useRef(null);
  const [viewLabel, setViewLabel] = useState("");
  const hero = variant === "hero";
  const empty = !(series.points ?? []).some((p) => typeof p[1] === "number");
  const { state, last } = seriesState(series);
  const meta = STATE_META[state];
  const delta = deltaOf(series, last);
  const alert = alertLine(series);

  useEffect(() => {
    if (empty || !el.current) return undefined;
    const chart = init(el.current, null, { renderer: "svg" });
    chart.group = group;
    chartRef.current = chart;
    const unregister = register?.(chart);

    // The incident band is drawn in pixels so that a one-second incident stays at least 8 px wide at any zoom; it is
    // hidden while the zoomed view does not include it.
    const band = () => {
      const m = latest.current.metrics;
      const rect = chart.getModel()?.getComponent("grid", 0)?.coordinateSystem?.getRect();
      if (!rect || !m.incident_from) return;
      const x0 = chart.convertToPixel({ xAxisIndex: 0 }, ms(m.incident_from));
      const x1 = chart.convertToPixel({ xAxisIndex: 0 }, m.incident_to ? ms(m.incident_to) : ms(m.to));
      const outside = x1 < rect.x || x0 > rect.x + rect.width;
      const left = Math.max(rect.x, Math.min(x0, rect.x + rect.width - 8));
      const right = Math.min(rect.x + rect.width, Math.max(left + 8, x1));
      chart.setOption({ series: [{}, { markArea: { data: outside ? [] : [[{ x: left, y: rect.y }, { x: right, y: rect.y + rect.height }]] } }] });
    };
    const label = () => {
      const m = latest.current.metrics;
      const z = chart.getOption()?.dataZoom?.[0];
      const start = z?.startValue ?? ms(m.from), end = z?.endValue ?? ms(m.to);
      // A window of 12 h or more spans two days: name the day too.
      const long = end - start >= 12 * 3_600_000;
      const fmt = (x) => (long ? new Date(x).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : clock(x));
      setViewLabel(`${fmt(start)} – ${fmt(end)} ${zoneLabel(end)}`);
    };

    const draw = (animate) => {
      const { series: s, metrics: m, view: v } = latest.current;
      const windowKey = `${m.from}|${m.to}`;
      const prev = chart.getOption()?.dataZoom?.[0];
      const keep = drawn.current === windowKey && prev?.startValue != null ? { start: prev.startValue, end: prev.endValue } : v;
      chart.setOption(buildChartOption({
        series: s, metrics: m, colors: latest.current.colors, variant: latest.current.variant, view: keep,
        reducedMotion: !animate || reducedMotion(), formatTime: (x) => clock(x), formatAxis: (x) => clockHM(x), zone: zoneLabel(ms(m.to)),
      }), { notMerge: true });
      drawn.current = windowKey;
      band();
      label();
    };
    drawRef.current = draw;
    chart.on("datazoom", () => { band(); label(); });
    const resize = new ResizeObserver(() => { chart.resize(); band(); });
    resize.observe(el.current);
    // ECharts' inside zoom swallows every wheel event over the plot, even with `zoomOnMouseWheel: "ctrl"`, so the page
    // could not scroll past a chart. A plain wheel is kept away from ECharts here (capture phase) and scrolls the
    // page; Ctrl + wheel (and a trackpad pinch, which the browser sends with ctrlKey) still zooms the charts.
    const box = el.current;
    const passWheel = (e) => { if (!e.ctrlKey) e.stopImmediatePropagation(); };
    box.addEventListener("wheel", passWheel, { capture: true });

    return () => {
      box.removeEventListener("wheel", passWheel, { capture: true });
      resize.disconnect();
      unregister?.();
      chart.dispose();
      chartRef.current = null;
      drawRef.current = null;
      drawn.current = null;
    };
  }, [empty, group, register]);

  // Redraw on new data, a new theme or a new variant. The first draw of an instance animates; later ones do not, so
  // a theme switch or a 30 s refresh does not replay the line.
  useEffect(() => {
    if (!drawRef.current) return;
    latest.current.colors = colors;
    latest.current.variant = variant;
    drawRef.current(drawn.current == null);
  }, [series, metrics, colors, variant, empty]);

  const notes = [
    series.baseline ? `Normal ${fmtNumber(series.baseline.p50)}–${fmtValue(series.baseline.p95, series.unit)}` : null,
    alert != null ? `Alert ${series.thresholds?.direction === "below" ? "≤" : "≥"} ${fmtValue(alert, series.unit)}` : null,
  ].filter(Boolean);

  return (
    <div className={`min-w-0 ${hero ? "rounded-xl border border-line bg-field/50 px-4 pb-2 pt-3" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-[13px] font-medium text-muted">{series.title}</span>
        <Hint text={meta.help}><Pill tone={meta.tone}>{meta.label}</Pill></Hint>
      </div>
      <div className="mt-1 flex min-w-0 items-baseline gap-3">
        <span className={`whitespace-nowrap font-semibold tracking-tight ${hero ? "text-[28px]" : "text-2xl"} ${series.fired ? "text-red-300" : "text-ink"}`}>
          {fmtNumber(last)}{series.unit && last != null ? <small className="ml-1 text-sm font-normal text-muted">{series.unit}</small> : null}
        </span>
        {delta && <span className={`truncate text-xs ${DELTA_TONE[delta.tone]}`}>{delta.text}</span>}
      </div>
      {/* Distinct keys: ECharts empties its node when disposed, so React must never reuse the chart's <div> for the
          "No data" block (same tag, same place) or the other way round. */}
      {empty ? (
        <div key="empty" className={`mt-2 grid place-items-center rounded-lg border border-dashed border-line text-center ${hero ? "h-[260px]" : "h-[170px]"}`}>
          <div><p className="text-sm text-muted">No data in this window</p><p className="mt-1 text-xs text-faint">A gap is a missing sample, never zero.</p></div>
        </div>
      ) : (
        <div key="chart" ref={el} role="img" aria-label={`${series.title}: ${fmtValue(last, series.unit)}, ${meta.label.toLowerCase()}. Chart with thresholds, normal range, incident window and events.`}
          className={`mt-1 w-full ${hero ? "h-[300px]" : "h-[190px]"}`} />
      )}
      <div className="flex flex-wrap justify-between gap-x-3 gap-y-0.5 px-0.5 pb-1 text-[11px] text-muted">
        <span>{notes.map((n, i) => <span key={n} className={i === notes.length - 1 && alert != null ? "text-red-300" : ""}>{i ? " · " : ""}{n}</span>)}</span>
        {!empty && <span className="ml-auto whitespace-nowrap font-mono">{viewLabel}</span>}
      </div>
    </div>
  );
}
