import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import RunbookCard from "../components/RunbookCard.jsx";
import RunbookDrawer from "../components/RunbookDrawer.jsx";
import { Book, Empty, fieldClass, LivePill, Search, Select, Warning } from "../components/ui.jsx";
import { useRunbooks } from "../hooks/useRunbooks.js";

export default function Runbooks() {
  const { items, loading, live } = useRunbooks();
  const [query, setQuery] = useState("");
  const [detector, setDetector] = useState("");
  const [action, setAction] = useState("");
  const [gapsOnly, setGapsOnly] = useState(false);
  // The open runbook lives in the URL (?runbook=RB-003): an incident can link straight to it, and Back closes it.
  const [params, setParams] = useSearchParams();
  const openId = params.get("runbook");
  const setOpenId = useCallback((id) => setParams((prev) => {
    const next = new URLSearchParams(prev);
    if (id) next.set("runbook", id); else next.delete("runbook");
    return next;
  }, { replace: !id }), [setParams]);

  const detectors = useMemo(() => [...new Set(items.map((r) => r.detector).filter(Boolean))].sort(), [items]);
  const filtered = useMemo(() => {
    const t = query.trim().toLowerCase();
    return items.filter(
      (r) =>
        (!detector || r.detector === detector) &&
        (!action || r.risk === action) &&
        (!gapsOnly || r.missing > 0) &&
        (!t || [r.id, r.title, r.detector, r.summary, r.scope, ...r.tools.map((x) => x.name)].join(" ").toLowerCase().includes(t))
    );
  }, [items, query, detector, action, gapsOnly]);

  const open = items.find((r) => r.id === openId); // looked up live, so the drawer refreshes with the server
  const close = useCallback(() => setOpenId(null), [setOpenId]);
  const clear = () => { setQuery(""); setDetector(""); setAction(""); setGapsOnly(false); };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Runbooks</h1>
          <p className="text-sm text-muted">Remediation guides from the Argus server. Edits show up here automatically.</p>
        </div>
        <LivePill live={live} />
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-60 flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" width="16" height="16" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by ID, title, detector or tool…" aria-label="Search runbooks" className={`${fieldClass} w-full pl-10`} />
        </div>
        <Select value={detector} onChange={(e) => setDetector(e.target.value)} aria-label="Filter by detector">
          <option value="">All detectors</option>
          {detectors.map((d) => <option key={d} value={d}>{d}</option>)}
        </Select>
        <Select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter by action type">
          <option value="">All actions</option>
          <option value="read-only">Read-only</option>
          <option value="high">High-risk actions</option>
        </Select>
        <button
          aria-pressed={gapsOnly}
          onClick={() => setGapsOnly((v) => !v)}
          className={`inline-flex h-11 cursor-pointer items-center gap-2 rounded-[10px] border px-3.5 text-sm transition ${gapsOnly ? "border-amber-400/40 bg-amber-400/10 text-amber-300" : "border-field-line bg-field text-muted hover:text-white"}`}
        >
          <Warning width="15" height="15" /> Missing tools
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-muted">Loading runbooks…</p>
      ) : items.length === 0 ? (
        <Empty icon={Book} title="No runbooks yet" text="Runbooks published on the Argus server will appear here." />
      ) : filtered.length === 0 ? (
        <div className="space-y-3 text-center">
          <Empty icon={Search} title="No runbooks match your filters" text="Try a different search or clear the filters." />
          <button onClick={clear} className="cursor-pointer text-[13px] text-accent-hover hover:underline">Clear filters</button>
        </div>
      ) : (
        <>
          <p className="text-xs text-muted">Showing {filtered.length} of {items.length}</p>
          <div className="grid gap-4 md:grid-cols-2">
            {filtered.map((r) => <RunbookCard key={r.id} runbook={r} onOpen={setOpenId} />)}
          </div>
        </>
      )}

      {open && <RunbookDrawer runbook={open} onClose={close} />}
    </div>
  );
}
