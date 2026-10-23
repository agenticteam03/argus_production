import { describe, expect, it } from "vitest";
import { hostsOf, matchesHost, targetsOfHost, withoutHost } from "./incidentFilter.js";

const ROWS = [
  { target: "vm-166/container:api" }, { target: "vm-095/container:worker" }, { target: "vm-166/host:vm-166" }, { target: "vm-166/container:api" },
];

describe("incident host / target filter", () => {
  it("lists the hosts that appear, sorted, once each", () => {
    expect(hostsOf(ROWS)).toEqual(["vm-095", "vm-166"]);
    expect(hostsOf(null)).toEqual([]);
  });
  it("offers targets only inside the chosen host", () => {
    expect(targetsOfHost(ROWS, "vm-166")).toEqual(["vm-166/container:api", "vm-166/host:vm-166"]);
    expect(targetsOfHost(ROWS, "")).toEqual([]);
  });
  it("matches by host, then by target", () => {
    expect(matchesHost(ROWS[0], "", "")).toBe(true);
    expect(matchesHost(ROWS[0], "vm-166", "")).toBe(true);
    expect(matchesHost(ROWS[1], "vm-166", "")).toBe(false);
    expect(matchesHost(ROWS[2], "vm-166", "vm-166/container:api")).toBe(false);
  });
  it("shows a target without its host", () => {
    expect(withoutHost("vm-166/container:api", "vm-166")).toBe("container:api");
    expect(withoutHost("vm-166/container:api", "")).toBe("vm-166/container:api");
  });
});
