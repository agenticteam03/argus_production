"""The ui-contract-samples skill: keep a sample's bytes unless its shape changed; never touch an unrelated file."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

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


def test_keep_new_handles_the_five_pr291_id_pairs(tmp_path, monkeypatch, capsys):
    module = load()
    samples = tmp_path / "contracts" / "samples"
    samples.mkdir(parents=True)
    contract = tmp_path / "contracts" / "ui-api.json"
    contract.write_text("old contract\n", encoding="utf-8")
    old_ids = {
        "incident": "inc_7e49840f50fa",
        "evidence1": "ev_f5de798421654c48",
        "evidence2": "ev_45ed7debb7264c5a",
        "observation1": "obs_9a72f05666764ae7",
        "observation2": "obs_b5f0c65434884487",
    }
    new_ids = {
        "incident": "inc_77b419ffd2c4",
        "evidence1": "ev_fbe03b6dd30b4d3f",
        "evidence2": "ev_fa1751bfec24478b",
        "observation1": "obs_906e33f1d6d34fe0",
        "observation2": "obs_1e2ba915fc634a86",
    }
    old_target = {
        "id": old_ids["incident"],
        "events": [{"incident_id": old_ids["incident"]}, {"incident_id": old_ids["incident"]}],
        "evidence": [{"evidence_id": old_ids["evidence1"]}, {"evidence_id": old_ids["evidence2"]}],
        "evidence_highlights": [
            {"evidence_id": old_ids["evidence1"]}, {"evidence_id": old_ids["evidence2"]}
        ],
        "observations": [{"evidence_id": old_ids["observation1"]}, {"evidence_id": old_ids["observation2"]}],
    }
    regenerated = {
        "id": new_ids["incident"],
        "events": [{"incident_id": new_ids["incident"]}, {"incident_id": new_ids["incident"]}],
        "evidence": [{"evidence_id": new_ids["evidence1"]}, {"evidence_id": new_ids["evidence2"]}],
        "evidence_highlights": [
            {"evidence_id": new_ids["observation1"]}, {"evidence_id": new_ids["observation2"]}
        ],
        "observations": [{"evidence_id": new_ids["observation1"]}, {"evidence_id": new_ids["observation2"]}],
    }
    (samples / "incident.json").write_text(dump(old_target), encoding="utf-8")
    (samples / "incidents.json").write_text(dump({"id": old_ids["incident"]}), encoding="utf-8")
    (samples / "evidence.json").write_text(dump({"evidence_id": old_ids["evidence1"]}), encoding="utf-8")
    (samples / "events.json").write_text(dump({"ids": [old_ids["observation1"], old_ids["observation2"]]}),
                                          encoding="utf-8")
    frontend_test = tmp_path / "frontend" / "src" / "sample.test.js"
    frontend_test.parent.mkdir(parents=True)
    frontend_test.write_text(f'{old_ids["incident"]} {old_ids["evidence1"]}', encoding="utf-8")
    contract_test = tmp_path / "tests" / "test_ui_contract.py"
    contract_test.parent.mkdir()
    contract_test.write_text("# fixture\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    module.SAMPLES = Path("contracts/samples")
    module.CONTRACT = Path("contracts/ui-api.json")

    def regenerate(*args, **kwargs):
        (samples / "incident.json").write_text(dump(regenerated), encoding="utf-8")
        (samples / "incidents.json").write_text(dump({"id": new_ids["incident"]}), encoding="utf-8")
        (samples / "evidence.json").write_text(dump({"evidence_id": new_ids["evidence1"]}), encoding="utf-8")
        (samples / "events.json").write_text(dump({"ids": [new_ids["observation1"], new_ids["observation2"]]}),
                                              encoding="utf-8")
        contract.write_text("new contract\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", regenerate)
    monkeypatch.setattr(sys, "argv", ["keep_unchanged_samples.py", "--keep-new", "incident.json"])

    assert module.main() == 0
    result = json.loads((samples / "incident.json").read_text(encoding="utf-8"))
    assert result["id"] == old_ids["incident"]
    assert all(event["incident_id"] == old_ids["incident"] for event in result["events"])
    assert result["evidence"][0]["evidence_id"] == old_ids["evidence1"]
    assert result["evidence"][1]["evidence_id"] == new_ids["evidence2"]
    assert result["evidence_highlights"][0]["evidence_id"] == old_ids["evidence1"]
    assert result["evidence_highlights"][1]["evidence_id"] == new_ids["observation2"]
    assert result["observations"] == [
        {"evidence_id": old_ids["observation1"]}, {"evidence_id": old_ids["observation2"]}
    ]
    assert json.loads((samples / "incidents.json").read_text(encoding="utf-8")) == {"id": old_ids["incident"]}
    assert json.loads((samples / "evidence.json").read_text(encoding="utf-8")) == {
        "evidence_id": old_ids["evidence1"]
    }
    output = capsys.readouterr().out
    for old_id, new_id in (old_ids["incident"], new_ids["incident"]), \
            (old_ids["evidence1"], new_ids["evidence1"]), \
            (old_ids["observation1"], new_ids["observation1"]), \
            (old_ids["observation2"], new_ids["observation2"]):
        assert f"{new_id} -> {old_id}" in output
    assert f"{new_ids['observation1']} -> {old_ids['evidence1']}" in output
    assert f"kept regenerated ID {new_ids['evidence2']}" in output
    assert old_ids["evidence2"] in output
    assert "frontend/src/sample.test.js" in output


def test_keep_new_rolls_back_when_a_shared_id_has_no_matching_position(tmp_path, monkeypatch, capsys):
    module = load()
    samples = tmp_path / "contracts" / "samples"
    samples.mkdir(parents=True)
    contract = tmp_path / "contracts" / "ui-api.json"
    contract.write_bytes(b"original contract")
    original = dump({"id": "inc_7e49840f50fa"})
    (samples / "incident.json").write_text(original, encoding="utf-8")
    (samples / "incidents.json").write_text(dump({"id": "inc_7e49840f50fa"}), encoding="utf-8")
    contract_test = tmp_path / "tests" / "test_ui_contract.py"
    contract_test.parent.mkdir()
    contract_test.write_text("# fixture\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    module.SAMPLES = Path("contracts/samples")
    module.CONTRACT = Path("contracts/ui-api.json")

    def regenerate(*args, **kwargs):
        (samples / "incident.json").write_text(dump({"replacement": "no id at old position"}), encoding="utf-8")
        contract.write_bytes(b"rewritten contract")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", regenerate)
    monkeypatch.setattr(sys, "argv", ["keep_unchanged_samples.py", "--keep-new", "incident.json"])

    assert module.main() == 1
    assert (samples / "incident.json").read_text(encoding="utf-8") == original
    assert contract.read_bytes() == b"original contract"
    assert "could not map shared ID inc_7e49840f50fa" in capsys.readouterr().out


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
