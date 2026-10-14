import { describe, expect, it } from "vitest";
import { POLL_MS } from "./polling.js";
import { INCIDENTS_CAP } from "./paging.js";

// ACR-0011 §3.1 row 8 (T-0016 step 4b): the UI must not load the 1-vCPU VM. The lists poll every 30 s (not 5 s) and
// ask for at most 200 incidents; only a running investigation refreshes fast, and only while it runs.
describe("polling budget", () => {
  it("polls the dashboard and the incident list every 30 s", () => {
    expect(POLL_MS.overview).toBe(30_000);
    expect(POLL_MS.incidents).toBe(30_000);
  });

  it("refreshes a running incident fast, and never faster than every 2 s", () => {
    expect(POLL_MS.runningIncident).toBeGreaterThanOrEqual(2_000);
    expect(POLL_MS.runningEvents).toBeGreaterThanOrEqual(2_000);
  });

  it("asks for at most 200 incidents per poll", () => {
    expect(INCIDENTS_CAP).toBe(200);
  });
});
