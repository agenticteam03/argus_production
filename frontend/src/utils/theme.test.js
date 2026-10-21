import { describe, expect, it } from "vitest";
import { applyTheme, otherTheme, readTheme, saveTheme } from "./theme.js";

const memory = (initial = {}) => ({ data: { ...initial }, getItem(k) { return this.data[k] ?? null; }, setItem(k, v) { this.data[k] = v; } });
const blocked = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };

describe("theme", () => {
  it("opens dark when nothing (or something invalid) is saved", () => {
    expect(readTheme(memory())).toBe("dark");
    expect(readTheme(memory({ "argus-theme": "purple" }))).toBe("dark");
  });
  it("remembers the choice", () => {
    const s = memory();
    saveTheme("light", s);
    expect(readTheme(s)).toBe("light");
  });
  it("survives blocked storage", () => {
    expect(readTheme(blocked)).toBe("dark");
    expect(() => saveTheme("light", blocked)).not.toThrow();
  });
  it("sets data-theme on the root and falls back to dark", () => {
    const root = { dataset: {} };
    applyTheme("light", root);
    expect(root.dataset.theme).toBe("light");
    applyTheme("nonsense", root);
    expect(root.dataset.theme).toBe("dark");
  });
  it("toggles", () => {
    expect(otherTheme("dark")).toBe("light");
    expect(otherTheme("light")).toBe("dark");
  });
});
