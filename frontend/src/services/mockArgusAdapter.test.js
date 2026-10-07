import { describe, expect, it } from "vitest";
import { mockArgusAdapter } from "./mockArgusAdapter.js";

// ACR-0001: in this release the UI only reads. The Argus port offers no way to start an investigation or to
// answer an approval, and the overview has no data the API does not serve (no health, no approvals).
describe("mockArgusAdapter", () => {
  it("is a read-only port: it only reads the overview", () => {
    expect(Object.keys(mockArgusAdapter)).toEqual(["getOverview"]);
  });

  it("returns only incidents, which GET /api/v1/incidents serves", async () => {
    expect(await mockArgusAdapter.getOverview()).toEqual({ incidents: [] });
  });
});
