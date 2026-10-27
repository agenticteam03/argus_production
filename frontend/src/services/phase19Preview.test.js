import { afterEach, expect, it, vi } from "vitest";
import { demoIncident, demoList } from "./demoIncidents.js";

afterEach(() => vi.unstubAllEnvs());

it("offers a coherent action-card preview only when the local Phase 19 demo is enabled", () => {
  vi.stubEnv("VITE_ARGUS_PHASE19_DEMO", "1");
  const row = demoList()[0];
  const incident = demoIncident(row.id);
  expect(row.target).toBe("vm-166/container:argus-lab-cache");
  expect(incident.next_actions).toEqual([expect.objectContaining({
    action: "container.start", target: row.target, risk_color: "green", is_executable: false,
  })]);
});

it("keeps the ordinary demo unchanged when the preview flag is off", () => {
  vi.stubEnv("VITE_ARGUS_PHASE19_DEMO", "0");
  expect(demoList()[0].target).not.toBe("vm-166/container:argus-lab-cache");
  expect(demoIncident("01K7Z4A6B8C0D2E4F6G8H0J2KM")).toBeNull();
});
