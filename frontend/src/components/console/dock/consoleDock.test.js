import { describe, expect, it } from "vitest";
import { canSeeConsole, clock, consoleBuilt, dockAccess, hostIncidents, maxDockWidth, timeLeft, unlockStep } from "./consoleDock.js";

const user = (secondFactor, extra = {}) => ({ name: "juanes6554", role: "approver", access: "investigate", actions: [],
  secondFactor, ...extra });

describe("dockAccess: the four cases of the console's access dialog (two keys, a confirmed session)", () => {
  it("case 2, no key at all: ask an administrator", () => {
    expect(dockAccess(user({ enrolled: 0, verified: false }))).toBe("no-keys");
  });
  it("case 1, one key: register the second one", () => {
    expect(dockAccess(user({ enrolled: 1, verified: true }, { access: "ops" }))).toBe("one-key");
  });
  it("case 3, two keys but this session is not the private one confirmed with a key: unlock it first", () => {
    expect(dockAccess(user({ enrolled: 2, verified: false }))).toBe("unlock");
    expect(dockAccess(user({ enrolled: 2, verified: true }))).toBe("unlock");              // a public session
    expect(dockAccess(user({ enrolled: 2, verified: false }, { access: "ops" }))).toBe("unlock");
  });
  it("case 4, two keys and a private session confirmed with one: only the reason", () => {
    expect(dockAccess(user({ enrolled: 2, verified: true }, { access: "ops" }))).toBe("ready");
  });
  it("Argus without security keys configured: the console cannot open", () => {
    expect(dockAccess(user(undefined))).toBe("unconfigured");
    expect(dockAccess(null)).toBe("unconfigured");
  });
});

describe("unlockStep: case 3's next step (ACR-0032: the private login, then the key)", () => {
  it("asks for the private login first, then the key, then nothing", () => {
    expect(unlockStep(user({ enrolled: 2, verified: true }))).toBe("private-login");
    expect(unlockStep(user({ enrolled: 2, verified: false }, { access: "ops" }))).toBe("second-factor");
    expect(unlockStep(user({ enrolled: 2, verified: true }, { access: "ops" }))).toBe(null);
  });
});

describe("canSeeConsole", () => {
  it("shows the console to the highest role only (an approver); the API still decides every command", () => {
    expect(canSeeConsole({ role: "approver" })).toBe(true);
    expect(canSeeConsole({ role: "operator" })).toBe(false);
    expect(canSeeConsole({ role: "viewer" })).toBe(false);
    expect(canSeeConsole(null)).toBe(false);
  });
});

describe("consoleBuilt", () => {
  it("is on in the demo, and in a real build only with VITE_ARGUS_CONSOLE=1 (the team's console flag)", () => {
    expect(consoleBuilt("demo", {})).toBe(true);
    expect(consoleBuilt("api", {})).toBe(false);
    expect(consoleBuilt("api", { VITE_ARGUS_CONSOLE: "1" })).toBe(true);
  });
});

describe("hostIncidents", () => {
  const inc = (id, target, opened_at, status = "escalated") => ({ id, target, opened_at, status });
  it("lists a host's incidents, newest first, and never another host's or one without a host", () => {
    const list = [inc("a", "vm-166/container:argus-lab-cache", "2026-10-29T10:00:00Z"),
      inc("b", "vm-095/container:argus-lab-api", "2026-10-29T11:00:00Z"),
      inc("c", "vm-166/container:argus-lab-api", "2026-10-29T12:00:00Z"), inc("d", "lab-victim", "2026-10-29T13:00:00Z")];
    expect(hostIncidents(list, "vm-166").map((i) => i.id)).toEqual(["c", "a"]);
    expect(hostIncidents(list, "vm-095").map((i) => i.id)).toEqual(["b"]);
    expect(hostIncidents(undefined, "vm-166")).toEqual([]);
  });
});

describe("timeLeft and clock", () => {
  it("counts down to the session's limit and never below zero", () => {
    const now = Date.parse("2026-10-29T12:00:00Z");
    expect(timeLeft("2026-10-29T12:30:00Z", now)).toBe(30 * 60_000);
    expect(timeLeft("2026-10-29T11:00:00Z", now)).toBe(0);
    expect(clock(29 * 60_000 + 5000)).toBe("29:05");
    expect(clock(-5)).toBe("0:00");
  });
});

describe("maxDockWidth", () => {
  it("leaves the page 600 px on a wide screen, 10 % on a narrow one, and never goes under the panel's minimum", () => {
    expect(maxDockWidth(1440)).toBe(840);
    expect(maxDockWidth(1024)).toBe(424);
    expect(maxDockWidth(800)).toBe(720);
    expect(maxDockWidth(390)).toBe(380);
  });
});
