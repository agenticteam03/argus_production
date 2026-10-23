// System map layout, ported from the ui-graphs prototype (renderMap): one section per host, side by side; inside a
// host, ELK's layered layout (left to right, orthogonal edges) for the active boxes and, when shown, a second ELK
// section for the idle scenario containers. Links ELK does not lay out (between hosts, between the active and idle
// sections, and "Argus reads") go through router.js. `elk` is passed in (an ELK instance from elkjs), so the tests use
// the real engine and the page loads elkjs only when a map is drawn.
import { connectionOf } from "./mapModel.js";
import { placeEdgeLabel, routeBetween } from "./router.js";

export const NODE_W = 232;
const NODE_H = 104;
// A box with two problem badges wraps them onto two lines, so ELK gets its real height.
export const nodeHeight = (n) => ((n.problems ?? []).length > 1 ? 128 : NODE_H);
const labelSize = (e) => (e.reason ? { width: 168, height: 42 } : { width: 104, height: 40 });

const OPTIONS = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.edgeRouting": "ORTHOGONAL",
  "elk.spacing.nodeNode": "38",
  "elk.layered.spacing.nodeNodeBetweenLayers": "90",
  "elk.spacing.componentComponent": "38",
  "elk.padding": "[top=12,left=12,bottom=12,right=12]",
  "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
};
const toElkEdge = (e) => ({
  id: e.id, sources: [e.from], targets: [e.to],
  labels: [{ id: `${e.id}-label`, text: `${e.label ?? ""}${e.reason ? ` · ${e.reason}` : ""}`, ...labelSize(e) }],
  layoutOptions: { "elk.edgeLabels.placement": "CENTER", "elk.edgeLabels.inline": "false" },
});
const edgeId = (e) => e.id ?? `${e.from}->${e.to}`;

// Returns { nodes, edges, groups, idleGroups, hiddenIdle, width, height } in pixels. `nodes` keep their topology
// fields plus x/y/width/height; `edges` keep theirs plus `points` (an orthogonal route) and `labels` (rectangles).
export async function layoutMap(topology, { showIdle = false, showReads = false } = {}, elk) {
  const allEdges = (topology.edges ?? []).map((e) => ({ ...e, id: edgeId(e) }));
  const nodes = [], edges = [], groups = [], idleGroups = [], hiddenIdle = {};
  let left = 20, maxHeight = 0;

  for (const host of topology.hosts ?? []) {
    const hostNodes = (topology.nodes ?? []).filter((n) => n.host === host.id);
    const active = hostNodes.filter((n) => !n.idle), idle = hostNodes.filter((n) => n.idle);
    if (!showIdle && idle.length) hiddenIdle[host.id] = idle.length;
    let y = 64, hostWidth = 0;
    for (const [kind, section] of [["active", active], ["idle", showIdle ? idle : []]]) {
      if (!section.length) continue;
      const ids = new Set(section.map((n) => n.id));
      const inner = allEdges.filter((e) => connectionOf(e) !== "argus_reads" && ids.has(e.from) && ids.has(e.to));
      const out = await elk.layout({
        id: `${host.id}/${kind}`, layoutOptions: OPTIONS,
        children: section.map((n) => ({ id: n.id, width: NODE_W, height: nodeHeight(n) })),
        edges: inner.map(toElkEdge),
      });
      if (kind === "idle") {
        y += 44;
        idleGroups.push({ host: host.id, x: left + 12, y: y - 32, width: out.width + 16, height: out.height + 38 });
      }
      const dx = left + 12, dy = y;
      const shift = (p) => ({ x: p.x + dx, y: p.y + dy });
      for (const c of out.children) nodes.push({ ...section.find((n) => n.id === c.id), x: c.x + dx, y: c.y + dy, width: NODE_W, height: c.height });
      for (const e of out.edges ?? []) {
        const src = inner.find((v) => v.id === e.id);
        const s = e.sections?.[0];
        if (!s) continue;
        edges.push({
          ...src,
          points: [shift(s.startPoint), ...(s.bendPoints ?? []).map(shift), shift(s.endPoint)],
          labels: (e.labels ?? []).map((l) => ({ x: l.x + dx, y: l.y + dy, width: l.width, height: l.height })),
        });
      }
      hostWidth = Math.max(hostWidth, out.width + 24);
      y += out.height;
    }
    const width = Math.max(hostWidth, 320);
    const height = y + (hiddenIdle[host.id] ? 44 : 16) - 20;
    groups.push({ id: host.id, role: host.role, x: left, y: 20, width, height });
    left += width + 30;
    maxHeight = Math.max(maxHeight, height + 40);
  }

  // The links ELK did not lay out: routed around every box, labelled where nothing else is.
  const width = left - 10;
  const drawn = new Set(edges.map((e) => e.id));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  for (const e of allEdges) {
    if (drawn.has(e.id) || !byId.has(e.from) || !byId.has(e.to)) continue;
    if (connectionOf(e) === "argus_reads" && !showReads) continue;
    const points = routeBetween(byId.get(e.from), byId.get(e.to), nodes, width, maxHeight);
    const { width: lw, height: lh } = labelSize(e);
    const label = placeEdgeLabel(points, lw, lh, nodes, edges.flatMap((d) => d.labels));
    edges.push({ ...e, points, labels: [label] });
  }

  return {
    nodes, edges, groups, idleGroups, hiddenIdle,
    width: Math.max(width, ...edges.flatMap((e) => e.labels.map((l) => l.x + l.width + 15))),
    height: Math.max(maxHeight, ...edges.flatMap((e) => e.labels.map((l) => l.y + l.height + 15))),
  };
}
