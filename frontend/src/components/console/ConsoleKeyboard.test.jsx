/** @vitest-environment jsdom */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConsolePanel from "./ConsolePanel.jsx";
import ConsoleTerminal from "./ConsoleTerminal.jsx";

const incident = { id: "inc_keyboard", status: "open", ruled_out: [] };
const commands = [{ id: "cache.status", usage: "cache status" }];
const history = [
  { command_id: "c1", input: "cache status", status: "ok", output: ["cache: running"],
    analysis: { status: "done", comment: "The cache is healthy.", suggestion: { command: "cache status", command_id: "cache.status" } } },
  { command_id: "c2", input: "api errors", status: "ok", output: [],
    analysis: { status: "error", message: "Metrics not available yet", retryable: true } },
];

const terminal = (run, entries = []) => render(<ConsoleTerminal incidentId={incident.id} history={entries} run={run} />);
const commandInput = () => screen.getByRole("textbox", { name: "Console command" });
const waitForFocus = (element) => waitFor(() => expect(document.activeElement).toBe(element));

afterEach(() => cleanup());

describe("Operator console keyboard behavior", () => {
  it("submits with Enter, restores input focus, and recalls history with Up and Down", async () => {
    const user = userEvent.setup();
    const run = vi.fn().mockResolvedValue({ status: "ok", output: ["cache is healthy"] });
    terminal(run, history);
    const input = commandInput();
    await waitForFocus(input);

    await user.type(input, "worker status{Enter}");
    await waitFor(() => expect(run).toHaveBeenCalledWith(expect.objectContaining({ input: "worker status" })));
    await waitForFocus(input);
    await user.keyboard("{ArrowUp}");
    expect(input.value).toBe("worker status");
    await user.keyboard("{ArrowUp}");
    expect(input.value).toBe("api errors");
    await user.keyboard("{ArrowDown}");
    expect(input.value).toBe("worker status");
    await user.keyboard("{ArrowDown}");
    expect(input.value).toBe("");
  });

  it("accepts yes only at the confirmation prompt, and Escape cancels without another run", async () => {
    const user = userEvent.setup();
    const run = vi.fn()
      .mockResolvedValueOnce({ status: "ok", output: ["command checked"] })
      .mockResolvedValueOnce({ status: "needs_confirmation", input: "cache restart", prompt: "Confirm cache restart?" })
      .mockResolvedValueOnce({ status: "ok", output: ["proposal submitted"] });
    const view = terminal(run);
    const input = commandInput();
    await waitForFocus(input);

    await user.type(input, "yes{Enter}");
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    expect(run).toHaveBeenLastCalledWith(expect.objectContaining({ input: "yes" }));
    await waitForFocus(input);

    await user.type(input, "cache restart{Enter}");
    await waitFor(() => expect(screen.getByText("Confirm cache restart?")).toBeTruthy());
    await waitForFocus(input);
    await user.type(input, "yes{Enter}");
    await waitFor(() => expect(run).toHaveBeenCalledTimes(3));
    expect(run).toHaveBeenLastCalledWith(expect.objectContaining({ input: "cache restart", confirmation: "yes" }));

    view.unmount();
    const cancelRun = vi.fn().mockResolvedValue({ status: "needs_confirmation", input: "cache restart", prompt: "Confirm cache restart?" });
    terminal(cancelRun);
    const cancelInput = commandInput();
    await waitForFocus(cancelInput);
    await user.type(cancelInput, "cache restart{Enter}");
    await waitFor(() => expect(screen.getByText("Confirm cache restart?")).toBeTruthy());
    await user.keyboard("{Escape}");
    expect(cancelRun).toHaveBeenCalledTimes(1);
    expect(screen.getByText("cancelled")).toBeTruthy();
    expect(screen.getByLabelText("argus$")).toBeTruthy();
  });

  it("tabs from Run through Insert, Copy, and Re-check in document order", async () => {
    const user = userEvent.setup();
    render(<>
      <ConsoleTerminal incidentId={incident.id} history={[]} run={vi.fn()} />
      <ConsolePanel incident={incident} history={history} commands={commands} onInsert={() => {}} onRecheck={() => {}} />
    </>);
    const input = commandInput();
    await waitForFocus(input);
    for (const name of ["Run", "Insert into console", "Copy", "Re-check"]) {
      await user.tab();
      expect(document.activeElement).toBe(screen.getByRole("button", { name }));
    }
  });

  it("announces pending status and log output, scrolls new lines, and keeps long output from trapping focus", async () => {
    const user = userEvent.setup();
    let finish;
    const run = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    terminal(run);
    const input = commandInput();
    await waitForFocus(input);
    await user.type(input, "worker status{Enter}");
    const status = await screen.findByRole("status");
    expect(status.textContent.toLowerCase()).toContain("running");
    expect(status.getAttribute("aria-live")).toBe("polite");
    const log = screen.getByRole("log");
    expect(log.getAttribute("aria-live")).toBe("polite");
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 800 });
    finish({ status: "ok", output: Array.from({ length: 100 }, (_, index) => `output line ${index + 1}`) });
    await screen.findByText("output line 100");
    await waitFor(() => expect(log.scrollTop).toBe(800));
    await waitForFocus(input);
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Run" }));
  });
});
