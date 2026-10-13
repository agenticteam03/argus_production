"""T-0043 (Phase 7, "an expected-jobs list for absent scrape targets"): a scrape job that disappears from a host's
Prometheus leaves no `up` series at all, so `up == 0` never fires and `scrape_targets_down` read 0: a blind spot nobody
saw. Now:
- `ArgusScrapeTargetMissing` fires (2 minutes) when one of the jobs every host has (exporter, node-exporter, cAdvisor)
  has no `up` series; each host's Prometheus labels its alerts with its own `argus_host` (`external_labels`), so the
  alert reaches intake as that host's;
- `scrape_targets_down` counts those missing jobs too, so `monitoring_blind_spot` (RB-014) matches.
`argus-v18-db-probe` exists only on vm-166; it is not in the shared list (its absence there is a follow-up).
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MON = ROOT / "deploy" / "monitoring"
EXPECTED = ("argus-v18-exporter", "argus-v18-node-exporter", "argus-v18-cadvisor")


def test_each_prometheus_labels_its_alerts_with_its_own_host():
    for host in ("vm-095", "vm-166"):
        cfg = yaml.safe_load((MON / f"prometheus-{host}.yml").read_text(encoding="utf-8"))
        assert cfg["global"]["external_labels"] == {"argus_host": host}
        jobs = {j["job_name"] for j in cfg["scrape_configs"]}
        assert set(EXPECTED) <= jobs, host                               # every expected job is scraped there


def test_the_missing_job_alert_covers_the_jobs_every_host_has():
    rules = yaml.safe_load((MON / "alerts.yml").read_text(encoding="utf-8"))
    r = next(x for g in rules["groups"] for x in g["rules"] if x.get("alert") == "ArgusScrapeTargetMissing")
    assert r["for"] == "2m"
    for job in EXPECTED:
        assert f'absent(up{{job="{job}"}})' in r["expr"]
    assert "db-probe" not in r["expr"]


def test_scrape_targets_down_counts_the_missing_expected_jobs():
    sig = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["scrape_targets_down"]
    assert 'count(up{argus_host="$host"} == 0) or vector(0)' in sig                       # down, as before
    assert '3 - (count(up{argus_host="$host",job=~"argus-v18-(exporter|node-exporter|cadvisor)"}) or vector(0))' in sig


def test_the_promql_case_is_in_the_promtool_tests():
    t = yaml.safe_load((ROOT / "tests" / "promql" / "op005_test.yml").read_text(encoding="utf-8"))
    names = [c["name"] for c in t["tests"]]
    assert "T-0043 a missing expected job counts as one target down" in names
