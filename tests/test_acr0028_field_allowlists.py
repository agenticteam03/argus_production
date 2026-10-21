"""ACR-0028 (OP-002 G-006): a sensitive read keeps only the value paths it declares.

The dispatcher drops every other path before redaction, truncation and storage, and the audit names what was dropped.
A canary per sensitive read: the fake gateway answers with every declared path plus an extra field (at the top, in
each row and in each object) holding a marker; the marker must reach neither the stored values nor the model's text.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from argus.capabilities import catalog
from argus.capabilities.catalog import ALLOWED_FIELDS, build_catalog
from argus.capabilities.redaction import Redactor
from argus.domain.minimize import minimize, parse_paths
from argus.domain.model import TargetInfo, TargetRef
from argus.tooling.dispatch import Dispatcher
from argus.tooling.executors import ExecutorRegistry

MARK = "CANARY-7f3a"
SPECS = {s.name: s for s in build_catalog()}


# --- the rule ----------------------------------------------------------------------------------------------------------
def test_minimize_keeps_declared_paths_and_names_the_rest():
    values = {"lines": ["a"], "env": {"K": "v"}, "rows": [{"pid": 1, "cmdline": "x --pw"}, "junk"],
              "limits": {"max_open_files": 1024, "core": 0}}
    kept, dropped = minimize(values, ["lines", "rows[].pid", "limits.max_open_files", "absent"])
    assert kept == {"lines": ["a"], "rows": [{"pid": 1}], "limits": {"max_open_files": 1024}}
    assert dropped == ["env", "limits.core", "rows[]", "rows[].cmdline"]


def test_a_bare_key_keeps_the_whole_value():
    assert minimize({"a": {"b": 1, "c": 2}}, ["a", "a.b"]) == ({"a": {"b": 1, "c": 2}}, [])


def test_values_that_are_not_an_object_are_dropped_whole():
    assert minimize(["x"], ["lines"]) == ({}, ["*"])


@pytest.mark.parametrize("path", ["a.b.c", "a[].b.c", "[].b", "a.", "a[].b[]"])
def test_a_malformed_path_is_refused(path):
    with pytest.raises(ValueError, match="one level"):
        parse_paths([path])


def test_a_list_and_an_object_under_one_key_are_refused():
    with pytest.raises(ValueError, match="both"):
        parse_paths(["a[].b", "a.c"])


# --- the registry ------------------------------------------------------------------------------------------------------
def test_every_sensitive_read_declares_its_fields():
    assert [s.name for s in SPECS.values() if s.safety_class == "READ_ONLY_SENSITIVE" and not s.allowed_fields] == []
    assert set(ALLOWED_FIELDS) <= set(SPECS)


def test_the_catalog_refuses_a_sensitive_read_without_fields(monkeypatch):
    monkeypatch.setattr(catalog, "ALLOWED_FIELDS", {k: v for k, v in ALLOWED_FIELDS.items() if k != "host.journal"})
    with pytest.raises(ValueError, match="host.journal is READ_ONLY_SENSITIVE"):
        build_catalog()


def test_the_catalog_refuses_a_list_for_no_read(monkeypatch):
    monkeypatch.setattr(catalog, "ALLOWED_FIELDS", {**ALLOWED_FIELDS, "host.nothing": ("x",)})
    with pytest.raises(ValueError, match="names no capability"):
        build_catalog()


# --- the canary, through the real dispatcher ---------------------------------------------------------------------------
# values a read checks before it answers ok (a journal needs its source, a limit is a [soft, hard] pair)
LISTS = {"lines": ["one ordinary line"], "by_state": {"active": 1}, "source": "syslog", "path": "/",
         "max_open_files": [1024, 4096], "max_processes": [100, 200]}


def _answer(paths) -> dict[str, Any]:
    """Every declared path with a plausible value, plus the marker at the top, in each row and in each object."""
    out: dict[str, Any] = {"canary": MARK}
    for top, rule in parse_paths(paths).items():
        if rule is None:
            out[top] = LISTS.get(top, "2026-10-21T00:00:00+00:00" if top == "collected_at" else 1)
        elif rule[0] == "[]":
            out[top] = [{**{k: 1 for k in rule[1]}, "canary": MARK}]
        else:
            out[top] = {**{k: LISTS.get(k, 1) for k in rule[1]}, "canary": MARK}
    return out


class Gateway:
    answer: dict[str, Any] = {}

    def __init__(self, url, token):
        pass

    def get(self, path, params=None):
        return json.loads(json.dumps(Gateway.answer))


class Inventory:
    def host(self, name):
        return type("H", (), {"executors": {e: "http://gw" for e in ("docker_read", "host_probe", "db_probe")}})()

    def target(self, ref):          # a database and a declared mount, for the reads that check them first
        return TargetInfo(ref=ref, mounts=["/"], database="app")


ARGS = {"minutes": 5, "tail": 50, "pattern": "error", "mount": "/", "path": "/var/log/app.log", "lines": 20,
        "pid": 1, "unit": "app", "stream": "both"}


def _args(spec):
    fields = spec.args_model.model_fields
    return spec.args_model.model_validate({k: v for k, v in ARGS.items() if k in fields and fields[k].is_required()})


DIRECT = sorted(n for n in ALLOWED_FIELDS if not SPECS[n].max_subcalls)


@pytest.mark.parametrize("name", DIRECT)
def test_the_canary_never_reaches_evidence_or_the_model(name):
    spec = SPECS[name]
    Gateway.answer = _answer(spec.allowed_fields)
    reg = ExecutorRegistry()
    reg.register(spec.executor, Gateway)
    kind = "container" if "container" in spec.target_kinds else "host"
    target = TargetRef.parse(f"vm-166/{kind}:{'app' if kind == 'container' else 'vm-166'}")
    obs = Dispatcher(Inventory(), reg, {}, Redactor()).call(spec, _args(spec), target)
    assert obs.status == "ok", obs.model_text
    assert MARK not in json.dumps(obs.values) and MARK not in obs.model_text
    assert "canary" in obs.dropped_fields and all(MARK not in d for d in obs.dropped_fields)


def test_a_declared_field_the_gateway_omits_is_not_an_error():
    spec = SPECS["container.detailed_logs"]                     # no `minutes`, `stream` or `truncated` in the answer
    Gateway.answer = {"lines": ["x"], "collected_at": "2026-10-21T00:00:00+00:00"}
    reg = ExecutorRegistry()
    reg.register(spec.executor, Gateway)
    obs = Dispatcher(Inventory(), reg, {}, Redactor()).call(spec, _args(spec), TargetRef.parse("vm-166/container:app"))
    assert obs.status == "ok" and obs.dropped_fields == []


def test_a_safe_read_without_a_list_is_not_minimized():
    spec = dataclasses.replace(SPECS["host.uptime"], allowed_fields=None)
    Gateway.answer = {"uptime_seconds": 5, "extra": 1, "collected_at": "2026-10-21T00:00:00+00:00"}
    reg = ExecutorRegistry()
    reg.register(spec.executor, Gateway)
    obs = Dispatcher(Inventory(), reg, {}, Redactor()).call(spec, _args(spec), TargetRef.parse("vm-166/host:vm-166"))
    assert obs.values.get("extra") == 1 and obs.dropped_fields == []


def test_the_snapshot_keeps_its_statuses_and_sub_read_references():
    kept, dropped = minimize({"statuses": {"container.logs": "ok"}, "subcalls": ["ev1"], "subcall_refs": [{}],
                              "canary": MARK}, SPECS["analysis.diagnostic_snapshot"].allowed_fields)
    assert set(kept) == {"statuses", "subcalls", "subcall_refs"} and dropped == ["canary"]
