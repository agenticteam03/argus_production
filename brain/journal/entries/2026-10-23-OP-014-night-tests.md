## 2026-10-23 — OP-014 step 9: mutation run of the WebAuthn second factor and the audit chain; list shapes in the UI contract

Type: tests
Who: conantkd (+ agent, night work)
Context: phase 16 step 3 (#280) added `argus/application/second_factor.py` (WebAuthn, step-up) and ACR-0018's audit hash
chain lives in `argus/domain/audit_chain.py`; neither had been through a mutation run. #291 found that
`tests/test_ui_contract.py` compared a list's shape by its first item only.
Decision / result:
- mutmut 3.3.1 in a `python:3.12-slim` container on `main` `6ee3aa1`, 2 workers, the two modules only, the tests that
  use them (`test_acr0018_webauthn`, `_sessions`, `_authz_matrix`, `_audit_chain`, `test_ui_access`; the Postgres
  ones skipped). 664 mutants: 461 killed, 89 survived, 114 timed out.
- The 114 timeouts, each alone under `MUTANT_UNDER_TEST` with the tests that cover its function (mutmut's own
  selection) and a 600 s limit, 2 at a time: 27 detected, 87 survived, none reached the limit (the slowest took
  157 s: the run had been slow, not hung).
- `tests/test_op014_mutation_second_factor.py` (19 tests) and `tests/test_op014_mutation_audit_chain.py` (2 tests)
  kill 171 of the 176 survivors, each checked under `MUTANT_UNDER_TEST`; both files pass on the original code. No
  code changed. What they pin:
  - **user verification:** a registration or an assertion whose authenticator data has the UV flag clear is
    refused ("User verification is required"); removing `require_user_verification=True` survived in both;
  - **the options sent to the browser:** the relying party's name, a stable user handle per person (the first 16
    bytes of the SHA-256 of the name), 5 minutes, `residentKey` preferred and `userVerification` required, the
    enrolled keys excluded from a new registration and allowed for a login;
  - an invalid ticket is refused when the options are asked for (only the end of the ceremony refused it before);
    a used ticket is refused at the end with its reason; a registration by step-up stores no ticket;
  - each refusal's reason (a library error cut to 200 characters), event, actor and credential or object; the
    audit of a registration (credential, label, count, with or without a ticket), a login, an enrolment ticket
    (person, hours), a step-up issued and used, and a reset (who revoked the keys and the sessions, and why); an
    audit id is `aud_` and 16 hex digits; an actor and a label are cut to 64 characters;
  - the enrolment code (18 random bytes) and the step-up token (32) keep their length; a step-up expires 5
    minutes after it is issued;
  - **the audit chain:** `verify` keeps checking the rows after one inserted outside the store (`break` for
    `continue` survived); the canonical form and the link hash are pinned to fixed values. A change to either (key
    order, separators, how non-ASCII text or a time is written) still verifies the rows written after it, so nothing
    else catches it, but every row already chained on vm-095 would then fail the chain's verification.
- Equivalent (5): `obj or ""` → `obj or "XXXX"` before the object pattern (neither matches, both refused);
  `token_urlsafe(None)` for `token_urlsafe(32)` (Python's default is 32 bytes); `ensure_ascii=None` for `False`
  (both false); `.encode("UTF-8")` for `"utf-8"`; the `ticket_hours=24` default of `SecondFactor` (every caller
  passes `webauthn_enrol_ticket_hours`).
- By module: `audit_chain.py` 47 mutants, 35 detected by the existing tests, 10 by the new ones, 2 equivalent;
  `second_factor.py` 617, 453, 161, 3. No defect found in either module.
- `tests/test_ui_contract.py`: a list's shape now joins every item's (union of the keys of its dicts, union of the
  types that differ), so a key or a type that only a later item has counts. Red seen: the new
  `test_shape_reads_every_item_of_a_list` fails with the first-item shape. The current `contracts/samples/` pass
  unchanged (no protected file touched).
Consequences: OP-014 step 9 covers the phase 16 security code too; the weekly job's floor gains 5 equivalents
(47 in all). Before the run, a mutation copy of the tests must not include the files written from it (here the
timeouts were re-run without them).
References: [OP-014](../../OPEN_PROBLEMS.md) step 9, #280, #291, ACR-0018.

### Test state

`tests/test_op014_mutation_second_factor.py` 19 passed, `tests/test_op014_mutation_audit_chain.py` 2 passed,
`tests/test_ui_contract.py` 4 passed (Docker `python:3.12-slim`); each of the 171 survivors fails the new tests.
