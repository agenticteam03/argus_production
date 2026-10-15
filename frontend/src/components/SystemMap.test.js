import { describe, expect, it } from "vitest";
import { layoutMap, miniNodes, stateOf } from "./SystemMap.jsx";

// The map is hand-rolled SVG (no library); these are its pure helpers, so the layout and the
// cause/affected derivation are checked here instead of through the pixels.

const TOPOLOGY = {
  hosts: [
    { id: "vm-095", label: "Host A", role: "argus" },
    { id: "vm-166", label: "Host T", role: "monitored" },
  ],
  nodes: [
    { id: "agent", host: "vm-095", label: "argus-v18-agent", kind: "argus" },
    { id: "api", host: "vm-166", label: "argus-lab-api", target: "vm-166/container:argus-lab-api" },
    { id: "worker", host: "vm-166", label: "argus-lab-worker", target: "vm-166/container:argus-lab-worker" },
    { id: "db", host: "vm-166", label: "argus-v18-db" },
  ],
  edges: [{ from: "agent", to: "api" }],
};

describe("layoutMap", () => {
  it("lays every node out inside its host box, left to right", () => {
    const { hosts, pos, width, height } = layoutMap(TOPOLOGY);
    expect(Object.keys(pos).sort()).toEqual(["agent", "api", "db", "worker"]);
    expect(hosts.map((h) => h.id)).toEqual(["vm-095", "vm-166"]);
    expect(hosts[0].x).toBeLessThan(hosts[1].x);          // hosts flow left to right
    expect(hosts.every((h) => h.width > 0 && h.height > 0)).toBe(true);
    expect(width).toBeGreaterThan(0);
    expect(height).toBeGreaterThan(0);
    // The Argus host (one column) and the monitored host (two columns) both keep their nodes inside the box.
    for (const n of TOPOLOGY.nodes) {
      const h = hosts.find((x) => x.id === n.host);
      expect(pos[n.id].x).toBeGreaterThanOrEqual(h.x);
      expect(pos[n.id].y).toBeGreaterThanOrEqual(h.y);
    }
  });

  it("survives an empty topology", () => {
    const { hosts, width, height } = layoutMap({ hosts: [], nodes: [] });
    expect(hosts).toEqual([]);
    expect(width).toBeGreaterThanOrEqual(1);
    expect(height).toBeGreaterThan(0);
  });
});

describe("stateOf", () => {
  const worker = TOPOLOGY.nodes[2];
  const agent = TOPOLOGY.nodes[0];
  it("marks the root cause red, the affected target amber, the Argus host blue and the rest normal", () => {
    const incident = { target: "vm-166/container:argus-lab-api", root_cause_target: "vm-166/container:argus-lab-worker" };
    expect(stateOf(worker, incident)).toBe("cause");
    expect(stateOf(TOPOLOGY.nodes[1], incident)).toBe("affected");
    expect(stateOf(agent, incident)).toBe("argus");
    expect(stateOf(TOPOLOGY.nodes[3], incident)).toBe("ok");
  });

  it("is normal for a node that matches nothing", () => {
    expect(stateOf(TOPOLOGY.nodes[1], { target: "vm-095/host:vm-095" })).toBe("ok");
    expect(stateOf(TOPOLOGY.nodes[1], null)).toBe("ok");
  });
});

describe("miniNodes", () => {
  it("pairs the affected target and its different root cause", () => {
    const incident = { target: "vm-166/container:argus-lab-api", root_cause_target: "vm-166/container:argus-lab-worker" };
    expect(miniNodes(TOPOLOGY, incident)).toEqual([TOPOLOGY.nodes[1], TOPOLOGY.nodes[2]]);
  });

  it("is null when the cause is the target itself or an endpoint is missing", () => {
    expect(miniNodes(TOPOLOGY, { target: "vm-166/container:argus-lab-api", root_cause_target: "vm-166/container:argus-lab-api" })).toBeNull();
    expect(miniNodes(TOPOLOGY, { target: "vm-095/container:absent" })).toBeNull();
    expect(miniNodes(null, { target: "vm-166/container:argus-lab-api" })).toBeNull();
  });
});
