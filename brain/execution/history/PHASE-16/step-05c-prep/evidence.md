# PHASE-16 step 05c-prep — evidence: the audit digest key and the OCI credential on vm-095 (2026-10-23 UTC, conantkd)

Goal: ACR-0018 step 5. The signed daily digest needs two secrets on vm-095 before the scheduler is given them: the Ed25519
key that signs the digests and the create-only OCI credential that ships them. Run by conantkd on vm-095 with the lease of
session `6bed2b5eda93` (vm-095 only). Commands: [`code.bash`](code.bash). Sanitized: no private key and no value of the
credential; what is recorded about the key is public.

Before the blocks, the agent claimed the lease and wrote the session marker (`SESSION OK`; `commit=77c4524…`, `ref=77c4524`,
`LAB BASELINE OK`; `health HTTP 200`; `nonint-check before` saved, 54 lines) and listed the secrets folder (names, modes,
owners only). Its attempt to generate the key was refused by the permission classifier (a remote write), so the blocks were
run by conantkd.

| Block | Observed | Result |
|---|---|---|
| KE.1 | `audit digest key generated`; the file `audit_digest_ed25519_key`, mode `400`, 119 bytes; `ED25519 Public-Key:`; the public key and `key_id` below | PASS |
| KE.2 (first run) | `install: invalid user: '10010'` at the first step; the clean-up branch shredded both staged files on the VM; nothing was installed | FAIL (4 of 5) |
| KE.2 (fixed) | the config (the `[ARGUS_DIGEST]` profile renamed `[DEFAULT]`) and the private key copied and installed; the staged files shredded | PASS (5 of 5) |
| KE.3 | `audit_digest_ed25519_key 400 10010:10010 119`, `oci_digest/config 400 10010:10010 309`, `oci_digest/key.pem 400 10010:10010 1715`; the config names `fingerprint key_file region tenancy user` (values not shown); header `[DEFAULT]`; **`the key matches the fingerprint in the config`**; `NO INTERFERENCE: non-Argus objects unchanged` | PASS |
| KE.4 | `Lease released on vm-095.` | PASS (2 of 2) |

## The public half of the audit digest key (public: the digests are checked with it)

```
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA/C/XhFNvq3nCwST8GgSZfg8T+E8xQZe6GJH7Jgcq0HM=
-----END PUBLIC KEY-----
```

`key_id` `52fe6eb06f4dd3b7` (the first 16 hex digits of the SHA-256 of the 32 raw bytes of the key). The agent recomputed it
from the public key above, outside the VM: the same value, and the DER is the expected 44 bytes. Every shipped digest carries
this `key_id`.

## Notes

1. **A folder of their own.** Both secrets are in `/opt/argus-v18/secrets/digest/`, not in `secrets/agent/`: the worker
   container mounts all of `secrets/agent/`, and neither secret is the worker's. The files are `0400`, owned by uid 10010 (the
   image's `argus` user, as the other secrets); the OCI folder is `0500`. Nothing mounts the new folder yet, so no container
   changed and nothing was deployed.
2. **The first KE.2 run failed on the VM's `install -o 10010`:** that coreutils refuses a user id that has no name there. The
   owner is now set with `chown` after `install`. The failed run left nothing behind (its clean-up shredded the staged files).
3. `stat` on the VM prints the owner of the key as `UNKNOWN:UNKNOWN` for the same reason; the numeric `10010:10010` is in KE.3.
4. The `key.pem` fingerprint equals the one in the config, which is the one OCI shows for the API key of the service user whose
   permissions were proved by hand the same day.
