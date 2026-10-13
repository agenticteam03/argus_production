// The incident list is paged in the browser: `GET /api/v1/incidents` takes only `limit` (the latest N) — there is
// no `offset` and no total — so the list is fetched once up to `INCIDENTS_CAP` and revealed `PAGE_SIZE` at a time.
// A real cursor + total needs a contract change (see ../README.md, "Known follow-ups").
export const PAGE_SIZE = 30;
export const INCIDENTS_CAP = 1000;

// The line under the filters: how many are on screen, how many match, and the real total. `truncated` means the
// API returned exactly `INCIDENTS_CAP` rows, so there may be more we cannot reach without a contract change.
export const incidentsSummary = ({ shown, matched, total, hasFilters, truncated }) => {
  let counts = `Showing ${shown} of ${total}`;
  if (hasFilters) {
    counts = matched === total
      ? `Showing ${shown} of ${matched} matching`
      : `Showing ${shown} of ${matched} matching · ${total} total`;
  }
  return `${counts} incidents${truncated ? ` · only the latest ${INCIDENTS_CAP} are loaded` : ""}`;
};
