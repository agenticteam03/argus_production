import { describe, expect, it } from "vitest";
import { ANALYSIS_TIMEOUT_S, analysisView, historyFailed, nextHistory } from "./consoleSession.js";

// CON-9: the console's error states (brain/tasks/current/argus-console-mockup-spec.md §8), outside the components.
describe("analysisView error states (CON-9)", () => {
  const now = Date.parse("2026-10-29T10:44:00Z");
  const ago = (s) => new Date(now - s * 1000).toISOString();

  it("counts down from countdown_s when the API sends it instead of settle_until", () => {
    expect(analysisView({ status: "waiting", countdown_s: 12 }, now).text).toBe("Waiting for metrics to settle (12 s)");
  });

  it("says the analysis is taking longer than expected once it runs past the timeout, and allows a re-check", () => {
    expect(analysisView({ status: "analyzing", settle_until: ago(ANALYSIS_TIMEOUT_S - 1) }, now))
      .toEqual({ tone: "blue", text: "Argus is analysing the result" });
    expect(analysisView({ status: "analyzing", settle_until: ago(ANALYSIS_TIMEOUT_S + 1) }, now))
      .toEqual({ tone: "amber", text: "Analysis is taking longer than expected", retryable: true });
  });

  it("shows the API's message for metrics not available yet, retryable only when the API says so", () => {
    expect(analysisView({ status: "error", message: "Metrics not available yet", retryable: true }, now))
      .toEqual({ tone: "amber", text: "Metrics not available yet", retryable: true });
    expect(analysisView({ status: "error", message: "Metrics not available yet" }, now))
      .toEqual({ tone: "amber", text: "Metrics not available yet" });
  });

  it("names a backend failure in words, with its reason when there is one", () => {
    expect(analysisView({ status: "error", error: "Analysis could not be completed", retryable: true }, now))
      .toEqual({ tone: "red", text: "Analysis unavailable: Analysis could not be completed", retryable: true });
    expect(analysisView({ status: "error" }, now)).toEqual({ tone: "amber", text: "Analysis unavailable" });
  });
});

describe("history polling (CON-9)", () => {
  it("treats a network failure or a 5xx as a temporary outage, and a 4xx as not one", () => {
    expect(historyFailed(new TypeError("Failed to fetch"))).toBe(true);
    expect(historyFailed({ status: 502 })).toBe(true);
    expect(historyFailed({ status: 403 })).toBe(false);
    expect(historyFailed({ status: 404 })).toBe(false);
  });

  it("keeps the last good entries on a failed poll and clears the outage on the next good one", () => {
    const good = nextHistory({ id: null, entries: [], unavailable: false }, "inc_1", { entries: [{ command_id: "c1" }] });
    expect(good).toEqual({ id: "inc_1", entries: [{ command_id: "c1" }], unavailable: false });
    const down = nextHistory(good, "inc_1", null, { status: 503 });
    expect(down).toEqual({ id: "inc_1", entries: [{ command_id: "c1" }], unavailable: true });
    expect(nextHistory(down, "inc_1", { entries: [] })).toEqual({ id: "inc_1", entries: [], unavailable: false });
  });

  it("does not show an outage for a refused poll, and never keeps another incident's entries", () => {
    const prev = { id: "inc_1", entries: [{ command_id: "c1" }], unavailable: false };
    expect(nextHistory(prev, "inc_1", null, { status: 403 })).toBe(prev);
    expect(nextHistory(prev, "inc_2", null, { status: 500 })).toEqual({ id: "inc_2", entries: [], unavailable: true });
  });
});
