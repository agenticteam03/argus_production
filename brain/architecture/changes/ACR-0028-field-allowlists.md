# ACR-0028 — Field allowlists: a sensitive read keeps only the fields it declares

Settles G-006 of [OP-002](../../OPEN_PROBLEMS.md) (data minimization). Builds on
ACR-0026 (#210), which decides which reads are `READ_ONLY_SENSITIVE`.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | conantkd (+ agent) · 2026-10-21 |
| Accepted by | — |
| Second approval (safety principle only) | **required**: secrets and evidence integrity (what a read may store and show the model) |
| Architecture version | the next free version when applied |
| Task / PR | OP-002 G-006 · `task/ACR-0028-field-allowlists` (proposal); one implementation PR applies it |

## 1. Detect and explain

A read's `values` are, in almost every capability, **the gateway's JSON answer as it came** (`values=d` in
`argus/capabilities/catalog.py`, 34 of 49 results). `Dispatcher.call` (`argus/tooling/dispatch.py:42`) checks the
host (attribution guard), redacts known secret patterns and declared literals (`capabilities/redaction.py`), cuts at
`max_output_bytes`, and stores the rest as evidence. The model sees those values: the runner puts up to 1800
characters of them in each `<evidence>` tag (`argus/orchestration/runner.py:322`).

So **any field a gateway adds reaches the evidence store and the model** unless the redactor happens to recognise its
content. Today the gateways minimise at the source, and do it well (`database.health` never reads the `query` column;
`host.top_*` sends the command name, never its arguments; `container.processes` the same). But that protection lives
on the target hosts, in a different service, with no check on Argus's side: a gateway change, a newer Docker or
PostgreSQL field, or a compromised gateway widens what Argus stores and shows without any Argus change.

Redaction is pattern-based: it masks what looks like a token, a key or a declared literal. It cannot know that a
field like `application_name`, a directory name or an environment block should not be there at all.

## 2. Why the current architecture is insufficient

§12.3 says an implementation "enforces its own timeout and output bounds, and applies redaction before returning";
§5.4 says evidence values are "redacted, bounded". Neither bounds **which fields** a read returns. The library's
G-006 asks for per-source field allowlists. ACR-0026's table promises one for every `READ_ONLY_SENSITIVE` read
("field allowlist and redaction before the model (G-006)"), and nothing implements it.

## 3. Smallest reasonable change

**§12.3, `CapabilitySpec`:** a new field

```python
    allowed_fields: frozenset[str] | None = None   # ACR-0028: the value paths this read may keep; required when sensitive
```

A path is a top-level key (`"lines"`), or a key inside the rows of a list (`"processes[].command"`) or of an object
(`"limits.max_open_files"`). One level of nesting is enough for every read today.

**§12.3, a new rule under "Rules for every capability implementation":**
- **Minimization (ACR-0028).** `Dispatcher.call` keeps only the declared paths of `values`, **before** redaction,
  truncation and storage; anything else is dropped, never stored, never shown. The number and names of the dropped
  keys (never their values) go into the `tool.completed` audit detail, so a gateway that grows a field is visible.
  `model_text` is built by the implementation from the values it reads; it may use only declared fields (a test
  holds this, §4).
- Every `READ_ONLY_SENSITIVE` capability **must** declare `allowed_fields`; the registry refuses one without it
  (startup and a test). A `READ_ONLY_SAFE` capability may declare one; doing so for all reads is a later step.
- A combined capability (§12.7) declares its own fields; its sub-reads are minimized by their own specs when they run
  through `InvokeCapability`.

**§5.4, `EvidenceRecord.values`:** "redacted, bounded" becomes "minimized to the capability's allowed fields
(ACR-0028), redacted, bounded".

**§17.1 (security layers):** one line: "a field allowlist is the first layer of data minimization; redaction is the
second; the gateways' own minimization is the third, outside Argus's control".

**The initial allowlists** (from the gateways' answers on `main`, `services/target/service.py`; row fields in
brackets):

| Capability | Allowed fields |
|---|---|
| `container.logs` | `lines`, `truncated`, `collected_at`, `earlier_matches.counts`, `earlier_matches.lines` |
| `container.detailed_logs` | `lines`, `minutes`, `stream`, `truncated`, `collected_at` |
| `container.search_logs` | `pattern`, `matched`, `lines`, `minutes`, `truncated`, `collected_at` |
| `host.top_cpu`, `host.top_memory` | `by`, `pids_read`, `truncated`, `cpus`, `sample_s`, `collected_at`, `processes[]` (`pid`, `command`, `state`, `rss_mib`, `cpu_percent`, `container_id`, `kernel_thread`) |
| `host.kernel_oom_records` | `window_minutes`, `oom_kill_since_boot`, `source`, `complete`, `records_total`, `by_container[]` (`container_id`, `count`), `records[]` (`time`, `scope`, `container_id`, `command`, `pid`, `anon_rss_mib`), `collected_at` |
| `host.directory_sizes` | `path`, `children[]` (`name`, `bytes`, `entries`, `complete`, `symlink`), `children_read`, `entries_read`, `complete`, `other_filesystems`, `limit_entries`, `limit_seconds`, `collected_at` |
| `host.read_file` | `target`, `path`, `lines`, `lines_returned`, `truncated`, `collected_at` |
| `host.service_config` | `target`, `files[]` (`path`, `text`, `truncated`), `collected_at` |
| `host.journal` | `target`, `unit`, `program`, `source`, `lines`, `window_complete`, `collected_at` |
| `host.process_details` | `target`, `pid`, `ppid`, `name`, `state`, `rss_mib`, `hwm_mib`, `threads`, `open_files`, `limits.max_open_files`, `context_switches`, `container_id`, `collected_at` |
| `database.health` | `ok`, `database`, `max_connections`, `reserved_connections`, `usable_connections`, `client_connections`, `usage_percent`, `monitor_slot_reserved`, `by_state`, `by_client[]` (`application_name`, `role`, `connections`), `longest_transactions[]` (`pid`, `application_name`, `state`, `wait_event_type`, `wait_event`, `age_s`), `lock_waits`, `blocked_sessions`, `collected_at` |
| `analysis.diagnostic_snapshot` | `statuses` |

The implementation PR checks each list against the gateway code once more; the canary test pins it.

**Alternatives considered:**
- A: **trust the gateways' minimization** (today). Rejected: Argus would store whatever a host service sends; the
  protection is in another process, on another host, and nothing on Argus's side would notice a change.
- B: **a deny list** (drop `env`, `cmdline`, `query`…). Rejected: it fails open; a field nobody thought of passes.
- C: **typed answer models per gateway route** (pydantic, `extra="forbid"`). Stronger, but it refuses the whole read
  when a gateway adds a field, which turns a gateway upgrade into an outage of the reads; and it is much more code.
  The allowlist drops the unknown field, keeps the read, and audits the drop. Typed models can come later.
- D: **minimize in each implementation.** Rejected: 13 places to get right, and nothing checks them; one place in
  the dispatcher, with the paths declared beside each spec, is reviewable.

## 4. Consequences

- **Code (the implementation PR):** `allowed_fields` on `CapabilitySpec` and the 13 sensitive specs; the
  minimization in `Dispatcher.call` (and in `InvokeCapability._combined` for a combined read's own values); the dropped
  keys in the audit detail; a startup check that every sensitive spec declares its fields.
- **Tests:**
  - every `READ_ONLY_SENSITIVE` spec declares `allowed_fields` (and the registry refuses one that does not);
  - **a canary test per sensitive read:** the fake gateway answer carries an extra top-level field and an extra row
    field holding a marker string; the marker is in neither the stored values nor `model_text`, and the audit names
    the dropped keys (red first: today the marker is stored);
  - a declared field that the gateway omits is simply absent (no error), so a missing field never fails a read;
  - the existing suites (SC-04 database, T-0019 host verbs, T-0037 docker verbs, ACR-0023 log matches) stay green
    with the allowlists on, which proves the lists are complete.
- **Evaluation:** none expected; the dropped fields are the ones no read uses. The implementation PR runs the
  offline evaluation and states the numbers.
- **Deployment:** the agent image only (vm-095); no gateway change, no migration.
- **Risk:** an allowlist that misses a field the model needs makes a read less useful; the existing suites and the
  evaluation catch it, and the audit shows what was dropped. Adding a field is a reviewed one-line change.
- **How to reverse it:** `allowed_fields = None` on a spec disables minimization for that read (the startup check
  forbids it for a sensitive read, so that is a reviewed change too).
- **Safety principles touched:** secrets (what is stored and shown) and evidence integrity (evidence values are
  minimized before hashing; the hash still covers exactly what is stored). Second approval required.

## 5. Decision

Proposed. To be accepted with a teammate's approval plus a second one for secrets and evidence integrity. Applied in
one implementation PR after ACR-0026 (#210) merges, since it relies on its classes.

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§5.4, §12.3, §17.1), version bumped, changelog line added (with this ACR's link)
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
