"""Signal thresholds for the UI (ACR-0021, T-0045 B1): where a gauge or a chart draws its warning and critical lines.

They live beside the PromQL templates in `config/signals.yaml` under a `thresholds:` key and are validated at startup
(a bad entry stops the API). They are display values: `critical` equals the detector's own threshold where a detector
uses the signal (a test pins it), so the line the UI draws is the line at which Argus opens an incident.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

DIRECTIONS = ("above", "below")
FIELDS = {"warning", "critical", "direction"}


@dataclass(frozen=True)
class Threshold:
    warning: float
    critical: float
    direction: str                      # "above": worse as the value rises; "below": worse as it falls

    def as_dict(self) -> dict:
        return {"warning": self.warning, "critical": self.critical, "direction": self.direction}

    def complement(self) -> "Threshold":
        """The same lines for 1 - value (an available ratio shown as a used ratio)."""
        flipped = "below" if self.direction == "above" else "above"
        return Threshold(round(1 - self.warning, 10), round(1 - self.critical, 10), flipped)


def _number(v) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool)


class Thresholds:
    def __init__(self, by_signal: dict[str, Threshold] | None = None):
        self._by_signal = dict(by_signal or {})

    @classmethod
    def from_data(cls, data, signals: set[str]) -> "Thresholds":
        """`data`: the `thresholds:` map of signals.yaml (or None). ValueError naming every bad entry."""
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("signals.yaml thresholds: must be a map of signal name to {warning, critical, direction}")
        problems, out = [], {}
        for name, entry in data.items():
            if name not in signals:
                problems.append(f"{name}: unknown signal")
                continue
            if not isinstance(entry, dict):
                problems.append(f"{name}: must be a map of warning, critical and direction")
                continue
            if set(entry) - FIELDS:
                problems.append(f"{name}: unknown field {sorted(set(entry) - FIELDS)}")
                continue
            if entry.get("direction") not in DIRECTIONS:
                problems.append(f"{name}: direction must be one of {list(DIRECTIONS)}")
                continue
            bad = [f for f in ("warning", "critical") if not _number(entry.get(f))]
            if bad:
                problems.append(f"{name}: {' and '.join(bad)} must be a number")
                continue
            w, c, d = entry["warning"], entry["critical"], entry["direction"]
            if (d == "above" and w > c) or (d == "below" and w < c):
                problems.append(f"{name}: warning {w} is past critical {c} for direction {d}")
                continue
            out[name] = Threshold(w, c, d)
        if problems:
            raise ValueError("signals.yaml thresholds: " + "; ".join(problems))
        return cls(out)

    def get(self, signal: str) -> Threshold | None:
        return self._by_signal.get(signal)

    def signals(self) -> list[str]:
        return sorted(self._by_signal)
