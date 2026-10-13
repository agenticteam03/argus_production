import { afterEach, describe, expect, it } from "vitest";
import { demoIncident } from "./demoIncidents.js";
import { demoSession } from "./demoSession.js";
import { mockArgusAdapter } from "./mockArgusAdapter.js";

const ESCALATED_E = "01K7YWE1J4K7M0P2R5T8U3V6DH"; // the demo incident that escalated with no action

afterEach(() => {
  demoSession.role = null;
});

describe("mockArgusAdapter escalations", () => {
  it("lists the escalations the demo incidents raised, in the contract shape", async () => {
    const raised = await mockArgusAdapter.listEscalations();

    expect(raised.map((e) => e.payload.outcome).sort()).toEqual(["no_action_escalated", "unsupported_escalated"]);
    expect(mockArgusAdapter.calls).toContainEqual({ method: "GET", path: "/api/v1/escalations" });
    expect(raised[0].key).toMatch(/:escalation$/);
    expect(raised[0].payload).toMatchObject({ route: "channel:operators", incident_id: expect.any(String), target: expect.any(String) });
  });

  it("includes escalations in the dashboard overview", async () => {
    const overview = await mockArgusAdapter.getOverview();

    expect(overview.escalations).toHaveLength(2);
    expect(overview.incidents.length).toBeLessThanOrEqual(5);
    expect(overview.approvals).toEqual([]);
  });
});

describe("mockArgusAdapter evidence", () => {
  it("refuses a viewer, like GET /api/v1/evidence/{id}", async () => {
    demoSession.role = "viewer";
    await expect(mockArgusAdapter.getEvidence("ev_v6dh_1")).rejects.toMatchObject({ status: 403 });
  });

  it("returns one record for operator/approver and 404s an unknown id", async () => {
    demoSession.role = "operator";
    const id = demoIncident(ESCALATED_E).evidence[0].evidence_id;

    await expect(mockArgusAdapter.getEvidence(id)).resolves.toMatchObject({ evidence_id: id });
    await expect(mockArgusAdapter.getEvidence("ev_nope")).rejects.toMatchObject({ status: 404 });
  });
});
