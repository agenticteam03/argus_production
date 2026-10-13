## 2026-10-13 — The redactor keeps only the paths Argus declared readable (REDACT-declared-paths)

Type: fix
Who: juanbetancurm (+ agent)
Context: #107 (REDACT-paths) left every run of lower-case path segments unmasked, so the nginx configuration path of
T-0019 3b reached the model readable. The review of #107 found that it also let lower-case secrets in URL paths
through (an API key in `/api/v1/keys/<32 hex>`, a webhook URL, a presigned download path), which `main` before #107
masked. #107 was merged on the condition that this is fixed before `main` is deployed to the VMs.
Decision / result: `Redactor(declared=...)` sets aside only the paths Argus itself declared before the high-entropy
rule and puts them back after it: the inspection policy's `service_config` and `files` entries and the inventory's
mounts (as directories; `/` declares nothing), from `wiring.declared_paths`, in both places the redactor is built
(`build`, `tools_dispatcher`). Every other path is masked as before #107. On the 899 fixture strings of the
evaluation cases, the new redactor differs from the one before #107 only on the 6 strings that are the declared nginx
`default.conf` path.
Consequences: the nginx configuration path stays readable for the model; a secret in any undeclared path is masked
again. Declaring a new `files` entry in the policy also makes its path readable.
References: `argus/capabilities/redaction.py`, `argus/infrastructure/wiring.py`, `tests/test_redaction_paths.py`.

### Test state

`tests/test_redaction_paths.py`: 18 tests (red seen: the three URL-path secrets unmasked on `main`, and no
`declared_paths`).

### Next step

AFTER-MERGE of both VMs to `main` once this and #109 are merged.
