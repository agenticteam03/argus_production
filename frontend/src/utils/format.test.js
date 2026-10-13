import { describe, expect, it } from "vitest";
import { liveLabel } from "./format.js";

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
