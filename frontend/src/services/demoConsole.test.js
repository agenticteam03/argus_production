import { beforeEach, describe, expect, it } from "vitest";
import { demoConsoleCommands, demoConsoleExecute, demoConsoleHistory, demoConsoleRecheck, resetDemoConsole } from "./demoConsole.js";

// CON-3: the offline demo of the console routes (shapes in brain/tasks/current/argus-console-mockup-spec.md §5).
// The real parser is argus/console/parser.py (CON-1); this one only has to answer like it for the demo.
describe("demo console", () => {
  beforeEach(() => resetDemoConsole());

  it("lists the same commands as the backend registry, three of them writes", () => {
    const { commands } = demoConsoleCommands();
    expect(commands.map((c) => c.usage)).toContain("cache status");
    expect(commands.filter((c) => c.class === "write").map((c) => c.id).sort()).toEqual(["cache.restart", "net.reconnect", "worker.restart"]);
    for (const c of commands) expect(Object.keys(c).sort()).toEqual(["class", "id", "scenario", "summary", "usage"]);
  });

  it("rejects shell syntax and unknown verbs before anything runs", () => {
    expect(demoConsoleExecute("inc_1", { input: "status; rm" }, "olga")).toMatchObject({ status: "rejected", output: [expect.stringContaining("syntax not allowed")] });
    expect(demoConsoleExecute("inc_1", { input: "ls" }, "olga")).toMatchObject({ status: "rejected", output: ["command not found: ls. Type 'help' to see available commands."] });
  });

  it("answers a read command and stores it in the incident's history", () => {
    const r = demoConsoleExecute("inc_1", { input: "cache status" }, "olga");
    expect(r).toMatchObject({ status: "ok", command: "cache.status", class: "read" });
    expect(r.output.length).toBeGreaterThan(0);
    expect(demoConsoleHistory("inc_1").entries.map((e) => [e.input, e.by])).toEqual([["cache status", "olga"]]);
    expect(demoConsoleHistory("inc_2").entries).toEqual([]);
  });

  it("asks before a write and, after 'yes', only proposes it: no approval is given", () => {
    const ask = demoConsoleExecute("inc_1", { input: "cache restart" }, "olga");
    expect(ask).toMatchObject({ status: "needs_confirmation", input: "cache restart" });
    expect(ask.prompt).toMatch(/yes/);
    const done = demoConsoleExecute("inc_1", { input: "cache restart", confirmation: "yes" }, "olga");
    expect(done.status).toBe("ok");
    expect(done.output.join("\n")).toMatch(/proposal/i);
    expect(done.output.join("\n")).toMatch(/approver/i);
  });

  it("accepts the optional --since and checks the service argument", () => {
    expect(demoConsoleExecute("inc_1", { input: "api cpu --since 10:30" }, "olga").status).toBe("ok");
    expect(demoConsoleExecute("inc_1", { input: "api errors" }, "olga").status).toBe("ok");
    expect(demoConsoleExecute("inc_1", { input: "map api" }, "olga").status).toBe("ok");
    expect(demoConsoleExecute("inc_1", { input: "map db" }, "olga").output[0]).toMatch(/unknown service: db/);
  });

  it("lists help from the catalog", () => {
    const r = demoConsoleExecute("inc_1", { input: "help" }, "olga");
    expect(r.output[0]).toBe("Available commands:");
    expect(r.output.length).toBe(demoConsoleCommands().commands.length + 1);
  });
});

describe("demo console suggestions (CON-5)", () => {
  beforeEach(() => resetDemoConsole());

  it("after a cache status, Argus's analysis suggests a registry command", () => {
    demoConsoleExecute("inc_1", { input: "cache status" }, "olga");
    const [e] = demoConsoleHistory("inc_1").entries;
    expect(e.analysis).toMatchObject({ status: "done", suggestion: { command: "cache restart", command_id: "cache.restart" } });
  });

  it("stores the suggestion id of an inserted, unedited run", () => {
    demoConsoleExecute("inc_1", { input: "cache status", suggestion_id: "sug-cmd_1" }, "olga");
    expect(demoConsoleHistory("inc_1").entries[0].suggestion_id).toBe("sug-cmd_1");
  });
});

describe("demo console errors and re-check (CON-9)", () => {
  beforeEach(() => resetDemoConsole());

  it("reaches each analysis failure: metrics not available yet, a stuck analysis and a backend failure", () => {
    demoConsoleExecute("inc_1", { input: "api errors" }, "olga");
    demoConsoleExecute("inc_1", { input: "host metrics" }, "olga");
    demoConsoleExecute("inc_1", { input: "worker throughput" }, "olga");
    const [metrics, stuck, failed] = demoConsoleHistory("inc_1").entries.map((e) => e.analysis);
    expect(metrics).toMatchObject({ status: "error", message: "Metrics not available yet", retryable: true });
    expect(stuck.status).toBe("analyzing");
    expect(Date.now() - Date.parse(stuck.settle_until)).toBeGreaterThan(90_000);
    expect(failed).toMatchObject({ status: "error", error: "Analysis could not be completed", retryable: true });
  });

  it("a re-check runs the analysis again and the next history read has the result", () => {
    demoConsoleExecute("inc_1", { input: "api errors" }, "olga");
    const [{ command_id }] = demoConsoleHistory("inc_1").entries;
    expect(demoConsoleRecheck("inc_1", command_id)).toMatchObject({ command_id, analysis: { status: "done" } });
    expect(demoConsoleHistory("inc_1").entries[0].analysis).toMatchObject({ status: "done", comment: expect.any(String) });
  });

  it("refuses a re-check of an unknown command or of one that is not retryable", () => {
    demoConsoleExecute("inc_1", { input: "cache status" }, "olga");
    expect(() => demoConsoleRecheck("inc_1", "cmd_nope")).toThrow(/not found/);
    expect(() => demoConsoleRecheck("inc_1", "cmd_1")).toThrow(/not retryable/);
  });
});
