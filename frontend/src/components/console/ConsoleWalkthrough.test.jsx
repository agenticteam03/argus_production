import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import ConsolePanel from "./ConsolePanel.jsx";
import ConsoleTerminal from "./ConsoleTerminal.jsx";
import { demoConsoleExecute, demoConsoleHistory, resetDemoConsole } from "../../services/demoConsole.js";
import { httpArgusAdapter } from "../../services/httpArgusAdapter.js";
import { analysisView, errorLine } from "../../utils/consoleSession.js";

const incident = { id: "walkthrough", status: "open", root_cause_target: "vm-166/container:argus-lab-cache",
  confidence: 0.82, ruled_out: [] };
const commands = [
  { id: "cache.restart", usage: "cache restart" },
  { id: "cache.status", usage: "cache status" },
  { id: "worker.restart", usage: "worker restart" },
  { id: "worker.status", usage: "worker status" },
  { id: "net.inspect", usage: "net inspect <service>" },
  { id: "net.expected", usage: "net expected <service>" },
  { id: "net.diff", usage: "net diff <service>" },
  { id: "net.reconnect", usage: "net reconnect api" },
];

function rehearse(id, steps) {
  const trace = [];
  for (const input of steps) {
    const asked = demoConsoleExecute(id, { input }, "operator");
    trace.push(asked);
    if (asked.status === "needs_confirmation") trace.push(demoConsoleExecute(id, { input, confirmation: "yes" }, "operator"));
  }
  return { trace, history: demoConsoleHistory(id).entries };
}

const terminalMarkup = (id, history) => renderToStaticMarkup(
  <ConsoleTerminal incidentId={id} history={history} run={vi.fn()} />,
);
const panelMarkup = (history, props = {}) => renderToStaticMarkup(
  <ConsolePanel incident={incident} history={history} commands={commands} now={Date.parse("2026-10-29T10:50:00Z")} {...props} />,
);
const visibleText = (markup) => markup.replace(/<[^>]*>/g, " ")
  .replace(/&(?:#\d+|#x[\da-f]+|amp|lt|gt|quot|apos);/gi, " ");

beforeEach(() => resetDemoConsole());
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.useRealTimers(); });

describe("offline operator console walkthroughs", () => {
  it("shows the cache red-herring reads, confirmation, proposal, and suggestion in order", () => {
    const id = "scenario-cache";
    const { trace, history } = rehearse(id, ["cache status", "api cpu", "cache restart"]);
    const terminal = terminalMarkup(id, trace);
    const panel = panelMarkup(history, { onInsert: vi.fn() });
    for (const text of ["cache status", "api cpu", "cache restart needs approval", "proposal created: container.start on vm-166/container:argus-lab-cache"]) {
      expect(terminal).toContain(text);
    }
    expect(terminal.indexOf("cache status")).toBeLessThan(terminal.indexOf("api cpu"));
    expect(terminal.indexOf("api cpu")).toBeLessThan(terminal.indexOf("cache restart needs approval"));
    expect(terminal.indexOf("cache restart needs approval")).toBeLessThan(terminal.indexOf("proposal created"));
    expect(visibleText(panel)).toContain("CPU did not change");
    expect(panel).toContain("Insert into console");
    expect(panel).toContain(">Copy<");
  });

  it("shows the frozen-worker reads, confirmation, and worker proposal in order", () => {
    const id = "scenario-worker";
    const { trace } = rehearse(id, ["worker status", "worker restart"]);
    const terminal = terminalMarkup(id, trace);
    for (const text of ["worker status", "worker: running, healthy", "worker restart needs approval",
      "proposal created: container.restart on vm-166/container:argus-lab-jobworker"]) expect(terminal).toContain(text);
    expect(terminal.indexOf("worker status")).toBeLessThan(terminal.indexOf("worker restart needs approval"));
    expect(terminal.indexOf("worker restart needs approval")).toBeLessThan(terminal.indexOf("proposal created"));
  });

  it("shows the network comparison reads and reconnect proposal in order", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-29T10:50:00Z"));
    const id = "scenario-network";
    const { trace } = rehearse(id, ["net inspect api", "net expected api", "net diff api", "net reconnect api"]);
    const history = demoConsoleHistory(id).entries;
    const terminal = terminalMarkup(id, trace);
    for (const text of ["net inspect api", "net expected api", "net diff api", "network mismatch",
      "net reconnect api needs approval", "proposal created: network.restore on vm-166/container:argus-lab-api"]) {
      expect(terminal).toContain(text);
    }
    expect(terminal.indexOf("net inspect api")).toBeLessThan(terminal.indexOf("net expected api"));
    expect(terminal.indexOf("net expected api")).toBeLessThan(terminal.indexOf("net diff api"));
    expect(terminal.indexOf("net diff api")).toBeLessThan(terminal.indexOf("net reconnect api needs approval"));
    expect(history.find((entry) => entry.command === "net.reconnect").analysis)
      .toMatchObject({ status: "waiting", countdown_s: 45 });
    vi.advanceTimersByTime(45_000);
    const analysis = demoConsoleHistory(id).entries.find((entry) => entry.command === "net.reconnect").analysis;
    expect(analysis).toMatchObject({ status: "done", ranking: [{ target: "api", rank: 1 }] });
    expect(analysis.comment).toContain("addressing the mismatch");
  });

  it("shows that the API is attached to the wrong network before proposing reconnect", () => {
    const { history } = rehearse("network-mismatch", ["net inspect api", "net expected api", "net diff api"]);
    const actual = history.find((entry) => entry.command === "net.inspect");
    const expected = history.find((entry) => entry.command === "net.expected");
    const diff = history.find((entry) => entry.command === "net.diff");
    expect(actual.output[0]).not.toBe(expected.output[0]);
    expect(diff.output.join(" ")).not.toContain("no difference");
  });

  it("provides waiting then done analysis and ranking changes for cache and worker writes", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-29T10:50:00Z"));
    const cacheId = "cache-lifecycle";
    const cache = rehearse(cacheId, ["cache status", "cache restart"]).history;
    const cacheWaiting = cache.find((entry) => entry.command === "cache.restart").analysis;
    expect(cacheWaiting).toMatchObject({ status: "waiting", countdown_s: 45 });
    vi.advanceTimersByTime(45_000);
    const cacheDone = demoConsoleHistory(cacheId).entries.find((entry) => entry.command === "cache.restart").analysis;
    expect(cacheDone).toMatchObject({ status: "done", ranking: [{ target: "cache", rank: 1 }] });
    expect(cacheDone.comment).toContain("cache read reported cache: exited");
    expect(cacheDone.suggestion).toMatchObject({ command: "cache status", command_id: "cache.status" });

    const workerId = "worker-lifecycle";
    const worker = rehearse(workerId, ["worker status", "worker restart"]).history;
    expect(worker.find((entry) => entry.command === "worker.restart").analysis)
      .toMatchObject({ status: "waiting", countdown_s: 45 });
    vi.advanceTimersByTime(45_000);
    const workerDone = demoConsoleHistory(workerId).entries.find((entry) => entry.command === "worker.restart").analysis;
    expect(workerDone).toMatchObject({ status: "done", ranking: [{ target: "worker", rank: 1 }] });
    expect(workerDone.comment).toContain("worker read reported worker: running, healthy");
    expect(workerDone.suggestion).toMatchObject({ command: "worker status", command_id: "worker.status" });
    expect(cacheDone.ranking[0].target).not.toBe(workerDone.ranking[0].target);
  });
});

describe("operator console errors and accessibility", () => {
  it("shows a refused command and hint without adding analysis", () => {
    const result = demoConsoleExecute("refused", { input: "ls" }, "operator");
    const terminal = terminalMarkup("refused", [result]);
    const [entry] = demoConsoleHistory("refused").entries;
    expect(result.status).toBe("rejected");
    expect(terminal).toContain("command not found: ls");
    expect(terminal).toContain("Type &#x27;help&#x27;");
    expect(entry.analysis).toBeUndefined();
    expect(panelMarkup([entry])).not.toContain("Analysis unavailable");
  });

  it("reports unavailable metrics with a retryable Re-check action", () => {
    demoConsoleExecute("metrics-error", { input: "api errors" }, "operator");
    const history = demoConsoleHistory("metrics-error").entries;
    const panel = panelMarkup(history, { onRecheck: vi.fn() });
    expect(panel).toContain("Metrics not available yet");
    expect(panel).toContain(">Re-check<");
  });

  it("counts down the 45 second metrics settle window with fake time", () => {
    vi.useFakeTimers();
    const start = new Date("2026-10-29T10:50:00Z");
    vi.setSystemTime(start);
    const analysis = { status: "waiting", countdown_s: 45, settle_until: new Date(start.getTime() + 45_000).toISOString() };
    expect(analysisView(analysis).text).toBe("Waiting for metrics to settle (45 s)");
    vi.advanceTimersByTime(12_000);
    expect(analysisView(analysis).text).toBe("Waiting for metrics to settle (33 s)");
  });

  it("renders the 429 retry line while leaving the command input and Run button enabled", () => {
    const message = errorLine({ status: 429, retryAfter: 9 });
    const terminal = terminalMarkup("rate-limit", [{ command_id: "limited", input: "api errors", status: "error", output: [message] }]);
    expect(terminal).toContain("too many commands, try again in 9 s");
    expect(terminal).toContain('aria-label="Console command"');
    expect(terminal).toContain(">Run</button>");
    expect(terminal).not.toContain('disabled=""');
  });

  it("hides the real console adapter route when VITE_ARGUS_CONSOLE is unset", async () => {
    vi.stubEnv("VITE_ARGUS_CONSOLE", "");
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    expect(await httpArgusAdapter.getConsoleCommands("inc_1")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("restores saved command output when a console panel is reopened", () => {
    const { history } = rehearse("restored", ["cache status"]);
    const reopened = terminalMarkup("restored", history);
    expect(reopened).toContain("Operator console for restored");
    expect(reopened).toContain("cache status");
    expect(reopened).toContain("cache: exited (code 137)");
  });

  it("labels the input and log and gives each console button a name", () => {
    const terminal = terminalMarkup("a11y", []);
    const panel = panelMarkup([], { onInsert: vi.fn() });
    expect(terminal).toContain('role="log" aria-live="polite"');
    expect(terminal).toContain('for="console-input-a11y"');
    expect(terminal).toContain('aria-label="Console command"');
    expect(terminal).toContain(">Run</button>");
    expect(panel).toContain("No commands yet");
  });
});

describe("operator console wording guard", () => {
  it("keeps forbidden terms out of visible walkthrough text", () => {
    const cache = rehearse("wording-cache", ["cache status", "api cpu", "cache restart"]);
    const worker = rehearse("wording-worker", ["worker status", "worker restart"]);
    const network = rehearse("wording-network", ["net inspect api", "net expected api", "net diff api", "net reconnect api"]);
    const refused = demoConsoleExecute("wording-refused", { input: "ls" }, "operator");
    const limited = [{ command_id: "limited", input: "api errors", status: "error", output: [errorLine({ status: 429, retryAfter: 9 })] }];
    const analysisStates = [
      { command_id: "waiting", input: "api errors", status: "ok", analysis: { status: "waiting", countdown_s: 10 } },
      { command_id: "done", input: "cache status", status: "ok", analysis: { status: "done", comment: "Cache analysis complete." } },
      { command_id: "error", input: "api errors", status: "ok", analysis: { status: "error", message: "Metrics not available yet", retryable: true } },
      { command_id: "denied", input: "worker restart", status: "ok", analysis: { status: "error", message: "This result cannot be re-checked", retryable: false } },
    ];
    const allMarkup = [
      terminalMarkup("wording-cache", cache.trace), panelMarkup(cache.history, { onInsert: vi.fn() }),
      terminalMarkup("wording-worker", worker.trace), panelMarkup(worker.history),
      terminalMarkup("wording-network", network.trace), panelMarkup(network.history),
      terminalMarkup("wording-refused", [refused]), terminalMarkup("wording-limited", limited), panelMarkup(analysisStates),
    ].join(" ");
    const rendered = visibleText(allMarkup).toLowerCase();
    expect(rendered).not.toMatch(/demo|mock|fake|simulat/);
  });

  it("keeps forbidden terms out of user-facing string literals in console components and utilities", () => {
    const roots = [new URL("./", import.meta.url), new URL("../../utils/", import.meta.url)];
    const sourceFiles = roots.flatMap((root) => readdirSync(fileURLToPath(root))
      .filter((name) => /\.jsx?$/.test(name) && !name.includes(".test.")
        && (!root.href.includes("/utils/") || name.startsWith("console")))
      .map((name) => `${fileURLToPath(root)}${name}`));
    const banned = /demo|mock|fake|simulat/i;
    for (const file of sourceFiles) {
      const source = readFileSync(file, "utf8");
      const literals = [...source.matchAll(/["'`]([^"'`\r\n]*)["'`]/g)].map((match) => match[1]);
      expect(literals.filter((literal) => banned.test(literal)), file).toEqual([]);
    }
  });
});
