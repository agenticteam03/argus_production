import { describe, expect, it } from "vitest";
import { countFrame, motionMs } from "./motion.js";

// A stand-in for getComputedStyle(document.documentElement): only getPropertyValue is read.
const style = (vars) => ({ getPropertyValue: (name) => vars[name] ?? "" });

describe("motionMs", () => {
  it("reads a --motion-* token in milliseconds, in ms or s", () => {
    expect(motionMs("count", style({ "--motion-count": " 700ms" }))).toBe(700);
    expect(motionMs("slow", style({ "--motion-slow": "0.32s" }))).toBe(320);
  });

  it("is 0 when the token says so (reduced motion), is missing or makes no sense", () => {
    expect(motionMs("count", style({ "--motion-count": "0ms" }))).toBe(0);
    expect(motionMs("count", style({}))).toBe(0);
    expect(motionMs("count", style({ "--motion-count": "fast" }))).toBe(0);
  });

  it("is 0 without a browser (a server render or a test), so nothing waits for an animation", () => {
    expect(motionMs("count")).toBe(0);
  });
});

describe("countFrame", () => {
  it("starts at the first value and ends exactly on the last", () => {
    expect(countFrame(0, 42, 0)).toBe(0);
    expect(countFrame(0, 42, 1)).toBe(42);
    expect(countFrame(10, 3, 1)).toBe(3);
  });

  it("shows whole numbers that only move towards the target, fast first and slow at the end", () => {
    const frames = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1].map((p) => countFrame(0, 100, p));
    for (const f of frames) expect(Number.isInteger(f)).toBe(true);
    for (let i = 1; i < frames.length; i += 1) expect(frames[i]).toBeGreaterThanOrEqual(frames[i - 1]);
    expect(frames[3]).toBeGreaterThan(50);      // eased out: past half way at half the time
  });

  it("clamps a progress outside 0..1", () => {
    expect(countFrame(0, 8, -1)).toBe(0);
    expect(countFrame(0, 8, 2)).toBe(8);
  });
});
