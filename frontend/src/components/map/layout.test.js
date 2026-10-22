import ELK from "elkjs/lib/elk.bundled.js";
import { describe, expect, it } from "vitest";
import { layoutMap } from "./layout.js";

const elk = new ELK();
const node = (host, name, extra = {}) => ({ id: `${host}/container:${name}`, host, label: name, target: `${host}/container:${name}`, kind: "container", status: "running", health: "healthy", ...extra });
// The lab as GET /api/v1/topology shows it: two hosts, some idle scenario containers, one cross-section link.
const topology = {
  hosts: [{ id: "vm-095", role: "argus" }, { id: "vm-166", role: "monitored" }],
  nodes: [
    node("vm-095", "argus-lab-api"), node("vm-095", "argus-lab-worker", { health: "unknown" }),
    { id: "vm-095/host:vm-095", host: "vm-095", label: "vm-095", kind: "host", status: "running", health: "healthy" },
    node("vm-166", "argus-lab-api"), node("vm-166", "argus-lab-cache"), node("vm-166", "argus-lab-db"),
    node("vm-166", "argus-lab-nginx", { health: "idle", idle: true }), node("vm-166", "argus-lab-slow", { health: "idle", idle: true }),
    { id: "vm-166/host:vm-166", host: "vm-166", label: "vm-166", kind: "host", status: "running", health: "healthy" },
  ],
  edges: [
    { id: "a", kind: "dependency", from: "vm-166/container:argus-lab-api", to: "vm-166/container:argus-lab-cache", state: "broken", label: "tcp 6379", reason: "connection refused" },
    { id: "b", kind: "dependency", from: "vm-166/container:argus-lab-api", to: "vm-166/container:argus-lab-db", state: "ok", label: "tcp 5432" },
    { id: "c", kind: "dependency", from: "vm-166/container:argus-lab-nginx", to: "vm-166/container:argus-lab-slow", state: "unknown", label: "tcp 8080" },
    { id: "d", kind: "dependency", from: "vm-166/container:argus-lab-nginx", to: "vm-166/container:argus-lab-api", state: "unknown", label: "tcp 8080" },
    { id: "r", kind: "argus_reads", from: "vm-095/host:vm-095", to: "vm-166/host:vm-166", state: "read", label: "Argus reads" },
  ],
};
const overlap = (a, b, pad = 0) => a.x < b.x + b.width + pad && a.x + a.width + pad > b.x && a.y < b.y + b.height + pad && a.y + a.height + pad > b.y;
const pairs = (list) => list.flatMap((a, i) => list.slice(i + 1).map((b) => [a, b]));

describe("layoutMap", () => {
  it("puts the hosts side by side and every box inside its host", async () => {
    const m = await layoutMap(topology, { showIdle: true }, elk);
    const [a, b] = m.groups;
    expect(a.id).toBe("vm-095");
    expect(b.x).toBeGreaterThanOrEqual(a.x + a.width);
    for (const n of m.nodes) {
      const g = m.groups.find((x) => x.id === n.host);
      expect(n.x).toBeGreaterThanOrEqual(g.x);
      expect(n.x + n.width).toBeLessThanOrEqual(g.x + g.width);
      expect(n.y + n.height).toBeLessThanOrEqual(g.y + g.height);
    }
  });

  it("hides the idle containers unless asked, and groups them apart when shown", async () => {
    const hidden = await layoutMap(topology, { showIdle: false }, elk);
    expect(hidden.nodes.map((n) => n.label)).not.toContain("argus-lab-nginx");
    expect(hidden.hiddenIdle).toEqual({ "vm-166": 2 });
    const shown = await layoutMap(topology, { showIdle: true }, elk);
    const idle = shown.idleGroups.find((g) => g.host === "vm-166");
    for (const n of shown.nodes.filter((x) => x.idle)) expect(overlap(n, idle)).toBe(true);
    for (const n of shown.nodes.filter((x) => !x.idle)) expect(overlap(n, idle)).toBe(false);
  });

  it("draws the Argus reads link only when asked", async () => {
    expect((await layoutMap(topology, { showReads: false }, elk)).edges.map((e) => e.id)).not.toContain("r");
    expect((await layoutMap(topology, { showReads: true }, elk)).edges.map((e) => e.id)).toContain("r");
  });

  it("overlaps no box with another box or label, and no label with another label", async () => {
    const m = await layoutMap(topology, { showIdle: true, showReads: true }, elk);
    const labels = m.edges.flatMap((e) => e.labels);
    for (const [a, b] of pairs(m.nodes)) expect(overlap(a, b)).toBe(false);
    for (const [a, b] of pairs(labels)) expect(overlap(a, b)).toBe(false);
    for (const l of labels) for (const n of m.nodes) expect(overlap(l, n)).toBe(false);
  });

  it("is the same for the same input", async () => {
    const one = await layoutMap(topology, { showIdle: true }, elk);
    const two = await layoutMap(topology, { showIdle: true }, elk);
    expect(two).toEqual(one);
  });
});
