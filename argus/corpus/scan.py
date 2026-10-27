"""ACR-0034 layer 3 (scanner): a passage that looks written for the model, not for a reader, is quarantined.

Heuristics only in this version (a similarity check against known injections is designed, not built): text that
addresses an AI or rewrites its instructions, chat-role markers, the names of Argus's own tools and action cards, a
long encoded blob, and a download piped into a shell. A finding never edits the passage; it keeps it out of the
index (`quarantine.jsonl`) until a person reviews it. Ordinary commands of the docs (`docker run`, `systemctl`) pass.
"""
from __future__ import annotations

import re
from functools import lru_cache

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rewrites instructions", re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your|the)\b"
        r"[^.\n]{0,25}\b(instructions?|rules|prompts?|directions|guidelines)\b", re.I)),
    ("addresses an AI", re.compile(
        r"\byou are (now )?(an?|the) (ai|assistant|language model|llm|agent|chatbot)\b|"
        r"\b(language model|ai assistant|llm|chatbot|ai agent)\b[^.\n]{0,30}\b(reading|read this|should|must|will)\b|"
        r"\b(from now on|new instructions|as an ai)\b", re.I)),
    ("chat role marker", re.compile(r"^\s*(system|assistant)\s*:|<\|?(im_start|im_end|system|endoftext)\|?>",
                                    re.I | re.M)),
    ("asks to approve", re.compile(r"\bapprove (every|all|any) (actions?|requests?|proposals?)\b", re.I)),
    ("encoded blob", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")),
    ("download piped to a shell", re.compile(r"\b(curl|wget)\b[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z|da)?sh\b", re.I)),
    ("wipes the root", re.compile(r"\brm\s+-[a-z]*r[a-z]*f?[a-z]*\s+/(\s|$|\*)", re.I)),
)

# Argus's own tool and action names (the catalogue's model names are added at run time when importable)
_STATIC_NAMES = ("query_runbook", "query_reference", "query_prior_incidents", "suggest_action", "approve_action",
                 "start_container", "restart_container", "stop_container", "write_gate", "place_hold")


@lru_cache(maxsize=1)
def _argus_names() -> re.Pattern[str]:
    names = set(_STATIC_NAMES)
    try:
        from argus.capabilities.catalog import build_catalog
        names |= {s.model_name for s in build_catalog()}
    except Exception:                                    # noqa: BLE001 (the static list still applies)
        pass
    return re.compile(r"\b(" + "|".join(sorted(map(re.escape, names))) + r")\b")


def findings(text: str) -> list[str]:
    out = [name for name, rule in _RULES if rule.search(text)]
    if _argus_names().search(text):
        out.append("names an Argus tool")
    return out
