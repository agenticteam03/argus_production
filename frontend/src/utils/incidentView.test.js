import { describe, expect, it } from "vitest";
import { chain, citedEvidence, runbooksRead, decidedBy, firstSentence, groupEvidence, modelCalls, reason, shortName, stages, summaryText } from "./incidentView.js";

const ev = (seq, sec, node, phase, data = {}) => ({ seq, at: `2026-10-14T10:39:${String(sec).padStart(2, "0")}Z`, node, phase, data });
const EVENTS = [
  ev(1, 16, "detect", "enter"), ev(2, 16, "detect", "exit", { class: "dependency_unavailable" }),
  ev(3, 16, "recall", "enter"), ev(4, 16, "recall", "exit", { passages: ["RB-003"] }),
  ev(5, 16, "investigate", "enter"), ev(6, 16, "investigate", "exit", { decision: "use_read_tools", decided_by: "rule" }),
  ev(7, 16, "act", "enter"),
  ev(8, 18, "act", "step", { capability: "container.status", target: "vm-166/container:a", status: "ok", evidence_id: "obs_1" }),
  ev(9, 19, "act", "step", { capability: "container.status", target: "vm-166/container:b", status: "ok", evidence_id: "obs_2" }),
  ev(10, 19, "act", "exit"),
  ev(11, 19, "investigate", "enter"), ev(12, 19, "investigate", "exit", { decision: "conclude", decided_by: "rule", root_cause_target: "vm-166/container:b", confidence: "medium" }),
  ev(13, 19, "record", "exit", { outcome: "diagnosed", cited: ["ev_1", "obs_1"] }),
];

describe("stages", () => {
  it("groups consecutive events of the same node and keeps investigate twice", () => {
    expect(stages(EVENTS).map((s) => s.name)).toEqual(["detect", "recall", "investigate", "act", "investigate", "record"]);
  });
  it("collects reads with their evidence ids and measures duration up to the next stage", () => {
    const act = stages(EVENTS).find((s) => s.name === "act");
    expect(act.reads.map((r) => r.evidenceId)).toEqual(["obs_1", "obs_2"]);
    expect(act.durationMs).toBe(3000);
    expect(act.summary).toBe("2 reads · all ok");
  });
  it("describes the conclusion and marks an unfinished last stage as not done", () => {
    expect(stages(EVENTS)[4].summary).toBe("Concluded: root cause b, confidence medium (rules)");
    const live = stages([ev(1, 16, "detect", "enter")]);
    expect(live[0].done).toBe(false);
  });
  it("is empty without events", () => expect(stages([])).toEqual([]));
});

describe("decidedBy / modelCalls", () => {
  it("reports rules, AI or nothing", () => {
    expect(decidedBy(EVENTS)).toBe("rules");
    expect(decidedBy([ev(1, 1, "investigate", "exit", { decided_by: "model" })])).toBe("AI");
    expect(decidedBy([])).toBeNull();
  });
  it("never guesses model calls", () => {
    expect(modelCalls({ model_calls: 0 })).toBe(0);
    expect(modelCalls({})).toBeNull();
  });
});

describe("citedEvidence", () => {
  it("prefers the incident field, then the record exit", () => {
    expect(citedEvidence({ cited_evidence: ["x"] }, EVENTS)).toEqual(["x"]);
    expect(citedEvidence({}, EVENTS)).toEqual(["ev_1", "obs_1"]);
    expect(citedEvidence({}, [])).toEqual([]);
  });
});

describe("groupEvidence", () => {
  it("groups by kind in a fixed order and drops empty groups", () => {
    const groups = groupEvidence([{ kind: "observation" }, { kind: "alert" }, { kind: "metric_snapshot" }], "vm-166");
    expect(groups.map((g) => g.title)).toEqual(["What triggered it", "Metrics", "Reads on vm-166"]);
  });
});

describe("chain / names / sentence", () => {
  it("hides the arrow when the root cause is the target", () => {
    expect(chain({ target: "a", root_cause_target: "a" }).sameTarget).toBe(true);
    expect(chain({ target: "a", root_cause_target: "b" }).sameTarget).toBe(false);
    expect(chain({ target: "a" }).sameTarget).toBe(true);
  });
  it("shortens targets", () => {
    expect(shortName("vm-166/container:argus-lab-client")).toBe("argus-lab-client");
    expect(shortName("vm-166")).toBe("vm-166");
  });
  it("takes the first sentence", () => {
    expect(firstSentence("One thing. Another thing.")).toBe("One thing.");
    expect(firstSentence("no period")).toBe("no period");
  });
});

describe("reason", () => {
  it("shows the root cause when diagnosed, the outcome's meaning otherwise", () => {
    expect(reason({ outcome: "diagnosed", target: "vm/a", root_cause_target: "vm/container:b" })).toBe("Root cause: b");
    expect(reason({ outcome: "no_incident" })).toBe("Healthy: no incident found");
    expect(reason({ outcome: null, status: "running" })).toBe("Investigation in progress");
  });
});

describe("summaryText", () => {
  it("lists the answer and the cited evidence ids", () => {
    const t = summaryText({ id: "inc_1", target: "t", status: "closed", outcome: "diagnosed", root_cause_target: "r" }, ["ev_1"]);
    expect(t).toContain("Incident inc_1");
    expect(t).toContain("Root cause: r");
    expect(t).toContain("Cited evidence: ev_1");
  });
});

describe("runbooksRead", () => {
  it("lists the recalled runbooks once each, in order", () => {
    expect(runbooksRead(EVENTS)).toEqual(["RB-003"]);
    const twice = [ev(1, 1, "recall", "exit", { passages: ["RB-1", "RB-2"] }), ev(2, 2, "recall", "exit", { passages: ["RB-2", "RB-3"] })];
    expect(runbooksRead(twice)).toEqual(["RB-1", "RB-2", "RB-3"]);
  });
  it("is empty when nothing was recalled", () => {
    expect(runbooksRead([ev(1, 1, "recall", "exit", { passages: [] })])).toEqual([]);
    expect(runbooksRead([])).toEqual([]);
  });
});

describe("real events carry objects, not strings", () => {
  it("never prints [object Object] and still finds the runbooks", () => {
    const real = [
      ev(1, 1, "recall", "exit", { passages: [{ runbook_id: "RB-003", section: "Detect" }, { runbook_id: "RB-003", section: "Fix" }, { source: "runbooks/RB-007-disk.md" }] }),
      ev(2, 2, "investigate", "exit", { decided_by: "model", decision: { kind: "use_read_tools", tools: ["container.logs"] } }),
      ev(3, 3, "act", "exit"),
      ev(4, 4, "investigate", "exit", { decided_by: "model", decision: { kind: "conclude", root_cause_target: "vm-1/container:x", confidence: "high" } }),
    ];
    expect(runbooksRead(real)).toEqual(["RB-003", "RB-007-disk"]);
    const text = stages(real).map((s) => s.summary).join(" | ");
    expect(text).not.toContain("[object");
    expect(text).toContain("Runbook RB-003, RB-007-disk");
    expect(text).toContain("Chose read tools (AI)");
    expect(text).toContain("Concluded: root cause x, confidence high (AI)");
  });
  it("says only what it can read when an object has nothing readable", () => {
    const odd = [ev(1, 1, "recall", "exit", { passages: [{ score: 0.4 }, { score: 0.2 }] }), ev(2, 2, "investigate", "exit", { decision: { weights: [1] } })];
    const text = stages(odd).map((s) => s.summary).join(" | ");
    expect(text).toBe("2 runbook passages recalled | Decision recorded");
    expect(runbooksRead(odd)).toEqual([]);
  });
});

describe("a real incident (dependency_unavailable, escalated)", () => {
  const real = [
    ev(1, 54, "detect", "exit", { result: "dependency_unavailable", family: "dependency" }),
    ev(2, 55, "recall", "exit", { passages: [{ runbook_id: "RB-003", section: "A" }, { runbook_id: "RB-003", section: "B" }, { runbook_id: "RB-009", section: "C" }] }),
    ev(3, 55, "investigate", "exit", { decided_by: "rule", decision: { kind: "use_read_tools", calls: [{ capability: "container.status" }, { capability: "container.status" }] } }),
    ev(4, 55, "act", "step", { capability: "container.status", target: "vm-166/container:a", status: "error", evidence_id: "obs_1" }),
    ev(5, 55, "act", "step", { capability: "container.status", target: "vm-166/container:b", status: "error", evidence_id: "obs_2" }),
    ev(6, 56, "investigate", "exit", { decided_by: "rule", decision: { kind: "escalate", reason: "no rule decides from the evidence" } }),
    ev(7, 56, "record", "exit", { outcome: "no_action_escalated", cited: ["ev_1", "obs_1"] }),
  ];
  it("describes each stage in plain words", () => {
    expect(stages(real).map((s) => s.summary)).toEqual([
      "Matched dependency_unavailable",
      "Runbook RB-003, RB-009",
      "Chose 2 read tools (rules)",
      "2 reads · 2 not ok",
      "Escalated: no rule decides from the evidence (rules)",
      "Closed as no action escalated",
    ]);
    expect(runbooksRead(real)).toEqual(["RB-003", "RB-009"]);
    expect(citedEvidence({}, real)).toEqual(["ev_1", "obs_1"]);
  });
});
