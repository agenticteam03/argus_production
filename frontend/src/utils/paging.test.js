import { describe, expect, it } from "vitest";
import { incidentsSummary } from "./paging.js";

describe("incidentsSummary", () => {
  it("shows how many are visible and the real total", () => {
    expect(incidentsSummary({ shown: 30, matched: 137, total: 137, hasFilters: false, truncated: false }))
      .toBe("Showing 30 of 137 incidents");
  });

  it("keeps the real total when filters narrow the list", () => {
    expect(incidentsSummary({ shown: 12, matched: 12, total: 137, hasFilters: true, truncated: false }))
      .toBe("Showing 12 of 12 matching · 137 total incidents");
  });

  it("does not double-report the total when the filters change nothing", () => {
    expect(incidentsSummary({ shown: 30, matched: 137, total: 137, hasFilters: true, truncated: false }))
      .toBe("Showing 30 of 137 matching incidents");
  });

  it("says when the API cap cut the list short", () => {
    expect(incidentsSummary({ shown: 30, matched: 200, total: 200, hasFilters: false, truncated: true }))
      .toBe("Showing 30 of 200 incidents · only the latest 200 are loaded");
  });
});
