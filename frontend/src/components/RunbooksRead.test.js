import { describe, expect, it } from "vitest";
import { resolveRunbook } from "./RunbooksRead.jsx";

// A recalled passage can reference a runbook by id, file name or title; the row must still find it.

const ITEMS = [
  { id: "RB-001", file: "RB-001-container-restart-loop.md", title: "Container restart loop" },
  { id: "RB-005", file: "RB-005-disk-pressure.md", title: "Disk pressure" },
];

describe("resolveRunbook", () => {
  it("matches by id, case-insensitively", () => {
    expect(resolveRunbook("RB-001", ITEMS)).toBe(ITEMS[0]);
    expect(resolveRunbook("rb-005", ITEMS)).toBe(ITEMS[1]);
  });

  it("matches by file name, with or without the folder or the .md suffix", () => {
    expect(resolveRunbook("RB-001-container-restart-loop.md", ITEMS)).toBe(ITEMS[0]);
    expect(resolveRunbook("runbooks/RB-001-container-restart-loop.md", ITEMS)).toBe(ITEMS[0]);
    expect(resolveRunbook("RB-005-disk-pressure", ITEMS)).toBe(ITEMS[1]);
  });

  it("matches by title", () => {
    expect(resolveRunbook("Disk pressure", ITEMS)).toBe(ITEMS[1]);
  });

  it("matches a section suffix that starts with the runbook id", () => {
    expect(resolveRunbook("RB-001_required-evidence", ITEMS)).toBe(ITEMS[0]);
  });

  it("is null when nothing matches", () => {
    expect(resolveRunbook("RB-999", ITEMS)).toBeNull();
    expect(resolveRunbook("", ITEMS)).toBeNull();
  });
});
