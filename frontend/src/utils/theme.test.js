import { describe, expect, it, vi } from "vitest";
import { applyTheme, otherTheme, readTheme, saveTheme, switchTheme } from "./theme.js";

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

// Switching must recolour everything in the same frame: CSS transitions are paused while data-theme changes (no
// component fades on its own), and where the browser can, one cross-fade of the whole page smooths the change.
describe("switchTheme", () => {
  const frames = () => {
    const queue = [];
    return { queue, frame: (cb) => queue.push(cb), flush() { while (queue.length) queue.shift()(); } };
  };

  it("pauses transitions while the theme changes, then resumes them (no View Transitions)", () => {
    const doc = { documentElement: { dataset: { theme: "dark" } } };
    const f = frames();
    switchTheme("light", { doc, frame: f.frame, reducedMotion: false });
    expect(doc.documentElement.dataset.theme).toBe("light");
    expect(doc.documentElement.dataset.themeSwitching).toBe("");
    f.flush();
    expect(doc.documentElement.dataset.themeSwitching).toBeUndefined();
  });

  it("cross-fades the whole page with a View Transition when the browser has one", async () => {
    let finish;
    const doc = {
      documentElement: { dataset: { theme: "dark" } },
      startViewTransition: vi.fn((update) => { update(); return { finished: new Promise((r) => { finish = r; }) }; }),
    };
    switchTheme("light", { doc, frame: () => {}, reducedMotion: false });
    expect(doc.startViewTransition).toHaveBeenCalledOnce();
    expect(doc.documentElement.dataset.theme).toBe("light");
    expect(doc.documentElement.dataset.themeSwitching).toBe("");
    finish();
    await Promise.resolve(); await Promise.resolve();
    expect(doc.documentElement.dataset.themeSwitching).toBeUndefined();
  });

  it("skips the cross-fade when the user asks for reduced motion", () => {
    const doc = { documentElement: { dataset: {} }, startViewTransition: vi.fn() };
    const f = frames();
    switchTheme("light", { doc, frame: f.frame, reducedMotion: true });
    expect(doc.startViewTransition).not.toHaveBeenCalled();
    expect(doc.documentElement.dataset.theme).toBe("light");
    f.flush();
    expect(doc.documentElement.dataset.themeSwitching).toBeUndefined();
  });
});
