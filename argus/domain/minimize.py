"""ACR-0028 (OP-002 G-006): a read keeps only the value paths its capability declares.

A path is a top-level key (`"lines"`), a key inside the rows of a list (`"processes[].command"`) or a key inside an
object (`"limits.max_open_files"`). One level of nesting. Everything else is dropped before redaction, truncation and
storage; the caller audits the dropped paths' names, never their values.
"""
from __future__ import annotations

from typing import Any, Iterable


def parse_paths(paths: Iterable[str]) -> dict[str, tuple[str, frozenset[str]] | None]:
    """{top key: None (keep it whole) | ("[]" or ".", the inner keys kept)}. A bare key wins over its inner paths."""
    out: dict[str, tuple[str, frozenset[str]] | None] = {}
    inner: dict[str, tuple[str, set[str]]] = {}
    for p in paths:
        if "[]." in p:
            top, key, kind = *p.split("[].", 1), "[]"
        elif "." in p:
            top, key, kind = *p.split(".", 1), "."
        else:
            out[p] = None
            continue
        if not top or not key or "." in key or "[" in key:
            raise ValueError(f"allowed field {p!r}: one level of nesting, as 'a', 'a[].b' or 'a.b'")
        seen = inner.setdefault(top, (kind, set()))
        if seen[0] != kind:
            raise ValueError(f"allowed field {p!r}: {top} is declared both as a list and as an object")
        seen[1].add(key)
    for top, (kind, keys) in inner.items():
        out.setdefault(top, (kind, frozenset(keys)))
    return out


def minimize(values: Any, allowed: Iterable[str]) -> tuple[Any, list[str]]:
    """(the values with only the allowed paths, the sorted names of the dropped paths). A declared path the values do
    not have is simply absent; values that are not an object are dropped whole (named "*")."""
    if not isinstance(values, dict):
        return {}, ["*"]
    rules, dropped, kept = parse_paths(allowed), set(), {}
    for key, value in values.items():
        if key not in rules:
            dropped.add(key)
            continue
        rule = rules[key]
        if rule is None:
            kept[key] = value
        elif rule[0] == "[]":
            if not isinstance(value, list):
                dropped.add(f"{key}[]")
                continue
            rows = []
            for row in value:
                if not isinstance(row, dict):
                    dropped.add(f"{key}[]")
                    continue
                rows.append({k: v for k, v in row.items() if k in rule[1]})
                dropped.update(f"{key}[].{k}" for k in row if k not in rule[1])
            kept[key] = rows
        else:
            if not isinstance(value, dict):
                dropped.add(f"{key}.")
                continue
            kept[key] = {k: v for k, v in value.items() if k in rule[1]}
            dropped.update(f"{key}.{k}" for k in value if k not in rule[1])
    return kept, sorted(dropped)
