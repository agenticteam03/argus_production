import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MetricsTab, MiniCharts } from "./ChartGrid.jsx";
import MetricChart from "./MetricChart.jsx";

// The markup around the ECharts canvas (the canvas itself is drawn in an effect, so not here; chartOptions.test.js
// checks what goes into it). Shapes from GET /api/v1/incidents/{id}/metrics.
const at = (min) => `2026-10-21T12:${String(min).padStart(2, "0")}:00Z`;
const COLORS = { accent: "#3b82f6", critical: "#ef4444", warning: "#f59e0b", ok: "#10b981", muted: "#8a92a3", axis: "#8a92a3", grid: "#1c212b", surface: "#090b10", ink: "#f2f4f8", border: "#232a37" };
const restarts = { key: "restarts_10m", title: "Restarts in 10 min", unit: "", fired: true, thresholds: { warning: 2, critical: 3, direction: "above" }, detector_threshold: 3, points: [[at(1), 0], [at(2), null], [at(3), 7]] };
const memory = { key: "mem", title: "Memory", unit: "MiB", fired: false, thresholds: null, baseline: { p50: 40, p95: 50 }, points: [[at(1), 41], [at(3), 80]] };
const empty = { key: "cpu", title: "CPU", unit: "cores", fired: false, thresholds: null, points: [[at(1), null], [at(2), null]] };
const METRICS = { from: at(0), to: at(10), incident_from: at(3), incident_to: at(4), ranges_available: ["15m", "30m", "1h", "6h", "24h"], summary: "7 restarts in 10 minutes.", events: [], series: [restarts, memory, empty] };
const chart = (series) => renderToStaticMarkup(<MetricChart series={series} metrics={METRICS} colors={COLORS} group="g" view={null} />);

describe("MetricChart", () => {
  it("shows the latest reading, its badge with an explanation, and the alert line in words", () => {
    const out = chart(restarts);
    expect(out).toContain("Restarts in 10 min");
    expect(out).toContain(">7<");
    expect(out).toContain("Fired");
    expect(out).toContain("The detector crossed its configured threshold and opened an alert.");
    expect(out).toContain("cursor-help");
    expect(out).toContain("Alert ≥ 3");
    expect(out).toContain('role="img"');
  });

  it("compares the reading with the normal range when the API gives one", () => {
    const out = chart(memory);
    expect(out).toContain("+60% over normal");
    expect(out).toContain("Normal 40–50 MiB");
    expect(out).toContain("No limit set");
  });

  it("says No data instead of drawing a chart without samples", () => {
    const out = chart(empty);
    expect(out).toContain("No data in this window");
    expect(out).not.toContain('role="img"');
  });
});

describe("MetricsTab and MiniCharts", () => {
  it("offers the ranges the API lists, Focus incident, the zoom buttons, the summary and the key", () => {
    const out = renderToStaticMarkup(<MetricsTab metrics={METRICS} incident={{ target: "vm-166/container:argus-lab-worker" }} range="30m" onRange={() => {}} />);
    for (const r of ["15m", "30m", "1h", "6h", "24h"]) expect(out).toContain(`>${r}<`);
    expect(out).toContain("Focus incident");
    expect(out).toContain('aria-label="Zoom in"');
    expect(out).toContain('aria-label="Reset zoom"');
    expect(out).toContain("vm-166 · Incident metrics");
    expect(out).toContain("7 restarts in 10 minutes.");
    expect(out).toContain("Gaps are missing samples, never zero.");
  });

  it("hides Focus incident without an incident window and falls back to the first three ranges", () => {
    const out = renderToStaticMarkup(<MetricsTab metrics={{ ...METRICS, incident_from: null, ranges_available: undefined }} incident={{ target: "x/y:z" }} range="30m" onRange={() => {}} />);
    expect(out).not.toContain("Focus incident");
    expect(out).toContain(">1h<");
    expect(out).not.toContain(">24h<");
  });

  it("MiniCharts shows the detector's signal first and one more", () => {
    const out = renderToStaticMarkup(<MiniCharts metrics={{ ...METRICS, series: [memory, empty, restarts] }} onOpen={() => {}} />);
    expect(out.indexOf("Restarts in 10 min")).toBeLessThan(out.indexOf("Memory"));
    expect(out).not.toContain(">CPU<");
    expect(out).toContain("All metrics");
  });
});
