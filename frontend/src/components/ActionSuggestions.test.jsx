import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ActionSuggestions from "./ActionSuggestions.jsx";

const candidate = {
  action: "container.start",
  target: "vm-166/container:argus-lab-cache",
  text: "Candidate remediation: execute container.start on vm-166/container:argus-lab-cache",
  basis: "runbook",
  grounds: ["RB-003"],
  evidence_refs: ["ev_123"],
  risk_color: "green",
  is_executable: false,
};

describe("ActionSuggestions", () => {
  it("shows reviewed candidate context without an execution control", () => {
    const html = renderToStaticMarkup(<ActionSuggestions items={[candidate]} />);
    for (const text of ["Suggested actions", "container.start", "argus-lab-cache", "Green risk", "Runbook", "RB-003", "ev_123", "Suggestion only"])
      expect(html).toContain(text);
    expect(html).not.toContain("<button");
  });

  it("does not render an action section without candidates", () => {
    expect(renderToStaticMarkup(<ActionSuggestions items={[]} />)).toBe("");
  });

  it("never turns an unexpected executable flag into an execution button", () => {
    const html = renderToStaticMarkup(<ActionSuggestions items={[{ ...candidate, is_executable: true }]} />);
    expect(html).toContain("Suggestion only");
    expect(html).not.toContain("<button");
  });
});
