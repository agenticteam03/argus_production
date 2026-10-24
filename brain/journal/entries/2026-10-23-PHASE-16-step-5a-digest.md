## 2026-10-23 — PHASE-16 step 5a: the signed daily digest of the audit chain (job, signature, local sink)

Type: code (offline; nothing deployed)
Who: conantkd (+ agent)
Context: ACR-0018 §3 asks for a signed daily digest of the audit chain, shipped off the VMs, so that someone with `sudo`
who rewrites the whole chain, hashes included, cannot also rewrite what was shipped. The store is now decided (OCI
Object Storage; a locked retention rule without versioning and a create-only credential: ACR-0018 §5, 2026-10-23), and
the bucket was created and its permissions proved by hand on 2026-10-23 (create works; overwrite and delete are
refused; the retention rule refuses a modification). Step 5 is split: 5a the digest and the job, 5b the OCI sink,
5c the key on vm-095 and the schedule turned on.
Decision / result:
- `domain/audit_digest.py` (pure): the digest of a closed UTC day is the last chained row written before the first row
  dated after that day, its hash, how many rows the chain holds up to it and how many were dated that day. A quiet day
  repeats the previous last row, so a gap in the sequence is visible; a row dated out of order cannot move an earlier
  day; rows from before the chain are not digested. Signed with Ed25519 over the canonical JSON (deterministic: the same
  digest gives the same bytes, so putting it again is recognised). `check_against_chain` compares a shipped digest with
  the chain as it stands (a different hash, a missing row, a wrong row count).
- `infrastructure/audit_digest.py` (`AuditDigestJob`): verifies the whole chain first and signs nothing if it is broken
  (a digest of a rewritten chain would vouch for it). Then, for each closed day, puts the object once under
  `audit-digest/<year>/<day>.json`. Every outcome is a `security.audit_digest_*` audit event (`shipped`, `failed` with
  the error class only, `conflict`, `skipped`, `unconfigured`); a failure stops at that day and the next run catches up;
  a different object under the same name is reported and never overwritten.
- `adapters/outbound/digest_sinks.py`: `LocalDirSink` creates exclusively and says `off_host = False`, so the events and
  the log say these digests do not protect the chain. The sink comes from `ARGUS_AUDIT_DIGEST_SINK` (`dir:<path>`); the
  OCI sink is 5b.
- `audit_digest` in `deploy/scheduler/schedules.yaml`, **off**; enabled without the key or the sink it records
  `security.audit_digest_unconfigured` and ships nothing. The key is the secret `audit_digest_ed25519_key` (`wiring`'s
  Ed25519 loader now takes the secret's name).
- ARCHITECTURE keeps the digest at 1.8.32 and current main at 1.8.33; ACR-0018 §6 and `policies/SECURITY.md` record the built step.
Consequences: nothing changes on the VMs. Next, 5b: the OCI sink (a new dependency and the credential's mount in a
compose file, both reviewed); 5c: generate the key on vm-095, copy the create-only credential without printing it, turn
the schedule on, and a command to check shipped digests against the chain. The alert on `security.audit_digest_failed`,
`_conflict` and `security.audit_chain_broken` waits for the team's alert route.
References: [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md) §3, §5, §6;
[PHASE-16](../../tasks/current/PHASE-16-operator-access.md).

### Test state

Red seen: `tests/test_phase16_step5_digest.py` failed to import `argus.domain.audit_digest` before the code existed.
Green: 21 passed (the digest of a day, quiet days, out-of-order rows, rows before the chain, signing and tampering, the
check against a rewritten chain, the job: once per day, catch-up, a broken chain, a failing sink, a conflicting object,
no key or no sink, the local sink and its path rules, the schedule section, the scheduler loop, the key loader, the
sink setting).

- Main alignment on 2026-10-24: merged `origin/main` at `c8d8594`. The manual `ARCHITECTURE.md` resolution uses the version-line reconciler: it keeps the digest row at 1.8.32, ACR-0024 at 1.8.33, and preserves the complete version history. The only header normalization was the parenthesis formatting on the shared 1.8.31 entry. ACR-0018 now states that OCI uses a locked retention rule without versioning, and its `Not yet` list no longer names `policies/SECURITY.md`, which this step updates.
- Post-merge focused tests: **136 passed** (`test_phase16_step5_digest`, evaluation, T-0049 prior incidents, T-0047 hypothesis checks). Ruff, `git diff --check`, Brain lint/audit, and the version-line helper passed.
- GitHub CI for the updated head is pending after push; the previous head's test and frontend checks were green.

### Next step

Request a fresh teammate review of the updated, protected architecture paths and wait for CI to pass. After review and merge, retain the task branch and continue with step 5b, the OCI sink.
