## 2026-10-23 — PHASE-16 step 5b: the OCI Object Storage sink of the audit digests

Type: code (offline; nothing deployed)
Who: conantkd (+ agent)
Context: step 5a built the signed daily digest with a local sink. The store is OCI Object Storage; its bucket, policy
(`OBJECT_CREATE` and `OBJECT_INSPECT` only) and retention rule were created and proved by hand on 2026-10-23 (create
works; overwrite and delete are refused; the retention rule refuses a modification). This step adds the sink that talks
to it.
Decision / result:
- `OciObjectSink` creates a digest once with `If-None-Match: *`, a `Content-MD5` check and the digest's SHA-256 as the
  object's metadata (`opc-meta-sha256`). The credential cannot read a body, so when the service says no (a precondition,
  or a retention rule on an existing object: the status is not the same in both) the sink does a HEAD: an object that is
  there is compared by that metadata (`exists_same` or `exists_different`); anything else is the refusal. It does not rely
  on one status code, because the SDK documentation does not give the one for a failed precondition.
- `DigestSinkError` carries only an HTTP status and the service's error code. The service's message holds request ids and
  the names of the namespace and bucket, so the job's `security.audit_digest_failed` event records the class and that
  short reason, never the message.
- `ARGUS_AUDIT_DIGEST_SINK=oci:<namespace>/<bucket>`; the credential is `oci_digest/config` (a profile `[DEFAULT]`) and
  `oci_digest/key.pem` under the secrets folder. The config's `key_file` is the path on the person's laptop; the key
  beside the config wins. Found by a test: `oci.config.from_file` checks that path before it can be replaced, so the
  profile is read directly.
- Dependency `oci==2.189.0`, the version the CLI used for the by-hand proof (`pip check` clean). The `oci` import is lazy:
  nothing else loads it.
- An opt-in test (`ARGUS_TEST_OCI_CONFIG`, `ARGUS_TEST_OCI_BUCKET`) runs create, same bytes and different bytes against a
  real bucket; each run leaves one small object under `selftest/`.
- **Left for 5c, on purpose:** the compose mounts of the digest key and the credential (a protected path; a bind mount of
  a file that does not exist yet would break the scheduler's start on the next deploy), the key and the credential on
  vm-095, the egress line in `policies/NETWORK.md`, the schedule turned on, and a command to check shipped digests.
Consequences: the digest can reach the bucket as soon as 5c puts the key and the credential on vm-095. The lock of the
retention rule waits until the job has run for a while; it is irreversible after its 14-day delay.
References: [ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md) §5, §6;
[PHASE-16](../../tasks/current/PHASE-16-operator-access.md); step 5a.

### Test state

Red seen: the new tests failed to import `DigestSinkError` on the 5a tree. Green: `tests/test_phase16_step5b_oci_sink.py`
(the sink against a fake client: created once, the same digest, another object, a retention refusal, a refusal with
nothing behind it, a failing HEAD, a transport error; the job's event; the setting; the key beside the config) and
`tests/test_phase16_step5_digest.py` pass. **Against the real bucket:** the opt-in test passed on conantkd's laptop
(2026-10-23, `1 passed`): a new name was created, the same bytes were recognised (`exists_same`) and other bytes under
the same name were recognised (`exists_different`), through the create-and-inspect credential. It left one object under
`selftest/`, kept by the retention rule until the rule is removed.

### Next step

A teammate reviews (it touches `brain/architecture/` and `brain/policies/`). Then 5c.
