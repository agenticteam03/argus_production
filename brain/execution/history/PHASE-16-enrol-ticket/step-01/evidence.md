# PHASE-16-enrol-ticket — step 01 evidence

Run by `juanes6554` on 2026-10-23 with the vm-095 lease (session `7175903bfff6`).

| Block | Result | Source |
|---|---|---|
| E.1 marker, `nonint-check before`, principals | ran; reported OK | developer's report |
| E.2 `argus webauthn allow-enrol conantkd --as juanes6554` (inside `argus-v18-agent`) | ticket issued; the one-time code given to conantkd privately, never recorded | developer's report |
| E.3 `audit verify`, `nonint-check after` | reported OK (NO INTERFERENCE) | developer's report |
| E.4 `brain.py release` | lease released | `brain.py status`: "Lease vm-095: released by juanes6554 · task PHASE-16-enrol-ticket" |

**Limitation:** the terminal output was not kept, so E.1–E.3 rest on the developer's word, not on pasted lines. The
ticket's own trace is on vm-095: the audit record `security.webauthn_enrol_allowed` (by juanes6554, for conantkd),
readable by the next lease holder.

**Lesson:** the first time `argus` was typed directly on the VM it was "not found" (the CLI lives in the
`argus-v18-agent` container: `sudo docker exec argus-v18-agent argus ...`); `apt install argus-server` is an unrelated
package and must not be installed.

**Next:** conantkd issues juanes6554's ticket the same way; each then registers two keys at `/account/security`.
