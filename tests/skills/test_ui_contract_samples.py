"""The ui-contract-samples skill: keep a sample's bytes unless its shape changed; never touch an unrelated file."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "ui-contract-samples"
SCRIPT = SKILL / "scripts" / "keep_unchanged_samples.py"


def load():
    spec = importlib.util.spec_from_file_location("keep_unchanged_samples", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(data) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def test_same_shape_keeps_the_old_bytes():
    old = {"me.json": dump({"user": "ana", "at": "2026-10-01T00:00:00"})}
    new = {"me.json": dump({"user": "bob", "at": "2026-10-22T00:00:00"})}
    keep, changed, _, added, gone = load().decide(old, new)
    assert keep == {"me.json": old["me.json"]} and changed == [] and added == [] and gone == []


def test_a_new_key_is_a_shape_change():
    old = {"me.json": dump({"user": "ana"})}
    new = {"me.json": dump({"user": "ana", "second_factor": None})}
    keep, changed, _, added, gone = load().decide(old, new)
    assert keep == {} and changed == ["me.json"]


def test_a_value_type_change_is_a_shape_change():
    _, changed, _, _, _ = load().decide({"x.json": dump({"n": 1})}, {"x.json": dump({"n": "1"})})
    assert changed == ["x.json"]


def test_list_shape_follows_its_first_item_like_the_contract_test():
    old = {"l.json": dump({"items": [{"id": 1}]})}
    new = {"l.json": dump({"items": [{"id": 2}, {"id": "x"}]})}
    keep, changed, _, _, _ = load().decide(old, new)
    assert changed == [] and "l.json" in keep


def test_a_value_only_change_is_reported_and_old_bytes_kept():
    old = {"me.json": dump({"actions": ["view_incidents"], "at": "2026-10-01T00:00:00Z", "id": "inc_0123456789ab"})}
    new = {"me.json": dump({"actions": ["start_investigation"], "at": "2026-10-22T09:30:00.12+00:00",
                            "id": "inc_ba9876543210"})}
    keep, changed, values, _, _ = load().decide(old, new)
    assert values == ["me.json"] and changed == [] and keep == {"me.json": old["me.json"]}


def test_only_times_ids_and_hashes_differing_is_not_a_value_change():
    old = {"i.json": dump({"at": "2026-10-01T00:00:00Z", "id": "inc_0123456789ab", "key": "inc_0123456789ab:x",
                           "sha256": "a" * 64})}
    new = {"i.json": dump({"at": "2026-10-22T09:30:00.123456+00:00", "id": "inc_ba9876543210",
                           "key": "inc_ba9876543210:x", "sha256": "b" * 64})}
    _, _, values, _, _ = load().decide(old, new)
    assert values == []


def test_keep_new_takes_the_regenerated_bytes():
    old = {"me.json": dump({"actions": ["a"]})}
    new = {"me.json": dump({"actions": ["b"]})}
    keep, _, values, _, _ = load().decide(old, new, {"me.json"})
    assert keep == {} and values == ["me.json"]


def test_a_failed_run_puts_back_samples_and_the_contract_and_removes_new_samples(tmp_path):
    samples = tmp_path / "samples"
    samples.mkdir()
    contract = tmp_path / "ui-api.json"
    (samples / "me.json").write_text(dump({"user": "bob"}), encoding="utf-8", newline="\n")
    (samples / "brand-new.json").write_text(dump({}), encoding="utf-8", newline="\n")
    contract.write_bytes(b"rewritten")
    load().put_back(samples, {"me.json": dump({"user": "ana"})}, contract, b"original")
    assert sorted(p.name for p in samples.iterdir()) == ["me.json"]
    assert json.loads((samples / "me.json").read_text(encoding="utf-8")) == {"user": "ana"}
    assert contract.read_bytes() == b"original"


def test_added_and_vanished_samples_are_reported():
    keep, changed, _, added, gone = load().decide({"old.json": dump({})}, {"new.json": dump({})})
    assert added == ["new.json"] and gone == ["old.json"] and keep == {}


def test_the_shape_matches_the_contract_test():
    sys_path = str(ROOT / "tests")
    import sys
    sys.path.insert(0, sys_path)
    try:
        import test_ui_contract
    finally:
        sys.path.remove(sys_path)
    sample = {"a": [{"b": 1.5, "c": None}], "d": [], "e": True}
    assert load().shape(sample) == test_ui_contract.shape(sample)


def test_restore_writes_only_the_kept_files(tmp_path):
    samples = tmp_path / "contracts" / "samples"
    samples.mkdir(parents=True)
    (samples / "me.json").write_text(dump({"user": "bob"}), encoding="utf-8", newline="\n")
    (samples / "incident.json").write_text(dump({"id": "new", "extra": 1}), encoding="utf-8", newline="\n")
    (tmp_path / "unrelated.txt").write_text("x", encoding="utf-8")
    written = load().restore(samples, {"me.json": dump({"user": "ana"})})
    assert written == ["me.json"]
    assert json.loads((samples / "me.json").read_text(encoding="utf-8")) == {"user": "ana"}
    assert json.loads((samples / "incident.json").read_text(encoding="utf-8")) == {"id": "new", "extra": 1}
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "x"


def test_restore_refuses_a_name_outside_the_folder(tmp_path):
    samples = tmp_path / "samples"
    samples.mkdir()
    with pytest.raises(ValueError, match="sample name"):
        load().restore(samples, {"../escape.json": "{}"})


def test_skill_names_the_regeneration_switch_and_the_review():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "ARGUS_UPDATE_UI_CONTRACT=1" in text and "keep_unchanged_samples.py" in text
