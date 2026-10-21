import { describe, expect, it } from "vitest";
import { auditDetail, clock, clockCot, dateTime, liveLabel } from "./format.js";

describe("liveLabel", () => {
  it("says Live only when the API answered and we are not in demo mode", () => {
    expect(liveLabel(true, "api")).toBe("Live");
  });

  it("says Reconnecting when the last request failed", () => {
    expect(liveLabel(false, "api")).toBe("Reconnecting…");
  });

  it("says Demo data in mock mode, whatever the poll says", () => {
    expect(liveLabel(true, "demo")).toBe("Demo data");
    expect(liveLabel(false, "demo")).toBe("Demo data");
  });

  it("keeps the old behaviour when no source is given (e.g. the runbook library)", () => {
    expect(liveLabel(true, undefined)).toBe("Live");
    expect(liveLabel(false, undefined)).toBe("Reconnecting…");
  });
});

// The real API sends `detail` as an object; rendering it directly threw "Objects are not valid as a React child"
// and blanked the incident page. It must be turned into text.
describe("auditDetail", () => {
  it("renders object detail (the real API shape) as JSON text", () => {
    const d = auditDetail({ request: "report", target: "vm-166" });
    expect(d.kind).toBe("json");
    expect(JSON.parse(d.text)).toEqual({ request: "report", target: "vm-166" });
  });

  it("renders string detail (the demo fixtures) inline", () => {
    expect(auditDetail("Read-only capability allowed.")).toEqual({ kind: "text", text: "Read-only capability allowed." });
  });

  it("treats null, undefined, empty strings and empty objects as nothing to show", () => {
    expect(auditDetail(null).kind).toBe("empty");
    expect(auditDetail(undefined).kind).toBe("empty");
    expect(auditDetail("").kind).toBe("empty");
    expect(auditDetail({}).kind).toBe("empty");
  });

  it("stringifies scalar detail", () => {
    expect(auditDetail(7)).toEqual({ kind: "text", text: "7" });
  });
});

// 21:12:55 UTC is 16:12:55 in Colombia (UTC-5, no daylight saving), whatever the browser's own zone is.
describe("Colombia time (COT)", () => {
  it("shows the clock in Bogota time and labels it", () => {
    expect(clock("2026-10-14T21:12:55Z")).toMatch(/16:12:55/);
    expect(clockCot("2026-10-14T21:12:55Z")).toMatch(/^16:12:55 COT$/);
  });
  it("accepts a timestamp in milliseconds, as the Live pill passes", () => {
    expect(clockCot(Date.parse("2026-10-14T21:12:55Z"))).toMatch(/^16:12:55 COT$/);
  });
  it("labels full dates as COT and keeps the dash for no date", () => {
    expect(dateTime("2026-10-14T21:12:55Z")).toMatch(/COT$/);
    // 24 h or 12 h depending on the browser's locale
    expect(dateTime("2026-10-14T21:12:55Z")).toMatch(/(16|4):12:55/);
    expect(dateTime(null)).toBe("—");
  });
});
