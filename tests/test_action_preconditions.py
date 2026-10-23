"""Tests for the safe precondition expression interpreter (ACR-0019 §3.4).

Evaluates action preconditions against observation dictionaries without using `eval` or `exec`.
"""
from __future__ import annotations

import inspect
import pytest

from argus.actions.preconditions import (
    evaluate_precondition,
    PreconditionSyntaxError,
)


def test_interpreter_does_not_use_eval_or_exec():
    import argus.actions.preconditions as module
    source = inspect.getsource(module)
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source


@pytest.mark.parametrize(
    ("expr", "context", "expected"),
    [
        # Basic equality and inequality
        ('status == "running"', {"status": "running"}, True),
        ('status == "running"', {"status": "exited"}, False),
        ('status != "running"', {"status": "exited"}, True),
        ('exit_code == 137', {"exit_code": 137}, True),
        ('exit_code == 137', {"exit_code": 0}, False),

        # Numeric comparisons
        ("restarts_10m >= 5", {"restarts_10m": 5}, True),
        ("restarts_10m >= 5", {"restarts_10m": 4}, False),
        ("memory_mb > 64", {"memory_mb": 128}, True),
        ("memory_mb < 64", {"memory_mb": 64}, False),
        ("memory_mb <= 64", {"memory_mb": 64}, True),

        # Membership
        ('"rw" in mounts', {"mounts": ["ro", "rw"]}, True),
        ('"ro" in mounts', {"mounts": ["rw"]}, False),
        ('"prod" not in tags', {"tags": ["dev", "test"]}, True),
        ('"dev" not in tags', {"tags": ["dev", "test"]}, False),

        # Boolean logic: and, or, not
        ('status == "exited" and exit_code == 137', {"status": "exited", "exit_code": 137}, True),
        ('status == "exited" and exit_code == 137', {"status": "exited", "exit_code": 1}, False),
        ('status == "exited" or status == "stopped"', {"status": "stopped"}, True),
        ('status == "exited" or status == "stopped"', {"status": "running"}, False),
        ('not (status == "running")', {"status": "stopped"}, True),
        ('not (status == "running")', {"status": "running"}, False),

        # Nested paths
        ('container.state.running == True', {"container": {"state": {"running": True}}}, True),
        ('container.state.running == False', {"container": {"state": {"running": True}}}, False),
        ('target.health.status == "unhealthy"', {"target": {"health": {"status": "unhealthy"}}}, True),
    ],
)
def test_valid_precondition_evaluations(expr: str, context: dict, expected: bool):
    assert evaluate_precondition(expr, context) is expected


def test_missing_attribute_evaluates_to_false_or_handles_safely():
    # If the observation lacks a path, comparison with missing value does not crash
    assert evaluate_precondition('non_existent == "val"', {}) is False
    assert evaluate_precondition('non_existent.nested == 10', {}) is False
    assert evaluate_precondition('not status', {}) is False
    assert evaluate_precondition('not (status == "running")', {}) is False


def test_observation_paths_do_not_invoke_object_properties():
    class HostileObservation:
        @property
        def status(self):
            raise AssertionError("property executed")

    with pytest.raises(PreconditionSyntaxError):
        evaluate_precondition('container.status == "running"', {"container": HostileObservation()})


@pytest.mark.parametrize(
    "malicious_expr",
    [
        "__import__('os').system('ls')",
        "eval('1 + 1')",
        "exec('a = 1')",
        "open('/etc/passwd').read()",
        "len([1, 2, 3]) == 3",             # function calls disallowed
        "status.__class__.__name__ == 'str'",  # dunder access disallowed
        "x = 10",                           # assignment disallowed
        "import os",                        # statements disallowed
        "lambda: True",                     # lambdas disallowed
    ],
)
def test_unsafe_and_disallowed_expressions_raise_syntax_error(malicious_expr: str):
    with pytest.raises(PreconditionSyntaxError):
        evaluate_precondition(malicious_expr, {"status": "running"})
