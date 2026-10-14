// How often the UI asks the API, in one place (ACR-0011 §3.1 row 8). Every poll goes through `usePoll`, so nothing
// is fetched while the tab is hidden, and a returning tab refreshes once at once.
export const POLL_MS = {
  overview: 30_000,          // the dashboard
  incidents: 30_000,         // the incident list
  runningIncident: 3_000,    // an incident whose investigation is still running (stops when it concludes)
  runningEvents: 2_000,      // its timeline, while running
};
