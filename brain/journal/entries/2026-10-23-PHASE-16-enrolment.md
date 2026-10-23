## 2026-10-23 — PHASE-16 step 3: the first-credential tickets issued on vm-095

Type: ops record
Who: conantkd (+ agent)
Context: WebAuthn was deployed on 2026-10-22 (DEPLOY-77c4524, migration 013) with no key enrolled. D4 makes the first
credential of each person depend on a one-time code from another administrator, and D3 asks for two credentials per
privileged person.
Decision / result:
- conantkd issued the tickets for `juanbetancurm` and `juanes6554` on vm-095 (lease of vm-095 only, `NO INTERFERENCE`,
  lease released). The codes went to each person privately; they appear in no record. The audit shows two
  `security.webauthn_enrol_allowed` rows.
- The same day a read-only check of the database on vm-095 (step 03b) showed the keys: `conantkd` 2, `juanes6554` 2,
  `juanbetancurm` 1. The check's verdict is `STOP`, on purpose (D3 asks for two); `NO INTERFERENCE`, lease released.
- A bug in the prepared block was found and fixed on the way: a "placeholder still there" guard compared against the
  text the person had just filled in. It now looks for the placeholder's stem. See the evidence, note 1.
Consequences: a privileged permission is effective only for a login completed with a key **and** two registered keys
(ARCHITECTURE §17.3): today that is `conantkd` and `juanes6554`; `juanbetancurm` needs his second. Nothing privileged
exists yet, so nothing is blocked. Phase 16 still lacks the deployment of the
private path (#298), the signed daily digest off the VMs (steps 5a to 5c) and the exit proof (step 6).
References: [evidence](../../execution/history/PHASE-16/step-03-enrolment/evidence.md),
[keys check](../../execution/history/PHASE-16/step-03b-keys-check/evidence.md), ACR-0018 D3 and D4, #280, #284.

### Test state

Documentation only. `brain.py lint` and `brain.py audit` clean.

### Next step

`juanbetancurm` registers his second key and the check (step 03b, KY.1) is repeated until it passes. Then deploy #298
(the private path), and the digest's OCI sink (step 5b).
