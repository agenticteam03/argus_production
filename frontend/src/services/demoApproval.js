// Synthetic frozen package for the opt-in local Phase 19 screen. It never reaches the API.
export const DEMO_APPROVAL_ID = "appr_phase19_demo";

export function demoApproval() {
  return {
    id: DEMO_APPROVAL_ID, state: "pending", expires_at: new Date(Date.now() + 20 * 60_000).toISOString(),
    reversible: true,
    proposal: {
      id: "prop_phase19_demo", digest: "a".repeat(64), basis: "runbook",
      input: {
        incident_id: "01K7Z4A6B8C0D2E4F6G8H0J2KM", capability: "container.start",
        target: "vm-166/container:argus-lab-cache", target_identity: { container_id: "demo-cache" },
        arguments: {}, root_cause: "Demo: the cache stopped and the API dependency probe failed.",
        rationale: "Starting the stopped cache is the reviewed RB-003 candidate for this lab dependency.",
        evidence_refs: ["ev_j2km_1"], grounds: ["runbook:RB-003"],
        prediction: { signal: "dependency_probe", target: "vm-166/container:argus-lab-api",
          expected: "healthy", within_seconds: 60 },
        alternatives: [{ action: "restart the API", why_not: "The API is the victim of the cache failure." }],
        preview: "Demo only: inspect the cache identity before any action.",
        rollback: "Demo only: stop the cache if its start causes a new failure.",
        inventory_version: "demo", policy_version: "demo", evidence_version: "demo",
      },
    },
    judge: { verdict: "agree", risk: "red", reasons: ["Demo judge: the cited status and runbook match this target."] },
  };
}
