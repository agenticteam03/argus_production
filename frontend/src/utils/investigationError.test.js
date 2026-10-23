import { describe, expect, it } from "vitest";
import { investigationError } from "./investigationError.js";

// What the dashboard form and the map drawer say when POST /api/v1/investigations is refused.
describe("investigationError", () => {
  it("says when to try again after a quota refusal", () => {
    expect(investigationError({ status: 429, retryAfter: 90 })).toBe("Too many investigations right now: try again in about 2 min.");
    expect(investigationError({ status: 429 })).toBe("Too many investigations right now.");
  });
  it("says the account may not start one", () => {
    expect(investigationError({ status: 403 })).toBe("Your account may not start investigations.");
  });
  it("shows the API's short reason when it gives one (http.js err.detail), else a generic line", () => {
    expect(investigationError({ status: 422, detail: "target not in the inventory" })).toBe("Could not start the investigation: target not in the inventory.");
    expect(investigationError({ status: 500 })).toBe("Could not start the investigation. Please try again.");
    expect(investigationError(null)).toBe("Could not start the investigation. Please try again.");
  });
});
