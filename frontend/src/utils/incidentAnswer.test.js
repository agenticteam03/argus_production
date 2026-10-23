import { describe, expect, it } from "vitest";
import { answerAboutIncident, SUGGESTIONS, topicOf } from "./incidentAnswer.js";

const ev = (seq, node, phase, data = {}) => ({ seq, at: `2026-10-14T21:12:${10 + seq}Z`, node, phase, data });
const INC = {
  id: "inc_1", target: "vm-166/container:client", status: "escalated", outcome: "no_action_escalated",
  diagnosis: "**Backend** cannot be reached. Restarting will not help.", root_cause_target: "vm-166/container:backend", confidence: "medium",
  recommendation: "Attach **backend** to the shared network.", findings: ["probe failing"], ruled_out: ["Host pressure"],
  opened_at: "2026-10-14T21:12:54Z", closed_at: "2026-10-14T21:13:14Z", model_calls: 0,
  evidence: [{ evidence_id: "obs_1", kind: "observation", capability: "container.status", target: "vm-166/container:backend", model_text: "status: not found\nmore" }],
};
const EVENTS = [ev(1, "recall", "exit", { passages: [{ runbook_id: "RB-003" }] }), ev(2, "investigate", "exit", { decided_by: "rule", decision: { kind: "escalate" } })];
const ctx = { incident: INC, events: EVENTS, cited: ["obs_1"] };
const ask = (q, c = ctx) => answerAboutIncident(q, c);

describe("topicOf", () => {
  it("routes the suggested questions and common phrasings", () => {
    expect(SUGGESTIONS.map(topicOf)).toEqual(["summary", "cause", "next", "runbooks"]);
    expect(topicOf("which evidence supports this?")).toBe("evidence");
    expect(topicOf("how long did it take")).toBe("time");
    expect(topicOf("was an AI involved?")).toBe("decided");
    expect(topicOf("hello there")).toBeNull();
  });
});

describe("answerAboutIncident", () => {
  it("summarises with the first sentence, without markdown marks", () => {
    const a = ask("What happened?");
    expect(a).toContain("vm-166/container:client: escalated, no action escalated.");
    expect(a).toContain("Backend cannot be reached.");
    expect(a).not.toContain("*");
  });
  it("gives the root cause, the full diagnosis and the confidence", () => {
    const a = ask("Why this root cause?");
    expect(a).toContain("Root cause: vm-166/container:backend.");
    expect(a).toContain("Restarting will not help.");
    expect(a).toContain("Confidence: medium.");
  });
  it("lists the cited evidence with what it read", () => {
    expect(ask("Which evidence supports it?")).toContain("obs_1: container.status on backend — status: not found");
  });
  it("lists the runbooks it read and the next step", () => {
    expect(ask("Which runbooks did it read?")).toContain("It read RB-003.");
    expect(ask("What should I do next?")).toBe("Attach backend to the shared network.");
  });
  it("says who decided and how long it took", () => {
    expect(ask("Who decided?")).toBe("Decisions were made by rules. No AI calls were made.");
    expect(ask("How long did it take?")).toMatch(/It took 20s\./);
  });
  it("says so when the data cannot answer, and never invents", () => {
    const bare = { incident: { id: "i", target: "t", status: "closed" }, events: [], cited: [] };
    expect(ask("What should I do next?", bare)).toBe("No next step was recorded for this incident.");
    expect(ask("Which runbooks?", bare)).toBe("No runbook was recalled for this run.");
    expect(ask("Why?", bare)).toBe("No root cause was identified for this incident.");
    expect(ask("Who decided?", bare)).toBe("This incident does not record who made the decisions.");
    expect(ask("evidence?", bare)).toBe("Argus did not cite specific evidence for this incident.");
  });
  it("lists what it can answer for anything else", () => {
    expect(ask("tell a joke please")).toMatch(/^I can answer about this incident:/);
  });
});
