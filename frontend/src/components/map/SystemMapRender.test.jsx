import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import MiniMap from "./MiniMap.jsx";
import NodeDrawer from "./NodeDrawer.jsx";
import SystemMap from "./SystemMap.jsx";

// The map's markup before ELK lays it out (layout.test.js checks the geometry), the mini map and the node drawer.
// Shapes from GET /api/v1/topology (ACR-0017, ACR-0021).
const API = "vm-166/container:argus-lab-api";
const CACHE = "vm-166/container:argus-lab-cache";
const TOPO = {
  hosts: [{ id: "vm-095", role: "argus" }, { id: "vm-166", role: "monitored" }],
  nodes: [
    { id: "api", host: "vm-166", label: "argus-lab-api", target: API, kind: "container", status: "running", health: "healthy", info: [{ label: "Image", value: "lab-api:1" }] },
    { id: "cache", host: "vm-166", label: "argus-lab-cache", target: CACHE, kind: "container", status: "exited", health: "failed",
      problems: [{ kind: "health", severity: "critical", summary: "container exited", value: 1, threshold: 0, unit: "" }] },
    { id: "db", host: "vm-166", label: "argus-lab-db", target: "vm-166/container:argus-lab-db", kind: "container", status: "unknown", health: "unknown" },
  ],
  edges: [{ id: "e", kind: "dependency", from: "api", to: "cache", state: "broken", label: "tcp 6379", reason: "name not resolved" }],
};
const INC = { id: "inc_1", target: API, root_cause_target: CACHE };
const html = (el) => renderToStaticMarkup(<MemoryRouter>{el}</MemoryRouter>);

describe("SystemMap", () => {
  it("names the map, counts its components and lays it out before drawing", () => {
    const out = html(<SystemMap topology={TOPO} />);
    expect(out).toContain("System map");
    expect(out).toContain("2 hosts · 3 components");
    expect(out).toContain('aria-label="System map. Tab through the boxes, Enter opens one."');
    expect(out).toContain("Laying out dependencies…");
    expect(out).toContain("Argus reads");
    expect(out).not.toContain("Focus cause path");
  });

  it("offers Focus cause path on an incident, on by default", () => {
    const out = html(<SystemMap topology={TOPO} incident={INC} />);
    expect(out).toMatch(/checked=""[^>]*\/>Focus cause path/);
    expect(out).toContain("Cause path highlighted");
  });
});

describe("MiniMap", () => {
  it("shows the root cause, the link and the affected box", () => {
    const out = html(<MiniMap topology={TOPO} incident={INC} onOpen={() => {}} />);
    expect(out).toContain("Where it broke");
    expect(out.indexOf("argus-lab-cache")).toBeLessThan(out.indexOf("argus-lab-api"));
    expect(out).toContain("Root cause");
    expect(out).toContain("Affected");
    expect(out).toContain("name not resolved");
  });

  it("shows the affected box alone without another cause, and nothing when it is not on the map", () => {
    const alone = html(<MiniMap topology={TOPO} incident={{ id: "inc_2", target: API }} onOpen={() => {}} />);
    expect(alone).toContain("argus-lab-api");
    expect(alone).not.toContain("Root cause");
    expect(html(<MiniMap topology={TOPO} incident={{ id: "inc_3", target: "vm-1/container:ghost" }} onOpen={() => {}} />)).toBe("");
  });
});

describe("NodeDrawer", () => {
  const node = { ...TOPO.nodes[1], health: "failed", glyph: "failed", role: "root_cause", icon: "box" };
  it("shows the box's state, facts and problems against their threshold, as a labelled dialog", () => {
    const out = html(<NodeDrawer node={node} incident={INC} onClose={() => {}} />);
    expect(out).toContain('role="dialog"');
    expect(out).toContain('aria-label="argus-lab-cache, Failed"');
    expect(out).toContain("Container state");
    expect(out).toContain("exited");
    expect(out).toContain("Health check · container exited");
    expect(out).toContain('role="meter"');
    expect(out).toContain('href="/incidents/inc_1"');
  });

  it("offers Investigate this only to an account that may start one", () => {
    expect(html(<NodeDrawer node={node} onClose={() => {}} />)).not.toContain("Investigate this");
  });

  it("says an idle container is expected and reads no signals for it", () => {
    const idle = { ...TOPO.nodes[2], health: "idle", glyph: "idle", idle: true, icon: "box" };
    const out = html(<NodeDrawer node={idle} onClose={() => {}} />);
    expect(out).toContain("Idle (expected)");
    expect(out).toContain("No recent reads");
  });
});
