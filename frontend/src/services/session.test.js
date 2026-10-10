import { beforeEach, describe, expect, it } from "vitest";
import { clearToken, getToken, setToken } from "./session.js";

describe("session (in-memory token)", () => {
  beforeEach(() => clearToken());

  it("starts empty", () => {
    expect(getToken()).toBeNull();
  });

  it("keeps a token in memory and forgets it on clear", () => {
    setToken("jwt-123");
    expect(getToken()).toBe("jwt-123");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("treats a missing token as null", () => {
    setToken(undefined);
    expect(getToken()).toBeNull();
  });
});
