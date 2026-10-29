from __future__ import annotations

import pytest

from argus.console.parser import ConsoleRefused, parse
from argus.console.registry import COMMANDS, LAB_SERVICES, WRITE, catalog, help_lines


def test_help_lists_every_command():
    lines = help_lines()
    assert lines[0] == "Available commands:"
    assert len(lines) == len(COMMANDS) + 1
    assert any("cache restart" in line and "needs approval" in line for line in lines)
    assert len(catalog()) == len(COMMANDS)


@pytest.mark.parametrize("text", ["ls", "rm -rf x", "cat passwd", "docker ps"])
def test_unknown_verbs_are_not_found(text):
    with pytest.raises(ConsoleRefused, match="command not found"):
        parse(text)


@pytest.mark.parametrize("text", [
    "status; rm", "status && ls", "status | cat", "status > f", "status $(id)", "status `id`", "cache status\nrm",
    "status 'x'", 'status "x"', "map ../api", "cache  status # c", "map {api}", "status\\x"])
def test_shell_syntax_is_rejected_before_anything_runs(text):
    with pytest.raises(ConsoleRefused, match="syntax not allowed"):
        parse(text)


def test_plain_commands_parse_and_normalise():
    p = parse("  Cache   STATUS ")
    assert (p.id, p.cls, p.args, p.text) == ("cache.status", "read", {}, "cache status")
    assert parse("host metrics").id == "host.metrics"
    assert parse("queue depth").id == "queue.depth"


def test_service_argument_is_checked_against_the_lab():
    assert parse("map api").args == {"service": "api"}
    assert parse("net diff api").args == {"service": "api"}
    for text in ("map db", "map argus-lab-api", "net inspect prod"):
        with pytest.raises(ConsoleRefused, match="unknown service"):
            parse(text)
    with pytest.raises(ConsoleRefused, match="usage"):
        parse("map")
    assert set(LAB_SERVICES) == {"cache", "api", "worker"}


def test_since_option():
    assert parse("api cpu --since 10:30").args == {"since": "10:30"}
    assert parse("api errors").args == {}
    for text in ("api cpu --since 25:00", "api cpu --since", "api cpu --since 9:5"):
        with pytest.raises(ConsoleRefused, match="HH:MM"):
            parse(text)
    with pytest.raises(ConsoleRefused, match="unexpected argument"):
        parse("host metrics --since 10:30")


def test_unknown_subcommand_and_extra_words():
    with pytest.raises(ConsoleRefused, match="unknown subcommand for cache"):
        parse("cache delete")
    with pytest.raises(ConsoleRefused, match="unexpected argument"):
        parse("cache restart now")


def test_empty_and_long_input():
    for text in ("", "   ", None):
        with pytest.raises(ConsoleRefused):
            parse(text)
    with pytest.raises(ConsoleRefused, match="too long"):
        parse("status " + "a" * 300)


def test_write_commands_are_exactly_the_three_scenario_fixes():
    writes = {c.id for c in COMMANDS if c.cls == WRITE}
    assert writes == {"cache.restart", "worker.restart", "net.reconnect"}
    for c in COMMANDS:
        if c.cls == WRITE:
            assert c.settle_s >= 45 and not c.service_arg and not c.since
    assert parse("net reconnect api").cls == "write"
    with pytest.raises(ConsoleRefused):
        parse("net reconnect cache")
