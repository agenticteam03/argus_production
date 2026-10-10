import { describe, expect, it } from "vitest";
import { parseRunbook } from "../utils/parseRunbook.js";
import { fileRunbooksAdapter } from "./fileRunbooksAdapter.js";

// PR #24 review item 9: read the real library instead of the two demo copies.
describe("fileRunbooksAdapter", () => {
  it("reads the whole real library (21 runbooks) and every card parses", async () => {
    const list = await fileRunbooksAdapter.listRunbooks();
    expect(list).toHaveLength(21);

    const parsed = list.map(parseRunbook);
    for (const rb of parsed) {
      expect(rb.id).toMatch(/^RB-\d+$/);
      expect(rb.status).toBeTruthy();
      expect(rb.detector).toBeTruthy();
    }
    // No duplicate ids: the drawer is looked up by id.
    expect(new Set(parsed.map((r) => r.id)).size).toBe(parsed.length);
  });
});
