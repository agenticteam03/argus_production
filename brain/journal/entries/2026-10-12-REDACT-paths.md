## 2026-10-12 — The redactor masks secrets, not file paths (REDACT-paths)

Type: fix
Who: conantkd (+ agent)
Context: T-0019 batch 3b step 08: `inspect_service_config` on vm-095 showed nginx's configuration path as
`/[REDACTED HIGH-ENTROPY].conf`; the high-entropy rule (40+ characters of `[A-Za-z0-9+/_=-]`) took
`opt/argus-v18/app/deploy/lab/nginx/default` for a token.
Decision / result: a high-entropy match that is a run of lower-case path segments (at most 32 characters each, no `+`
or `=`, optionally after `key=`) is left as is; everything else is masked as before. On all 853 fixture strings of the
55 evaluation cases the new redactor gives exactly the old output; tokens (mixed case, base64, long hex) stay masked.
Consequences: paths in observations (configuration files, mounts, logs) reach the model readable.
References: `argus/capabilities/redaction.py`, `tests/test_redaction_paths.py`.

### Test state

`tests/test_redaction_paths.py`: 8 tests (red seen 3/3 on the paths); the core and knowledge tests that use the
redactor pass.

### Next step

None.
