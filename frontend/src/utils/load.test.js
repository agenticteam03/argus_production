import { describe, expect, it } from "vitest";
import { loadLevel, worstLevel } from "./load.js";

describe("loadLevel", () => {
  it("is normal below 75 %, high from 75 %, critical from 90 %", () => {
    expect(loadLevel(0.034)).toBe("ok");
    expect(loadLevel(0.7499)).toBe("ok");
    expect(loadLevel(0.75)).toBe("high");
    expect(loadLevel(0.8999)).toBe("high");
    expect(loadLevel(0.9)).toBe("critical");
    expect(loadLevel(1.2)).toBe("critical");
  });
  it("has no level without a reading", () => {
    expect(loadLevel(null)).toBeNull();
    expect(loadLevel(undefined)).toBeNull();
    expect(loadLevel(Number.NaN)).toBeNull();
  });
});

describe("worstLevel", () => {
  it("takes the worst metric of the host", () => {
    expect(worstLevel(["ok", "high", "ok"])).toBe("high");
    expect(worstLevel(["ok", "critical", "high"])).toBe("critical");
    expect(worstLevel(["ok", null, "ok"])).toBe("ok");
    expect(worstLevel([null, null])).toBeNull();
  });
});
