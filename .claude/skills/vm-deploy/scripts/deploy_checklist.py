"""Print the deploy checklist for one commit on one Argus VM. Read-only: it runs only `git` on this checkout.

It never connects to a VM, runs docker or writes a block: the deploy owner writes the blocks (code-bash-step) from
this list, under the leases, and the developer runs them. Run from the repository root:

    python .claude/skills/vm-deploy/scripts/deploy_checklist.py --target vm-095 --from <deployed sha> --to <sha>

`--from` is what the VM runs now (`deploy.sh status` prints it); the changed paths between the two decide the steps.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

SHA = re.compile(r"^[0-9a-f]{7,40}$")
NEW_ENV = re.compile(r"^\+.*\$\{(ARGUS_[A-Z0-9_]+)")
NEW_SECRET = re.compile(r"^\+\s*-\s*(/opt/argus-v18/secrets/[^:\s]+):")
AGENT = ("argus/", "config/", "pyproject.toml", "Dockerfile", "deploy/vm-095/compose.core.yml", "deploy/agent/",
         "deploy/scheduler/")
UI = ("frontend/", "deploy/ui/", "contracts/")
MIGRATIONS = "deploy/migrations/"
VM166 = ("deploy/lab/",)
BOTH = ("deploy/target/", "deploy/monitoring/")
# The compose files each VM brings up: a secret mount added in one of them must exist on that VM before any `up`.
COMPOSE = {"vm-095": ("deploy/vm-095/", "deploy/ui/", "deploy/target/", "deploy/monitoring/"),
           "vm-166": ("deploy/lab/", "deploy/target/", "deploy/monitoring/")}
OVERLAY = {"vm-095": "compose.core-join.yml", "vm-166": "compose.loopback.yml"}
COVERED = AGENT + UI + (MIGRATIONS,) + VM166 + BOTH + ("deploy/hosts.env.example",)
APP = "/opt/argus-v18/app"


def _any(paths, prefixes):
    return [p for p in paths if p.startswith(prefixes)]


def not_covered(changed: list[str]) -> list[str]:
    """The deploy/ paths this list maps to no step: the deploy owner checks them by hand."""
    return sorted(p for p in changed if p.startswith("deploy/") and not p.startswith(COVERED))


def checklist(target: str, commit: str, changed: list[str], new_env, new_secrets=()) -> list[str]:
    """The ordered steps to deploy `commit` on `target`, given the paths changed since the deployed commit.

    `new_secrets` holds (compose file, host path) for every secret bind mount the diff adds."""
    if target not in ("vm-095", "vm-166"):
        raise ValueError("target must be vm-095 or vm-166")
    if not SHA.match(commit or ""):
        raise ValueError("commit must be 7 to 40 lowercase hex characters (a sha, never a branch name)")
    migrations = sorted(p for p in _any(changed, (MIGRATIONS,)) if p.endswith(".sql"))
    agent = _any(changed, AGENT) if target == "vm-095" else []
    ui = _any(changed, UI) if target == "vm-095" else []
    lab = _any(changed, VM166) if target == "vm-166" else []
    shared = sorted({p.split("/")[1] for p in _any(changed, BOTH)})
    secrets = sorted({path for file, path in new_secrets if file.startswith(COMPOSE[target])})
    unknown = not_covered(changed)
    tail = ["not covered by this list (check by hand): " + ", ".join(unknown)] if unknown else []
    if not (agent or ui or migrations or lab or shared or secrets):
        return [f"nothing to deploy on {target}: no file it builds or brings up changed"] + tail

    if target == "vm-095" and (agent or migrations):
        lease = "Leases: both leases (an agent change on vm-095 invalidates a batch on vm-166; PARALLEL_LANES.md)"
    else:
        lease = f"Leases: {target}'s lease (brain.py start --vm {target}), renewed at every step"
    steps = [lease,
             f"[{target}] first line of every VM block: the SESSION marker the lease printed; then the SESSION check",
             f"[{target}] sudo bash {APP}/ops/deploy.sh status: note the deployed commit (the rollback target) "
             "and LAB BASELINE OK",
             f"[{target}] sudo bash {APP}/ops/nonint-check.sh before"]
    if target == "vm-095" and (agent or migrations):
        steps.append(f"[vm-095] sudo bash {APP}/ops/db-backup.sh backup --as <handle>: BACKUP OK before any change")
    steps.append(f"[{target}] sudo bash {APP}/ops/deploy.sh {commit} --as <handle>: DEPLOY OK: {commit}")
    for path in secrets:
        steps.append(f"[{target}] create {path} (owner and mode like its neighbours, value from its owner, never "
                     "printed or in Git) BEFORE any up: a missing bind source becomes a directory")
    for name in sorted(set(new_env)):
        steps.append(f"[{target}] {name} in /opt/argus-v18/hosts.env (value from its owner, never in Git or the "
                     "chat) BEFORE any up: the compose file now reads it")
    if migrations:
        steps.append(f"[vm-095] sudo bash {APP}/ops/db-migrate.sh BEFORE the new image: "
                     + ", ".join(p.rsplit("/", 1)[1] for p in migrations) + " applied, each once")
    if agent:
        steps.append("[vm-095] docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml "
                     "up -d --build --no-deps argus-v18-agent argus-v18-worker argus-v18-scheduler: three "
                     "Recreated/Started, health 200")
        steps.append(f"[vm-095] docker exec argus-v18-agent argus deploy record --commit {commit} --ref <ref> "
                     "--as <handle>")
    if ui:
        steps.append("[vm-095] docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d "
                     "--build: ui Recreated/Started, ports 443 and 80 only")
    for folder in shared:
        main = "compose.target.yml" if folder == "target" else "compose.monitoring.yml"
        steps.append(f"[{target}] cd {APP}/deploy/{folder} && docker compose --env-file {target}.env -f {main} "
                     f"-f {OVERLAY[target]} up -d --build: the {folder} services Recreated/Started")
    if lab:
        steps.append("[vm-166] rebuild only the changed services: " + ", ".join(sorted(lab)))
    if target == "vm-095" and (agent or migrations):
        steps.append("[vm-095] docker exec argus-v18-agent argus db check: every check passed, no FAIL")
    steps += [f"[{target}] sudo bash {APP}/ops/deploy.sh status: the new commit, LAB BASELINE OK",
              f"[{target}] sudo bash {APP}/ops/nonint-check.sh after: NO INTERFERENCE",
              "laptop: brain.py release, then a DEPLOY-<sha> record PR (history step and journal entry)",
              "Rollback: deploy.sh <the commit noted above> --as <handle>, the same compose commands; a migration "
              "is never rolled back by deploy.sh (restore the backup only with both leases and the team's OK)"]
    return steps + tail


def changed_paths(base: str, head: str) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    names = subprocess.run(["git", "diff", "--name-only", f"{base}..{head}"], capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout.split()
    diff = subprocess.run(["git", "diff", f"{base}..{head}", "--", "deploy/vm-095/compose.core.yml",
                           "deploy/ui/"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    env = sorted({m.group(1) for line in diff.splitlines() if (m := NEW_ENV.match(line))})
    secrets, file = [], ""
    compose = subprocess.run(["git", "diff", f"{base}..{head}", "--", "deploy/"], capture_output=True, text=True,
                             encoding="utf-8", check=True).stdout
    for line in compose.splitlines():
        if line.startswith("+++ b/"):
            file = line[6:]
        elif m := NEW_SECRET.match(line):
            secrets.append((file, m.group(1)))
    return names, env, secrets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, choices=["vm-095", "vm-166"])
    parser.add_argument("--from", dest="base", required=True, help="the commit the VM runs now")
    parser.add_argument("--to", dest="head", required=True, help="the commit to deploy")
    args = parser.parse_args()
    try:
        sha = subprocess.run(["git", "rev-parse", "--short=7", args.head], capture_output=True, text=True,
                             encoding="utf-8", check=True).stdout.strip()
        names, env, secrets = changed_paths(args.base, args.head)
        lines = checklist(args.target, sha, names, env, secrets)
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"ERROR: {getattr(exc, 'stderr', '') or exc}".strip(), file=sys.stderr)
        return 2
    print(f"CHECKLIST deploy {sha} on {args.target} ({len(names)} changed paths since {args.base})")
    for n, line in enumerate(lines, 1):
        print(f"{n:2}. {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
