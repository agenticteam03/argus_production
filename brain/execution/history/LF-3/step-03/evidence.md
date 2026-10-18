# LF-3 step 03 — evidence: the worker exports to Langfuse Cloud (EU), ACR-0016 (2026-10-18, conantkd, session ceeb8c3e6e42)

Goal: connect vm-095's worker to Langfuse Cloud as ACR-0016 defines, check what leaves the host, check that an
unreachable Cloud changes nothing in Argus, and remove the self-hosted stack that failed its capacity gate. Leases:
vm-095 + vm-166 (the agent changes); vm-166 itself was not changed. Commands: [`code.bash`](code.bash). Times are UTC.
No key, address or Langfuse project id is written here (`policies/SECURITY.md` rule 4).

| Block | Observed | Result |
|---|---|---|
| L.0 laptop | the leases were taken over from an EXPIRED lease of juanbetancurm (DEPLOY-164); markers `holder=conantkd session=ceeb8c3e6e42` on both VMs | OK |
| L.1 vm-095 | `commit=813e0d9` `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE`; the six `argus-v18-langfuse-*` containers `Exited` (since 2026-10-15), none running; mem available 4244 MiB; disk free 63G | OK |
| L.2 vm-095 | `BACKUP OK` (2318802 bytes); `DEPLOY OK: 7e6e33c` (the tip of PR #156: main plus the ACR-0016 compose line); migrations 001-006 already applied; only the worker image changed (recreated); `health 200`; `WRITE GATE CLOSED`; `NO INTERFERENCE` | OK |
| L.3 | from `argus-v18-worker`: `https://cloud.langfuse.com/api/public/health` 200 | OK |
| L.4-L.5 developer | Cloud project created (EU, Hobby); keys typed at a hidden prompt: `400 10010 42 bytes` for both files; never printed | OK |
| L.6 vm-095 | `hosts.env` with the four lines (copy kept as `hosts.env.before-lf3cloud`); worker and agent recreated; `health 200`; `tracing=1`, endpoint host `cloud.langfuse.com`, 2 key files; `NO INTERFERENCE` | OK |
| Keys | read-only call with the worker's key pair to the Cloud project API: authenticated, project id matches | OK |

## What reached Cloud (L.7, read through Cloud's observations API, read-only)

- **Healthy check** (`inc_bd63774111f2`, closed at `detect` as `no_incident`): 3 observations (`argus.investigation`,
  `detect`, `record`).
- **SC-02 crash loop** (`inc_44a2eb17c118` and the runner's `inc_2200c3ceb3c1`): two traces of 11 observations each: the
  `argus.investigation` agent, spans `detect`, `recall`, `investigate` (x2), `act`, `record`, two `llm.decide`
  generations (model `gpt-5.6-luna`, input/output tokens per call) and two `capability` tools (`container.status`,
  `container.logs`, with their evidence ids). Outcome `diagnosed`, class `container_restart_loop`, strategy `model_loop`.
- **Attributes present:** incident id and attempt, class, strategy, outcome, node, capability, status, error category,
  step, `decided_by`, evidence id, the host inventory name (`vm-095`), model, finish reason, token counts, and the
  trace name `argus <incident id>`. All are on the allowlist of ACR-0016 section 3.
- **Absent:** `input` and `output` are empty in all 33 observations seen (the Langfuse UI shows "undefined"): no
  prompt, reply, tool argument or result, evidence body, container or target name, address or credential. This is the
  design (ACR-0013/0016), not a fault; the audit of record stays in Argus (`audit`, `evidence`). The team keeps it
  (option C: no change).
- Cloud's `/api/public/traces` answers 410 Gone in v4; observations v2 was used to read.
- The incident view's "Open in Langfuse" link works (the developer opened it). The Agent page shows only the trace id,
  by design.

## L.8 — Cloud unreachable must not change Argus

The endpoint was pointed at a closed local port and the worker recreated. SC-02 (runner, `inc_8cb269dfbc8e`) gave
**PASS**. The worker logged once `tracing: 1 span(s) dropped (URLError); investigations are not affected`. The
investigation took 7.03 s (6.99 s with Cloud reachable; the runner's 366 s vs 106 s is the Prometheus gate wait); the
incident has 10 audit rows, 4 evidence rows and 13 run events. The endpoint was restored to Cloud and the worker
recreated: `tracing=1`, endpoint host `cloud.langfuse.com`, 2 key files, `health 200`, `WRITE GATE CLOSED`, mem
available 4374 MiB, I/O pressure `some avg10=0.32`, `NO INTERFERENCE`.

## L.C — the self-hosted stack removed (requested by the developer)

Six stopped containers, five volumes, the network, the Langfuse/ClickHouse/MinIO images (postgres and redis images
kept) and `/opt/argus-v18/secrets/langfuse` removed. Nothing remained (`0 0 0`); disk free 63G to 70G; `health 200`;
`tracing=1`; `LAB BASELINE OK`; `NO INTERFERENCE`. `deploy/langfuse/` stays in the repository as the reviewed
alternative for a host with headroom (ACR-0016 section 3).

## Leftovers and notes

- vm-095 runs 7e6e33c, the head of PR #156, deployed before the merge; juanbetancurm merged it as `f7df417`, so the
  commit is in `main`. The next deploy of `main` moves vm-095 to the merge commit.
- `argus-lab-cache` on vm-166 (found stopped in step 02) was not looked at: vm-166 was not changed.
- Hobby allows two users: the team names them. Rollback if needed: `hosts.env.before-lf3cloud` and the two key files
  (block L.R of `code.bash`).
