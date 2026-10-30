"""CON-2 (ACR-0043): the console's handlers. Every output line comes from a capability or a metric read through the
ports; nothing is typed into the handler. Write commands never run; scenario 2 and 4 commands are not bound yet."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from argus.console.handlers import ConsolePorts, ConsoleResult, execute
from argus.console.parser import parse
from argus.domain.model import TargetRef

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
HOST = "vm-166/host:vm-166"
REFS = {"cache": "vm-166/container:argus-lab-cache", "api": "vm-166/container:argus-lab-api",
        "worker": "vm-166/container:argus-lab-jobworker"}
PRINCIPAL = SimpleNamespace(id="olga", kind="human", role="operator")


def obs(text="", values=None, status="ok", category=None):
    return SimpleNamespace(status=status, model_text=text, values=values or {}, error_category=category)


class FakePorts(ConsolePorts):
    """Answers each (capability, target, args) from a table and records every read."""

    def __init__(self, answers=None, topology=None, history=(), metrics=None):
        self.answers, self.calls = answers or {}, []
        super().__init__(read=self._read, service_ref=REFS.__getitem__, host_ref=HOST,
                         topology=lambda: topology or {"edges": []}, history=lambda _incident: list(history),
                         now=lambda: NOW, metrics=metrics)

    def _read(self, capability, target, **args):
        self.calls.append((capability, target, args))
        answer = self.answers.get((capability, target))
        if answer is None:
            answer = self.answers.get(capability)
        if answer is None:
            raise AssertionError(f"unexpected read {capability} {target}")
        return answer(args) if callable(answer) else answer


def run(text, ports):
    return execute(parse(text), "inc_1", PRINCIPAL, ports)


def test_help_lists_the_registry_and_runs_nothing():
    ports = FakePorts()
    result = run("help", ports)

    assert isinstance(result, ConsoleResult) and result.status == "ok"
    assert result.output_lines[0] == "Available commands:"
    assert any("cache status" in line for line in result.output_lines)
    assert ports.calls == []
    assert result.started_at <= result.finished_at


def test_clear_returns_no_lines():
    result = run("clear", FakePorts())
    assert (result.status, result.output_lines) == ("ok", [])


def test_history_reads_the_stored_rows_of_the_incident():
    rows = [{"input": "cache status", "status": "ok", "started_at": NOW - timedelta(minutes=2), "cls": "read"},
            {"input": "api cpu", "status": "error", "started_at": NOW - timedelta(minutes=1), "cls": "read"}]
    result = run("history", FakePorts(history=rows))

    assert result.status == "ok"
    assert "cache status" in result.output_lines[0] and "ok" in result.output_lines[0]
    assert "api cpu" in result.output_lines[1] and "error" in result.output_lines[1]


def test_history_of_an_incident_without_commands_says_so_from_the_store():
    result = run("history", FakePorts())
    assert result.status == "ok" and result.output_lines == ["No commands yet in this incident."]


def test_cache_status_is_one_container_status_read_and_the_lines_are_its_values():
    values = {"state": "exited", "health": "none", "restart_count": 0, "exit_code": 137, "oom_killed": False,
              "started_at": "S-START", "finished_at": "S-FINISH"}
    ports = FakePorts({("container.status", REFS["cache"]): obs("text", values)})

    result = run("cache status", ports)

    assert result.status == "ok"
    assert ports.calls == [("container.status", REFS["cache"], {})]
    text = "\n".join(result.output_lines)
    assert "exited" in text and "S-FINISH" in text and "137" in text      # a stopped cache: since = when it stopped
    assert "S-START" not in text


def test_a_running_container_reports_since_its_start():
    values = {"state": "running", "health": "healthy", "restart_count": 2, "started_at": "S-START",
              "finished_at": "S-FINISH"}
    result = run("cache status", FakePorts({"container.status": obs("t", values)}))
    text = "\n".join(result.output_lines)
    assert "running" in text and "S-START" in text and "S-FINISH" not in text and "healthy" in text


def test_status_reads_every_lab_service_and_shows_what_it_could_not_read():
    answers = {("container.status", REFS["cache"]): obs("t", {"state": "running", "health": "none"}),
               ("container.status", REFS["api"]): obs("t", {"state": "running", "health": "healthy"}),
               ("container.status", REFS["worker"]): obs("not found", status="error", category="not_found")}
    ports = FakePorts(answers)

    result = run("status", ports)

    assert result.status == "ok"
    assert [c[1] for c in ports.calls] == [REFS["cache"], REFS["api"], REFS["worker"]]
    text = "\n".join(result.output_lines)
    assert "argus-lab-cache" in text and "healthy" in text
    assert "argus-lab-jobworker" in text and "not_found" in text


def test_status_is_an_error_when_nothing_can_be_read():
    ports = FakePorts({"container.status": obs("down", status="error", category="unavailable")})
    result = run("status", ports)
    assert result.status == "error" and "unavailable" in "\n".join(result.output_lines)


def test_map_shows_the_edges_of_the_service_with_state_and_change_time():
    edges = [{"from": REFS["api"], "to": REFS["cache"], "state": "broken", "reason": "refused", "port": 6379,
              "since": "S-SINCE"},
             {"from": REFS["worker"], "to": REFS["cache"], "state": "ok", "reason": None, "port": 6379,
              "since": None},
             {"from": "vm-166/container:other", "to": "vm-166/container:else", "state": "ok", "reason": None,
              "port": None, "since": None}]
    ports = FakePorts(topology={"edges": edges})

    result = run("map api", ports)

    assert result.status == "ok" and ports.calls == []
    text = "\n".join(result.output_lines)
    assert "argus-lab-api" in text and "argus-lab-cache" in text and "broken" in text and "refused" in text
    assert "S-SINCE" in text and "other" not in text and "jobworker" not in text


def test_map_of_the_cache_includes_the_edges_that_point_at_it():
    edges = [{"from": REFS["api"], "to": REFS["cache"], "state": "broken", "reason": "refused", "port": 6379,
              "since": None}]
    result = run("map cache", FakePorts(topology={"edges": edges}))
    assert "argus-lab-api" in "\n".join(result.output_lines)


def test_api_cpu_reads_the_cpu_history_and_finds_the_onset_in_the_points():
    points = [[NOW.timestamp() - 600 + 30 * i, 0.02] for i in range(10)]
    points += [[NOW.timestamp() - 300 + 30 * i, 0.9] for i in range(10)]
    ports = FakePorts({("metrics.cpu_history", REFS["api"]): obs("CPU HISTORY TEXT", {"points": points})})

    result = run("api cpu", ports)

    assert result.status == "ok"
    assert ports.calls == [("metrics.cpu_history", REFS["api"], {"minutes": 30})]
    text = "\n".join(result.output_lines)
    assert "CPU HISTORY TEXT" in text
    onset = datetime.fromtimestamp(points[10][0], timezone.utc)
    assert f"{onset:%H:%M:%S}" in text and "onset" in text
    assert "0.9" in text                                              # the latest value, from the points


def test_api_cpu_with_no_rise_reports_no_onset():
    points = [[NOW.timestamp() - 600 + 30 * i, 0.02] for i in range(20)]
    result = run("api cpu", FakePorts({"metrics.cpu_history": obs("T", {"points": points})}))
    assert "no rise" in "\n".join(result.output_lines)


def test_since_sets_the_window_in_minutes():
    ports = FakePorts({"metrics.cpu_history": obs("T", {"points": [[NOW.timestamp(), 0.1]]})})
    run("api cpu --since 11:15", ports)
    assert ports.calls[0][2] == {"minutes": 45}


def test_since_in_the_future_means_yesterday_and_a_window_over_two_hours_is_refused():
    ports = FakePorts({"metrics.cpu_history": obs("T", {"points": []})})
    result = run("api cpu --since 13:00", ports)
    assert result.status == "error" and "at most 120" in "\n".join(result.output_lines)
    assert ports.calls == []


def test_api_errors_counts_named_patterns_from_the_log_search():
    def search(args):
        return obs("t", {"matched": {"error": 7, "timeout": 0, "refused": 3}[args["pattern"]],
                         "lines": [f"LINE-{args['pattern']}"]})
    ports = FakePorts({("container.search_logs", REFS["api"]): search})

    result = run("api errors --since 11:30", ports)

    assert result.status == "ok"
    assert [(c[0], c[2]) for c in ports.calls] == [("container.search_logs", {"pattern": p, "minutes": 30})
                                                    for p in ("error", "timeout", "refused")]
    text = "\n".join(result.output_lines)
    assert "error" in text and "7" in text and "3" in text and "LINE-refused" in text


def test_host_metrics_prints_the_host_reads():
    answers = {("host.cpu", HOST): obs("CPU LINE"), ("host.memory", HOST): obs("MEMORY LINE"),
               ("host.disk_usage", HOST): obs("DISK LINE")}
    ports = FakePorts(answers)

    result = run("host metrics", ports)

    assert result.status == "ok"
    assert [c[0] for c in ports.calls] == ["host.cpu", "host.memory", "host.disk_usage"]
    assert result.output_lines == ["CPU LINE", "MEMORY LINE", "DISK LINE"]


def test_a_failed_read_makes_the_command_an_error_with_the_reason():
    ports = FakePorts({"container.status": obs("REFUSED container.status: out of scope", status="error",
                                               category="out_of_scope")})
    result = run("cache status", ports)
    assert result.status == "error" and "out of scope" in "\n".join(result.output_lines)


def test_an_exception_in_a_port_becomes_a_generic_error_not_a_crash():
    def broken(args):
        raise RuntimeError("secret internal detail")
    result = run("cache status", FakePorts({"container.status": broken}))
    assert result.status == "error"
    assert "secret internal detail" not in "\n".join(result.output_lines)


class FakeMetrics:
    def __init__(self, current=None, histories=None):
        self.current = current or {}
        self.histories = histories or {}
        self.snapshots, self.ranges = [], []

    def snapshot(self, target, signals):
        self.snapshots.append((target, signals))
        return SimpleNamespace(target=target, observed_at=NOW,
                               values={signal: self.current.get(signal) for signal in signals})

    def range(self, target, signal, minutes, step_s):
        self.ranges.append((target, signal, minutes, step_s))
        return self.histories.get(signal, [])


def test_worker_status_uses_the_worker_container_capability():
    values = {"state": "running", "health": "healthy", "started_at": "S-START"}
    ports = FakePorts({("container.status", REFS["worker"]): obs("worker status", values)})

    result = run("worker status", ports)

    assert result.status == "ok" and result.output_lines == ["argus-lab-jobworker: state=running health=healthy since=S-START"]
    assert ports.calls == [("container.status", REFS["worker"], {})]


def test_worker_heartbeat_uses_the_named_metric_and_shows_age_and_last_processed_time():
    metrics = FakeMetrics({"worker_last_processed_age_s": 123})
    ports = FakePorts(metrics=metrics)

    result = run("worker heartbeat", ports)

    assert result.status == "ok"
    assert metrics.snapshots == [(TargetRef.parse(REFS["worker"]), {"worker_last_processed_age_s"})]
    assert "123" in result.output_lines[0] and "last_processed" in result.output_lines[0]


def test_worker_heartbeat_age_grows_across_successive_reads():
    metrics = FakeMetrics({"worker_last_processed_age_s": 180})
    ports = FakePorts(metrics=metrics)

    first = run("worker heartbeat", ports)
    metrics.current["worker_last_processed_age_s"] = 240
    second = run("worker heartbeat", ports)

    assert "180 s" in first.output_lines[0] and "240 s" in second.output_lines[0]


def test_worker_throughput_converts_the_current_rate_and_reads_an_earlier_rate():
    metrics = FakeMetrics({"jobs_processed_rate": 0.0},
                          {"jobs_processed_rate": [(NOW.timestamp() - 600, 0.5), (NOW.timestamp(), 0.0)]})
    ports = FakePorts(metrics=metrics)

    result = run("worker throughput", ports)

    assert result.status == "ok"
    assert "0 jobs/min" in result.output_lines[0] and "30 jobs/min" in result.output_lines[0]
    assert "10 min" in result.output_lines[0]
    assert metrics.ranges[0][1:] == ("jobs_processed_rate", 10, 30)


def test_queue_depth_reports_point_and_trend_from_range():
    metrics = FakeMetrics({"queue_depth": 18}, {"queue_depth": [(0, 4), (15, 8), (30, 18)]})
    ports = FakePorts(metrics=metrics)

    result = run("queue depth", ports)

    assert result.status == "ok" and "18" in result.output_lines[0] and "rising" in result.output_lines[0]
    assert metrics.ranges[0][1:] == ("queue_depth", 3, 15)


@pytest.mark.parametrize("command,signal", [("worker heartbeat", "worker_last_processed_age_s"),
                                              ("worker throughput", "jobs_processed_rate"),
                                              ("queue depth", "queue_depth")])
def test_worker_metric_commands_say_no_data_when_the_signal_is_missing(command, signal):
    result = run(command, FakePorts(metrics=FakeMetrics({signal: None})))

    assert result.status == "ok" and "no data yet" in "\n".join(result.output_lines)


@pytest.mark.parametrize("text", ["cache restart", "worker restart", "net reconnect api"])
def test_write_commands_are_rejected_and_nothing_runs(text):
    ports = FakePorts()
    result = run(text, ports)

    assert result.status == "rejected" and result.output_lines == ["write commands are not enabled yet"]
    assert ports.calls == []


@pytest.mark.parametrize("text", ["net inspect api", "net expected api", "net diff api"])
def test_scenario_2_and_4_reads_are_not_available_yet(text):
    ports = FakePorts()
    result = run(text, ports)

    assert result.status == "rejected" and "not available yet" in result.output_lines[0]
    assert ports.calls == []
