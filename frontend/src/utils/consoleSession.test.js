import { describe, expect, it } from "vitest";
import { analysisView, errorLine, historyInputs, planInput, printable, resultLines, seedLines, stepHistory } from "./consoleSession.js";

// CON-3 (ACR-0043): the terminal's logic, kept out of the component so it is tested without a DOM.
describe("planInput", () => {
  it("sends a trimmed command, keeps blank input local and clears the screen locally", () => {
    expect(planInput("  cache status ", null)).toEqual({ kind: "send", input: "cache status" });
    expect(planInput("   ", null)).toEqual({ kind: "empty" });
    expect(planInput("CLEAR", null)).toEqual({ kind: "clear" });
  });

  it("while a write waits for confirmation, only 'yes' resends the same input with the confirmation", () => {
    const pending = { input: "cache restart" };
    expect(planInput(" Yes ", pending)).toEqual({ kind: "send", input: "cache restart", confirmation: "yes" });
    for (const other of ["no", "", "y", "yes please", "clear"]) expect(planInput(other, pending)).toEqual({ kind: "cancel" });
  });
});

describe("resultLines", () => {
  it("prints the output of a command, one line each", () => {
    expect(resultLines({ status: "ok", output: ["cache: exited", "health: none"] })).toEqual({
      lines: [{ kind: "out", text: "cache: exited" }, { kind: "out", text: "health: none" }], pending: null });
  });

  it("prints a rejected or failed command in the error colour", () => {
    expect(resultLines({ status: "rejected", output: ["command not found: ls."] }).lines).toEqual([{ kind: "error", text: "command not found: ls." }]);
    expect(resultLines({ status: "error", output: ["timeout"] }).lines[0].kind).toBe("error");
  });

  it("asks for confirmation with the API's prompt and remembers the input", () => {
    const r = resultLines({ status: "needs_confirmation", input: "cache restart", output: [], prompt: "cache restart needs approval. Type 'yes'." });
    expect(r.pending).toEqual({ input: "cache restart" });
    expect(r.lines).toEqual([{ kind: "prompt", text: "cache restart needs approval. Type 'yes'." }]);
  });

  it("never prints control characters from the output", () => {
    expect(printable("a\x1b[2Jb\x07c")).toBe("a�[2Jb�c");
    expect(resultLines({ status: "ok", output: ["x\x1bc"] }).lines[0].text).toBe("x�c");
    expect(resultLines({ status: "ok" }).lines).toEqual([]);
  });
});

describe("errorLine", () => {
  it("says when to retry after a 429 and why the console failed otherwise", () => {
    expect(errorLine(Object.assign(new Error("Too many"), { status: 429, retryAfter: 12 }))).toBe("too many commands, try again in 12 s");
    expect(errorLine(Object.assign(new Error("Too many"), { status: 429 }))).toBe("too many commands, try again later");
    expect(errorLine(new Error("Failed to fetch"))).toBe("console unavailable: Failed to fetch");
    expect(errorLine(null)).toBe("console unavailable: unknown error");
  });
});

describe("history", () => {
  const entries = [
    { command_id: "c1", input: "status", status: "ok", output: ["cache: exited"] },
    { command_id: "c2", input: "ls", status: "rejected", output: ["command not found: ls."] },
  ];

  it("opens with a greeting and replays the incident's stored commands", () => {
    expect(seedLines("inc_1", entries)).toEqual([
      { kind: "info", text: "Operator console for inc_1. Type 'help' to see available commands." },
      { kind: "input", text: "status" }, { kind: "out", text: "cache: exited" },
      { kind: "input", text: "ls" }, { kind: "error", text: "command not found: ls." },
    ]);
  });

  it("lists inputs newest first, typed ones before stored ones, without repeats in a row", () => {
    expect(historyInputs(entries, ["api cpu", "api cpu", "map api"])).toEqual(["map api", "api cpu", "ls", "status"]);
  });

  it("walks the list with the arrows and comes back to an empty line", () => {
    const list = ["map api", "api cpu"];
    expect(stepHistory(list, -1, "ArrowUp")).toEqual({ index: 0, value: "map api" });
    expect(stepHistory(list, 0, "ArrowUp")).toEqual({ index: 1, value: "api cpu" });
    expect(stepHistory(list, 1, "ArrowUp")).toEqual({ index: 1, value: "api cpu" });
    expect(stepHistory(list, 1, "ArrowDown")).toEqual({ index: 0, value: "map api" });
    expect(stepHistory(list, 0, "ArrowDown")).toEqual({ index: -1, value: "" });
    expect(stepHistory([], -1, "ArrowUp")).toEqual({ index: -1, value: "" });
  });
});

describe("analysisView", () => {
  const now = Date.parse("2026-10-29T10:44:00Z");

  it("shows Argus's analysis states as the API sends them, and nothing without one", () => {
    expect(analysisView(undefined, now)).toBeNull();
    expect(analysisView({ status: "waiting", settle_until: "2026-10-29T10:44:30Z" }, now))
      .toEqual({ tone: "neutral", text: "Waiting for metrics to settle (30 s)" });
    expect(analysisView({ status: "waiting", settle_until: "2026-10-29T10:43:00Z" }, now).text).toBe("Waiting for metrics to settle");
    expect(analysisView({ status: "analyzing" }, now)).toEqual({ tone: "blue", text: "Argus is analysing the result" });
    expect(analysisView({ status: "done", comment: "The cache came back; API errors fell to zero." }, now))
      .toEqual({ tone: "green", text: "The cache came back; API errors fell to zero." });
    expect(analysisView({ status: "error", reason: "metrics not available yet" }, now))
      .toEqual({ tone: "amber", text: "Analysis unavailable: metrics not available yet" });
  });
});
