import { hostOf } from "../../../utils/incidentView.js";

// T-0016: the side panel around the team's operator console (ACR-0043). Pure rules, so the components stay thin.
// The API decides every command (ACR-0001); this only picks what the panel shows before it opens.

export const DOCK_HOSTS = ["vm-095", "vm-166"];   // the two lab hosts the "+" offers
export const MAX_TABS = 4;
const HOST_INCIDENTS = 8;

// The console is shown to the highest role, an approver (real /me of the lab, 2026-10-29); its routes still need the
// private session and `investigate`, and its writes the approval path.
export const canSeeConsole = (user) => user?.role === "approver";

// Built in: always in the demo; in a real build only with the team's console flag (VITE_ARGUS_CONSOLE=1), so a build
// for an API without the console routes shows no entry and calls none (frontend/e2e/console.e2e.js).
export const consoleBuilt = (source, env) => source === "demo" || env?.VITE_ARGUS_CONSOLE === "1";

// The access dialog's case. Two registered keys, and (ACR-0032, ACR-0043) the private session confirmed with one.
// `user.secondFactor` is /me's `second_factor` ({ enrolled, verified }); absent when Argus has no keys configured.
export function dockAccess(user) {
  const sf = user?.secondFactor;
  if (!sf) return "unconfigured";
  if (sf.enrolled <= 0) return "no-keys";
  if (sf.enrolled === 1) return "one-key";
  return user.access === "ops" && sf.verified ? "ready" : "unlock";
}

// Case 3's next step: the private login, then the security key that completes it.
export function unlockStep(user) {
  if (user?.access !== "ops") return "private-login";
  return user.secondFactor?.verified ? null : "second-factor";
}

// A host's incidents, newest first (the console works inside an incident: its routes are scoped to one).
export const hostIncidents = (incidents, host) =>
  (incidents ?? []).filter((i) => String(i.target ?? "").includes("/") && hostOf(i.target) === host)
    .sort((a, b) => String(b.opened_at).localeCompare(String(a.opened_at))).slice(0, HOST_INCIDENTS);

// The panel's widest: on a wide screen the page keeps 600 px beside it (more: full screen); narrower, 90 % of it.
export const MIN_WIDTH = 380;
const MIN_PAGE = 600;
export const maxDockWidth = (viewport) => Math.max(MIN_WIDTH, viewport >= 1024 ? viewport - MIN_PAGE : viewport * 0.9);

export const timeLeft = (expiresAt, now = Date.now()) => Math.max(0, Date.parse(expiresAt) - now);

export const clock = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
