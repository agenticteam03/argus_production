import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ApprovalCard from "./ApprovalCard.jsx";

const approval = {
  id: "appr_demo", state: "pending", expires_at: "2099-01-01T00:00:00Z", reversible: true,
  proposal: { digest: "a".repeat(64), basis: "runbook", input: {
    capability: "container.start", target: "vm-166/container:argus-lab-cache",
    target_identity: { container_id: "cache-1" }, arguments: { timeout: 10 },
    rationale: "The cache is stopped.", root_cause: "The API depends on the cache.",
    grounds: ["runbook:RB-003"], evidence_refs: ["ev_status"], preview: "Start the stopped cache.",
    rollback: "Stop the cache if the check fails.",
    prediction: { signal: "dependency_probe", target: "vm-166/container:argus-lab-api", expected: "healthy", within_seconds: 60 },
    alternatives: [{ action: "do nothing", why_not: "The API remains unavailable." }],
  } },
  judge: { verdict: "agree", risk: "red", reasons: ["The dependency is confirmed stopped."] },
};

const html = (canAnswer = false, confirmation = "", reason = "", item = approval) => renderToStaticMarkup(
  <ApprovalCard approval={item} canAnswer={canAnswer} busy={false} confirmation={confirmation}
    onConfirmation={() => {}} reason={reason} onReason={() => {}} onAnswer={() => {}} />,
);
const withJudge = (verdict, risk) => ({ ...approval, judge: { verdict, risk, reasons: ["Exit evidence conflicts."] } });
const approveDisabled = (out) => /disabled=""[^>]*>Approve<\/button>/.test(out);
const denyDisabled = (out) => /disabled=""[^>]*>Deny<\/button>/.test(out);

describe("ApprovalCard", () => {
  it("shows the frozen action, identity, arguments, reversibility, judge, risk, evidence, prediction and rollback", () => {
    const out = html();
    for (const text of ["container.start", "argus-lab-cache", "Red risk", "The cache is stopped.",
      "The dependency is confirmed stopped.", "ev_status", "dependency_probe", "Stop the cache",
      "container_id", "cache-1", "timeout", "Reversible", "yes"])
      expect(out).toContain(text);
  });

  it("shows disabled decisions without a full privileged session", () => {
    const out = html();
    expect(out).toContain("Approve");
    expect(out).toContain("Deny");
    expect(out).toContain("disabled");
    expect(out).toContain("A full private session is required");
  });

  it("requires the exact host-qualified target for a red-risk approval", () => {
    expect(approveDisabled(html(true, "wrong"))).toBe(true);
    expect(approveDisabled(html(true, "argus-lab-cache"))).toBe(true);     // the name exists on both hosts
    expect(approveDisabled(html(true, "vm-166/container:argus-lab-cache"))).toBe(false);
  });

  it("lets a person approve a doubted action, saying so and showing the raised risk (ACR-0039)", () => {
    const out = html(true, "", "", withJudge("doubt", "amber"));
    for (const text of ["The independent judge doubted this action.", "you decide", "amber risk", "Exit evidence conflicts.",
      "Amber risk", ">doubt<"])
      expect(out).toContain(text);
    expect(approveDisabled(out)).toBe(false);
    expect(html(true, "", "", withJudge("agree", "green"))).not.toContain("doubted this action");
  });

  it("never lets a person approve an action the judge disagreed with", () => {
    expect(approveDisabled(html(true, "", "", withJudge("disagree", "amber")))).toBe(true);
  });

  it("requires a reason before a denial", () => {
    expect(denyDisabled(html(true, "", ""))).toBe(true);
    expect(denyDisabled(html(true, "", "   "))).toBe(true);
    expect(denyDisabled(html(true, "", "The owner is restoring it."))).toBe(false);
  });
});
