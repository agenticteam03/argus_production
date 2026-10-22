import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import MetricChart, { ChartGrid } from "./MetricChart.jsx";

const FROM = "2026-10-21T12:00:00Z", TO = "2026-10-21T12:10:00Z";
const at = (min) => `2026-10-21T12:${String(min).padStart(2, "0")}:00Z`;
const html = (series, band) => renderToStaticMarkup(<MetricChart series={series} from={FROM} to={TO} band={band} />);
const pathOf = (out) => /<path d="([^"]*)"/.exec(out)?.[1] ?? "";

describe("MetricChart", () => {
  it("draws a missing sample as a gap in the line, never as a zero", () => {
    const d = pathOf(html({ key: "cpu", title: "CPU", points: [[at(1), 10], [at(2), 20], [at(3), null], [at(4), 30], [at(5), 40]] }));
    expect(d.match(/M/g)).toHaveLength(2);           // two segments: the null starts a new one
    expect(d.match(/L/g)).toHaveLength(2);
  });

  it("leaves out samples outside the window", () => {
    const d = pathOf(html({ key: "cpu", title: "CPU", points: [["2026-10-21T11:50:00Z", 5], [at(1), 10], [at(2), 20], ["2026-10-21T12:30:00Z", 50]] }));
    expect((d.match(/[ML]/g) ?? []).length).toBe(2);
  });

  it("labels the last value with its unit, a dash when there is none, and no line without samples", () => {
    const out = html({ key: "mem", title: "Memory", unit: "%", points: [[at(1), 12.345], [at(2), 50]] });
    expect(out).toContain('aria-label="Memory: 50 %"');
    const empty = html({ key: "mem", title: "Memory", points: [[at(1), null]] });
    expect(empty).toContain('aria-label="Memory: —"');
    expect(empty).not.toContain("<path");
  });

  it("marks a fired series in red and shades the incident window", () => {
    const out = html({ key: "errors", title: "Errors", fired: true, points: [[at(1), 1], [at(2), 3]] }, { from: Date.parse(at(2)), to: Date.parse(at(4)) });
    expect(out).toContain("stroke-red-400");
    expect(out).toContain("<rect");
    expect(html({ key: "cpu", title: "CPU", points: [[at(1), 1]] })).not.toContain("<rect");
  });

  it("ChartGrid shows at most `limit` series, with the band from the incident's open to close", () => {
    const metrics = { from: FROM, to: TO, series: ["a", "b", "c"].map((k) => ({ key: k, title: `T-${k}`, points: [[at(1), 1]] })) };
    const out = renderToStaticMarkup(<ChartGrid metrics={metrics} incident={{ opened_at: at(2), closed_at: at(3) }} limit={2} />);
    expect(out).toContain("T-a");
    expect(out).toContain("T-b");
    expect(out).not.toContain("T-c");
    expect(out.match(/<rect/g)).toHaveLength(2);
  });
});
