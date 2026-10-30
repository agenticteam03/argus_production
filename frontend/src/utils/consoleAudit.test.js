import { describe, expect, it } from "vitest";
import { consoleAuditLine } from "./consoleAudit.js";

const row = (event, detail) => ({ event, detail, actor: "juanes6554", at: "2026-10-29T20:56:12Z" });

describe("consoleAuditLine: the operator console's record, readable in the incident's Audit tab", () => {
  it("says who opened the console and why, and how it ended", () => {
    expect(consoleAuditLine(row("console.session_opened", { session: "csn_1", reason: "Check the cache" })))
      .toBe("Opened the console · reason: Check the cache");
    expect(consoleAuditLine(row("console.session_closed", { session: "csn_1", why: "disconnect" }))).toBe("Closed the console: disconnected");
    expect(consoleAuditLine(row("console.session_closed", { why: "time_limit" }))).toBe("Closed the console: its 30-minute limit");
    expect(consoleAuditLine(row("console.session_closed", { why: "signed_out" }))).toBe("Closed the console: signed out");
  });

  it("names each command, its result, and every refusal", () => {
    expect(consoleAuditLine(row("console.command", { command: "cache.status", cls: "read", status: "ok" })))
      .toBe("Ran cache.status (read) · ok");
    expect(consoleAuditLine(row("console.refused", { reason: "unknown command 'ls'" }))).toBe("Refused input · unknown command 'ls'");
    expect(consoleAuditLine(row("console.quota_refused", { command: "api.cpu", quota: "minute" }))).toBe("Read limit reached (minute) · api.cpu");
    expect(consoleAuditLine(row("console.budget_refused", { command: "api.cpu" }))).toBe("This incident's read budget is used · api.cpu");
    expect(consoleAuditLine(row("security.console_refused", { reason: "the console is for a person's own session" })))
      .toBe("Console refused · the console is for a person's own session");
  });

  it("leaves any other row as it is", () => {
    expect(consoleAuditLine(row("tool.invoked", { capability: "container.status" }))).toBeNull();
    expect(consoleAuditLine(row("console.session_opened", null))).toBe("Opened the console");
  });
});
