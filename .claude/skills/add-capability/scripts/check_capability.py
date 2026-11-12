"""Check that a new Argus read capability has every piece of its lifecycle before review.

Read-only: it imports the repository's catalog, classes and wiring and reads config/policy.yaml and tests/.
Run from the repository root:

    python .claude/skills/add-capability/scripts/check_capability.py <capability.name> [--allow-offer]
    python .claude/skills/add-capability/scripts/check_capability.py --all

`--allow-offer` is only for the separate, evaluated change that offers the read to a class. `--all` checks the
structure of every committed read (spec, policy limit, executor), not its offer or its tests.
Tests, Brain lint and human review remain authoritative.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

READ_CLASSES = ("READ_ONLY_SAFE", "READ_ONLY_SENSITIVE")
TARGET_KINDS = {"container", "host", "service", "process"}     # ACR-0044: the kinds an executor can read
MODEL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def structure(spec, specs, policy: dict, executor_kinds, replay_executors) -> list[str]:
    """The spec, its policy limit and its executor: what every committed read must already have."""
    errors = []
    n = spec.name
    if not MODEL_NAME.match(spec.model_name):
        errors.append(f"{n}: model_name {spec.model_name!r} is not snake_case")
    if [s.name for s in specs if s.model_name == spec.model_name] != [n]:
        errors.append(f"{n}: model_name {spec.model_name!r} is not unique in the catalog")
    for field in ("description", "use_when"):
        if not str(getattr(spec, field) or "").strip():
            errors.append(f"{n}: empty {field}")
    if spec.level not in (1, 2, 3):
        errors.append(f"{n}: level {spec.level!r} is not 1, 2 or 3")
    if spec.safety_class not in READ_CLASSES:
        errors.append(f"{n}: {spec.safety_class!r} is not a read safety class {READ_CLASSES}")
    if spec.safety_class == "READ_ONLY_SENSITIVE" and spec.allowed_fields is None:
        errors.append(f"{n}: READ_ONLY_SENSITIVE needs allowed_fields (ALLOWED_FIELDS in catalog.py, ACR-0028)")
    if not spec.tags:
        errors.append(f"{n}: no tag (a class offers a read through its tags)")
    if not spec.target_kinds or not set(spec.target_kinds) <= TARGET_KINDS:
        errors.append(f"{n}: target kinds {sorted(spec.target_kinds)} must be a non-empty subset of "
                      f"{sorted(TARGET_KINDS)}")

    entry = (policy.get("capabilities") or {}).get(n)
    if entry is None:
        errors.append(f"{n}: no entry in config/policy.yaml capabilities (refused at call time)")
    elif "max_per_incident" not in (entry or {}):
        errors.append(f"{n}: no max_per_incident in config/policy.yaml (the engine would allow 10)")
    else:
        limit = entry["max_per_incident"]
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            errors.append(f"{n}: max_per_incident {limit!r} must be a positive integer")

    in_worker = spec.executor == "argus_internal"
    if spec.executor not in executor_kinds:
        errors.append(f"{n}: unknown executor {spec.executor!r} (wiring EXECUTOR_KINDS)")
    elif in_worker != (spec.runs_in == "worker"):
        errors.append(f"{n}: an in-worker read has executor argus_internal and runs_in 'worker', not "
                      f"{spec.executor!r} and {spec.runs_in!r}")
    elif not in_worker and spec.executor not in replay_executors:
        errors.append(f"{n}: replay's FixtureExecutor does not answer executor {spec.executor!r} "
                      "(argus/evaluation/replay.py EXECUTORS)")
    if spec.max_subcalls and spec.runs_in != "worker":
        errors.append(f"{n}: a combined read (max_subcalls > 0) runs in the worker")
    return errors


def check(name: str, specs, policy: dict, classes, executor_kinds, replay_executors, tests_text: str,
          allow_offer: bool = False) -> list[str]:
    """Every problem of the new read `name`; [] when its lifecycle is complete."""
    spec = next((s for s in specs if s.name == name), None)
    if spec is None:
        return [f"{name}: not in the catalog (build_catalog in argus/capabilities/catalog.py)"]
    errors = structure(spec, specs, policy, executor_kinds, replay_executors)
    offered = sorted(c.name for c in classes if spec.tags & c.tool_tags)
    if offered and not allow_offer:
        errors.append(f"{name}: offered to {offered} through tags {sorted(spec.tags)}; a new read starts offered to "
                      "no class, and the offer is a separate, evaluated change")
    if f'"{name}"' not in tests_text and f"'{name}'" not in tests_text:
        errors.append(f"{name}: no test under tests/ names it")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--allow-offer", action="store_true")
    args = parser.parse_args()
    if bool(args.name) == args.all:
        parser.error("give one capability name or --all")
    root = Path.cwd()
    sys.path.insert(0, str(root))
    import yaml

    from argus.capabilities.catalog import build_catalog
    from argus.detectors.classes import CLASSES
    from argus.evaluation.replay import EXECUTORS
    from argus.infrastructure.wiring import EXECUTOR_KINDS

    specs = build_catalog()
    policy = yaml.safe_load((root / "config" / "policy.yaml").read_text(encoding="utf-8")) or {}
    if args.all:
        errors = [e for s in specs for e in structure(s, specs, policy, EXECUTOR_KINDS, EXECUTORS)]
    else:
        tests = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted((root / "tests").rglob("*.py")))
        errors = check(args.name, specs, policy, CLASSES, EXECUTOR_KINDS, EXECUTORS, tests, args.allow_offer)
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"PASS: {'every committed read' if args.all else args.name} has the pieces this checker knows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
