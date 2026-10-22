import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import SystemMap, { MapTab, MiniMapCard, SystemMapCard } from "./SystemMap.jsx";

const API = "vm-166/container:argus-lab-api";
const CACHE = "vm-166/container:argus-lab-cache";
const TOPO = {
  hosts: [{ id: "h95", label: "vm-095", role: "argus" }, { id: "h166", label: "vm-166", role: "monitored" }],
  nodes: [
    { id: "argus", host: "h95", label: "Argus", kind: "argus" },
    { id: "api", host: "h166", label: "api", sub: "container", target: API, status: "running", info: [{ label: "Image", value: "lab-api:1" }] },
    { id: "cache", host: "h166", label: "cache", target: CACHE },
    { id: "db", host: "h166", label: "db", status: "unknown" },
  ],
  edges: [
    { from: "api", to: "cache", state: "broken", label: "name not resolved" },
    { from: "api", to: "db", state: "unknown" },
    { from: "argus", to: "api", state: "read" },
    { from: "api", to: "ghost" },                                      // an endpoint not on the map: not drawn
  ],
};
const INC = { id: "inc_1", target: API, root_cause_target: CACHE };
const html = (el) => renderToStaticMarkup(<MemoryRouter>{el}</MemoryRouter>);

describe("SystemMap (full)", () => {
  it("names the map and each box with its state for screen readers", () => {
    const out = html(<SystemMap topology={TOPO} incident={INC} />);
    expect(out).toContain('aria-label="System map: 2 hosts, 4 components"');
    expect(out).toContain('aria-label="cache, root cause"');
    expect(out).toContain('aria-label="api, container, affected"');
    expect(out).toContain('aria-label="db, unknown"');
    expect(out).toContain('aria-label="Argus, argus"');
  });

  it("draws an unknown box dashed, and edges only between boxes on the map", () => {
    const out = html(<SystemMap topology={TOPO} incident={INC} />);
    expect(out.match(/stroke-dasharray="3 3"/g)).toHaveLength(1);                  // the unknown db box
    expect(out.match(/<path /g)).toHaveLength(3);                                   // not the edge to "ghost"
    expect(out).toContain('stroke-dasharray="5 4"');                                // broken
    expect(out).toContain("name not resolved");
  });

  it("is a set of buttons only when a box can be selected, and marks the selected one", () => {
    expect(html(<SystemMap topology={TOPO} incident={INC} />)).not.toContain('role="button"');
    const out = html(<SystemMap topology={TOPO} incident={INC} selectedId="cache" onSelect={() => {}} />);
    expect(out.match(/role="button"/g)).toHaveLength(4);
    expect(out.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(out).toMatch(/aria-label="cache, root cause"[^>]*aria-pressed="true"/);
  });
});

describe("SystemMap (mini) and its card", () => {
  it("shows only the affected target and its root cause, with the link between them", () => {
    const out = html(<SystemMap variant="mini" topology={TOPO} incident={INC} />);
    expect(out).toContain('aria-label="argus-lab-api and argus-lab-cache: name not resolved"');
    expect(out.match(/<rect /g)).toHaveLength(2);
  });

  it("hides itself when there is no separate root cause", () => {
    const self = { id: "inc_2", target: API, root_cause_target: API };
    expect(html(<SystemMap variant="mini" topology={TOPO} incident={self} />)).toBe("");
    expect(html(<MiniMapCard topology={TOPO} incident={self} onOpen={() => {}} />)).toBe("");
    expect(html(<MiniMapCard topology={TOPO} incident={INC} onOpen={() => {}} />)).toContain("Where it broke");
  });
});

describe("MapTab and SystemMapCard", () => {
  it("opens on the root cause and links the incident from its details", () => {
    const out = html(<MapTab topology={TOPO} incident={INC} />);
    expect(out).toMatch(/aria-label="cache, root cause"[^>]*aria-pressed="true"/);
    expect(out).toContain("No further details for this component.");
    expect(out).toContain('href="/incidents/inc_1"');
  });

  it("shows a component's status and facts when it has them", () => {
    const out = html(<MapTab topology={TOPO} incident={{ id: "inc_3", target: API }} />);   // no root cause: the affected
    expect(out).toContain("Status");
    expect(out).toContain("lab-api:1");
  });

  it("hides the dashboard card when the topology has no components", () => {
    expect(html(<SystemMapCard topology={{ hosts: [], nodes: [] }} />)).toBe("");
    expect(html(<SystemMapCard topology={null} />)).toBe("");
    expect(html(<SystemMapCard topology={TOPO} />)).toContain("dependency ok");
  });
});
