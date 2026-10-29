# Operator console: mockup spec (CON-3)

The visual and behaviour spec for the console UI of [ACR-0043](../../architecture/changes/ACR-0043-operator-console.md),
named in [OPERATOR-CONSOLE-spec](OPERATOR-CONSOLE-spec.md) §10. It also fixes the shapes the UI reads, as a proposal for
CON-2 (the routes and the contract entry belong to CON-2).

## 1. Where it lives

- A **Console** tab on the incident page, after Metrics and before Runtime Timeline. The tab lives in the URL (`?tab=console`)
  like the others.
- The tab is shown **only when the console answers**: the adapter has the console calls and `commands` returns a non-empty
  list. A viewer, a refused call (403/404), the flag off (`ARGUS_OPERATOR_CONSOLE`, ACR-0043) or an API without the routes all
  hide it, the same rule as Map and Metrics. The API decides who may use it, never the UI.
- Wording: **Operator console**. Never "demo", "mock" or "shell" in the UI.

## 2. Layout

```
┌──────────────────────────── Operator console ─────────────────────────────┐
│ Commands run through Argus's own tools. No shell. Writes need approval.   │
├────────────────────────────────────────┬───────────────────────────────────┤
│ TERMINAL (≈55 %)                       │ ARGUS PANEL (≈45 %)               │
│                                        │ ┌ Current diagnosis ────────────┐ │
│ argus$ cache status                    │ │ root cause: argus-lab-cache   │ │
│ cache: exited (since 10:41:58)         │ │ confidence 0.86 · ruled out…  │ │
│ health: none                           │ └───────────────────────────────┘ │
│ argus$ status; rm                      │ ┌ Activity ─────────────────────┐ │
│ syntax not allowed: ;. Only plain …    │ │ cache status   ok · 10:44:02  │ │
│ argus$ cache restart                   │ │  Argus: waiting for metrics…  │ │
│ cache restart needs approval. Type     │ │ status; rm     rejected       │ │
│ 'yes' to propose it, anything else …   │ │ …                             │ │
│ confirm> _                             │ └───────────────────────────────┘ │
├────────────────────────────────────────┤                                   │
│ argus$ [ input ................ ] Run  │                                   │
└────────────────────────────────────────┴───────────────────────────────────┘
```

- Desktop (≥ 1024 px): two columns, `55fr / 45fr`. Narrower: stacked, terminal first.
- Fixed height for both columns: 28 rem (448 px), each scrolls inside itself. At **1280×720** the whole console is visible once
  the tab is scrolled into view; no horizontal scroll at 1280 or at 375 px.
- Terminal: monospace, dark field background (`bg-field`), the page's tokens only (works in the light theme too).

## 3. Terminal behaviour

| Case | What the operator sees |
|---|---|
| Opened | A greeting line ("Operator console for <incident>. Type 'help' to see available commands.") and the incident's earlier commands, each as its input line and its output |
| Enter | The input line is echoed as `argus$ <input>`; the input is disabled and a "running…" line shows until the answer; then the output lines, one per line |
| `clear` | Clears the screen only (local); the stored history and the panel are unchanged |
| ↑ / ↓ | Walk through the inputs typed in this session and the stored ones, newest first; ↓ past the newest gives an empty line |
| Rejected input (`ls`, `status; rm`) | The API's message in the error colour; nothing ran |
| `needs_confirmation` | The prompt text from the API, then the prompt changes to `confirm>`. `yes` resends the same input with `confirmation: "yes"`; anything else prints "cancelled" and returns to `argus$`. A `yes` is a confirmation of intent, **never an approval** (ACR-0043) |
| Error (network, 5xx, 429) | One error line ("console unavailable: <reason>", or "too many commands, try again in N s" for a 429 with `Retry-After`); the input is enabled again |

- Output is text only: no HTML, no colours from the output, control characters shown as `�`.
- The input keeps focus after each command; at most 200 characters (the parser's limit).

## 4. Argus panel

- **Current diagnosis** (read from the incident, the same state as the rest of the page, never console-local state): root cause,
  confidence, what was ruled out, the incident status. It updates with the page's own polling.
- **Activity**: one card per stored command, newest first: the input, its status (`ok`, `error`, `rejected`,
  `needs confirmation`), the time and the person. Under it, Argus's analysis when the API sends one (CON-4):
  - `waiting`: "Waiting for metrics to settle" with a countdown to `settle_until`;
  - `analyzing`: "Argus is analysing the result";
  - `done`: the comment (plain text, two or three sentences);
  - `error`: "Analysis unavailable" and the reason.
  Without an `analysis` field the card shows only the command. The UI never writes a comment of its own.
- The panel reads the history every 3 s while the tab is visible (`usePoll`), and right after each command.
- Suggestions with Insert and Copy are CON-5, not this card.

## 5. Shapes the UI reads (proposal for CON-2)

Private prefix, scoped to the incident (ACR-0043 §3):

- `GET /api/v1/ops/console/incidents/{id}/commands` → `{ "commands": [ { "id", "usage", "class", "scenario", "summary" } ] }`
  (`catalog()` of `argus/console/registry.py`).
- `POST /api/v1/ops/console/incidents/{id}/execute` with `{ "input", "confirmation"?: "yes", "suggestion_id"? }` →
  `{ "command_id", "input", "command", "class", "status": "ok" | "error" | "needs_confirmation" | "rejected", "output": [lines],
  "prompt"?: text, "started_at", "finished_at" }`. A rejected input is a 200 with `status: "rejected"` and the parser's message
  as the only output line.
- `GET /api/v1/ops/console/incidents/{id}/history` → `{ "entries": [ { "command_id", "input", "command", "class", "status",
  "output", "by", "started_at", "finished_at", "analysis"?: { "status": "waiting" | "analyzing" | "done" | "error",
  "settle_until"?, "comment"?, "reason"? } } ] }`, oldest first.

The real HTTP adapter gets these calls in CON-2 together with `contracts/ui-api.json` (protected); until then only the offline
demo adapter implements them, so a build against the real API keeps the tab hidden.

## 6. Accessibility

- The output is a `role="log"` region with polite announcements; the input has a label ("Console command").
- Status is never shown by colour alone (each status has its word).
- Keyboard only: the tab, the input, ↑/↓, Enter; no hidden shortcuts.
