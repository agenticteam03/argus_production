## 2026-10-14 — AFTER-MERGE: both VMs on main; the public edge's 502 after an agent recreate, fixed

Type: deployment + fix
Who: conantkd (+ agent)
Context: #141, #144–#147 merged.
- vm-166 was on `main` `ad72617`.
- vm-095 was on the T-0016 branch (the public UI edge).

Decision / result:
- **Both VMs on `main` `ccc810e`**:
  - the read gateway with #141's `error` pattern;
  - the agent with D-003 (`dependency_unavailable` and `nginx_upstream_failure` on `baseline`): 20/20, 55/55,
    WRITE GATE CLOSED;
  - NO INTERFERENCE on both.
- **Found:** the public UI's API answered **502** after the agent was recreated, because Nginx had resolved the name
  once at start. Restored by a reload within about 2 minutes.
- **Fixed:** the upstream re-resolves through Docker's DNS (`resolver 127.0.0.11`, `server … resolve`), with a test
  on real Nginx (red, then green). Deployed on vm-095: a later agent recreate without a reload kept the API
  answering. Docker happened to reuse the address that time, so the test is the proof.

Consequences: every deployment of the agent recreates it, so without the fix the public UI would have broken on
each AFTER-MERGE.
References: [evidence](../../execution/history/AFTER-MERGE-main-2026-10-14/step-01/evidence.md).

### Test state

`tests/test_acr0011_ui_edge.py`: 25 (1 new, red seen).

### Next step

vm-095 back to `main` (checkout only) after this PR's merge; a person's browser login on the public UI.
