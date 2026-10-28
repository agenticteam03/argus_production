import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ActionTrail from "./ActionTrail.jsx";

const action = {
  proposal_id: "prop_1",
  capability: "container.restart",
  target: "vm-166/container:argus-lab-jobworker",
  rationale: "argus-lab-jobworker is running but its worker_stalled persists.",
  judge: { verdict: "agree", risk: "green", reasons: ["RB-022 supports one approved restart."] },
  approval: { id: "appr_1", state: "approved", answered_by: "operator1", answered_at: "2026-10-28T12:48:56Z" },
  action: { id: "act_1", state: "confirmed", result_at: "2026-10-28T12:53:16Z" },
  outcome: { outcome: "recovered_verified", recorded_at: "2026-10-28T12:54:00Z" },
};

describe("ActionTrail", () => {
  it("shows the proposal, the judge, who approved, the execution and the verification, with no control", () => {
    const html = renderToStaticMarkup(<ActionTrail action={action} />);
    for (const text of ["container.restart", "argus-lab-jobworker", "Judge agreed", "RB-022", "Approved",
      "operator1", "Done", "Recovery verified"])
      expect(html).toContain(text);
    expect(html).not.toContain("<button");
  });

  it("says plainly what has not happened yet", () => {
    const html = renderToStaticMarkup(<ActionTrail action={{ ...action, judge: { verdict: "doubt", reasons: ["Protocol not shown."] }, approval: null, action: null, outcome: null }} />);
    for (const text of ["Judge doubted", "Not requested", "Not run", "Not recorded"]) expect(html).toContain(text);
  });

  it("renders nothing for an incident without a proposal", () => {
    expect(renderToStaticMarkup(<ActionTrail action={undefined} />)).toBe("");
  });
});
