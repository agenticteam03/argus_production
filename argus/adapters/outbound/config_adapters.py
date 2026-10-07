"""InventoryPort (YAML), MetricsPort (Prometheus), KnowledgePort (TF-IDF over runbook library v1.1.0)."""
from __future__ import annotations

import hashlib
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from string import Template

import httpx
import yaml

from argus.domain.model import HostInfo, MetricSnapshot, Passage, TargetInfo, TargetRef
from argus.ports.ports import MetricsUnavailable, StaleMetrics


# --- Inventory ----------------------------------------------------------------------------------
class YamlInventory:
    def __init__(self, text: str):
        data = yaml.safe_load(text) or {}
        self._version = hashlib.sha256(text.encode()).hexdigest()
        self._hosts = {name: HostInfo(name=name, executors=(h or {}).get("executors", {}) or {})
                       for name, h in (data.get("hosts") or {}).items()}
        self._targets: dict[TargetRef, TargetInfo] = {}
        for t in data.get("targets") or []:
            ref = TargetRef.parse(t["ref"])
            if ref.host not in self._hosts:
                raise ValueError(f"inventory target {ref} names unknown host {ref.host}")
            self._targets[ref] = TargetInfo(ref=ref, scope=t.get("scope", "lab"),
                                            depends_on=[TargetRef.parse(d) for d in t.get("depends_on", [])],
                                            http_endpoints=t.get("http_endpoints", []),
                                            tcp_ports=t.get("tcp_ports", []), mounts=t.get("mounts", []),
                                            database=(t.get("database") or {}).get("dbname"))
        for info in self._targets.values():
            for d in info.depends_on:
                if d not in self._targets:
                    raise ValueError(f"{info.ref} depends on unknown target {d}")

    def hosts(self) -> list[HostInfo]:
        return list(self._hosts.values())

    def host(self, name: str) -> HostInfo | None:
        return self._hosts.get(name)

    def target(self, ref: TargetRef) -> TargetInfo | None:
        return self._targets.get(ref)

    def targets(self, host: str | None = None) -> list[TargetInfo]:
        return [t for t in self._targets.values() if host is None or t.ref.host == host]

    def neighbours(self, ref: TargetRef) -> list[TargetRef]:
        info = self._targets.get(ref)
        deps = list(info.depends_on) if info else []
        dependents = [t.ref for t in self._targets.values() if ref in t.depends_on]
        return deps + dependents

    def version(self) -> str:
        return self._version


# --- Metrics -----------------------------------------------------------------------------------
class PrometheusMetrics:
    """Signal names → PromQL templates with $host/$name. Per-series freshness (G-003/G-007)."""

    def __init__(self, inventory: YamlInventory, signals: dict[str, str], max_staleness_s: int = 90):
        self.inventory, self.signals, self.max_staleness_s = inventory, signals, max_staleness_s

    def _url(self, host: str) -> str:
        h = self.inventory.host(host)
        url = h.executors.get("prometheus") if h else None
        if not url:
            raise MetricsUnavailable(f"no prometheus executor for host {host}")
        return url.rstrip("/")

    def snapshot(self, target: TargetRef, signals: set[str]) -> MetricSnapshot:
        base = self._url(target.host)
        gate = self.signals.get("_scrape_up")
        if gate:
            # Monitoring blind spot (RB-014): range functions keep answering from older samples after the
            # exporter stops, so a partial snapshot could read as healthy. The scrape itself must be up.
            try:
                r = httpx.get(f"{base}/api/v1/query", params={"query": Template(gate).substitute(host=target.host)},
                              timeout=8)
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise MetricsUnavailable(f"prometheus at {base}: {type(e).__name__}") from e
            up = r.json().get("data", {}).get("result", [])
            if not up or any(float(x["value"][1]) < 1 for x in up):
                raise StaleMetrics(f"exporter scrape is down on {target.host} (monitoring blind spot)")
        values: dict[str, float | None] = {}
        newest: float | None = None
        now = time.time()
        for s in sorted(signals):
            if s not in self.signals:
                raise ValueError(f"unknown signal {s}")
            expr = Template(self.signals[s]).substitute(host=target.host, name=target.name)
            try:
                r = httpx.get(f"{base}/api/v1/query", params={"query": expr}, timeout=8)
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise MetricsUnavailable(f"prometheus at {base}: {type(e).__name__}") from e
            res = r.json().get("data", {}).get("result", [])
            if not res:
                values[s] = None
                continue
            ts, val = float(res[0]["value"][0]), float(res[0]["value"][1])
            # An instant query stamps the evaluation time; staleness of the underlying series is
            # handled by Prometheus' 5-minute lookback. A value older than the limit is treated as missing.
            values[s] = val if now - ts <= self.max_staleness_s else None
            newest = ts if newest is None else max(newest, ts)
        if all(v is None for v in values.values()):
            raise StaleMetrics(f"no fresh samples for {target} ({', '.join(sorted(signals))})")
        return MetricSnapshot(target=target, values=values,
                              observed_at=datetime.fromtimestamp(newest, timezone.utc) if newest else None)

    def range(self, target: TargetRef, signal: str, minutes: int, step_s: int) -> list[tuple[float, float]]:
        raise NotImplementedError("history is served by the metrics.* capabilities")


# --- Knowledge ---------------------------------------------------------------------------------
_WORD = re.compile(r"[a-z0-9_]{3,}")
_META = re.compile(r"```yaml\s*\n(.*?)\n```", re.S)


class TfidfRunbooks:
    """Runbook IDs come from metadata, never file names; sections longer than the bound are refused, not cut."""

    MAX_SECTION_CHARS = 2400

    PINNED_SECTIONS = ("Safety and approval contract",)

    def __init__(self, directory: str, library_version: str | None = None):
        root = Path(directory)
        if not root.is_dir():
            raise ValueError(f"runbook library not found at {root}")
        # The index and conventions sit next to the runbooks (argus/runbooks/) or, in the old library layout, one up.
        home = root if (root / "RUNBOOK-INDEX.md").is_file() else root.parent
        self.library_version = library_version or self._index_version(home / "RUNBOOK-INDEX.md")
        self.pinned_text = self._pinned(home / "RUNBOOK-CONVENTIONS.md")
        self.ids: set[str] = set()
        self.titles: dict[str, str] = {}                                  # id → title (metadata)
        self.sections: list[tuple[str, str, str, str, list[str]]] = []   # (id, version, status, section, text)
        for path in sorted(root.glob("RB-*.md")):
            text = path.read_text(encoding="utf-8")
            m = _META.search(text)
            meta = yaml.safe_load(m.group(1)) if m else {}
            rid = str(meta.get("id") or "")
            if not rid:
                continue
            self.ids.add(rid)
            self.titles[rid] = str(meta.get("title") or "")
            for chunk in re.split(r"\n(?=## )", text):
                title = chunk.splitlines()[0].lstrip("# ").strip() if chunk.strip() else ""
                if title.lower() in {"metadata", ""} or len(chunk) > self.MAX_SECTION_CHARS:
                    continue
                self.sections.append((rid, str(meta.get("version", "?")), str(meta.get("status", "?")),
                                      title, chunk.strip()))
        n = max(len(self.sections), 1)
        df: dict[str, int] = {}
        self._tf: list[dict[str, int]] = []
        for *_, body in self.sections:
            words = _WORD.findall(body.lower())
            tf: dict[str, int] = {}
            for w in words:
                tf[w] = tf.get(w, 0) + 1
            self._tf.append(tf)
            for w in tf:
                df[w] = df.get(w, 0) + 1
        self._idf = {w: math.log(n / c) + 1 for w, c in df.items()}

    @staticmethod
    def _index_version(index: Path) -> str | None:
        try:
            m = re.search(r"Library version ([0-9.]+)", index.read_text(encoding="utf-8"))
            return f"library {m.group(1)}" if m else None
        except OSError:
            return None

    def _pinned(self, conventions: Path) -> str:
        try:
            text = conventions.read_text(encoding="utf-8")
        except OSError:
            return ""
        parts = [c.strip() for c in re.split(r"\n(?=## )", text)
                 if c.lstrip("# ").startswith(self.PINNED_SECTIONS)]
        return "\n\n".join(parts)[:3000]

    def search(self, query: str, k: int, runbook_ids: list[str] | None = None) -> list[Passage]:
        q = _WORD.findall(query.lower())
        scored = []
        for (rid, ver, status, sec, body), tf in zip(self.sections, self._tf):
            if runbook_ids and rid not in runbook_ids:
                continue
            score = sum(tf.get(w, 0) * self._idf.get(w, 0) for w in q) / (1 + math.log(1 + sum(tf.values())))
            scored.append((score, rid, ver, status, sec, body))
        scored.sort(key=lambda x: -x[0])
        return [Passage(runbook_id=r, runbook_version=v, runbook_status=st, section=se, text=b, score=round(s, 3))
                for s, r, v, st, se, b in scored[:k] if s > 0]
