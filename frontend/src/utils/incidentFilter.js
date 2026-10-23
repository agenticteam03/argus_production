import { hostOf } from "./incidentView.js";

// The Incidents list filters by host first, then by a target inside that host. Both lists come from the incidents
// already loaded, so only hosts and targets that have had an incident are offered.
export const hostsOf = (rows) => [...new Set((rows ?? []).map((r) => hostOf(r.target)).filter(Boolean))].sort();

export const targetsOfHost = (rows, host) =>
  host ? [...new Set((rows ?? []).filter((r) => hostOf(r.target) === host).map((r) => r.target))].sort() : [];

export const matchesHost = (row, host, target) =>
  (!host || hostOf(row.target) === host) && (!target || row.target === target);

// "vm-166/container:api" -> "container:api" (the host is already chosen).
export const withoutHost = (target, host) => (host && String(target).startsWith(`${host}/`) ? String(target).slice(host.length + 1) : target);
