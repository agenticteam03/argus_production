## 2026-10-23 — PHASE-16 step 5c: the secrets on vm-095, the scheduler's mounts and the command that checks the digests

Type: code + ops record (the VM got two files; nothing is deployed)
Who: conantkd (+ agent)
Context: steps 5a (#303) and 5b (#311) built the signed daily digest and its OCI sink. The job needs two secrets on vm-095 and
the scheduler needs to be given them, and a person needs a way to prove the digests match the chain.
Decision / result:
- **The secrets are on vm-095** (evidence: `execution/history/PHASE-16/step-05c-prep`): the Ed25519 audit digest key,
  generated there and never printed (its public half and `key_id` `52fe6eb06f4dd3b7` are recorded), and the create-only OCI
  credential (`config` and `key.pem`), copied from the laptop without being printed; the key matches the fingerprint in the
  config. They are in **`/opt/argus-v18/secrets/digest/`**, not in `secrets/agent/` as the first drafts of
  `policies/SECURITY.md` said: the worker mounts all of `secrets/agent/` and neither secret is the worker's.
- **`compose.core.yml`:** the scheduler mounts the key file and the `oci_digest` folder read-only from there, and no other
  service mounts the folder (a test per service). `ARGUS_AUDIT_DIGEST_SINK` comes from `hosts.env` and is empty by default.
  The scheduler's `mem_limit` goes from 160m to 256m: measured, importing the OCI SDK adds about 19 MB to its start (74 to
  93 MB), and the job reads the whole chain into memory, as the daily chain check already does.
- **`argus audit check-digests <files or folders> --public-key <pem>`** reads the digests (downloaded from the bucket by someone
  whose credential can read them: the shipping credential cannot) and reports a signature that does not verify, a row the
  chain no longer holds, a changed hash, a wrong row count, a digest twice for a day and a gap in the days. A file that is not
  a digest is named; finding nothing to check is a problem, not a pass.
- **`policies/NETWORK.md`** names the scheduler's one outbound destination, OCI Object Storage; **`policies/SECURITY.md`** now
  says where the two secrets live. `audit_digest` stays **`enabled: false`**.
- The first attempt to generate the key from the agent's session was refused by the permission classifier (a remote write), so
  conantkd ran the blocks; two bugs of the prepared blocks showed up and were fixed (the VM's `install -o` and, earlier,
  `brain.py start` hanging on the GitHub verification of `main`: `BRAIN_NO_GH=1` skips it).
Consequences: after #302, #303 and #311 merge and this one, the deploy needs both leases and a block: the repository to
`main`, `ARGUS_AUDIT_DIGEST_SINK=oci:<namespace>/<bucket>` in `hosts.env`, the scheduler recreated, one manual run of the job
checked in the bucket and with `check-digests`, and only then `audit_digest: enabled: true`. Until the schedule is on, nothing
leaves vm-095.
References: [evidence](../../execution/history/PHASE-16/step-05c-prep/evidence.md),
[ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md) §5, §6; steps 5a and 5b.

### Test state

Red seen: `tests/test_phase16_step5c_check.py` failed against the 5b tree (no `check_digest_files`, no digest mounts, no
sink variable, the old memory limit). Green: that file (the series checked as a whole: clean, a single file, an edited digest,
another key, a missing day, a rewritten chain, a file that is not a digest, nothing to check; the compose file: only the
scheduler mounts the digest folder, read-only, never `secrets/agent/`, the sink variable, the memory limit) and the updated
`tests/test_compose_split.py`.

### Next step

A teammate reviews, after #302, #303 and #311 are merged (this branch contains them). Then the deploy of step 5c, with both
leases.
