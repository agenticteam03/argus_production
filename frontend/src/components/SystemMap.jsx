import { useState } from "react";
import { Link } from "react-router-dom";
import { shortName } from "../utils/incidentView.js";
import { Card, Fact, Pill } from "./ui.jsx";

// Hand-rolled SVG map, no library. Expected data (GET /api/v1/topology, see hooks/useTopology.js):
//   hosts: [{ id, label, role: "argus" | "monitored" }]
//   nodes: [{ id, host, label, sub?, target?, kind?: "argus" | "app", status?, info?: [{ label, value }] }]
//   edges: [{ from, to, state?: "ok" | "broken" | "read", label? }]
// The cause / affected boxes are derived from the incident's own targets (`node.target`), never from the topology.
const W = 150, H = 38, STEP_X = 280, STEP_Y = 94, PAD = 20, HEAD = 44, GAP = 40, OUT = 10;

export function layoutMap(topology) {
  let x = OUT;
  let maxH = 0;
  const pos = {};
  const hosts = [];
  for (const h of topology.hosts ?? []) {
    const nodes = (topology.nodes ?? []).filter((n) => n.host === h.id);
    const cols = h.role === "argus" ? 1 : 2;
    const rows = Math.max(1, Math.ceil(nodes.length / cols));
    const width = 2 * PAD + W + (cols - 1) * STEP_X;
    const height = HEAD + (rows - 1) * STEP_Y + H + PAD;
    nodes.forEach((n, i) => { pos[n.id] = { x: x + PAD + (i % cols) * STEP_X, y: OUT + HEAD + Math.floor(i / cols) * STEP_Y }; });
    hosts.push({ ...h, x, y: OUT, width, height });
    x += width + GAP;
    maxH = Math.max(maxH, height);
  }
  return { hosts, pos, width: Math.max(x - GAP + OUT, 1), height: maxH + 2 * OUT };
}

export function stateOf(node, incident) {
  if (incident?.root_cause_target && node.target === incident.root_cause_target) return "cause";
  if (incident?.target && node.target === incident.target) return "affected";
  if (node.kind === "argus") return "argus";
  // ACR-0017: "unknown" means Argus does not know the component's state. It is never drawn as "ok".
  return node.status === "unknown" ? "unknown" : "ok";
}

// The two boxes of "where it broke": the affected target and its root cause.
export function miniNodes(topology, incident) {
  const find = (t) => (t ? topology?.nodes?.find((n) => n.target === t) : null);
  const a = find(incident?.target);
  const c = find(incident?.root_cause_target);
  return a && c && a.id !== c.id ? [a, c] : null;
}

// "unknown" is a first-class state (ACR-0017): neither green ("ok") nor red ("broken"). Exported so the styles can
// be checked without a DOM (SystemMap.test.js).
export const RECT = { ok: "stroke-field-line", unknown: "stroke-slate-500", cause: "stroke-red-400", affected: "stroke-amber-400/60", argus: "stroke-accent/40" };
const TITLE = { cause: "fill-red-300", ok: "fill-[#d7dce5]", unknown: "fill-[#d7dce5]", affected: "fill-[#d7dce5]", argus: "fill-[#d7dce5]" };
export const EDGE = { ok: "stroke-emerald-400/45", unknown: "stroke-slate-500/70", broken: "stroke-red-400", read: "stroke-field-line" };
export const DASH = { broken: "5 4", read: "2 3", unknown: "4 4" };
const LABEL = { cause: "Root cause", affected: "Affected", argus: "Argus", unknown: "Unknown" };
const TONE = { cause: "red", affected: "amber", argus: "blue", ok: "neutral", unknown: "neutral" };

function anchors(a, b) {
  const ac = { x: a.x + W / 2, y: a.y + H / 2 };
  const bc = { x: b.x + W / 2, y: b.y + H / 2 };
  const dx = bc.x - ac.x;
  const dy = bc.y - ac.y;
  if (Math.abs(dx) >= Math.abs(dy)) {
    const s = dx >= 0 ? 1 : -1;
    return [ac.x + (s * W) / 2, ac.y, bc.x - (s * W) / 2, bc.y];
  }
  const s = dy >= 0 ? 1 : -1;
  return [ac.x, ac.y + (s * H) / 2, bc.x, bc.y - (s * H) / 2];
}

function Box({ node, p, state, selected, interactive, onSelect }) {
  const props = interactive
    ? { role: "button", tabIndex: 0, "aria-pressed": selected, onClick: () => onSelect(node.id), onKeyDown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(node.id); } } }
    : {};
  return (
    <g aria-label={`${node.label}${node.sub ? `, ${node.sub}` : ""}${LABEL[state] ? `, ${LABEL[state].toLowerCase()}` : ""}`} className={`${interactive ? "cursor-pointer" : ""} outline-none [&:focus-visible>rect]:stroke-accent-hover`} {...props}>
      <rect x={p.x} y={p.y} width={W} height={H} rx="7" strokeWidth={selected ? 1.5 : 1} strokeDasharray={state === "unknown" ? "3 3" : undefined} className={`fill-field ${selected ? "stroke-accent" : RECT[state]}`} />
      <text x={p.x + 10} y={p.y + 16} className={`font-mono text-[11px] ${TITLE[state]}`}>{node.label}</text>
      {node.sub && <text x={p.x + 10} y={p.y + 29} className="fill-muted font-mono text-[9.5px]">{node.sub}</text>}
    </g>
  );
}

function Edges({ edges, pos }) {
  return edges.filter((e) => pos[e.from] && pos[e.to]).map((e, i) => {
    const [x1, y1, x2, y2] = anchors(pos[e.from], pos[e.to]);
    const k = e.state ?? "ok";
    return (
      <g key={i}>
        <path d={`M${x1},${y1} L${x2},${y2}`} strokeWidth={k === "broken" ? 1.5 : 1.3} strokeDasharray={DASH[k]} className={`fill-none ${EDGE[k] ?? EDGE.ok}`} />
        {e.label && <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 8} textAnchor="middle" className={`text-[9.5px] ${k === "broken" ? "fill-red-300" : "fill-muted"}`}>{e.label}</text>}
      </g>
    );
  });
}

export default function SystemMap({ topology, incident, selectedId, onSelect, variant = "full" }) {
  if (variant === "mini") {
    const pair = miniNodes(topology, incident);
    if (!pair) return null;
    const pos = { [pair[0].id]: { x: 40, y: 36 }, [pair[1].id]: { x: 330, y: 36 } };
    const edge = topology.edges?.find((e) => (e.from === pair[0].id && e.to === pair[1].id) || (e.from === pair[1].id && e.to === pair[0].id));
    return (
      <svg viewBox="0 0 520 110" role="img" aria-label={`${shortName(pair[0].target)} and ${shortName(pair[1].target)}${edge?.label ? `: ${edge.label}` : ""}`} className="block h-auto max-h-40 w-full">
        <Edges edges={edge ? [edge] : []} pos={pos} />
        {pair.map((n) => <Box key={n.id} node={n} p={pos[n.id]} state={stateOf(n, incident)} />)}
      </svg>
    );
  }
  const { hosts, pos, width, height } = layoutMap(topology);
  const interactive = Boolean(onSelect);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="group" aria-label={`System map: ${hosts.length} hosts, ${topology.nodes?.length ?? 0} components`} className="block h-auto w-full">
      {hosts.map((h) => (
        <g key={h.id}>
          <rect x={h.x} y={h.y} width={h.width} height={h.height} rx="14" className="fill-none stroke-line" />
          <text x={h.x + 16} y={h.y + 26} className="fill-muted text-[11px]">{h.label}</text>
        </g>
      ))}
      <Edges edges={topology.edges ?? []} pos={pos} />
      {(topology.nodes ?? []).filter((n) => pos[n.id]).map((n) => (
        <Box key={n.id} node={n} p={pos[n.id]} state={stateOf(n, incident)} selected={n.id === selectedId} interactive={interactive} onSelect={onSelect} />
      ))}
    </svg>
  );
}

function NodeInfo({ node, state, incident }) {
  return (
    <Card title={node.label} right={<Pill tone={TONE[state]}>{LABEL[state] ?? node.status ?? "Component"}</Pill>}>
      {node.info?.length > 0 || node.status ? (
        <dl className="space-y-3">
          {node.status && <Fact label="Status">{node.status}</Fact>}
          {(node.info ?? []).map((r) => <Fact key={r.label} label={r.label}>{r.value}</Fact>)}
        </dl>
      ) : (
        <p className="text-sm text-muted">No further details for this component.</p>
      )}
      {(state === "cause" || state === "affected") && (
        <p className="mt-4 border-t border-line pt-3 text-xs text-muted">Linked incident: <Link to={`/incidents/${incident.id}`} className="font-mono text-accent-hover hover:underline">{incident.id}</Link></p>
      )}
    </Card>
  );
}

const Swatch = ({ cls, label }) => <span className="inline-flex items-center gap-2"><i className={`inline-block w-5 border-t-[1.5px] ${cls}`} />{label}</span>;

// The edge legend, shared by the Map tab and the Dashboard map. "unknown" has its own entry so it is never read as
// "dependency ok" (ACR-0017).
export function MapLegend() {
  return (
    <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
      <Swatch cls="border-emerald-400/45" label="dependency ok" />
      <Swatch cls="border-dashed border-slate-500/70" label="unknown" />
      <Swatch cls="border-dashed border-red-400" label="broken" />
      <Swatch cls="border-dotted border-field-line" label="Argus reads" />
    </p>
  );
}

// The "Map" tab: the whole system on the left, the selected box on the right.
export function MapTab({ topology, incident }) {
  const nodes = topology.nodes ?? [];
  const initial = nodes.find((n) => stateOf(n, incident) === "cause") ?? nodes.find((n) => stateOf(n, incident) === "affected") ?? nodes[0];
  const [selectedId, setSelectedId] = useState(initial?.id ?? null);
  const node = nodes.find((n) => n.id === selectedId);
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2.3fr)_minmax(0,1fr)]">
      <Card title="System map" right={<span className="text-xs text-muted">Select a box</span>}>
        <SystemMap topology={topology} incident={incident} selectedId={selectedId} onSelect={setSelectedId} />
        <MapLegend />
      </Card>
      {node && <NodeInfo node={node} state={stateOf(node, incident)} incident={incident} />}
    </div>
  );
}

// The Dashboard's live map (ACR-0017): the whole system, read-only. Hides itself when the route answers nothing.
export function SystemMapCard({ topology }) {
  if (!topology?.nodes?.length) return null;
  return (
    <Card title="System map" right={<span className="text-xs text-muted">Click a box on an incident's Map tab for details</span>}>
      <SystemMap topology={topology} />
      <MapLegend />
    </Card>
  );
}

export function MiniMapCard({ topology, incident, onOpen }) {
  if (!miniNodes(topology, incident)) return null;
  return (
    <Card title="Where it broke" right={<button type="button" onClick={onOpen} className="cursor-pointer text-xs text-accent-hover hover:underline">Full map</button>}>
      <SystemMap variant="mini" topology={topology} incident={incident} />
    </Card>
  );
}
