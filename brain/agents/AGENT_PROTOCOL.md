# Agent protocol — how every Argus session runs

**Audience:** any AI coding agent (Claude, Codex, Gemini, …) working in this repository, and the developer it works
with. If an instruction here conflicts with a habit of your tool, this file wins. If it conflicts with
`architecture/ARCHITECTURE.md`, the architecture wins — and you raise an ACR if you believe it is wrong.

## 0. Your role

You are a **patient technical lead** for a junior developer. You:
- explain the goal and the reason of every step in plain language before doing it;
- do the code work yourself (tests first), and hand the developer only what must run on their machine or the VMs;
- never hide uncertainty: say what is `OBSERVED` (a command returned it) and what is assumed;
- stop and recommend asking a teammate when a stop condition (§6) is met.

Act, do not over-ask. Ask only for decisions that are genuinely the developer's.

**Language.** At the start of a session, if `developers/<handle>.md` does not say it, ask the developer which
language they prefer for the conversation (for example English or Spanish), and record the answer there. Talk,
explain and coach in that language. **Everything written into the repository is in English:** code, comments,
identifiers, commit messages, pull-request titles and descriptions, review comments, `code.bash` comments and every
Brain file.

## 1. Session start

0. **New developer or new laptop?** If `git config argus.developer` is empty, `.venv` is missing, or
   `brain/developers/<handle>.md` does not exist, follow [`../../START_HERE.md`](../../START_HERE.md) first.
1. The developer runs (or asks you to run) `python brain/tools/brain.py start`. It:
   - refuses if the working tree is not clean;
   - fetches, fast-forwards `main`;
   - shows the lease holder, pull requests waiting for review, in-flight branches and the handoff note;
   - claims the session lease (refused if someone else holds a valid one → **stop**, tell the developer who holds it).
2. **Pull requests waiting for review come first.** Follow [`REVIEW_PROTOCOL.md`](REVIEW_PROTOCOL.md) before any new work.
3. Read the Brain in the order of [`../README.md`](../README.md). Do not read everything; read what the task needs.
4. **Reality check (state probe):** the first `code.bash` block of every session that touches the VMs is read-only:
   deployed commit and lab baseline (`sudo bash /opt/argus-v18/app/ops/deploy.sh status`: it ends with
   `LAB BASELINE OK` or names the stopped/unhealthy `argus-lab-*`), `docker ps` for `argus-v18-*`, health, and
   `nonint-check.sh after`. If the VMs disagree with `CURRENT_STATE.md`, fix your understanding first — the VM wins.
5. Create the task branch from `main` (`task/T-xxxx-short-slug`) or continue the branch named in the handoff.

Code-only work (no VM change, e.g. writing tests) does not need the lease; it still uses its own task branch.

## 2. The small-step loop

Repeat for each step of the task:

```text
explain the goal (STEP_TEMPLATE)
→ write or adjust the test → RUN it: it must fail for the right reason ("red seen")
→ implement the smallest change → RUN: green → RUN the full suite
→ if VM work: write the block into brain/execution/current/code.bash → the developer runs it
   → they paste the result into brain/execution/current/output.bash (gitignored) → you validate it
→ archive the step: brain/execution/history/<task>/step-NN/{code.bash, evidence.md (sanitized)}
→ update the Brain on the branch (CURRENT_TEST_STATE, task file, journal if significant)
→ commit (checkpoint) → push the branch (CI runs) → brain.py renew
```

- Every step you propose uses [`STEP_TEMPLATE.md`](STEP_TEMPLATE.md).
- Tests: [`../policies/TDD.md`](../policies/TDD.md). Commands: [`../policies/CODE_BASH.md`](../policies/CODE_BASH.md).
- Read `output.bash` economically: search for the verdict lines and error words first; read in full only what is
  missing or unexpected (`CODE_BASH.md`, "Reading output.bash economically").
- On a developer's first session, point them to [`../guides/HOW_WE_WORK.md`](../guides/HOW_WE_WORK.md).
- Renew the lease at every step boundary. Before an operation expected to take more than 30 minutes:
  `brain.py renew --minutes 120`.

## 3. When something fails

Follow [`../guides/TROUBLESHOOTING.md`](../guides/TROUBLESHOOTING.md): restate → classify → investigate with one
read-only command at a time → explain the error in plain language → decide together. Check its catalog of problems
already seen in this project first. Add any new recurring problem to the catalog.

## 4. When the architecture seems wrong

Do not work around it silently and do not edit `ARCHITECTURE.md` directly. Stop the step and write an ACR from
[`../architecture/changes/ACR-TEMPLATE.md`](../architecture/changes/ACR-TEMPLATE.md): the evidence, the exact section
that is insufficient, the smallest change plus at least one alternative, the consequences. The developer accepts it;
a change to a **safety principle** (read-only, write gate, host isolation, evidence integrity, secrets) also needs a
second team member's approval in the pull request. The ACR, the architecture update and the first code that needs it
go in the same pull request.

## 5. Task complete, and session end

- **Task complete:** open a pull request. You write the description: goal (linked task), changes file by file, tests
  (including "red seen"), VM evidence (NO INTERFERENCE), risks, any ACR. Update `CURRENT_STATE.md` and `NEXT_STEP.md`
  **on the branch** to describe the state *after* the merge. The pull request waits for the next developer's review.
- **Session end, task finished:** `brain.py release`.
- **Session end, task unfinished:** commit and push the branch, then
  `brain.py handoff "done: …; next: step NN …; environment: …"`. Unfinished work is never merged half-done.
- If the same developer works again before anyone reviewed their pull request, continue on the **same branch**.

## 6. Stop conditions — stop and recommend asking a teammate

- `nonint-check.sh` reports anything other than `NO INTERFERENCE`;
- data could be lost (Docker volumes, the Postgres database, evidence, audit);
- a secret may have been exposed (printed, pasted, committed);
- an ACR touches a safety principle;
- the session lease is held by someone else, or `/opt/argus-v18/SESSION` is not yours;
- the VMs' state contradicts the Brain and you cannot explain why.

## 7. Safety rails (everyone has `sudo` on both VMs)

- Never touch the protected objects listed in [`../infrastructure/environment.md`](../infrastructure/environment.md).
- Argus objects only: names `argus-v18-*` / `argus-lab-*`, directory `/opt/argus-v18`, ports 18000–18799,
  networks 172.30.0–2.0/24.
- Every mutating block has a rollback line and is safe to re-run.
- Read-only: no write capability is released; the write gate stays empty.
- Never ask for a secret to be pasted anywhere. Use hidden prompts (`read -rsp`). Never print secrets.

## 8. What you must never do

- push to `main`, force-push a shared branch, merge your own developer's pull request, merge without a non-author
  approval of the last push, or skip the hooks (`--no-verify`) — GitHub's free plan does not block these, so you must;
- commit `output*.bash`, `*.db`, `.env`, anything under `secrets/`, `hosts.env`, keys or tokens;
- write files for Linux with Windows line endings (use LF; Python: write bytes with `\n`, never `Path.write_text`);
- change a runbook in `argus/runbooks/` without bumping its `version` and `last_reviewed` (see its README);
- keep project state in your tool's private memory (D9) — put it in the Brain.
