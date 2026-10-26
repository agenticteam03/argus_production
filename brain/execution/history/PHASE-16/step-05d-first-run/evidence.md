# PHASE-16 step 05d — evidence: the audit digest's first checked run (2026-10-26 UTC, conantkd)

Goal: ACR-0018 step 5's last part on vm-095: set the OCI sink, ship the digests of the closed days once by hand, check
them, then turn the daily job on. Run by conantkd's agent over ssh at conantkd's request, both leases (session
`13d7ed00`). Commands: [`code.bash`](code.bash). Sanitized: the bucket's namespace and name, keys and credentials are
not written here (the sink lives only in vm-095's `hosts.env`).

| Block | Observed | Result |
|---|---|---|
| O.1 | `hosts.env` copied to `.bak-before-digest-sink`; `sink lines in hosts.env: 1`; scheduler `Recreated`, `Started`, `running restarts=0`; `sink set in scheduler: yes` | OK |
| O.2 | the public half of the audit digest key derived in the scheduler (3 PEM lines) and kept at `/opt/argus-v18/audit-digest-public.pem` (outside the checkout; public) | OK |
| O.3 | `run_once: shipped 5 digest(s), 0 conflict(s)`: `audit-digest/2026/2026-10-21.json` to `2026-10-25.json`, five `security.audit_digest_shipped` audit rows | OK |
| After O.3 | `AUDIT CHAIN OK: 311 rows chained`; scheduler error lines 0 | OK |
| From the laptop | the service credential lists the five objects but its reads are refused (`404 BucketNotFound`, OCI's answer to an unauthorized read): create and inspect only, as designed | OK |
| O.4 (read-only) | for each day, the object's stored SHA-256 (HEAD metadata) **equals** the chain's signed digest rebuilt on vm-095; the signature verifies; 0 chain problems; series problems 0: **`VERIFIED 5/5`** | OK |

## Notes

1. `argus audit check-digests` on downloaded files needs a credential that can read the bucket (an administrator's);
   none is configured on the laptop. O.4 checks the same thing through the stored hash: the bytes in the bucket are
   exactly the signed digests the chain produces today.
2. The bucket's retention is one year (ACR-0018 §5). Whether the retention rule is locked is the bucket administrator's
   step in the OCI console.
3. Next: `audit_digest: enabled: true` (this PR), applied by checking out the merge on vm-095 and restarting the
   scheduler; the next run ships 2026-10-26 after that day closes.
