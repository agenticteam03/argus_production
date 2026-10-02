# History — the condensed past (before the shared repository)

Sanitized summary of the decisions that still constrain the work. The full private logbook of that period is not
part of this repository. New entries go to [`logbook.md`](logbook.md).

## Earlier iterations — OBSOLETE, do not use as a reference for current code

- `03_MVP_LabAgent`, `04_MVP_Argus`, `05_prodArgus01`, `06_prodArgus02` (architecture v1.7, one host, SQLite, CLI
  only, no authentication) — superseded.
- `07_prodArgus03` — the **v1.8-lab**: v1.8 simplified (SQLite, one process, no LangGraph/MCP/scheduler) and emulated
  on LXD containers on a private server. It proved the core; the current code was ported from it. Obsolete.

## Decisions that still hold

| Date | Decision |
|---|---|
| 2026-09-29 | Argus is **read-only** in this release; writes only by authenticated humans. Model: OpenAI `gpt-5.6-luna` (no `temperature`; parameters are configuration). |
| 2026-09-30 | **Architecture v1.8**: general SRE agent with a fixed safety skeleton and registered extensions; `InvokeCapability`; `TargetRef(host, kind, name)`; `InventoryPort`; executors per host; evidence once with SHA-256; incident classes describing symptoms; policy as data; peer-agent collaboration designed in. No matching class ⇒ evidence pack, no diagnosis claimed. |
| 2026-09-30 | Classes aligned one-to-one with the runbook library v1.1.0 (`agenticteam03/runbooks`, RB-001…RB-021). The library is **read in place**, never copied; IDs from metadata. Open problems OP-001…OP-003 opened. |
| 2026-09-30 | Real v1.8 on two VMs: `vm-095` = agent host + light target, `vm-166` = primary target + monitoring; executors are v1.8 gateways and probes, **not SSH**; names `argus-v18-*` / `argus-lab-*`; ports 18000–18799; both output modes (formatted, `--raw`) built from real node events. |
| 2026-09-30 | Clean-up only for resources **proven** to be ours. |
| 2026-10-01 | Discovery: a **separate WireGuard-linked Argus deployment** (owner `conantkd`) spans both VMs and uses older `labmvp` objects on vm-166 → **protected objects** (rule N13). Argus networks 172.30.0–2.0/24. |
| 2026-10-01 | Only port 22 is open between the VMs and the team has no cloud-console access → cross-host path = **restricted SSH tunnel** (user `argus-v18-tunnel`, forward-only to five loopback ports, pinned host key, autossh sidecar). Alerts are **pulled**. (Pending team decision D-001 about the long term.) |
| 2026-10-01 | Phase 3 deployed on both VMs; `phase3_check` 28/28. Allowlists rendered from the inventory; answers echo their host (attribution check). |
| 2026-10-01 | **CRLF lesson:** Python `Path.write_text` on Windows writes CRLF and broke bash scripts → files written as bytes with `\n`; a test blocks CRLF. |
| 2026-10-01 | Agent live on vm-095 (`127.0.0.1:18000`); model calls through the **Responses API** (the model refuses tools on chat completions); 4xx not retried; a provider error escalates at once. |
| 2026-10-01 | Scenario fixes: the exporter takes the last exit from `die`/`oom` events (Docker resets them on restart); an empty diagnosis is rejected; `sudo --preserve-env` for the CLI helper; the `_scrape_up` **freshness gate** ("missing is unknown, never healthy"); down executors marked `UNAVAILABLE`. |
| 2026-10-02 | **Phase 5:** Postgres is the system of record (`argus-v18-postgres`, no host port); forward-only migrations; evidence/audit/run events insert-only for every role; runtime role without DELETE or DDL; `argus db check` 13/13; history imported from SQLite; rollback `ARGUS_DB_BACKEND=sqlite`. |
| 2026-10-02 | **Team logins:** one Argus user per developer (GitHub handle), one shared password, the old personal user disabled. |
| 2026-10-02 | **Shared Brain** (this repository): `brain/` is the single source of truth; task branches; the next developer reviews and merges; 60-minute renewable session lease; VMs deploy by `git fetch` with read-only deploy keys; the architecture changes only through ACRs (no longer frozen). |
| 2026-10-02 | Private addresses moved to the VM-local `/opt/argus-v18/hosts.env`; runbook pin in `config/runbooks.lock`. |

## Learned (recurring lessons)

- Never assume infrastructure facts: run a read-only discovery first, mark facts `OBSERVED` or `UNKNOWN`.
- Prove non-interference after every mutating step; anonymous Docker volumes need an ownership proof.
- A check must never say "healthy" from stale or missing data.
- Commands labelled with where they run prevent the most common mistake (a VM command in PowerShell).
