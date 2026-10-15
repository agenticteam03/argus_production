import { Link } from "react-router-dom";
import { useRunbooks } from "../hooks/useRunbooks.js";
import { Book, InsetRow } from "./ui.jsx";

// The runbooks the agent recalled for this run. Each row opens that runbook on the Runbooks page.
const low = (s) => String(s ?? "").toLowerCase();
const stem = (file) => low(file).split("/").pop().replace(/\.md$/, "");

// The recalled reference can be a runbook id, a file name or a title: find the runbook of the library it points to.
export function resolveRunbook(ref, items) {
  const r = low(ref);
  return items.find((x) => low(x.id) === r)
    ?? items.find((x) => x.file && stem(x.file) === stem(r))
    ?? items.find((x) => low(x.title) === r)
    ?? items.find((x) => x.id && (r.startsWith(`${low(x.id)}-`) || r.startsWith(`${low(x.id)}_`)))
    ?? null;
}

export default function RunbooksRead({ ids }) {
  const { items } = useRunbooks();
  // Several passages of one runbook are one row.
  const rows = [];
  for (const ref of ids) {
    const rb = resolveRunbook(ref, items);
    const id = rb?.id ?? ref;
    if (!rows.some((r) => r.id === id)) rows.push({ id, title: rb?.title });
  }
  return (
    <ul className="mt-2 space-y-1.5">
      {rows.map(({ id, title }) => {
        return (
          <InsetRow as="li" key={id} className="p-0">
            <Link to={`/tools/runbooks?runbook=${encodeURIComponent(id)}`} className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition hover:bg-white/[0.04] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none">
              <Book width="15" height="15" className="shrink-0 text-muted" />
              <span className="font-mono text-xs text-accent-hover">{id}</span>
              {title && <span className="min-w-0 truncate text-[#d6dbe6]">{title}</span>}
              <span className="ml-auto shrink-0 text-xs text-muted">Read runbook</span>
            </Link>
          </InsetRow>
        );
      })}
    </ul>
  );
}
