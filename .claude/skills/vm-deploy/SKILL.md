---
name: vm-deploy
description: >-
  Print the ordered checklist for deploying one Argus commit on vm-095 or
  vm-166 (leases, SESSION, nonint-check, backup, migration before the image,
  rebuild, deploy record, db check, rollback). Manual invocation only; it
  never connects to a VM or runs a deploy.
disable-model-invocation: true
---

# Deploy checklist for an Argus VM

Read `brain/policies/PARALLEL_LANES.md` (leases), `brain/policies/CODE_BASH.md`
(VM blocks) and the last `brain/execution/history/DEPLOY-*` record first; they
win over this skill. Deploys are the integration owner's lane (`conantkd` in
`PARALLEL_LANES.md`): another developer deploys only when asked.

This skill **prints a list**. It never connects to a VM, runs `docker`, writes
`hosts.env` or holds a lease, and it grants no permission to deploy.

1. Find what the VM runs now: `deploy.sh status` in the last deploy record, or
   a read-only block under the lease. That commit is also the rollback target.
2. From the repository root:
   `python .claude/skills/vm-deploy/scripts/deploy_checklist.py --target vm-095 --from <deployed> --to <commit>`
   It reads only `git diff` between the two commits and prints the steps the
   changed paths need, in order:
   - the leases (both for an agent change on vm-095);
   - the SESSION marker as every VM block's first line, `deploy.sh status`, `nonint-check.sh before`;
   - `db-backup.sh` before any agent or database change;
   - `deploy.sh <sha>`;
   - every new secret file a compose file mounts, created on that VM before any `up`;
   - every new `${ARGUS_*}` the compose file reads, in `hosts.env` before any `up`;
   - `db-migrate.sh` **before** the new image, naming each new migration;
   - the rebuild of what changed (agent, worker and scheduler; the UI; `deploy/target` and
     `deploy/monitoring` on both VMs with that host's overlay; vm-166's lab services);
   - `argus deploy record`, `argus db check`;
   - `deploy.sh status`, `nonint-check.sh after`, the release and the `DEPLOY-<sha>` record;
   - the rollback;
   - last, any `deploy/` path it maps to no step ("not covered"): check those by hand.
3. Turn the list into blocks with `code-bash-step`, one VM per block, each
   with its `Expected:` line. The developer runs them; read every output
   before the next block.

The helper decides from paths only. It does not know whether a migration is
safe, whether a value in `hosts.env` is right, or whether the lab is at its
baseline: the deploy owner and the outputs do.
