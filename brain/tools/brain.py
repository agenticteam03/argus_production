#!/usr/bin/env python3
"""Argus Brain helper — Python standard library + git only.

  status                       who holds each VM's lease, branches in flight, pull requests waiting for review
  start [--task T-xxxx]        clean tree → fetch → fast-forward main → show status → claim the lease
        [--vm VM]              vm-095, vm-166 or both (the default); all or nothing
        [--no-claim]           (code-only work: no VM lease)
  renew [--minutes N]          extend your leases (default 60 minutes)
  handoff "note"               release your leases, leaving a note for the next developer (task unfinished)
  release                      release your leases (task finished or nothing left in flight)
                               renew, handoff and release take --vm too (default: every VM you hold)
  checkpoint "message"         tests → stage → audit → commit → push the task branch → renew
  archive-step T-xxxx NN       move execution/current/code.bash into execution/history/T-xxxx/step-NN/
  audit [--staged]             forbidden files and patterns (secrets, addresses, local paths)
  lint                         Brain structure, relative links, LF line endings; a task branch made after LANES-2
                               must not edit the logbook, CURRENT_TEST_STATE or NEXT_STEP
  rollup                       fold brain/journal/entries/*.md into those three files (after merges, on a
                               task/rollup-<date> branch) and remove the entry files
  verify-main [--ref R]        every commit on main came from a PR approved by someone other than its author
                               (our free-plan substitute for GitHub branch protection; exceptions in
                               brain/policies/main-exceptions.txt)
  guard-push                   pre-push hook: refuses a push to main (changes reach main only through PRs)

The live leases are session.json on the `session` branch, one per VM (brain/policies/PARALLEL_LANES.md); a change to
the agent on vm-095 (deploy, rebuild, hosts.env, a migration or a restore) needs both. A claim is a fast-forward push:
if two developers claim at the same moment, Git accepts exactly one. Your GitHub handle comes from --as, $ARGUS_DEVELOPER or
`git config argus.developer <handle>`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

SESSION_BRANCH = "session"
SESSION_FILE = "session.json"
DEFAULT_TTL = 60
VMS = ("vm-095", "vm-166")
CURRENT = Path("brain/execution/current")
CODE_BASH_HEADER = """\
# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================

# (no task in progress)
"""


class BrainError(Exception):
    pass


# --------------------------------------------------------------------------------------------- git and time helpers
def git(*args: str, check: bool = True, stdin: str | None = None) -> str:
    # Bytes, not text mode: on Windows text mode would turn "\n" into "\r\n" in what we feed to mktree/hash-object.
    p = subprocess.run(["git", *args], input=stdin.encode("utf-8") if stdin is not None else None,
                       capture_output=True)
    out, err = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    if check and p.returncode != 0:
        raise BrainError(f"git {' '.join(args)} failed: {(err or out).strip()}")
    return out.strip()


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel"))


def now() -> dt.datetime:
    fake = os.environ.get("BRAIN_NOW")  # tests only
    return dt.datetime.fromisoformat(fake) if fake else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t: dt.datetime) -> str:
    return t.isoformat()


def me(args) -> str:
    who = getattr(args, "as_", None) or os.environ.get("ARGUS_DEVELOPER") or git("config", "argus.developer", check=False)
    if not who:
        raise BrainError("who are you? Run once:  git config argus.developer <your-github-handle>")
    return who.strip()


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


# ------------------------------------------------------------------------------------------------------ the lease
def read_lease(fetch: bool = True) -> tuple[dict | None, str | None]:
    """Return (lease, commit) from origin/session; (None, None) if the branch does not exist yet."""
    if fetch:
        git("fetch", "origin", f"+refs/heads/{SESSION_BRANCH}:refs/remotes/origin/{SESSION_BRANCH}", check=False)
    sha = git("rev-parse", "--verify", "-q", f"refs/remotes/origin/{SESSION_BRANCH}", check=False)
    if not sha:
        return None, None
    return json.loads(git("show", f"{sha}:{SESSION_FILE}")), sha


def lease_state(lease: dict | None, t: dt.datetime) -> str:
    if not lease:
        return "none"
    if lease.get("released"):
        return "released"
    if dt.datetime.fromisoformat(lease["expires_at"]) <= t:
        return "expired"
    return "active"


def write_lease(lease: dict, parent: str | None, message: str) -> str:
    """Commit session.json on top of `parent` and push it without force: a concurrent writer makes this fail."""
    blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(lease, indent=2) + "\n")
    tree = git("mktree", stdin=f"100644 blob {blob}\t{SESSION_FILE}\n")
    commit = git("commit-tree", tree, *(["-p", parent] if parent else []), "-m", message)
    p = subprocess.run(["git", "push", "origin", f"{commit}:refs/heads/{SESSION_BRANCH}"],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise BrainError("the lease changed on GitHub before your update (someone else was faster). "
                         "Run `python brain/tools/brain.py status` and stop if someone else holds it.")
    git("update-ref", f"refs/remotes/origin/{SESSION_BRANCH}", commit)
    return commit


def read_leases(fetch: bool = True) -> tuple[dict[str, dict | None], dict | None, str | None]:
    """({vm: lease or None}, the raw session.json, its commit)."""
    raw, sha = read_lease(fetch)
    return per_vm(raw), raw, sha


def per_vm(raw: dict | None) -> dict[str, dict | None]:
    """One lease per VM. A session.json in the old format (one lease, no `vms`) holds both VMs."""
    if not raw:
        return {vm: None for vm in VMS}
    if "vms" not in raw:
        return {vm: dict(raw) for vm in VMS}
    vms = {vm: (dict(raw["vms"][vm]) if raw["vms"].get(vm) else None) for vm in VMS}
    # A brain.py older than LANES-1 (run from a branch made before it) edits only the top-level summary. When the
    # summary no longer matches the leases and its holder is the only holder, its renew, release and handoff apply to
    # that holder's leases.
    held = [v for v in vms.values() if v and not v.get("released")]
    expected = summary(vms)
    edited = (raw.get("released"), raw.get("expires_at")) != (expected["released"], expected["expires_at"])
    if edited and held and {v["holder"] for v in held} == {raw.get("holder")}:
        for v in held:
            if raw.get("released"):
                v.update(released=True, handoff=raw.get("handoff"))
            elif raw.get("expires_at") and (dt.datetime.fromisoformat(raw["expires_at"])
                                            > dt.datetime.fromisoformat(v["expires_at"])):
                v["expires_at"] = raw["expires_at"]
    return vms


def summary(vms: dict[str, dict | None]) -> dict:
    """The top-level fields, for a brain.py older than LANES-1: busy while any VM is held, and held by `a+b` when two
    developers hold one VM each, so an old `start` refuses everyone."""
    known = [v for v in vms.values() if v]
    held = [v for v in known if not v.get("released")]
    if not held:
        return {**max(known, key=lambda v: v.get("started_at") or ""), "released": True}
    top = dict(max(held, key=lambda v: dt.datetime.fromisoformat(v["expires_at"])))
    holders = sorted({v["holder"] for v in held})
    if len(holders) > 1:
        top.update(holder="+".join(holders), session_id=None, task=None, branch=None, handoff=None)
        top.pop("took_over_from", None)
    return {**top, "released": False}


def write_leases(vms: dict[str, dict | None], parent: str | None, message: str) -> str:
    return write_lease({**summary(vms), "vms": vms}, parent, message)


def describe(lease: dict | None, t: dt.datetime) -> str:
    state = lease_state(lease, t)
    if state == "none":
        return "no lease yet (the session branch does not exist)"
    base = f"{lease['holder']} · task {lease.get('task') or '-'} · branch {lease.get('branch') or '-'}"
    if state == "active":
        return f"ACTIVE: {base} · until {lease['expires_at']}"
    if state == "expired":
        return f"EXPIRED: {base} · expired {lease['expires_at']}"
    return f"released by {base}"


def chosen_vms(args) -> tuple[str, ...]:
    vm = getattr(args, "vm", None) or "both"
    return VMS if vm == "both" else (vm,)


def own_leases(args) -> tuple[dict[str, dict | None], str | None, list[str]]:
    """Your unreleased leases among the VMs asked (--vm, default both): ({vm: lease}, commit, [your VMs])."""
    who = me(args)
    vms, _, sha = read_leases()
    mine = [vm for vm in chosen_vms(args) if vms[vm] and vms[vm]["holder"] == who and not vms[vm].get("released")]
    if not mine:
        raise BrainError(f"you ({who}) do not hold a lease on {' or '.join(chosen_vms(args))}: "
                         + "; ".join(f"{vm}: {describe(vms[vm], now())}" for vm in VMS))
    return vms, sha, mine


def print_leases(vms: dict[str, dict | None], t: dt.datetime) -> None:
    a, b = (vms[vm] for vm in VMS)
    if a == b:
        print(f"Lease (both VMs): {describe(a, t)}")
    else:
        for vm in VMS:
            print(f"Lease {vm}: {describe(vms[vm], t)}")
    notes = []
    for lease in (a, b):
        h = (lease or {}).get("handoff")
        if h and h.get("note") not in notes:
            notes.append(h.get("note"))
            print(f"Handoff: from {lease['holder']} at {h.get('at')} on branch {h.get('branch')}:\n         {h.get('note')}")


# --------------------------------------------------------------------------------------------------- commands
def cmd_status(args) -> int:
    vms, _, _ = read_leases()
    print_leases(vms, now())
    branches = [b.strip() for b in git("branch", "-r", "--list", "origin/task/*", check=False).splitlines() if b.strip()]
    print("Task branches on GitHub: " + (", ".join(b.removeprefix("origin/") for b in branches) or "none"))
    print_prs()
    return 0


def print_prs() -> None:
    if os.environ.get("BRAIN_NO_GH"):
        return
    try:
        p = subprocess.run(["gh", "pr", "list", "--state", "open", "--json", "number,title,author,headRefName"],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        print("Pull requests: (gh not available — check GitHub)")
        return
    if p.returncode != 0:
        print("Pull requests: (gh failed — check GitHub)")
        return
    prs = json.loads(p.stdout or "[]")
    if not prs:
        print("Pull requests waiting for review: none")
        return
    print("Pull requests waiting for review (REVIEW THESE FIRST — brain/agents/REVIEW_PROTOCOL.md):")
    for pr in prs:
        print(f"  #{pr['number']} {pr['title']} — by {pr['author']['login']} ({pr['headRefName']})")


def cmd_start(args) -> int:
    who = me(args)
    dirty = git("status", "--porcelain")
    if dirty:
        raise BrainError("your working tree has uncommitted changes — commit, stash or discard them first:\n" + dirty)
    git("fetch", "origin", "--prune")
    branch = current_branch()
    if branch == "main" and git("rev-parse", "--verify", "-q", "refs/remotes/origin/main", check=False):
        git("merge", "--ff-only", "origin/main")
        print(f"main is up to date ({git('rev-parse', '--short', 'HEAD')}).")
    else:
        print(f"You are on '{branch}' (not main): fetched only, nothing merged.")
    cmd_status(args)
    if not os.environ.get("BRAIN_NO_GH"):
        try:
            problems = verify_main("refs/remotes/origin/main")
        except BrainError as e:
            problems = [f"could not verify main ({e})"]
        if problems:
            print("\nWARNING: main has changes that did not follow the review rule - tell the team:\n  "
                  + "\n  ".join(problems))
    if args.no_claim:
        print("\nNo lease claimed (code-only work). Do not run mutating VM steps.")
        return 0
    vms, _, sha = read_leases(fetch=False)
    t = now()
    wanted = chosen_vms(args)
    busy = [vm for vm in wanted if lease_state(vms[vm], t) == "active" and vms[vm]["holder"] != who]
    if busy:                                        # all or nothing: no lease is claimed when one VM is taken
        raise BrainError("STOP: " + "; ".join(f"{vm} is in use by {vms[vm]['holder']} until {vms[vm]['expires_at']}"
                                              for vm in busy)
                         + ". Claim the other VM (--vm), do code-only work (--no-claim) or wait.")
    session_id, base = uuid.uuid4().hex[:12], git("rev-parse", "HEAD")
    for vm in wanted:
        old = vms[vm]
        new = {"holder": who, "session_id": session_id, "task": args.task or (old or {}).get("task"),
               "branch": branch, "base_commit": base, "started_at": iso(t),
               "expires_at": iso(t + dt.timedelta(minutes=DEFAULT_TTL)), "released": False, "handoff": None}
        if lease_state(old, t) == "expired" and old["holder"] != who:
            new["took_over_from"] = {"holder": old["holder"], "task": old.get("task"), "branch": old.get("branch"),
                                     "expired_at": old["expires_at"]}
            print(f"\nNOTE: taking over an EXPIRED lease of {old['holder']} on {vm}. Record it in the journal, start "
                  f"with the state probe, and do not modify their branch without talking to them.")
        vms[vm] = new
    task = vms[wanted[0]]["task"]
    write_leases(vms, sha, f"claim: {who} ({task or 'no task'}) {'+'.join(wanted)}")
    print(f"\nLease CLAIMED by {who} on {' and '.join(wanted)} until {vms[wanted[0]]['expires_at']} "
          "(renew at every step: brain.py renew).")
    if wanted == ("vm-095",):
        print("vm-095 only: a change to the agent (deploy, rebuild, hosts.env, a migration or a restore of "
              "argus-v18-postgres) needs BOTH leases (brain/policies/PARALLEL_LANES.md).")
    print("VM marker (first block of your session on each VM claimed):")
    for vm in wanted:
        print(f"  [VM {vm} · bash]  echo 'holder={who} session={session_id}' | sudo tee /opt/argus-v18/SESSION >/dev/null")
    return 0


def cmd_renew(args) -> int:
    vms, sha, mine = own_leases(args)
    until = iso(now() + dt.timedelta(minutes=args.minutes))
    for vm in mine:
        vms[vm]["expires_at"] = until
    write_leases(vms, sha, f"renew: {me(args)} {'+'.join(mine)}")
    print(f"Lease renewed on {' and '.join(mine)} until {until}.")
    return 0


def cmd_handoff(args) -> int:
    vms, sha, mine = own_leases(args)
    for vm in mine:
        vms[vm].update(released=True, handoff={"note": args.note, "branch": current_branch(), "at": iso(now())})
    write_leases(vms, sha, f"handoff: {me(args)} {'+'.join(mine)}")
    print(f"Lease released with a handoff note on {' and '.join(mine)}. Make sure your task branch is pushed "
          "(git push).")
    return 0


def cmd_release(args) -> int:
    vms, sha, mine = own_leases(args)
    for vm in mine:
        vms[vm].update(released=True, handoff=None)
    write_leases(vms, sha, f"release: {me(args)} {'+'.join(mine)}")
    print(f"Lease released on {' and '.join(mine)}.")
    return 0


def cmd_checkpoint(args) -> int:
    branch = current_branch()
    if branch in ("main", SESSION_BRANCH, "HEAD"):
        raise BrainError(f"you are on '{branch}': checkpoints go on a task branch (git checkout -b task/T-xxxx-slug)")
    if not args.no_tests:
        print("Running the test suite ...")
        if subprocess.run([sys.executable, "-m", "pytest", "-q"]).returncode != 0:
            raise BrainError("tests failed — fix them (or say why) before a checkpoint")
    git("add", "-A")
    staged = git("diff", "--cached", "--name-only")
    if not staged:
        print("Nothing to commit.")
        return 0
    problems = audit(staged_only=True)
    if problems:
        print("\n".join(problems))
        raise BrainError("audit failed - nothing was committed (the files are still staged: git restore --staged <f>)")
    print("Committing:\n  " + staged.replace("\n", "\n  "))
    git("commit", "-m", args.message)
    git("push", "-u", "origin", branch)
    print(f"Pushed {branch} (CI runs on this push).")
    vms, _, sha = read_leases()
    mine = [vm for vm in VMS if vms[vm] and vms[vm]["holder"] == me(args) and lease_state(vms[vm], now()) == "active"]
    if mine:
        until = iso(now() + dt.timedelta(minutes=DEFAULT_TTL))
        for vm in mine:
            vms[vm]["expires_at"] = until
        write_leases(vms, sha, f"renew: {me(args)} {'+'.join(mine)}")
        print(f"Lease renewed on {' and '.join(mine)} until {until}.")
    return 0


def cmd_archive_step(args) -> int:
    if not re.fullmatch(r"T-\d{4}", args.task):
        raise BrainError("task id must look like T-0013")
    root = repo_root()
    src = root / CURRENT / "code.bash"
    dest = root / "brain/execution/history" / args.task / f"step-{int(args.step):02d}"
    if dest.exists():
        raise BrainError(f"{dest.relative_to(root)} already exists")
    text = src.read_bytes().decode("utf-8")
    if text == CODE_BASH_HEADER:
        raise BrainError("execution/current/code.bash has no commands to archive")
    dest.mkdir(parents=True)
    (dest / "code.bash").write_bytes(text.encode("utf-8"))
    (dest / "evidence.md").write_bytes((
        f"# {args.task} step {int(args.step):02d} — evidence\n\n"
        "Key output lines from output.bash, SANITIZED (no addresses, no secrets, no personal names).\n\n"
        "| Check | Expected | Observed |\n|---|---|---|\n| | | |\n\n"
        "nonint-check: NO INTERFERENCE on … (yes/no)\n").encode("utf-8"))
    src.write_bytes(CODE_BASH_HEADER.encode("utf-8"))
    print(f"Archived to {dest.relative_to(root).as_posix()}/ — fill in evidence.md from output.bash (sanitized).")
    return 0


# ------------------------------------------------------------------------------------------------- audit and lint
FORBIDDEN_PATHS = [
    (re.compile(r"(^|/)output[^/]*\.bash$"), "raw output file"),
    (re.compile(r"\.db$"), "database file"),
    (re.compile(r"(^|/)secrets/"), "secrets directory"),
    (re.compile(r"(^|/)\.env$|(^|/)hosts\.env$"), "environment / addresses file"),
    (re.compile(r"_ed25519$|_rsa$|\.(pem|key|p12|pfx)$"), "key file"),
    (re.compile(r"\.(7z|tgz)$"), "archive"),
]
FORBIDDEN_TEXT = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "API key (sk-...)"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS key"),
    (re.compile(r"\b[A-Za-z]:\\+Users\\+", re.I), "Windows user-profile path"),
    (re.compile("devops" + "-platform"), "private server name"),
]
IPV4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
ALLOW_MARK = "brain-audit: allow"


def ip_problem(text: str) -> str | None:
    try:
        ip = ipaddress.IPv4Address(text)
    except ValueError:
        return None
    if ip.is_loopback or ip.is_unspecified or ip in ipaddress.IPv4Network("172.16.0.0/12") \
            or ip in ipaddress.IPv4Network("192.168.0.0/16"):
        return None                     # loopback, any-address, Docker ranges
    if ip in ipaddress.IPv4Network("10.0.0.0/8"):
        return None if text.endswith(".0") else "private host address"   # networks allowed, hosts not
    return "public IP address" if ip.is_global else None


def candidate_files(staged_only: bool) -> list[str]:
    if staged_only:
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    else:
        out = git("ls-files", "--cached", "--others", "--exclude-standard")
    return [f for f in out.splitlines() if f]


def audit(staged_only: bool = False) -> list[str]:
    root = repo_root()
    problems = []
    for f in candidate_files(staged_only):
        for rx, why in FORBIDDEN_PATHS:
            if rx.search(f):
                problems.append(f"{f}: forbidden file ({why})")
        p = root / f
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        data = p.read_bytes()
        if b"\0" in data:
            continue
        for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if ALLOW_MARK in line:
                continue
            for rx, why in FORBIDDEN_TEXT:
                if rx.search(line):
                    problems.append(f"{f}:{n}: {why}")
            for m in IPV4.finditer(line):
                why = ip_problem(m.group(0))
                if why:
                    problems.append(f"{f}:{n}: {why} {m.group(0)}")
    return problems


def cmd_audit(args) -> int:
    problems = audit(args.staged)
    if problems:
        print("AUDIT FAILED:\n  " + "\n  ".join(problems))
        print(f"(a false positive can be allowed by adding '{ALLOW_MARK}' to that line - explain why in the PR)")
        return 1
    print("audit: clean")
    return 0


REQUIRED = ["README.md", "CURRENT_STATE.md", "NEXT_STEP.md", "IMPLEMENTATION_PLAN.md", "OPEN_PROBLEMS.md",
            "architecture/ARCHITECTURE.md", "architecture/changes/ACR-TEMPLATE.md", "agents/AGENT_PROTOCOL.md",
            "agents/STEP_TEMPLATE.md", "agents/REVIEW_PROTOCOL.md", "tdd/CURRENT_TEST_STATE.md",
            "journal/logbook.md", "execution/current/code.bash", "infrastructure/environment.md"]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def lint() -> list[str]:
    root = repo_root()
    problems = [f"brain/{r}: missing" for r in REQUIRED if not (root / "brain" / r).is_file()]
    for f in candidate_files(False):
        p = root / f
        if not p.is_file():
            continue
        data = p.read_bytes()
        if b"\0" not in data and b"\r\n" in data:
            problems.append(f"{f}: Windows line endings (CRLF)")
        if f.startswith("brain/") and f.endswith(".md"):
            for target in LINK.findall(data.decode("utf-8", errors="replace")):
                if re.match(r"[a-z]+:", target) or target.startswith("#"):
                    continue
                if not (p.parent / target.split("#")[0]).exists():
                    problems.append(f"{f}: broken link {target}")
    return problems + summary_edits()


# ------------------------------------------------- journal entries as files and the roll-up (PARALLEL_LANES, LANES-2)
ENTRIES = Path("brain/journal/entries")
LOGBOOK = Path("brain/journal/logbook.md")
TEST_STATE = Path("brain/tdd/CURRENT_TEST_STATE.md")
NEXT = Path("brain/NEXT_STEP.md")
SUMMARIES = (LOGBOOK, TEST_STATE, NEXT)          # edited only by a roll-up (task/rollup-*) or on main
SECTIONS = {"### Test state": TEST_STATE, "### Next step": NEXT}


def summary_edits() -> list[str]:
    """A task branch created from a main that has the roll-up must not edit the shared summaries: two parallel PRs
    that both append there always conflict. Branches made before the rule keep their edits (PARALLEL_LANES
    transition); a roll-up branch (task/rollup-*) and main are exempt."""
    branch = os.environ.get("GITHUB_HEAD_REF") or git("rev-parse", "--abbrev-ref", "HEAD", check=False)
    if not branch.startswith("task/") or branch.startswith("task/rollup"):
        return []
    base = git("merge-base", "HEAD", "refs/remotes/origin/main", check=False)
    if not base or "def cmd_rollup" not in git("show", f"{base}:brain/tools/brain.py", check=False):
        return []
    changed = set(git("diff", "--name-only", base, check=False).splitlines())
    return [f"{p.as_posix()}: a task branch does not edit the shared summaries; write "
            f"brain/journal/entries/<YYYY-MM-DD>-<task>.md instead (brain.py rollup folds it in after the merge)"
            for p in SUMMARIES if p.as_posix() in changed]


def rebase_links(text: str, src: str, dst: str) -> str:
    """Rewrite the relative Markdown links of text written in folder `src` so they work from folder `dst`."""
    def moved(target: str) -> str:
        if re.match(r"[a-z]+:", target) or target.startswith(("#", "/")):
            return target
        path, _, frag = target.partition("#")
        new = os.path.relpath(os.path.normpath(os.path.join(src, path)), dst).replace(os.sep, "/")
        return new + ("#" + frag if frag else "")

    def fix(m: re.Match) -> str:                          # [`path`](path): the shown path moves with the link
        label, tick, target = m.group(2), m.group(1), m.group(3)
        shown = moved(label) if label == target else label
        return f"[{tick}{shown}{tick}]({moved(target)})"
    return re.sub(r"\[(`?)([^\]`]+)\1\]\(([^)\s]+)\)", fix, text)


def split_entry(name: str, text: str) -> tuple[str, dict[Path, str]]:
    """(the journal part, {summary file: its section}) of one entry file."""
    if not text.startswith("## "):
        raise BrainError(f"{name}: an entry must start with '## <date> — <title>' (nothing was rolled up)")
    parts = re.split(r"(?m)^(### Test state|### Next step)[ \t]*$", text)
    journal, sections = parts[0].strip(), {}
    for heading, body in zip(parts[1::2], parts[2::2]):
        sections[SECTIONS[heading]] = body.strip()
    return journal, sections


def insert_after(text: str, marker: str, block: str) -> str:
    """Insert block (with blank lines around it) after the paragraph that starts with marker, else after the title."""
    lines = text.split("\n")
    at = next((i for i, ln in enumerate(lines) if ln.startswith(marker)), 0)
    while at < len(lines) and lines[at].strip():          # the end of that paragraph (its blank line follows)
        at += 1
    return "\n".join(lines[:at] + ["", block] + lines[at:])


def cmd_rollup(args) -> int:
    """Fold brain/journal/entries/*.md (oldest first) into the logbook, CURRENT_TEST_STATE and NEXT_STEP, and remove
    them. Run it on a task/rollup-<date> branch after merges; review the diff; open a small PR."""
    root = repo_root()
    files = sorted((root / ENTRIES).glob("*.md")) if (root / ENTRIES).is_dir() else []
    if not files:
        print("nothing to roll up (no file in brain/journal/entries/)")
        return 0
    parsed = [(f, *split_entry(f.name, f.read_text(encoding="utf-8"))) for f in files]   # all checked before writing
    texts = {p: (root / p).read_text(encoding="utf-8") for p in SUMMARIES}
    for _, journal, sections in parsed:
        texts[LOGBOOK] = texts[LOGBOOK].rstrip("\n") + "\n\n" + rebase_links(journal, ENTRIES.as_posix(),
                                                                             LOGBOOK.parent.as_posix()) + "\n"
        for target, body in sections.items():
            body = rebase_links(body, ENTRIES.as_posix(), target.parent.as_posix())
            texts[target] = insert_after(texts[target], "**Last updated:**" if target == TEST_STATE else "# ", body)
    for p, text in texts.items():
        (root / p).write_bytes(text.encode("utf-8"))
    for f, _, _ in parsed:
        f.unlink()
    print(f"{len(parsed)} journal entries rolled up into the logbook, CURRENT_TEST_STATE and NEXT_STEP:\n  "
          + "\n  ".join(f.name for f, _, _ in parsed) + "\nReview `git diff`, then commit on a task/rollup-<date> branch.")
    return 0


def cmd_lint(args) -> int:
    problems = lint()
    if problems:
        print("LINT FAILED:\n  " + "\n  ".join(problems))
        return 1
    print("lint: clean")
    return 0


# ------------------------------------------------------------- review rule on main (free plan: no branch protection)
EXCEPTIONS = Path("brain/policies/main-exceptions.txt")


def read_exceptions(root: Path) -> set[int]:
    """PR numbers allowed without a non-author approval (one per line: `pr <n>  <reason>`)."""
    p = root / EXCEPTIONS
    if not p.is_file():
        return set()
    return {int(line.split()[1]) for line in p.read_text(encoding="utf-8").splitlines()
            if line.startswith("pr ") and len(line.split()) > 1 and line.split()[1].isdigit()}


def check_main(commits: list[tuple[str, int]], pr_for, reviews_for, allowed: set[int]) -> list[str]:
    """commits: (sha, number of parents) along main's first-parent line. pr_for(sha) -> PR dict or None;
    reviews_for(n) -> review dicts. Returns the violations (empty = rule kept)."""
    problems = []
    for sha, parents in commits:
        if parents == 0:
            continue                                   # the initial import
        pr = pr_for(sha)
        if not pr:
            problems.append(f"{sha[:7]}: pushed directly to main (no pull request)")
            continue
        n, author, head = pr["number"], pr["user"]["login"], pr["head"]["sha"]
        if n in allowed:
            continue
        ok = any(r.get("state") == "APPROVED" and r["user"]["login"] != author and r.get("commit_id") == head
                 for r in reviews_for(n))
        if not ok:
            problems.append(f"{sha[:7]}: PR #{n} by {author} merged without an approval of its last push by "
                            "another developer")
    return problems


def gh_json(path: str):
    p = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8", timeout=60)
    if p.returncode != 0:
        raise BrainError(f"gh api {path}: {(p.stderr or p.stdout).strip()}")
    return json.loads(p.stdout or "null")


def verify_main(ref: str) -> list[str]:
    if not git("rev-parse", "--verify", "-q", ref, check=False):
        return []
    commits = [(line.split()[0], len(line.split()) - 1)
               for line in git("rev-list", "--first-parent", "--parents", ref).splitlines()]

    def pr_for(sha):
        prs = [p for p in gh_json(f"repos/{{owner}}/{{repo}}/commits/{sha}/pulls") or []
               if p.get("merge_commit_sha") == sha]
        return prs[0] if prs else None

    return check_main(commits, pr_for, lambda n: gh_json(f"repos/{{owner}}/{{repo}}/pulls/{n}/reviews"),
                      read_exceptions(repo_root()))


def cmd_verify_main(args) -> int:
    problems = verify_main(args.ref)
    if problems:
        print("MAIN RULE BROKEN:\n  " + "\n  ".join(problems))
        return 1
    print("verify-main: every change on main came through an approved pull request (or a recorded exception)")
    return 0


def cmd_guard_push(args) -> int:
    target = os.environ.get("PRE_COMMIT_REMOTE_BRANCH", "")
    if target in ("refs/heads/main", "main"):
        print("brain.py: pushing to main is not allowed. Push your task branch and open a pull request "
              "(brain/policies/GIT_WORKFLOW.md).", file=sys.stderr)
        return 1
    return 0


# ------------------------------------------------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="brain.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--as", dest="as_", help="your GitHub handle (default: git config argus.developer)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("start")
    s.add_argument("--task")
    s.add_argument("--no-claim", action="store_true")
    r = sub.add_parser("renew")
    r.add_argument("--minutes", type=int, default=DEFAULT_TTL)
    h = sub.add_parser("handoff")
    h.add_argument("note")
    rl = sub.add_parser("release")
    for parser, fn in ((s, cmd_start), (r, cmd_renew), (h, cmd_handoff), (rl, cmd_release)):
        parser.add_argument("--vm", choices=[*VMS, "both"], default="both", help="vm-095, vm-166 or both (default)")
        parser.set_defaults(fn=fn)
    c = sub.add_parser("checkpoint")
    c.add_argument("message")
    c.add_argument("--no-tests", action="store_true")
    c.set_defaults(fn=cmd_checkpoint)
    a = sub.add_parser("archive-step")
    a.add_argument("task")
    a.add_argument("step")
    a.set_defaults(fn=cmd_archive_step)
    au = sub.add_parser("audit")
    au.add_argument("--staged", action="store_true")
    au.set_defaults(fn=cmd_audit)
    sub.add_parser("lint").set_defaults(fn=cmd_lint)
    sub.add_parser("rollup").set_defaults(fn=cmd_rollup)
    v = sub.add_parser("verify-main")
    v.add_argument("--ref", default="refs/remotes/origin/main")
    v.set_defaults(fn=cmd_verify_main)
    sub.add_parser("guard-push").set_defaults(fn=cmd_guard_push)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except BrainError as e:
        print(f"brain.py: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
