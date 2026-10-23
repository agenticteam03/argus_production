import { describe, expect, it } from "vitest";
import { causePathOf, CONNECTIONS, connectionOf, edgeDetail, fmtSignal, mapNodes, roleOf } from "./mapModel.js";

const NOW = Date.parse("2026-10-22T03:00:00Z");
// Shapes from the live GET /api/v1/topology, trimmed.
const topology = {
  hosts: [{ id: "vm-095", role: "argus" }, { id: "vm-166", role: "monitored" }],
  nodes: [
    { id: "api", host: "vm-166", label: "argus-lab-api", target: "vm-166/container:argus-lab-api", kind: "container", status: "running", health: "healthy", problems: [] },
    { id: "cache", host: "vm-166", label: "argus-lab-cache", target: "vm-166/container:argus-lab-cache", kind: "container", status: "exited", health: "failed", problems: [{ kind: "health", severity: "critical", summary: "exited" }] },
    { id: "nginx", host: "vm-166", label: "argus-lab-nginx", target: "vm-166/container:argus-lab-nginx", kind: "container", status: "unknown", health: "idle", idle: true },
    { id: "db", host: "vm-166", label: "argus-lab-db", target: "vm-166/container:argus-lab-db", kind: "container", sub: "database container", status: "running", health: "healthy" },
  ],
  edges: [
    { id: "e1", kind: "dependency", from: "api", to: "cache", state: "broken", label: "tcp 6379", reason: "connection refused" },
    { id: "e2", kind: "dependency", from: "api", to: "db", state: "ok", label: "tcp 5432", latency_ms: 0.5 },
    { id: "e3", kind: "dependency", from: "nginx", to: "api", state: "unknown", label: "tcp 8080" },
    { id: "e4", kind: "argus_reads", from: "vm-095", to: "vm-166", state: "read", label: "Argus reads" },
  ],
};

describe("connections", () => {
  it("styles every edge state the contract allows, and never shows unknown as OK", () => {
    expect(topology.edges.map(connectionOf)).toEqual(["broken", "ok", "not_checked", "argus_reads"]);
    expect(connectionOf({ state: "slow" })).toBe("slow");
    expect(connectionOf({ state: "something-new" })).toBe("not_checked");
    for (const k of ["ok", "slow", "broken", "not_checked", "argus_reads"]) expect(CONNECTIONS[k].label).toBeTruthy();
  });
  it("says why a link is in its state", () => {
    expect(edgeDetail(topology.edges[0])).toBe("connection refused");
    expect(edgeDetail(topology.edges[1])).toBe("OK · 0.5 ms");
    expect(edgeDetail(topology.edges[2])).toBe("Not checked");
  });
});

describe("roles and cause path", () => {
  const incident = { id: "inc_1", target: "vm-166/container:argus-lab-api", root_cause_target: "vm-166/container:argus-lab-cache" };
  it("uses the overlay's role, else derives it from the incident", () => {
    expect(roleOf({ ...topology.nodes[0], role: "on_path" }, incident)).toBe("on_path");
    expect(roleOf(topology.nodes[0], incident)).toBe("affected");
    expect(roleOf(topology.nodes[1], incident)).toBe("root_cause");
    expect(roleOf(topology.nodes[3], incident)).toBeNull();
    expect(roleOf(topology.nodes[0], null)).toBeNull();
  });
  it("uses the overlay's cause path, else the target and the root cause", () => {
    expect(causePathOf({ ...topology, cause_path: ["api", "cache"] }, incident)).toEqual(["api", "cache"]);
    expect(causePathOf(topology, incident)).toEqual(["api", "cache"]);
    expect(causePathOf(topology, null)).toEqual([]);
  });
});

describe("mapNodes", () => {
  it("gives every box its health, glyph, icon and role", () => {
    const incidents = [{ target: "vm-166/container:argus-lab-nginx", status: "escalated", opened_at: "2026-10-22T02:29:02Z" }];
    const nodes = mapNodes(topology, { incidents, now: NOW });
    expect(nodes.map((n) => [n.label, n.health, n.glyph, n.icon])).toEqual([
      ["argus-lab-api", "ok", "ok", "box"],
      ["argus-lab-cache", "failed", "failed", "box"],
      ["argus-lab-nginx", "degraded", "degraded", "box"],    // idle, but its escalated incident needs a look
      ["argus-lab-db", "ok", "ok", "database"],
    ]);
  });
  it("keeps an idle container that needs attention out of the hidden idle group", () => {
    const incidents = [{ target: "vm-166/container:argus-lab-nginx", status: "escalated", opened_at: "2026-10-22T02:29:02Z" }];
    expect(mapNodes(topology, { now: NOW }).find((n) => n.id === "nginx").idle).toBe(true);
    expect(mapNodes(topology, { incidents, now: NOW }).find((n) => n.id === "nginx").idle).toBe(false);
  });
  it("draws the root cause as failing and a healthy affected box as degraded", () => {
    const incident = { target: "vm-166/container:argus-lab-api", root_cause_target: "vm-166/container:argus-lab-db" };
    const nodes = mapNodes(topology, { incident, now: NOW });
    expect(nodes.find((n) => n.id === "api")).toMatchObject({ role: "affected", health: "ok", glyph: "degraded" });
    expect(nodes.find((n) => n.id === "db")).toMatchObject({ role: "root_cause", health: "ok", glyph: "failed" });
  });
});

describe("fmtSignal", () => {
  it("shows ratios as percentages and bytes as MiB", () => {
    expect(fmtSignal(0.03754, "ratio")).toBe("3.8 %");
    expect(fmtSignal(11124736, "bytes")).toBe("10.6 MiB");
    expect(fmtSignal(5, "")).toBe("5");
    expect(fmtSignal(null, "ratio")).toBe("—");
  });
});
