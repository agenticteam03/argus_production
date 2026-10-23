# DEPLOY-77c4524 step 01 — evidence: vm-095 to main 77c4524, migration 013 (2026-10-22 UTC, conantkd)

Goal: run on vm-095 PHASE-16 step 3 (#280: migration 013, the WebAuthn second factor and the step-up token; #284: the
UI's security keys page) and the Bearer redaction fix (#278). vm-166 does not change. Run by conantkd's agent over ssh
at conantkd's request ("corre tú el deploy", with permission given), lease `DEPLOY-77c4524` on both VMs (session
`3f6be5c3`). Commands: [`code.bash`](code.bash). Sanitized: no name, address, key or code.

| Block | Observed | Result |
|---|---|---|
| D.1 vm-166 | marker; `nonint-check before` saved (63 lines) | OK |
| D.2 vm-095 | `SESSION OK`; `ref=afb72e8`, `LAB BASELINE OK`; `before` saved (54 lines); `BACKUP OK` (2435158 bytes, 20:39Z); **`VERIFY OK: 18 tables, 32976 rows match`**. First `deploy.sh`: `DEPLOY STOP: local modifications` (see note 1); after moving the file out: `DEPLOY OK: 77c45243de62 (77c4524)`; **`+ 013_webauthn applied`**, schema 001 to 013 | OK |
| D.3 vm-095 | the UI's name read from its env file (not printed); `hosts.env WebAuthn lines: 2` (a `.bak-before-webauthn` copy kept); agent, worker, scheduler `Recreated`, `Started`; `health 200`; `deploy recorded: 77c4524 (main) on vm-095 by conantkd` | OK |
| D.4 vm-095 | UI `Recreated`, `Started`; `running health=healthy restarts=0`; the bundle holds `/api/v1/auth/webauthn`, `register/options`, `manage_second_factor`, "Security keys" (see note 2) | OK |
| D.5 vm-095 | three `running restarts=0`; error lines 0, 0, 0 (the scheduler's `argus_probe_error` queries excluded); **`WebAuthn relying party set`**; the edge proxies a ceremony (401 without a token); `/me` 401; **`49/49 database checks passed`**; `AUDIT CHAIN OK: 137 rows chained`; **`Bearer fix live`**; `ref=77c4524`, `LAB BASELINE OK` | OK |
| D.6 / D.7 | `NO INTERFERENCE` on vm-095 and vm-166; leases released. Juan's enrolment ticket is not issued here: its one-time code must go to Juan, never through the agent's output | OK |
| From the laptop | through the public name: a ceremony 401, the credential list 401, `/account/security` 200 | OK |

## Notes

1. **`deploy.sh` stopped on an untracked file in the checkout:** `deploy/ui/vm-095.env.bak-ip`, the backup the
   D2-ui-domain commands (given by the agent) told the developer to write next to `vm-095.env`, inside
   `/opt/argus-v18/app`. `deploy.sh` refuses any local change, as it should. The file was moved to
   `/opt/argus-v18/ui-vm-095.env.bak-ip` (root, 0600) and the deploy re-run. Lesson: a backup of a VM-local file goes
   outside the checkout.
2. **The bundle check of code.bash D.4 looked for `auth/webauthn/register/options` in one string;** the adapter builds
   the path from two parts, so it counted 0 although the page is there. The four pieces were found one by one.
3. **Next:** Juan's ticket (conantkd: `argus webauthn allow-enrol <Juan> --as conantkd` on vm-095, the code given
   privately) and conantkd's from Juan; then each registers two keys at `/account/security`.
4. **Rollback:** `deploy.sh afb72e8 --as conantkd` and the compose commands of D.3 and D.4; migration 013 stays;
   `hosts.env` from `hosts.env.bak-before-webauthn`.
