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
