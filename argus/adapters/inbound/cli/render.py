"""Two output modes for the same run (stdlib only).

formatted — a human-readable view of the REAL v1.8 node sequence, built only from run events
raw       — every run event as a JSON line, then the full incident record (evidence + audit) as JSON
No stage is invented: each block header is the name of the v1.8 node that emitted the event.
"""
from __future__ import annotations

import json
import shutil
import textwrap

_COLORS = {"b": "\033[1m", "d": "\033[2m", "r": "\033[31m", "g": "\033[32m", "y": "\033[33m",
           "bl": "\033[34m", "m": "\033[35m", "c": "\033[36m", "x": "\033[0m"}
EXECUTOR_TAG = {"docker_read": ("bl", "docker"), "host_probe": ("m", "host"), "network_probe": ("c", "net"), "db_probe": ("g", "db"),
                "prometheus": ("y", "metric"), "argus_internal": ("d", "argus"), "none": ("r", "policy")}
OUTCOME = {"diagnosed": ("g", "DIAGNOSED"), "no_incident": ("g", "HEALTHY — nothing to do"),
           "unsupported_escalated": ("y", "UNSUPPORTED → escalated to a human with evidence"),
           "undiagnosable": ("y", "UNDIAGNOSABLE → escalated (metrics missing)"),
           "no_action_escalated": ("y", "ESCALATED to a human"), "refused": ("r", "REFUSED")}


class Formatter:
    def __init__(self, color: bool = True, width: int | None = None):
        self.c = _COLORS if color else {k: "" for k in _COLORS}
        self.w = width or min(shutil.get_terminal_size((100, 30)).columns, 110)
        self._last_node: str | None = None

    def _k(self, key: str, text: str) -> str:
        return f"{self.c[key]}{text}{self.c['x']}"

    def header(self, node: str) -> list[str]:
        self._last_node = node
        return ["", self._k("b", f"▌ {node.upper()}") + self._k("d", "  " + "─" * max(0, self.w - len(node) - 4))]

    def event(self, ev: dict) -> list[str]:
        node, phase, d = ev["node"], ev["phase"], ev.get("data", {})
        out: list[str] = []
        if node != self._last_node and phase in ("enter", "step") or (node == "record" and node != self._last_node):
            out += self.header(node)
        if node == "detect" and phase == "enter":
            out.append(f"  target {self._k('c', d.get('target', '?'))}  ·  host {self._k('b', d.get('host', '?'))}"
                       f"  ·  trigger {d.get('trigger')}/{d.get('request')}")
            out.append(self._k("d", "  scope: " + ", ".join(d.get("scope", []))))
        elif node == "detect" and phase == "exit":
            sig = d.get("signals") or {}
            if sig:
                shown = ", ".join(f"{k}={'unknown' if v is None else v}" for k, v in sig.items())
                out.append(self._k("d", f"  signals: {shown}"))
            result = d.get("result")
            color = "g" if result not in ("no class matched", "undiagnosable") else "y"
            out.append(f"  class: {self._k(color, str(result))}" + (f"  ·  strategy {d['strategy']}" if d.get("strategy") else ""))
            for f in d.get("findings", []):
                out.append(f"  • {f}")
            out.append(self._k("d", f"  → next: {d.get('next')}"))
        elif node == "recall" and phase == "exit":
            ps = d.get("passages", [])
            if not ps:
                out.append(self._k("y", "  no runbook passage retrieved"))
            for p in ps:
                out.append(f"  📖 {self._k('b', p['runbook_id'])} v{p['version']} ({p['status']}) — {p['section']}"
                           + self._k("d", f"  sha256 {p['sha256'][:12]}"))
            if d.get("library"):
                out.append(self._k("d", f"  runbook library: {d['library']}"))
        elif node == "investigate" and phase == "exit":
            dec, who = d.get("decision", {}), d.get("decided_by")
            who_txt = self._k("m", "AI model") if who == "model" else self._k("d", "rule")
            kind = dec.get("kind")
            if kind == "use_read_tools":
                calls = ", ".join(f"{c['capability']}({c['arguments'].get('target', '')})" for c in dec.get("calls", []))
                out.append(f"  step {d.get('step')} · {who_txt} decides: read → {calls}")
            elif kind == "conclude":
                out.append(f"  step {d.get('step')} · {who_txt} decides: {self._k('g', 'conclude')} "
                           f"(confidence {dec.get('confidence')}, root cause {dec.get('root_cause_target')})")
            elif kind == "escalate":
                out.append(f"  step {d.get('step')} · {who_txt} decides: {self._k('y', 'escalate')} — {dec.get('reason', '')[:120]}")
            elif kind == "invalid":
                out.append(f"  step {d.get('step')} · {who_txt}: {self._k('r', 'invalid decision')} "
                           f"({dec.get('reason')}) {dec.get('detail', '')[:100]}")
        elif node in ("act", "evidence_pack") and phase == "step":
            color, tag = EXECUTOR_TAG.get(d.get("executor") or "none", ("d", d.get("executor", "?")))
            ok = d.get("status") == "ok"
            mark = self._k("g", "✓") if ok else self._k("r", "✗ " + str(d.get("status")))
            out.append(f"  {self._k(color, f'[{tag:>6}@{d.get('host')}]')} {self._k('b', f'{d.get('tool', ''):<24}')} {mark} "
                       + self._k("d", str(d.get("result", ""))[: max(20, self.w - 46)]))
        elif node == "record" and phase == "exit":
            color, label = OUTCOME.get(str(d.get("outcome")), ("y", str(d.get("outcome"))))
            out.append(f"  outcome: {self._k(color, self._k('b', label))}"
                       + (f"  ·  class {d['incident_class']}" if d.get("incident_class") else ""))
            if d.get("root_cause_target"):
                out.append(f"  root cause: {self._k('r', self._k('b', d['root_cause_target']))}  ·  confidence {d.get('confidence')}")
            out += self.box("diagnosis", d.get("diagnosis") or "—", color)
            if d.get("cited"):
                out.append(self._k("d", "  cited evidence: " + ", ".join(d["cited"])))
        return out

    def box(self, label: str, text: str, color: str) -> list[str]:
        inner = self.w - 6
        lines = textwrap.wrap(text, inner) or ["—"]
        top = self._k(color, f"  ┌─ {label} " + "─" * max(0, self.w - len(label) - 7) + "┐")
        body = [self._k(color, "  │") + f" {ln.ljust(inner + 1)}" + self._k(color, "│") for ln in lines]
        return [top, *body, self._k(color, "  └" + "─" * (self.w - 4) + "┘")]


def raw_event(ev: dict) -> str:
    return json.dumps(ev, ensure_ascii=False, default=str)


def raw_incident(incident: dict) -> str:
    return json.dumps(incident, indent=2, ensure_ascii=False, default=str)
