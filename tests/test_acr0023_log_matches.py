"""ACR-0023: a log read also brings the window's lines that match a named failure pattern and are not in its tail."""
from argus.capabilities.catalog import LogsArgs, container_logs
from argus.capabilities.spec import ExecutorError
from argus.domain.model import TargetRef
from argus.evaluation.replay import FixtureExecutor

API = TargetRef.parse("vm-166/container:argus-lab-api")
CAUSE = "KeyError: 'FEATURE_FLAGS' in settings.load()"
NOISE = [f"GET /items 500 ({i})" for i in range(120)]


def _read(lines, **kw):
    return container_logs(LogsArgs(**kw), API, None, FixtureExecutor({"/containers/argus-lab-api/log": {"lines": lines}}))


def test_a_cause_outside_the_tail_reaches_the_model_text_with_its_count():
    r = _read([CAUSE, "connection timed out to cache"] + NOISE)
    assert r.model_text.startswith("vm-166/container:argus-lab-api: last 50 log lines; ")   # the disk rule reads this
    assert "error×1" in r.model_text and "timeout×1" in r.model_text
    assert CAUSE in r.model_text and "connection timed out to cache" in r.model_text
    assert r.values["earlier_matches"] == {"counts": {"error": 1, "timeout": 1},
                                           "lines": [CAUSE, "connection timed out to cache"]}


def test_a_match_already_in_the_tail_is_not_repeated():
    r = _read(NOISE + [CAUSE])
    assert r.model_text == "vm-166/container:argus-lab-api: last 50 log lines"
    assert "earlier_matches" not in r.values


def test_a_line_matching_two_patterns_is_shown_once_and_at_most_six_lines_in_all():
    both = "error: upstream timed out"
    r = _read([both] + [f"refused {i}" for i in range(9)] + NOISE)
    assert r.values["earlier_matches"]["counts"] == {"error": 1, "timeout": 1, "refused": 9}
    assert r.values["earlier_matches"]["lines"].count(both) == 1
    assert len(r.values["earlier_matches"]["lines"]) <= 6


class _NoSearch:
    def __init__(self, inner):
        self.inner = inner

    def get(self, path, params=None):
        if path.endswith("/search"):
            raise ExecutorError("unreachable", path)
        return self.inner.get(path, params)


def test_a_failed_search_leaves_the_tail_read_as_it_was():
    fx = FixtureExecutor({"/containers/argus-lab-api/log": {"lines": [CAUSE] + NOISE}})
    r = container_logs(LogsArgs(), API, None, _NoSearch(fx))
    assert r.model_text == "vm-166/container:argus-lab-api: last 50 log lines"
    assert "earlier_matches" not in r.values


def test_ordinary_lines_add_nothing():
    r = _read(["GET /health 200", "starting worker", "cache warm"] * 40)
    assert "earlier" not in r.model_text
