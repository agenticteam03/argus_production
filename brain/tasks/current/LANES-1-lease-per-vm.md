# LANES-1 — One lease per VM

| Field | Value |
|---|---|
| Status | `done` offline (2026-10-10); in use after its pull request merges |
| Policy | [`../../policies/PARALLEL_LANES.md`](../../policies/PARALLEL_LANES.md), change 1 (accepted in PR #52) |
| Architecture | no change (no ACR): the developer workflow, not Argus |
| Branch | `task/LANES-1-lease-per-vm` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | no (`brain.py` and its tests only) |

## Goal (plain language)

One lease covered both VMs, so every VM run waited for one person. Now each VM has its own lease: one developer can
run scenarios on vm-166 while another runs the evaluation or a backup on vm-095.

## Design

- `session.json` keeps one lease per VM under `vms`. `brain.py start --vm vm-095|vm-166|both` (default both, as
  before). A claim is **all or nothing**: when one of the VMs asked is someone else's, nothing is claimed.
- `renew`, `handoff` and `release` act on every VM you hold; `--vm` limits them to one. `checkpoint` renews yours.
- `status` prints `Lease (both VMs): ...` when one lease covers both, otherwise one line per VM.
- Claiming vm-095 alone prints the rule: a change to the agent (deploy, rebuild, `hosts.env`, a migration or a
  restore of `argus-v18-postgres`) needs **both** leases. The tool cannot see what a block does; the developer and
  the agent apply the rule.
- The VM marker `/opt/argus-v18/SESSION` is unchanged; `start` prints the marker block only for the VMs claimed.

### Transition (no flag day)

`brain.py` runs from the developer's checkout, so a branch made before this one runs the old code.
- A `session.json` in the old format (no `vms`) holds **both** VMs: the lease held when this merges stays valid.
- The new code also writes the old top-level fields as a **summary**: busy while any VM is held, held by `a+b` when
  two developers hold one VM each. An old `start` then refuses everyone, never claims over a held VM.
- An old `renew`, `release` or `handoff` edits only the summary. When the summary no longer matches the leases and
  its holder is the only holder, the new code applies that edit to the holder's leases.
- An old `start` by the only holder (or on a lab with nothing held) writes the old format: it holds both VMs, as the
  old tool meant.

## Tests (`tests/brain/test_brain.py`)

8 new tests, red seen (7 at first: `--vm` unknown; then the 8th, `renewing_one_vm_does_not_renew_the_other`, against
a first version that mistook a one-VM renew for an old tool's renew). All 27 brain tests pass; the 19 that existed
pass unchanged (the default `start` still claims both).
- two developers, one VM each; claiming both refused while one is held (nothing claimed);
- the summary an old `brain.py` reads; the old format holds both VMs (refused, then taken over after expiry);
- an old tool's renew and release honoured; renew/handoff touch only my VM; renewing one VM leaves the other;
- the vm-095-alone reminder and the marker block for the claimed VM only.

Checked by hand: the live `session.json` (old format, `conantkd` until 04:06 UTC) reads as `conantkd` on both VMs.

## After the merge

Everyone runs `git pull` on `main` (and merges `main` into their task branch before the next `start --vm`). Until a
branch has it, its old `brain.py` still works and keeps out of a VM someone else holds.
