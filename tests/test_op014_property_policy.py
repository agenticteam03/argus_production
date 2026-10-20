"""OP-014 step 10 (the policy engine): property-based tests (Hypothesis) of `PolicyEngine.check` and the inspection
policy. Whatever the inputs, the engine fails closed: one failed condition is a refusal, an allow means every condition
held, and no path that is not normal or that the deny floor names is ever readable, even under an allowlist of `/`."""
from __future__ import annotations

import string
from pathlib import Path

import yaml
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from argus.domain.model import TARGET_KINDS, TargetRef
from argus.policy.engine import PolicyEngine
from argus.policy.inspection import BUILTIN_DENY, InspectionPolicy

SETTINGS = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
ROOT = Path(__file__).resolve().parents[1]
REAL = (ROOT / "config" / "policy.yaml").read_text(encoding="utf-8")
ENGINE = PolicyEngine(yaml.safe_load(REAL), REAL)
CAPS = sorted(ENGINE.capabilities)
SAFETY = ["READ_ONLY_SAFE", "READ_ONLY_SENSITIVE", "WRITE_LOW_RISK", "WRITE_HIGH_RISK", "DESTRUCTIVE", ""]

refs = st.builds(TargetRef, host=st.sampled_from(["vm-095", "vm-166", "h1"]),
                 kind=st.sampled_from(sorted(TARGET_KINDS)),
                 name=st.text(alphabet=string.ascii_lowercase + "-", min_size=1, max_size=8))


# --- PolicyEngine.check: fail closed -----------------------------------------------------------------------------------
@SETTINGS
@given(cap=st.one_of(st.sampled_from(CAPS), st.text(max_size=30)), level=st.integers(-2, 9),
       safety=st.sampled_from(SAFETY), target=refs, scope=st.sets(refs, max_size=4), used=st.integers(0, 30))
def test_an_allow_means_every_condition_held(cap, level, safety, target, scope, used):
    d = ENGINE.check(capability=cap, level=level, safety_class=safety, target=target, incident_scope=scope,
                     used_in_incident=used, arguments={})
    entry = ENGINE.capabilities.get(cap)
    held = (entry is not None and level <= ENGINE.max_tool_level and safety in ENGINE.allowed_safety_classes
            and target in scope and used < int(entry.get("max_per_incident", 10)))
    if d.allowed:
        assert held and d.rule == f"allow:{cap}"
    if not held:
        assert not d.allowed and d.rule != f"allow:{cap}"


@SETTINGS
@given(cap=st.text(max_size=40))
def test_a_capability_without_a_policy_entry_is_always_refused(cap):
    assume(cap not in ENGINE.capabilities)
    target = TargetRef.parse("vm-166/container:x")
    d = ENGINE.check(capability=cap, level=0, safety_class="READ_ONLY_SAFE", target=target,
                     incident_scope={target}, used_in_incident=0, arguments={})
    assert not d.allowed and d.rule == "allowlist"


@SETTINGS
@given(opened=st.lists(st.text(max_size=12), min_size=1, max_size=3))
def test_a_non_empty_write_gate_refuses_startup(opened):
    data = yaml.safe_load(REAL)
    data["write_gate"] = {"open": opened}
    try:
        PolicyEngine(data, REAL)
    except ValueError:
        return
    raise AssertionError("a policy with an open write gate started")


# --- the inspection policy: paths ------------------------------------------------------------------------------------
TARGET = TargetRef.parse("h1/host:h1")
EVERYTHING = InspectionPolicy.from_data({"targets": {"h1/host:h1": {"files": ["/"], "service_config": ["/"]}}})
segment = st.text(alphabet=string.ascii_letters + string.digits + "._-", min_size=1, max_size=10).filter(
    lambda s: s not in (".", ".."))
paths = st.lists(segment, min_size=1, max_size=5).map(lambda parts: "/" + "/".join(parts))


def read(policy, path, capability="host.read_file"):
    return policy.allows(TARGET, capability, {"path": path})


@SETTINGS
@given(parts=st.lists(segment, min_size=1, max_size=4), trick=st.sampled_from(["..", ".", ""]),
       at=st.integers(0, 4), cap=st.sampled_from(["host.read_file", "host.service_config"]))
def test_a_path_that_is_not_normal_is_never_readable(parts, trick, at, cap):
    parts.insert(min(at, len(parts)), trick)
    path = "/" + "/".join(parts)
    assert not read(EVERYTHING, path, cap).allowed


@SETTINGS
@given(path=st.text(max_size=40))
def test_a_relative_or_odd_path_is_never_readable(path):
    assume(not path.startswith("/") or "\x00" in path)
    assert not read(EVERYTHING, path).allowed


floor_names = st.sampled_from([".ssh", "id_rsa", "id_ed25519", "x.key", "cert.PEM", ".env", "prod.env",
                               "db_password.txt", "MyPassword", "api_TOKEN", "tokens"])
floor_dirs = st.sampled_from(["/run/secrets/", "/opt/argus-v18/secrets/", "/root/", "/proc/", "/var/lib/docker/",
                              "/etc/sudoers.d/"])


@SETTINGS
@given(before=st.lists(segment, max_size=3), name=floor_names, after=st.lists(segment, max_size=2),
       cap=st.sampled_from(["host.read_file", "host.service_config"]))
def test_a_floor_name_anywhere_in_the_path_is_never_readable_even_under_slash(before, name, after, cap):
    path = "/" + "/".join([*before, name, *after])
    d = read(EVERYTHING, path, cap)
    assert not d.allowed and "deny pattern" in d.reason


@SETTINGS
@given(base=floor_dirs, rest=st.lists(segment, max_size=3))
def test_a_floor_directory_is_never_readable_even_under_slash(base, rest):
    path = base.rstrip("/") + ("/" + "/".join(rest) if rest else "")
    assert not read(EVERYTHING, path).allowed


@SETTINGS
@given(path=paths, allowed=st.lists(st.one_of(paths, paths.map(lambda p: p + "/")), max_size=4))
def test_an_allowed_read_is_inside_the_allowlist_and_outside_the_floor(path, allowed):
    policy = InspectionPolicy.from_data({"targets": {"h1/host:h1": {"files": allowed}}})
    d = read(policy, path)
    if d.allowed:
        assert any(path == a or (a.endswith("/") and path.startswith(a)) for a in allowed)
        parts = [p.lower() for p in path.split("/") if p]
        assert ".ssh" not in parts and not any("token" in p or "password" in p for p in parts)
        assert not path.startswith(("/root/", "/proc/", "/run/secrets/"))


@SETTINGS
@given(path=paths, extra=st.lists(paths, max_size=3))
def test_the_data_deny_list_only_adds_to_the_floor(path, extra):
    policy = InspectionPolicy.from_data({"targets": {"h1/host:h1": {"files": ["/"]}}, "deny": extra})
    assert set(BUILTIN_DENY) <= set(policy.deny)
    if read(policy, path).allowed:
        assert read(EVERYTHING, path).allowed                     # a data deny never re-opens what the floor closed


# --- the inspection policy: journal and processes ----------------------------------------------------------------------
JOURNAL = InspectionPolicy.from_data({"targets": {"h1/host:h1": {"journal": {"units": ["nginx.service"],
                                                                              "max_lines": 200}}}})


@SETTINGS
@given(unit=st.text(max_size=20), lines=st.one_of(st.integers(-5, 400), st.booleans(), st.none(), st.text(max_size=3)))
def test_journal_reads_only_a_listed_unit_within_its_line_limit(unit, lines):
    d = JOURNAL.allows(TARGET, "host.journal", {"unit": unit, "lines": lines})
    ok = unit == "nginx.service" and isinstance(lines, int) and not isinstance(lines, bool) and 0 < lines <= 200
    assert d.allowed == ok


@SETTINGS
@given(target=refs, cap=st.sampled_from(["host.read_file", "host.service_config", "host.journal",
                                         "host.process_details"]), args=st.dictionaries(st.text(max_size=5),
                                                                                         st.text(max_size=5), max_size=3))
def test_a_target_without_an_inspection_entry_allows_no_inspected_read(target, cap, args):
    assume(target != TARGET)
    assert not EVERYTHING.allows(target, cap, args).allowed
