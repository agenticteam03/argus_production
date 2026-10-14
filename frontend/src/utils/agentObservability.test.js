import { describe, expect, it } from "vitest";
import { summarizeRun } from "./agentObservability.js";

describe("agent run summary", () => {
  it("counts tools and derives the current node without exposing event payloads", () => {
    const events = [
      { node: "detect", phase: "enter", data: { trace_id: "a".repeat(32), reason: "private" } },
      { node: "detect", phase: "exit", data: {} },
      { node: "act", phase: "step", data: { capability: "read_memory", status: "ok", result: "secret" } },
    ];
    expect(summarizeRun(events)).toEqual({ traceId: "a".repeat(32), node: "act", tools: 1, decisions: 0, steps: 3 });
  });
});
