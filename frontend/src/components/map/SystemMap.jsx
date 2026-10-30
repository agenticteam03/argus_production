import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HEALTH_META, HexGlyph } from "../Glyph.jsx";
import { Card, Hint, Server } from "../ui.jsx";
import { layoutMap } from "./layout.js";
import { causePathOf, CONNECTIONS, connectionOf, edgeDetail, mapNodes, PROBLEM_LABELS, ROLES } from "./mapModel.js";
import NodeDrawer from "./NodeDrawer.jsx";
import { roundedPath } from "./router.js";

// The 2D system map (ui-graphs prototype): one section per host, the boxes laid out by ELK, health as a hexagon and a
// coloured border, problems as badges, the incident's root cause and affected box marked, every checked link drawn
// with its state. Click (or Enter on) a box to open its drawer. Used on the Dashboard (live health) and on an
// incident's Map tab (cause path). Topology: docs/API-FOR-UI.md item 12.

// elkjs is loaded on the first map only (it is ~1.4 MB unminified), and shared by every map after that.
let elkPromise = null;
const loadElk = () => (elkPromise ??= import("elkjs/lib/elk.bundled.js").then((m) => new m.default()));

const BOX = {
  ok: "border-emerald-400/35 bg-linear-to-b from-emerald-400/[0.06]",
  degraded: "border-amber-400/45 bg-linear-to-b from-amber-400/[0.07]",
  failed: "border-red-400/55 bg-linear-to-b from-red-400/[0.08]",
  unknown: "border-line bg-linear-to-b from-ink/[0.03]",
  idle: "border-dashed border-line",
};
const ROLE_TAG = { root_cause: "text-red-300", affected: "text-amber-300", on_path: "text-muted" };
const PROBLEM_TONE = { critical: "border-red-400/30 bg-red-400/10 text-red-300", warning: "border-amber-400/30 bg-amber-400/10 text-amber-300", info: "border-sky-400/30 bg-sky-400/10 text-sky-300" };

function subline(n) {
  if (n.idle) return "Scenario container · expected";
  if (n.kind === "host") return "Host · monitoring active";
  if (n.networks?.length) return `net: ${n.networks.join(", ")}`;
  return n.sub && n.sub !== "container" ? `${n.sub} · ${n.status ?? "unknown"}` : `status: ${n.status ?? "unknown"}`;
}

function NodeBox({ n, dim, selected, onOpen }) {
  const meta = HEALTH_META[n.health] ?? HEALTH_META.unknown;
  const problems = n.problems ?? [];
  const root = n.role === "root_cause";
  return (
    <button type="button" onClick={() => onOpen(n.id)}
      aria-label={`${n.host} ${n.label}: ${meta.label}${n.role ? `, ${ROLES[n.role].label}` : ""}. Open details`}
      style={{ left: n.x, top: n.y, width: n.width, height: n.height }}
      className={`absolute flex cursor-pointer items-start gap-3 overflow-hidden rounded-xl border bg-card to-card p-3 text-left shadow-[0_10px_24px_-16px_rgb(0_0_0/0.6)] transition hover:-translate-y-px hover:shadow-[0_14px_30px_-16px_rgb(0_0_0/0.7)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none
        ${root ? "border-2 border-red-400 bg-linear-to-b from-red-400/[0.10]" : BOX[n.health] ?? BOX.unknown}
        ${selected ? "ring-2 ring-accent/70" : ""} ${dim ? "opacity-35" : ""} ${n.idle ? "opacity-80" : ""}`}>
      <HexGlyph health={n.glyph} icon={n.icon} pulse={root || n.glyph === "failed"} size={34} />
      <span className="flex h-full min-w-0 flex-1 flex-col gap-1">
        <span className="flex min-h-[18px] items-center gap-2">
          <span className={`inline-flex items-center gap-1 whitespace-nowrap text-xs font-medium ${meta.text}`}><span className="size-1.5 rounded-full bg-current" />{meta.label}</span>
          {n.role && <span className={`ml-auto whitespace-nowrap text-[10px] font-bold uppercase tracking-wider ${ROLE_TAG[n.role]}`}>{ROLES[n.role].label}</span>}
        </span>
        <span className="truncate font-mono text-[13px] font-semibold text-ink">{n.label}</span>
        {problems.length ? (
          <span className="mt-auto flex min-w-0 flex-wrap gap-1">
            {problems.slice(0, 2).map((p, i) => (
              <span key={i} title={`${PROBLEM_LABELS[p.kind] ?? p.kind}: ${p.summary}`}
                className={`max-w-full truncate rounded-full border px-2 py-px text-[11px] ${PROBLEM_TONE[p.severity] ?? PROBLEM_TONE.info}`}>
                {PROBLEM_LABELS[p.kind] ?? p.kind} · {p.summary}
              </span>
            ))}
            {problems.length > 2 && <span className="rounded-full border border-line px-2 py-px text-[11px] text-muted">+{problems.length - 2}</span>}
          </span>
        ) : (
          <span className="truncate text-xs text-muted">{subline(n)}</span>
        )}
      </span>
    </button>
  );
}

function Edges({ m, dimEdge, litEdge }) {
  return (
    <svg width={m.width} height={m.height} className="pointer-events-none absolute left-0 top-0 overflow-visible" aria-hidden="true">
      <defs>
        {Object.entries(CONNECTIONS).map(([k, c]) => (
          <marker key={k} id={`map-arrow-${k}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0 1 L7 4 L0 7" fill="none" strokeWidth="1.3" className={c.stroke} />
          </marker>
        ))}
      </defs>
      {m.edges.map((e) => {
        const k = connectionOf(e), c = CONNECTIONS[k], d = roundedPath(e.points);
        const dim = dimEdge(e), lit = !dim && (k === "broken" || litEdge(e));
        return (
          <g key={e.id} opacity={dim ? 0.3 : 1}>
            {lit && <path d={d} fill="none" strokeWidth="9" className={`${c.stroke} edge-glow`} />}
            <path d={d} fill="none" strokeWidth={k === "broken" ? 2.4 : lit ? 2.2 : 1.6} strokeDasharray={c.dash} className={c.stroke} markerEnd={`url(#map-arrow-${k})`} />
            {(k === "ok" || k === "slow") && !dim && <path d={d} fill="none" className={`${c.stroke} edge-flow`} />}
          </g>
        );
      })}
    </svg>
  );
}

const Toggle = ({ checked, onChange, children }) => (
  <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-body">
    <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-4 cursor-pointer accent-[var(--color-accent)]" />
    {children}
  </label>
);

function Legend({ incident }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
      <span className="font-medium text-body">Boxes</span>
      {Object.entries(HEALTH_META).map(([h, meta]) => <span key={h} className="inline-flex items-center gap-1.5"><HexGlyph health={h} pulse={false} size={16} />{meta.label}</span>)}
      {incident && <span className="inline-flex items-center gap-1.5"><i className="inline-block h-3 w-4 rounded border-2 border-red-400" />Root cause</span>}
      <span className="ml-2 font-medium text-body">Links</span>
      {["ok", "slow", "broken", "not_checked", "argus_reads"].map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden="true"><line x1="0" x2="22" y1="3" y2="3" strokeWidth="1.8" strokeDasharray={CONNECTIONS[k].dash} className={CONNECTIONS[k].stroke} /></svg>
          {CONNECTIONS[k].label}
        </span>
      ))}
    </div>
  );
}

// `incidents`: the dashboard's latest incidents (a box whose incident still needs attention turns amber or red);
// `incident`: the incident whose Map tab this is (its root cause and affected box are marked, the cause path lit).
// One empty list for every render: a fresh `[]` default re-ran the layout on each render, and each new layout scrolled
// the map back to the root cause, so it could not be moved sideways (T-0016).
const NO_INCIDENTS = [];

export default function SystemMap({ topology, incidents = NO_INCIDENTS, incident = null, title = "System map" }) {
  const [showIdle, setShowIdle] = useState(false);
  const [showReads, setShowReads] = useState(false);
  const path = useMemo(() => causePathOf(topology, incident), [topology, incident]);
  const [focus, setFocus] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [layout, setLayout] = useState({ key: null, m: null, error: false });
  const nodes = useMemo(() => mapNodes(topology, { incidents, incident }), [topology, incidents, incident]);
  const key = `${showIdle}|${showReads}`;

  useEffect(() => {
    let alive = true;
    loadElk()
      .then((elk) => layoutMap({ ...topology, nodes }, { showIdle, showReads }, elk))
      .then((m) => alive && setLayout({ key: `${showIdle}|${showReads}`, m, error: false }))
      .catch(() => alive && setLayout({ key: `${showIdle}|${showReads}`, m: null, error: true }));
    return () => { alive = false; };
  }, [topology, nodes, showIdle, showReads]);

  const m = layout.m;
  const viewport = useRef(null);
  // On an incident, bring the root cause (the end of the cause path) into view when the map is wider than its card.
  // Once per root cause: a later layout (a poll, a toggle) leaves the person's own scroll where it is.
  const causeId = path.at(-1);
  const scrolledTo = useRef(null);
  useEffect(() => {
    const n = causeId && m?.nodes.find((x) => x.id === causeId);
    if (!n || !viewport.current || scrolledTo.current === causeId) return;
    scrolledTo.current = causeId;
    viewport.current.scrollLeft = Math.max(0, n.x + n.width + 40 - viewport.current.clientWidth);
  }, [m, causeId]);
  const focusing = Boolean(incident) && focus && path.length > 0;
  const onPath = (id) => path.includes(id);
  const close = useCallback(() => setSelectedId(null), []);
  const selected = nodes.find((n) => n.id === selectedId);
  const hostCount = topology.hosts?.length ?? 0;

  return (
    <Card title={title} right={<span className="text-xs text-muted">{hostCount} {hostCount === 1 ? "host" : "hosts"} · {nodes.length} components</span>} className="min-w-0">
      <p className="-mt-2 mb-3 text-xs text-muted">{incident ? "Cause path highlighted. Select a box to inspect its signals." : "Live health of every container and checked connection. Select a box for details."}</p>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        <Toggle checked={showIdle} onChange={setShowIdle}>
          Show <Hint align="left" text="A scenario container that is intentionally stopped. No failure is implied."><span className="border-b border-dotted border-current">idle</span></Hint> containers
        </Toggle>
        <Toggle checked={showReads} onChange={setShowReads}>Argus reads</Toggle>
        {incident && path.length > 0 && <Toggle checked={focus} onChange={setFocus}>Focus cause path</Toggle>}
      </div>

      <div ref={viewport} className="map-viewport overflow-x-auto rounded-xl border border-line" role="region" aria-label="System map. Tab through the boxes, Enter opens one.">
        {!m ? (
          <div className="grid h-56 place-items-center text-sm text-muted">{layout.error ? "The map could not be laid out." : "Laying out dependencies…"}</div>
        ) : (
          <div className={`relative transition-opacity ${layout.key === key ? "" : "opacity-60"}`} style={{ width: m.width, height: m.height }}>
            {m.groups.map((g) => (
              <div key={g.id} style={{ left: g.x, top: g.y, width: g.width, height: g.height }}
                className="absolute rounded-2xl border border-line bg-card/60">
                <div className="absolute inset-x-4 top-3 flex items-center gap-2 text-[13px]">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-2.5 py-0.5 font-medium text-ink"><Server width="13" height="13" />{g.id}</span>
                  <span className="text-xs text-muted">{g.role}</span>
                  <span className="ml-auto text-xs text-muted">{m.nodes.filter((n) => n.host === g.id).length} shown</span>
                </div>
                {m.hiddenIdle[g.id] > 0 && (
                  <div className="absolute bottom-3 left-4 text-xs text-muted">
                    {m.hiddenIdle[g.id]} idle scenario {m.hiddenIdle[g.id] === 1 ? "container" : "containers"} (expected) ·{" "}
                    <button type="button" onClick={() => setShowIdle(true)} className="cursor-pointer text-accent-hover hover:underline">Show</button>
                  </div>
                )}
              </div>
            ))}
            {m.idleGroups.map((g) => (
              <div key={`idle-${g.host}`} style={{ left: g.x, top: g.y, width: g.width, height: g.height }} className="absolute rounded-xl border border-dotted border-field-line">
                <span className="absolute left-3 top-2 text-xs text-muted">Idle scenario containers (expected)</span>
              </div>
            ))}
            <Edges m={m} dimEdge={(e) => focusing && !(onPath(e.from) || onPath(e.to))} litEdge={(e) => focusing && onPath(e.from) && onPath(e.to)} />
            {m.edges.flatMap((e) => e.labels.map((l, i) => {
              const k = connectionOf(e);
              return (
                <div key={`${e.id}-${i}`} style={{ left: l.x, top: l.y, width: l.width, height: l.height }}
                  className={`absolute flex flex-col justify-center rounded-lg border bg-card px-2 text-center text-[11px] leading-tight shadow-sm ${k === "broken" ? "border-red-400/40" : "border-line"} ${focusing && !(onPath(e.from) || onPath(e.to)) ? "opacity-30" : ""}`}>
                  <span className="truncate font-medium text-ink">{e.label}</span>
                  <span className={`truncate ${CONNECTIONS[k].text}`}>{edgeDetail(e)}</span>
                </div>
              );
            }))}
            {m.nodes.map((n) => (
              <NodeBox key={n.id} n={n} dim={focusing && !onPath(n.id)} selected={n.id === selectedId} onOpen={setSelectedId} />
            ))}
          </div>
        )}
      </div>
      <Legend incident={incident} />
      {selected && <NodeDrawer node={selected} incidents={incidents} incident={incident} onClose={close} />}
    </Card>
  );
}
