import { useCallback, useEffect, useId, useRef, useState } from "react";
import { clock } from "../../utils/format.js";
import { hostOf } from "../../utils/incidentView.js";
import { Card, Crosshair, Hint, Info, Scan, Segmented, ZoomIn, ZoomOut } from "../ui.jsx";
import { focusWindow, MARKERS } from "./chartOptions.js";
import { connect } from "./echarts.js";
import MetricChart from "./MetricChart.jsx";
import { useChartColors } from "./useChartColors.js";

// The incident metrics: the "Metrics" tab (MetricsTab) and the small "Around the incident" card (MiniCharts), ported
// from the ui-graphs prototype. All charts of one grid share one time window: dragging pans, Ctrl + scroll zooms, the
// crosshair is linked, and the toolbar zooms, focuses the incident or resets every chart at once.
export const DEFAULT_RANGES = ["15m", "30m", "1h"];
const ms = (t) => (typeof t === "number" ? t : Date.parse(t));
const MIN_SPAN = 2 * 60_000;

// The charts of one grid: registered by MetricChart, linked with echarts.connect, and moved together.
function useChartGroup(metrics) {
  const group = `argus-charts-${useId()}`;
  const charts = useRef(new Set());
  const register = useCallback((chart) => {
    charts.current.add(chart);
    return () => charts.current.delete(chart);
  }, []);
  useEffect(() => { connect(group); }, [group]);

  const zoomTo = useCallback((start, end) => {
    const from = ms(metrics.from), to = ms(metrics.to);
    const s = Math.max(from, Math.min(start, to - MIN_SPAN)), e = Math.min(to, Math.max(end, s + MIN_SPAN));
    charts.current.forEach((c) => c.dispatchAction({ type: "dataZoom", dataZoomIndex: 0, startValue: s, endValue: e }));
  }, [metrics.from, metrics.to]);

  const current = useCallback(() => {
    const first = charts.current.values().next().value;
    const z = first?.getOption()?.dataZoom?.[0];
    return { start: z?.startValue ?? ms(metrics.from), end: z?.endValue ?? ms(metrics.to) };
  }, [metrics.from, metrics.to]);

  // Zoom around the middle of what is shown now: factor < 1 zooms in, > 1 out.
  const zoomBy = useCallback((factor) => {
    const { start, end } = current();
    const mid = (start + end) / 2, half = ((end - start) * factor) / 2;
    zoomTo(mid - half, mid + half);
  }, [current, zoomTo]);

  return { group, register, zoomTo, zoomBy };
}

const iconButton = "inline-grid size-8 cursor-pointer place-items-center rounded-lg border border-line text-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none";

function EventChips({ events, metrics, onZoom }) {
  const from = ms(metrics.from), to = ms(metrics.to);
  const inWindow = (events ?? []).filter((e) => ms(e.at) >= from && ms(e.at) <= to);
  if (!inWindow.length) return null;
  const shown = inWindow.slice(-10);
  const TONE = { critical: "border-red-400/30 bg-red-400/[0.07]", warning: "border-amber-400/30 bg-amber-400/[0.07]", ok: "border-emerald-400/30 bg-emerald-400/[0.07]", accent: "border-accent/30 bg-accent/[0.07]" };
  const DOT = { critical: "bg-red-400", warning: "bg-amber-400", ok: "bg-emerald-400", accent: "bg-accent" };
  return (
    <div className="mt-4 flex flex-wrap items-center gap-1.5" aria-label="Events in this window">
      {shown.map((e, i) => {
        const tone = MARKERS[e.kind]?.tone ?? "accent";
        return (
          <button key={`${e.at}-${i}`} type="button" title="Zoom to this event" onClick={() => onZoom(ms(e.at) - 3 * 60_000, ms(e.at) + 3 * 60_000)}
            className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs text-ink transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover ${TONE[tone] ?? TONE.accent}`}>
            <span className={`size-1.5 rounded-full ${DOT[tone] ?? DOT.accent}`} />
            {e.label}
            <span className="font-mono text-muted">{clock(e.at)}</span>
          </button>
        );
      })}
      {inWindow.length > shown.length && <span className="text-xs text-muted">+{inWindow.length - shown.length} earlier</span>}
    </div>
  );
}

const Key = () => (
  <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-line pt-3 text-[11px] text-muted">
    <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-4 rounded bg-accent" />Reading</span>
    <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-4 rounded bg-red-400" />During the incident (fired signal)</span>
    <span className="inline-flex items-center gap-1.5"><i className="w-4 border-t border-dashed border-red-400" />Alert line</span>
    <span className="inline-flex items-center gap-1.5"><i className="w-4 border-t border-dotted border-amber-400" />Warning line</span>
    <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-4 rounded-sm bg-muted/20" />Normal range</span>
    <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-4 rounded-sm bg-red-400/15" />Incident window</span>
    <span>Gaps are missing samples, never zero.</span>
  </div>
);

// The "Metrics" tab: toolbar, the lead chart (the detector's signal) big, the others compact, events and a key.
export function MetricsTab({ metrics, incident, range, onRange }) {
  const colors = useChartColors();
  const { group, register, zoomTo, zoomBy } = useChartGroup(metrics);
  const [focus, setFocus] = useState(false);
  const focusView = focusWindow(metrics);
  const lead = metrics.series.find((s) => s.fired) ?? metrics.series[0];
  const rest = metrics.series.filter((s) => s !== lead);
  const ranges = (metrics.ranges_available?.length ? metrics.ranges_available : DEFAULT_RANGES).map((r) => ({ value: r, label: r }));
  const view = focus ? focusView : null;

  const toggleFocus = () => {
    const next = !focus;
    setFocus(next);
    if (next && focusView) zoomTo(focusView.start, focusView.end);
    else zoomTo(ms(metrics.from), ms(metrics.to));
  };
  const reset = () => { setFocus(false); zoomTo(ms(metrics.from), ms(metrics.to)); };

  const toolbar = (
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      <Segmented label="Time range" options={ranges} value={range} onChange={onRange} />
      {focusView && (
        <button type="button" aria-pressed={focus} onClick={toggleFocus}
          className={`inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 text-xs transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none ${focus ? "border-red-400/40 bg-red-400/10 text-red-300" : "border-line text-muted hover:text-ink"}`}>
          <Crosshair width="14" height="14" />Focus incident
        </button>
      )}
      <button type="button" className={iconButton} aria-label="Zoom out" title="Zoom out" onClick={() => zoomBy(2)}><ZoomOut width="15" height="15" /></button>
      <button type="button" className={iconButton} aria-label="Zoom in" title="Zoom in (or Ctrl + scroll on a chart)" onClick={() => zoomBy(0.5)}><ZoomIn width="15" height="15" /></button>
      <button type="button" className={iconButton} aria-label="Reset zoom" title="Reset zoom" onClick={reset}><Scan width="15" height="15" /></button>
    </div>
  );

  return (
    <Card title={`${hostOf(incident.target) || "Host"} · Incident metrics`} right={toolbar} className="min-w-0">
      <div className="-mt-2 mb-3 flex items-center gap-1.5 text-xs text-muted">
        Drag to move, Ctrl + scroll to zoom. All charts share one time window.
        <Hint align="left" text="Each chart shows its alert and warning lines, the normal range of the last day, the incident window in red and the events (restarts, OOM kills, alerts, deploys, link changes) on the lane under the time axis.">
          <Info width="14" height="14" className="text-muted" />
        </Hint>
      </div>
      {metrics.summary && (
        <p className="mb-3 flex items-start gap-2 rounded-xl border border-line bg-field/50 px-3 py-2 text-[13px] text-body">
          <Info width="15" height="15" className="mt-0.5 shrink-0 text-accent-hover" />{metrics.summary}
        </p>
      )}
      <MetricChart key={lead.key} series={lead} metrics={metrics} variant="hero" colors={colors} group={group} view={view} register={register} />
      {rest.length > 0 && (
        <div className="mt-4 grid gap-x-5 gap-y-4 md:grid-cols-2 xl:grid-cols-3">
          {rest.map((s) => <MetricChart key={s.key} series={s} metrics={metrics} colors={colors} group={group} view={view} register={register} />)}
        </div>
      )}
      <EventChips events={metrics.events} metrics={metrics} onZoom={zoomTo} />
      <Key />
    </Card>
  );
}

// The "Around the incident" card on the Incident & Diagnosis tab: the detector's signal and the next one, compact.
export function MiniCharts({ metrics, onOpen }) {
  const colors = useChartColors();
  const { group, register } = useChartGroup(metrics);
  const lead = metrics.series.find((s) => s.fired) ?? metrics.series[0];
  const shown = [lead, ...metrics.series.filter((s) => s !== lead)].slice(0, 2);
  return (
    <Card title="Around the incident" right={<button type="button" onClick={onOpen} className="cursor-pointer text-xs text-accent-hover hover:underline">All metrics</button>}>
      <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
        {shown.map((s) => <MetricChart key={s.key} series={s} metrics={metrics} colors={colors} group={group} view={null} register={register} />)}
      </div>
    </Card>
  );
}
