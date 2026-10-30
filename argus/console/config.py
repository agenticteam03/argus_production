"""ACR-0043 (CON-2): the console's switches and limits, read from the environment like the ACR-0012 quotas.

The flag is off by default: with it off the console's routes are not mounted and answer 404.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConsoleConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("ARGUS_OPERATOR_CONSOLE", "0") == "1")
    # ACR-0043 §5.3: read commands per person; `help`, `history` and `clear` are not counted
    reads_per_minute: int = field(default_factory=lambda: int(os.getenv("ARGUS_CONSOLE_READS_PER_MINUTE", "20")))
    reads_per_hour: int = field(default_factory=lambda: int(os.getenv("ARGUS_CONSOLE_READS_PER_HOUR", "200")))
    # the console's own read budget for one incident, separate from the policy caps of the investigation
    incident_read_budget: int = field(default_factory=lambda: int(os.getenv("ARGUS_CONSOLE_INCIDENT_READS", "60")))
    history_limit: int = field(default_factory=lambda: int(os.getenv("ARGUS_CONSOLE_HISTORY_LIMIT", "50")))
    # the lab host the console reads (vm-095 also carries an api twin; the console never reads it)
    lab_host: str = field(default_factory=lambda: os.getenv("ARGUS_CONSOLE_HOST", "vm-166"))
    # CON-4b: the pause between the two samples after a command (about one scrape interval), how long missing metrics
    # are waited for after the settle delay, how long an analysis may run before a re-check is offered, and the
    # background workers (one analysis each)
    analysis_enabled: bool = field(default_factory=lambda: os.getenv("ARGUS_CONSOLE_ANALYSIS", "1") == "1")
    analysis_gap_s: int = field(default_factory=lambda: int(os.getenv("ARGUS_CONSOLE_ANALYSIS_GAP_S", "15")))
    analysis_metrics_timeout_s: int = 60
    analysis_stuck_s: int = 90
    analysis_workers: int = field(default_factory=lambda: int(os.getenv("ARGUS_CONSOLE_ANALYSIS_WORKERS", "2")))
    output_max_bytes: int = 4096        # spec §7.4: what is stored (and later shown to the model) per command
    # §12.6: how long the API waits for the worker to run a console read, and a write proposal (the judge is a model
    # call); the worker never starts a job older than the longer one, which the API has given up on
    job_timeout_s: float = field(default_factory=lambda: float(os.getenv("ARGUS_CONSOLE_JOB_TIMEOUT_S", "30")))
    propose_timeout_s: float = field(default_factory=lambda: float(os.getenv("ARGUS_CONSOLE_PROPOSE_TIMEOUT_S", "120")))
