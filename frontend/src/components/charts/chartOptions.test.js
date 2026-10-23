import { describe, expect, it } from "vitest";
import { alertLine, buildChartOption, fmtValue, focusWindow, seriesState, STATE_META, thresholdState } from "./chartOptions.js";

const COLORS = {
  accent: "#3b82f6", critical: "#ef4444", warning: "#f59e0b", ok: "#10b981", muted: "#8a92a3",
  axis: "#8a92a3", grid: "#1c212b", surface: "#090b10", ink: "#f2f4f8", border: "#232a37",
};
const T = (iso) => Date.parse(iso);

// Shapes taken from the live API (GET /api/v1/incidents/{id}/metrics), trimmed.
const metrics = {
  from: "2026-10-16T12:20:00Z",
  to: "2026-10-16T12:50:00Z",
  incident_from: "2026-10-16T12:41:00Z",
  incident_to: "2026-10-16T12:41:10Z",
  events: [
    { at: "2026-10-16T12:41:18Z", kind: "oom_kill", label: "Killed by the kernel (out of memory)" },
    { at: "2026-10-16T12:41:48Z", kind: "restart", label: "Container <b>restarted</b>" },
    { at: "2026-10-16T12:00:00Z", kind: "deploy", label: "Outside the window" },
  ],
};
const restarts = {
  key: "restarts_10m", title: "Restarts in 10 min", unit: "", kind: "restarts", fired: true, max: null,
  thresholds: { warning: 2, critical: 3, direction: "above" }, detector_threshold: 3, baseline: null,
  points: [["2026-10-16T12:40:00Z", 0], ["2026-10-16T12:40:30Z", null], ["2026-10-16T12:41:00Z", 3], ["2026-10-16T12:41:30Z", 7]],
};
const memAvailable = {
  key: "host_memory_available_ratio", title: "Host memory available", unit: "%", kind: "memory", fired: false, max: 100,
  thresholds: { warning: 25, critical: 10, direction: "below" }, detector_threshold: null,
  baseline: { p50: 81.5, p95: 81.9, from: "x", to: "y" },
  points: [["2026-10-16T12:40:00Z", 81.2], ["2026-10-16T12:40:30Z", 81.4]],
};

describe("values and states", () => {
  it("formats tiny, small and large values readably", () => {
    expect(fmtValue(0.000022, "cores")).toBe("0.000022 cores");
    expect(fmtValue(7.315789, "%")).toBe("7.32 %");
    expect(fmtValue(59.347656, "MiB")).toBe("59.3 MiB");
    expect(fmtValue(1234.5, "")).toBe("1235");
    expect(fmtValue(3, "")).toBe("3");
    expect(fmtValue(null, "%")).toBe("—");
  });

  it("knows on which side of the lines a value is, for both directions", () => {
    const up = { warning: 75, critical: 90, direction: "above" };
    expect(thresholdState(10, up)).toBe("normal");
    expect(thresholdState(80, up)).toBe("warning");
    expect(thresholdState(95, up)).toBe("critical");
    const down = { warning: 25, critical: 10, direction: "below" };
    expect(thresholdState(81, down)).toBe("normal");
    expect(thresholdState(20, down)).toBe("warning");
    expect(thresholdState(5, down)).toBe("critical");
    expect(thresholdState(null, up)).toBe("no_data");
    expect(thresholdState(5, null)).toBe("no_threshold");
  });

  it("gives each chart one state: fired wins, then no data, then the thresholds", () => {
    expect(seriesState(restarts)).toEqual({ state: "fired", last: 7 });
    expect(seriesState(memAvailable)).toEqual({ state: "normal", last: 81.4 });
    expect(seriesState({ ...memAvailable, points: [["t", null]] })).toEqual({ state: "no_data", last: null });
    expect(seriesState({ ...memAvailable, thresholds: null })).toEqual({ state: "no_threshold", last: 81.4 });
    for (const s of ["fired", "critical", "warning", "normal", "no_data", "no_threshold"]) {
      expect(STATE_META[s].label).toBeTruthy();
      expect(STATE_META[s].help.length).toBeGreaterThan(20);  // every badge explains itself on hover
    }
  });

  it("uses the detector's line as the alert line, else the critical threshold", () => {
    expect(alertLine(restarts)).toBe(3);
    expect(alertLine(memAvailable)).toBe(10);
    expect(alertLine({ thresholds: null, detector_threshold: null })).toBeNull();
  });
});

describe("focusWindow", () => {
  it("is 4 minutes before the incident to 2 minutes after, inside the data window", () => {
    expect(focusWindow(metrics)).toEqual({ start: T("2026-10-16T12:37:00Z"), end: T("2026-10-16T12:43:10Z") });
  });
  it("is at least 5 minutes wide and works while the incident is open", () => {
    const open = { ...metrics, incident_from: "2026-10-16T12:48:00Z", incident_to: null };
    const w = focusWindow(open);
    expect(w.start).toBe(T("2026-10-16T12:44:00Z"));
    expect(w.end).toBe(T("2026-10-16T12:50:00Z"));
  });
  it("is null when the API gives no incident window", () => {
    expect(focusWindow({ ...metrics, incident_from: null })).toBeNull();
  });
});

describe("buildChartOption", () => {
  const build = (series, extra = {}) => buildChartOption({ series, metrics, colors: COLORS, variant: "hero", formatTime: (t) => String(t), zone: "COT", ...extra });
  const main = (o) => o.series[0];

  it("draws the alert and warning lines when the series has thresholds", () => {
    const lines = main(build(restarts)).markLine.data.filter((d) => "yAxis" in d);
    expect(lines.map((l) => [l.name, l.yAxis])).toEqual([["Alert", 3], ["Warning", 2]]);
    expect(main(build({ ...restarts, thresholds: null, detector_threshold: null })).markLine.data.filter((d) => "yAxis" in d)).toEqual([]);
  });

  it("keeps the threshold lines inside the y axis even when the values stay low", () => {
    const yMax = build({ ...restarts, points: [["2026-10-16T12:40:00Z", 0]] }).yAxis[0].max;
    expect(yMax({ max: 0 })).toBeGreaterThanOrEqual(3);
    expect(build(memAvailable).yAxis[0].max).toBe(100);      // the API's max wins
  });

  it("leaves headroom above the peak so the line never touches the top", () => {
    const yMax = build({ ...restarts, thresholds: null, detector_threshold: null }).yAxis[0].max;
    expect(yMax({ max: 59.3 })).toBeGreaterThan(59.3);
    expect(yMax({ max: 0 })).toBe(1);                         // a flat zero still gets an axis
  });

  it("labels the time axis with its own (short) formatter", () => {
    const o = build(restarts, { formatAxis: () => "07:41" });
    expect(o.xAxis[1].axisLabel.formatter(0)).toBe("07:41");
  });

  it("shades the normal range (baseline p50–p95) only when the API sends one", () => {
    expect(main(build(memAvailable)).markArea.data).toEqual([[expect.objectContaining({ yAxis: 81.5 }), { yAxis: 81.9 }]]);
    expect(main(build(restarts)).markArea.data).toEqual([]);
  });

  it("draws a gap for a missing sample, never a zero", () => {
    const o = build(restarts);
    expect(main(o).connectNulls).toBe(false);
    expect(main(o).data[1]).toEqual([T("2026-10-16T12:40:30Z"), null]);
  });

  it("colours a fired signal red from the moment the incident starts", () => {
    const during = build(restarts).series.find((s) => s.name === "During the incident");
    expect(during.lineStyle.color).toBe(COLORS.critical);
    expect(during.data.map((p) => p[1])).toEqual([null, null, 3, 7]);
    expect(build(memAvailable).series.find((s) => s.name === "During the incident")).toBeUndefined();
  });

  it("puts the window's events on the event lane with one symbol per kind", () => {
    const lane = build(restarts).series.find((s) => s.name === "Events");
    expect(lane.data.map((d) => d.symbol)).toEqual(["triangle", "circle"]);   // the deploy is outside the window
    expect(lane.data[0].symbolRotate).toBe(180);
  });

  it("zooms with Ctrl + scroll and pans by dragging, and links the time axes", () => {
    const o = build(restarts);
    expect(o.dataZoom[0]).toMatchObject({ type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseMove: true, moveOnMouseWheel: false });
    expect(o.dataZoom.some((z) => z.type === "slider")).toBe(true);           // the big chart has a slider too
    expect(buildChartOption({ series: restarts, metrics, colors: COLORS, variant: "compact", formatTime: String, zone: "COT" }).dataZoom.some((z) => z.type === "slider")).toBe(false);
    expect(o.xAxis.map((x) => [x.min, x.max])).toEqual([[T(metrics.from), T(metrics.to)], [T(metrics.from), T(metrics.to)]]);
  });

  it("starts at a given view (Focus incident) when one is passed", () => {
    const view = focusWindow(metrics);
    expect(build(restarts, { view }).dataZoom[0]).toMatchObject({ startValue: view.start, endValue: view.end });
  });

  it("escapes API text in the tooltip", () => {
    const o = build(restarts);
    const html = o.tooltip.formatter([{ seriesName: restarts.title, value: [T("2026-10-16T12:41:30Z"), 7] }]);
    expect(html).toContain("Above alert");
    expect(html).toContain("&lt;b&gt;restarted&lt;/b&gt;");
    expect(html).not.toContain("<b>restarted</b>");
  });
});
