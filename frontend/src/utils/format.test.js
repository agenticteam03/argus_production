import { afterEach, describe, expect, it, vi } from "vitest";
import { auditDetail, duration, isActive, liveLabel, shortHash, timeAgo } from "./format.js";

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

describe("isActive", () => {
  it("is true only for a queued or running investigation", () => {
    expect(["queued", "running"].map(isActive)).toEqual([true, true]);
    expect(["closed", "escalated", "failed", undefined].map(isActive)).toEqual([false, false, false, false]);
  });
});

describe("timeAgo", () => {
  afterEach(() => vi.useRealTimers());

  it("rounds to minutes, hours or days, and never says a future time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-21T12:00:00Z"));
    expect(timeAgo("2026-10-21T11:59:40Z")).toBe("just now");
    expect(timeAgo("2026-10-21T12:05:00Z")).toBe("just now");
    expect(timeAgo("2026-10-21T11:15:00Z")).toBe("45m ago");
    expect(timeAgo("2026-10-21T09:00:00Z")).toBe("3h ago");
    expect(timeAgo("2026-10-18T12:00:00Z")).toBe("3d ago");
  });
});

describe("duration", () => {
  it("shows seconds, minutes and seconds, or hours and minutes", () => {
    expect(duration("2026-10-21T12:00:00Z", "2026-10-21T12:00:42Z")).toBe("42s");
    expect(duration("2026-10-21T12:00:00Z", "2026-10-21T12:03:05Z")).toBe("3m 5s");
    expect(duration("2026-10-21T12:00:00Z", "2026-10-21T14:07:00Z")).toBe("2h 7m");
    expect(duration("2026-10-21T12:00:10Z", "2026-10-21T12:00:00Z")).toBe("0s");
  });
});

describe("shortHash", () => {
  it("keeps the first 12 characters, or a dash when there is none", () => {
    expect(shortHash("0123456789abcdef0123")).toBe("0123456789ab…");
    expect(shortHash(null)).toBe("—");
  });
});
