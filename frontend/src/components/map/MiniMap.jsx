import { HEALTH_META, HexGlyph } from "../Glyph.jsx";
import { Card, Hint } from "../ui.jsx";
import { CONNECTIONS, connectionOf, edgeDetail, mapNodes, PROBLEM_LABELS, ROLES } from "./mapModel.js";

// "Where it broke" on an incident's first tab (ui-graphs prototype, miniMap): the root cause, the link to the
// affected component and the affected component, or the affected component alone when Argus named no other cause.
function MiniBox({ n }) {
  const meta = HEALTH_META[n.health] ?? HEALTH_META.unknown;
  const role = n.role ? ROLES[n.role] : null;
  return (
    <div className={`flex min-w-0 flex-1 items-start gap-3 rounded-xl border bg-card p-3 ${n.role === "root_cause" ? "border-2 border-red-400 bg-red-400/[0.05]" : n.role === "affected" ? "border-amber-400/45" : "border-line"}`}>
      <HexGlyph health={n.glyph} icon={n.icon} pulse={n.role === "root_cause"} size={32} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className={`inline-flex items-center gap-1 text-xs font-medium ${meta.text}`}><span className="size-1.5 rounded-full bg-current" />{meta.label}</span>
          {role && <Hint align="left" text={role.help}><span className={`text-[10px] font-bold uppercase tracking-wider ${n.role === "root_cause" ? "text-red-300" : "text-amber-300"}`}>{role.label}</span></Hint>}
        </div>
        <p className="mt-0.5 truncate font-mono text-[13px] font-semibold text-ink">{n.label}</p>
        {(n.problems ?? []).slice(0, 2).map((p, i) => (
          <p key={i} className="mt-1 truncate text-xs text-muted">{PROBLEM_LABELS[p.kind] ?? p.kind} · {p.summary}</p>
        ))}
      </div>
    </div>
  );
}

// The incident's own boxes, or null when the topology does not contain its target (the card then stays hidden).
export function miniPair(topology, incident) {
  const nodes = mapNodes(topology, { incident });
  const target = nodes.find((n) => n.target === incident?.target);
  if (!target) return null;
  const root = nodes.find((n) => n.role === "root_cause" && n.id !== target.id) ?? null;
  const edge = root ? (topology.edges ?? []).find((e) => [e.from, e.to].includes(root.id) && [e.from, e.to].includes(target.id)) : null;
  return { target, root, edge };
}

export default function MiniMap({ topology, incident, onOpen }) {
  const pair = miniPair(topology, incident);
  if (!pair) return null;
  const { target, root, edge } = pair;
  const k = edge ? connectionOf(edge) : "not_checked";
  return (
    <Card title="Where it broke" right={<button type="button" onClick={onOpen} className="cursor-pointer text-xs text-accent-hover hover:underline">Full map</button>}>
      {root ? (
        <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
          <MiniBox n={root} />
          <div className="flex shrink-0 flex-col items-center px-1 text-center sm:w-28" title="From the cause to the affected component">
            <span className="text-[11px] font-medium text-ink">{edge?.label ?? "no checked link"}</span>
            <svg width="100%" height="10" className="my-1 hidden sm:block" aria-hidden="true">
              <line x1="0" x2="100%" y1="5" y2="5" strokeWidth="1.8" strokeDasharray={CONNECTIONS[k].dash} className={CONNECTIONS[k].stroke} />
            </svg>
            <span className={`text-[11px] ${CONNECTIONS[k].text}`}>{edge ? edgeDetail(edge) : CONNECTIONS.not_checked.label}</span>
          </div>
          <MiniBox n={target} />
        </div>
      ) : (
        <MiniBox n={target} />
      )}
    </Card>
  );
}
