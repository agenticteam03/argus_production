"""The authored runbooks name the incident classes assigned in architecture §1.3."""
from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNBOOKS = ROOT / "argus/runbooks"
ARCHITECTURE = ROOT / "brain/architecture/ARCHITECTURE.md"


def _class_runbooks() -> dict[str, str]:
    section = ARCHITECTURE.read_text(encoding="utf-8").split("### 1.3 Incident classes", 1)[1]
    section = section.split("### 1.4", 1)[0]
    mapping: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"`[a-z_]+`", cells[1]):
            continue
        incident_class = cells[1].strip("`")
        for runbook_id in re.findall(r"RB-\d{3}", cells[2]):
            assert runbook_id not in mapping, f"{runbook_id} has two primary classes"
            mapping[runbook_id] = incident_class
    return mapping


def test_every_runbook_detector_matches_its_architecture_class():
    expected = _class_runbooks()
    files = sorted(RUNBOOKS.glob("RB-*.md"))
    actual: dict[str, str | None] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        metadata = yaml.safe_load(re.search(r"```yaml\n(.*?)\n```", text, re.DOTALL).group(1))
        assert metadata["id"] == path.name[:6]
        actual[metadata["id"]] = metadata["detector"]
    assert actual == expected
    assert len(set(expected.values())) == 20


def test_runbook_index_uses_the_same_detector_classes():
    expected = _class_runbooks()
    index = (RUNBOOKS / "RUNBOOK-INDEX.md").read_text(encoding="utf-8")
    listed: dict[str, str] = {}
    for line in index.splitlines():
        match = re.match(r"\| \[(RB-\d{3})\]", line)
        if match:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            listed[match.group(1)] = cells[2].strip("`")
    assert listed == expected
