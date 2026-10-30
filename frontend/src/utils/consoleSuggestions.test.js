import { describe, expect, it } from "vitest";
import { appliedIds, isRegistryCommand, suggestionIdFor, suggestionsFrom } from "./consoleSession.js";

// CON-5 (ACR-0043): Argus's suggestions come with its analysis of a command (CON-4, #406: `analysis.suggestion` =
// {command, command_id}); the UI shows only registry commands, never runs one, and tags an unedited run.
const commands = [
  { id: "cache.status", usage: "cache status" }, { id: "cache.restart", usage: "cache restart" },
  { id: "map", usage: "map <service>" }, { id: "api.cpu", usage: "api cpu [--since HH:MM]" },
];
const entry = (command_id, input, suggestion, extra = {}) =>
  ({ command_id, input, status: "ok", analysis: suggestion ? { status: "done", suggestion } : undefined, ...extra });

describe("isRegistryCommand", () => {
  it("accepts only commands of the catalog, with their argument shapes", () => {
    for (const ok of ["cache restart", "map api", "api cpu", "api cpu --since 10:30"]) expect(isRegistryCommand(ok, commands)).toBe(true);
    for (const bad of ["ls", "cache", "cache restart now", "map", "status; rm", "rm -rf /", ""]) expect(isRegistryCommand(bad, commands)).toBe(false);
  });
});

describe("suggestionsFrom", () => {
  it("takes each analysis' suggestion, newest first, one card per command, ids from the command they follow", () => {
    const history = [
      entry("cmd_1", "cache status", { command: "cache restart", command_id: "cache.restart" }),
      entry("cmd_2", "api cpu", { command: "map api", command_id: "map" }),
      entry("cmd_3", "map api", { command: "cache restart", command_id: "cache.restart", rationale: "the link is broken" }),
    ];
    expect(suggestionsFrom(history, commands)).toEqual([
      { id: "sug-cmd_3", command: "cache restart", rationale: "the link is broken", after: "map api" },
      { id: "sug-cmd_2", command: "map api", rationale: null, after: "api cpu" },
    ]);
  });

  it("drops a suggestion outside the registry and entries without one", () => {
    const history = [entry("cmd_1", "status", { command: "rm -rf /" }), entry("cmd_2", "help", null),
      entry("cmd_3", "x", { command: "  " })];
    expect(suggestionsFrom(history, commands)).toEqual([]);
    expect(suggestionsFrom(undefined, commands)).toEqual([]);
  });

  it("keeps an id the API sends", () => {
    expect(suggestionsFrom([entry("cmd_1", "status", { id: "sug-07", command: "cache status" })], commands)[0].id).toBe("sug-07");
  });
});

describe("applied and tagging", () => {
  it("a suggestion is applied once a stored command carries its id", () => {
    expect(appliedIds([entry("cmd_1", "cache restart", null, { suggestion_id: "sug-cmd_0" }), entry("cmd_2", "x", null)]))
      .toEqual(new Set(["sug-cmd_0"]));
  });

  it("tags a run only when the input is the inserted command, unedited", () => {
    const inserted = { id: "sug-cmd_3", command: "cache restart" };
    expect(suggestionIdFor("cache restart", inserted)).toBe("sug-cmd_3");
    expect(suggestionIdFor("  cache restart ", inserted)).toBe("sug-cmd_3");
    expect(suggestionIdFor("cache restart now", inserted)).toBeUndefined();
    expect(suggestionIdFor("cache restart", null)).toBeUndefined();
  });
});
