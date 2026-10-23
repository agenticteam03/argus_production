import { describe, expect, it } from "vitest";
import { MIN_SPIN_MS, runRefresh } from "./refresh.js";

// A fake clock: `wait` only advances time, so the tests are instant and exact.
const clock = () => {
  let t = 0;
  return { now: () => t, advance: (ms) => { t += ms; }, wait: async (ms) => { t += ms; } };
};

describe("runRefresh", () => {
  it("reports success when the refresh resolves (true or nothing)", async () => {
    const c = clock();
    expect(await runRefresh(async () => true, c)).toBe(true);
    expect(await runRefresh(async () => undefined, c)).toBe(true);
  });

  it("reports failure when the refresh answers false or throws", async () => {
    const c = clock();
    expect(await runRefresh(async () => false, c)).toBe(false);
    expect(await runRefresh(async () => { throw new Error("down"); }, c)).toBe(false);
  });

  it("keeps the spinner for at least MIN_SPIN_MS, so a fast answer is still visible", async () => {
    const c = clock();
    await runRefresh(async () => { c.advance(50); }, c);
    expect(c.now()).toBe(MIN_SPIN_MS);
  });

  it("adds no wait when the refresh was already slower than the minimum", async () => {
    const c = clock();
    await runRefresh(async () => { c.advance(MIN_SPIN_MS + 300); }, c);
    expect(c.now()).toBe(MIN_SPIN_MS + 300);
  });
});
