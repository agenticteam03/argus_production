# T-0041 step 02 — evidence: the first real db_probe rotation on vm-166 (2026-10-13, conantkd, session 2b41a356d48c)

Both leases (until 21:42 UTC). Run by the agent over ssh with `conantkd`'s explicit go-ahead. Both VMs on `main`
`ad72617`. The token was never printed: only 12-character SHA-256 prefixes.

| Check | Before | After |
|---|---|---|
| vm-166 service copy `secrets/db_probe_token` | `600 root:root`, `97f15d44e745` | `600 root:root`, `804c84827c26` |
| vm-166 Prometheus copy `secrets/prometheus/db_probe_token` | `400 nobody:nogroup`, `97f15d44e745` | `400 nobody:nogroup`, `804c84827c26` (owner and mode kept) |
| `rotate-token.sh db_probe --as conantkd` | — | `argus-v18-db-probe recreated; sha256 804c84827c26`; "the prometheus copy updated too" |
| `up{job="argus-v18-db-probe"}` on vm-166 | 1 | 0 on the scrape during the recreate (as the task says), then **1**; no `ArgusScrapeTargetMissing` or blind-spot alert (only the heartbeat, which always fires) |
| agent copy on vm-095 `secrets/agent/vm-166/db_probe_token` | `400 10011:10011`, `97f15d44e745` | old copy: `database.health` **forbidden (HTTP 401)**; new copy piped vm-166 → vm-095 (never displayed), hashes equal `804c84827c26`; put in place with the same owner and mode, old one kept as `.prev` |
| `database.health` on `vm-166/container:argus-lab-db` from vm-095's worker | ok (0/16 connections) | **ok** with the new copy |
| worker restarted? | started `16:14:40Z`, restarts 0 | the same: the agent re-read its copy after the rejected read (T-0033) |
| NO INTERFERENCE | — | both VMs |

Note: the pre-check block called `nonint-check.sh before` again after the rotation, so vm-166's baseline file was
saved a second time; the rotation recreates only `argus-v18-db-probe`, and `after` still reported NO INTERFERENCE.

Result: the `db_probe` token of vm-166 rotates like the other executors, both its copies at once, with no blind spot
and no worker restart. Phase 13's last open item is done.
