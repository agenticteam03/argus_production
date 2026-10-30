import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("../../services/index.js", () => ({ argus: {} }));
const { default: OperatorConsole } = await import("./OperatorConsole.jsx");
const { default: ConsolePanel } = await import("./ConsolePanel.jsx");

const incident = { id: "inc_1", status: "closed", root_cause_target: "vm-166/container:argus-lab-cache", confidence: 0.86,
  ruled_out: ["vm-166/container:argus-lab-api"] };
const history = [
  { command_id: "c1", input: "cache status", status: "ok", output: ["cache: exited"], by: "olga", started_at: "2026-10-29T10:44:00Z",
    analysis: { status: "done", comment: "The cache is stopped; that explains the API errors." } },
  { command_id: "c2", input: "status; rm", status: "rejected", output: ["syntax not allowed: ;."], by: "olga", started_at: "2026-10-29T10:45:00Z" },
];
const consoleState = { commands: [{ id: "help", usage: "help", class: "meta", scenario: "all", summary: "List the commands" }], history, run: async () => ({}) };

describe("OperatorConsole (CON-3)", () => {
  it("is a terminal and the Argus panel side by side on desktop, stacked on narrow screens", () => {
    const html = renderToStaticMarkup(<OperatorConsole incident={incident} console={consoleState} />);
    expect(html).toContain("Operator console");
    expect(html).toContain("lg:grid-cols-[minmax(0,55fr)_minmax(0,45fr)]");
    expect(html).toContain('role="log"');
    expect(html).toContain('aria-label="Console command"');
    expect(html).toContain("argus$");
    for (const word of ["demo", "mock", "shell"]) expect(html.toLowerCase()).not.toContain(`${word} console`);
  });

  it("replays the incident's stored commands in the terminal", () => {
    const html = renderToStaticMarkup(<OperatorConsole incident={incident} console={consoleState} />);
    expect(html).toContain("Operator console for inc_1");
    expect(html).toContain("cache: exited");
    expect(html).toContain("syntax not allowed: ;.");
  });
});

describe("ConsolePanel", () => {
  it("shows the incident's own diagnosis, not console state", () => {
    const html = renderToStaticMarkup(<ConsolePanel incident={incident} history={[]} now={Date.parse("2026-10-29T10:46:00Z")} />);
    expect(html).toContain("Current diagnosis");
    expect(html).toContain("argus-lab-cache");
    expect(html).toContain("86%");
    expect(html).toContain("argus-lab-api");
    expect(html).toContain("No commands yet");
  });

  it("lists commands newest first with their status word and Argus's comment when there is one", () => {
    const html = renderToStaticMarkup(<ConsolePanel incident={incident} history={history} now={Date.parse("2026-10-29T10:46:00Z")} />);
    expect(html.indexOf("status; rm")).toBeLessThan(html.indexOf("cache status"));
    expect(html).toContain("Rejected");
    expect(html).toContain("The cache is stopped; that explains the API errors.");
    expect(html).toContain("olga");
  });
});

describe("ConsolePanel suggestions (CON-5)", () => {
  const commands = [{ id: "cache.restart", usage: "cache restart" }, { id: "cache.status", usage: "cache status" }];
  const withSuggestion = [
    { command_id: "c1", input: "cache status", status: "ok", by: "olga", started_at: "2026-10-29T10:44:00Z",
      analysis: { status: "done", comment: "The cache is stopped.", suggestion: { command: "cache restart", command_id: "cache.restart", rationale: "The API depends on it." } } },
    { command_id: "c2", input: "map api", status: "ok", by: "olga", started_at: "2026-10-29T10:45:00Z",
      analysis: { status: "done", comment: "x", suggestion: { command: "rm -rf /" } } },
  ];
  const render = (history) => renderToStaticMarkup(<ConsolePanel incident={incident} history={history} commands={commands} now={0} onInsert={() => {}} />);

  it("shows a card per registry suggestion with Insert and Copy, and never one outside the registry", () => {
    const html = render(withSuggestion);
    expect(html).toContain("Suggestions");
    expect(html).toContain("cache restart");
    expect(html).toContain("The API depends on it.");
    expect(html).toContain("Insert into console");
    expect(html).toContain(">Copy<");
    expect(html).not.toContain("rm -rf");
    expect(html).not.toContain("Applied");
  });

  it("marks a suggestion Applied once a stored command carries its id", () => {
    const html = render([...withSuggestion, { command_id: "c3", input: "cache restart", status: "ok", suggestion_id: "sug-c1" }]);
    expect(html).toContain("Applied");
  });

  it("shows no Suggestions card without a suggestion", () => {
    expect(render([])).not.toContain("Suggestions");
  });
});

describe("ConsolePanel errors and re-check (CON-9)", () => {
  const now = Date.parse("2026-10-29T10:50:00Z");
  const entry = (command_id, analysis) => ({ command_id, input: "api errors", status: "ok", by: "olga", started_at: "2026-10-29T10:44:00Z", analysis });
  const render = (history, props = {}) => renderToStaticMarkup(<ConsolePanel incident={incident} history={history} now={now} {...props} />);

  it("shows Re-check only on a retryable analysis, and only when the console can re-check", () => {
    const history = [entry("c1", { status: "error", message: "Metrics not available yet", retryable: true }),
      entry("c2", { status: "error", reason: "no samples" })];
    const html = render(history, { onRecheck: () => {} });
    expect(html).toContain("Metrics not available yet");
    expect(html).toContain("Analysis unavailable: no samples");
    expect(html.match(/>Re-check</g)).toHaveLength(1);
    expect(render(history)).not.toContain("Re-check");
  });

  it("says when an analysis is taking longer than expected", () => {
    const html = render([entry("c1", { status: "analyzing", settle_until: "2026-10-29T10:45:00Z" })], { onRecheck: () => {} });
    expect(html).toContain("Analysis is taking longer than expected");
    expect(html).toContain(">Re-check<");
  });

  it("keeps the last history and says it is retrying while the history cannot be read", () => {
    const html = render([entry("c1", { status: "done", comment: "Errors follow the cache." })], { historyUnavailable: true });
    expect(html).toContain("Console history unavailable, retrying");
    expect(html).toContain('role="status"');
    expect(html).toContain("Errors follow the cache.");
    expect(render([])).not.toContain("Console history unavailable");
  });
});
