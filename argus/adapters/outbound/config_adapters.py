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

from argus.domain.model import DependencyLink, HostInfo, MetricSnapshot, Passage, TargetInfo, TargetRef
from argus.ports.ports import MetricsUnavailable, ProbeSample, StaleMetrics


# --- Inventory ----------------------------------------------------------------------------------
class YamlInventory:
    def __init__(self, text: str):
        data = yaml.safe_load(text) or {}
        self._version = hashlib.sha256(text.encode()).hexdigest()
        self._hosts = {name: HostInfo(name=name, executors=(h or {}).get("executors", {}) or {},
                                      alertmanager=(h or {}).get("alertmanager"))       # ACR-0003: not an executor
                       for name, h in (data.get("hosts") or {}).items()}
        self._targets: dict[TargetRef, TargetInfo] = {}
        for t in data.get("targets") or []:
            ref = TargetRef.parse(t["ref"])
            for m in t.get("mounts", []):            # T-0024: mounts fill a PromQL regex ($mounts): plain paths only
                if not _MOUNT.fullmatch(m):
                    raise ValueError(f"inventory target {ref}: mount {m!r} is not a plain absolute path")
            if ref.host not in self._hosts:
                raise ValueError(f"inventory target {ref} names unknown host {ref.host}")
            if t.get("profile") not in (None, "scenario"):
                raise ValueError(f"inventory target {ref}: profile must be 'scenario', not {t['profile']!r}")
            warn = t.get("link_warning_ms")
            if warn is not None and (isinstance(warn, bool) or not isinstance(warn, (int, float)) or warn <= 0):
                raise ValueError(f"inventory target {ref}: link_warning_ms must be a positive number")
            _observable(ref, t.get("process"))
            service = t.get("service")
            if service is not None:
                from argus.actions.catalog import ACTION_CATALOGUE, NEVER_OFFERED_ACTIONS
                from argus.domain.service_card import ServiceCard
                card = ServiceCard.from_dict(service)
                declared = set(card.safe_actions) | set(card.never)
                unknown = declared - set(ACTION_CATALOGUE)
                if unknown or set(card.safe_actions) & NEVER_OFFERED_ACTIONS:
                    raise ValueError(f"inventory target {ref}: service card has unsupported actions")
            links = [_dependency_link(ref, d) for d in t.get("depends_on", [])]
            refs = [str(x.ref) for x in links]
            if len(refs) != len(set(refs)):         # one link per dependency: link() would keep the first silently
                twice = sorted({r for r in refs if refs.count(r) > 1})
                raise ValueError(f"inventory target {ref}: depends_on names {', '.join(twice)} twice "
                                 f"(one link per dependency)")
            self._targets[ref] = TargetInfo(ref=ref, scope=t.get("scope", "lab"),
                                            depends_on=[x.ref for x in links], links=links,
                                            http_endpoints=t.get("http_endpoints", []),
                                            tcp_ports=t.get("tcp_ports", []), mounts=t.get("mounts", []),
                                            networks=t.get("networks", []),
                                            database=(t.get("database") or {}).get("dbname"),
                                            profile=t.get("profile"),
                                            link_warning_ms=None if warn is None else float(warn),
                                            service=service, process=t.get("process"))
        for info in self._targets.values():
            for d in info.depends_on:
                if d not in self._targets:
                    raise ValueError(f"{info.ref} depends on unknown target {d}")
            for x in info.links:                 # ACR-0025: a declared port must be one the dependency lists
                if x.port is not None and x.port not in self._targets[x.ref].tcp_ports:
                    raise ValueError(f"{info.ref} depends on {x.ref} port {x.port}, which {x.ref} does not list "
                                     f"in tcp_ports {self._targets[x.ref].tcp_ports}")

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


def _dependency_link(owner: TargetRef, entry) -> DependencyLink:
    """ACR-0025: a `depends_on` entry is a plain ref, or `{ref, port, required}`. Links are per host (host isolation:
    a cross-host link is never probed), and a host dependency has no port (it is never probed either)."""
    if isinstance(entry, str):
        link = DependencyLink(ref=TargetRef.parse(entry))
    elif isinstance(entry, dict) and "ref" in entry and not set(entry) - {"ref", "port", "required"}:
        port, required = entry.get("port"), entry.get("required", True)
        if port is not None and (isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536):
            raise ValueError(f"inventory target {owner}: depends_on {entry['ref']}: port must be a TCP port number")
        if not isinstance(required, bool):
            raise ValueError(f"inventory target {owner}: depends_on {entry['ref']}: required must be true or false")
        link = DependencyLink(ref=TargetRef.parse(entry["ref"]), port=port, required=required)
        if port is not None and link.ref.kind == "host":
            raise ValueError(f"inventory target {owner}: depends_on {link.ref}: a host dependency has no port")
    else:
        raise ValueError(f"inventory target {owner}: a depends_on entry is a ref or {{ref, port, required}}, "
                         f"not {entry!r}")
    if link.ref.host != owner.host:
        raise ValueError(f"inventory target {owner}: depends_on {link.ref} is on another host (links are per host)")
    return link


_UNIT = re.compile(r"[A-Za-z0-9@_.:-]+\.service")
_PIDFILE = re.compile(r"/[A-Za-z0-9_./-]*")


def _observable(ref: TargetRef, process: dict | None) -> None:
    """ACR-0044: a service or process target is one the host probe can find. A service is a systemd unit named
    `<name>.service`; a process is found by its command name (comm, at most 15 characters, as the kernel keeps it) or
    by a pidfile, exactly one of them. Never a command line: it can hold secrets."""
    if ref.kind == "service" and not _UNIT.fullmatch(ref.name):
        raise ValueError(f"inventory target {ref}: a service is a systemd unit and must end in .service")
    if process is not None and ref.kind != "process":
        raise ValueError(f"inventory target {ref}: `process` is allowed on only a process target")
    if ref.kind != "process":
        return
    keys = set(process or {})
    if len(keys) != 1 or not keys <= {"comm", "pidfile"}:
        raise ValueError(f"inventory target {ref}: `process` needs exactly one of comm or pidfile")
    comm, pidfile = process.get("comm"), process.get("pidfile")
    if comm is not None and not (isinstance(comm, str) and 0 < len(comm) <= 15 and "/" not in comm):
        raise ValueError(f"inventory target {ref}: comm is the kernel's command name, at most 15 characters")
    if pidfile is not None and not (isinstance(pidfile, str) and _PIDFILE.fullmatch(pidfile) and ".." not in pidfile):
        raise ValueError(f"inventory target {ref}: pidfile must be a plain absolute path")


# --- Metrics -----------------------------------------------------------------------------------
_MOUNT = re.compile(r"/[A-Za-z0-9_/-]*")
class PrometheusMetrics:
    """Signal names → PromQL templates with $host/$kind/$name. Per-series freshness (G-003/G-007)."""

    LINK_HISTORY_STEP_S = 5                 # oversamples the configured 15 s scrape; duplicate source samples collapse
    LINK_HISTORY_MAX_S = 4 * 60 * 60         # maximum cursor replay range; older gaps become unknown

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
        info = self.inventory.target(target)
        mounts = "|".join(info.mounts) if info else ""      # validated plain paths; none: matches no series
        values: dict[str, float | None] = {}
        newest: float | None = None
        now = time.time()
        for s in sorted(signals):
            if s not in self.signals:
                raise ValueError(f"unknown signal {s}")
            expr = Template(self.signals[s]).substitute(host=target.host, kind=target.kind, name=target.name, mounts=mounts)
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

    def range(self, target: TargetRef, signal: str, minutes: int, step_s: int,
              end: datetime | None = None) -> list[tuple[float, float]]:
        """ACR-0017: one named signal over `minutes` ending at `end` (None = now), one sample per `step_s`. Only the
        target's own host's Prometheus; a missing step is simply absent (the caller shows a gap, never 0)."""
        if signal not in self.signals:
            raise ValueError(f"unknown signal {signal}")
        info = self.inventory.target(target)
        mounts = "|".join(info.mounts) if info else ""
        expr = Template(self.signals[signal]).substitute(host=target.host, kind=target.kind, name=target.name, mounts=mounts)
        stop = (end or datetime.now(timezone.utc)).timestamp()
        try:
            r = httpx.get(f"{self._url(target.host)}/api/v1/query_range",
                          params={"query": expr, "start": stop - minutes * 60, "end": stop, "step": step_s}, timeout=8)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise MetricsUnavailable(f"prometheus for {target.host}: {type(e).__name__}") from e
        result = r.json().get("data", {}).get("result", [])
        if not result:
            return []
        return [(float(t), float(v)) for t, v in result[0]["values"]]

    def dependency_probes(self, target: TargetRef) -> dict[str, ProbeSample]:
        """ACR-0021: the owner's probes by dependency, from the target exporter's own `argus_probe_success` and
        `argus_probe_duration_seconds` (catalogue signals), on the target's own host. A sample older than
        `max_staleness_s` is missing (success None), never 0. An instant query stamps a value with the evaluation time,
        not the sample's (as `snapshot`): against a real Prometheus `at` is the read time and the age check does not
        trigger; a stopped exporter still reads as missing through Prometheus' staleness markers (5-minute lookback)."""
        base, now = self._url(target.host), time.time()
        found: dict[str, dict[str, tuple[float, float]]] = {}
        kinds: dict[str, tuple[float, str]] = {}
        for field, signal in (("success", "dependency_probe_success"), ("duration", "dependency_probe_duration_s"),
                              ("error", "dependency_probe_error")):
            expr = Template(self.signals[signal]).substitute(host=target.host, kind=target.kind, name=target.name, mounts="")
            try:
                r = httpx.get(f"{base}/api/v1/query", params={"query": expr}, timeout=8)
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise MetricsUnavailable(f"prometheus at {base}: {type(e).__name__}") from e
            for series in r.json().get("data", {}).get("result", []):
                dep = (series.get("metric") or {}).get("dependency")
                if dep and field == "error":                # T-0045 B8: the failure kind is a label, not a value
                    kinds[dep] = (float(series["value"][0]), (series.get("metric") or {}).get("kind") or "other")
                elif dep:
                    found.setdefault(dep, {})[field] = (float(series["value"][0]), float(series["value"][1]))
        out: dict[str, ProbeSample] = {}
        for dep, parts in found.items():
            stamps = [ts for ts, _ in parts.values()]
            at = datetime.fromtimestamp(max(stamps), timezone.utc)
            fresh = now - max(stamps) <= self.max_staleness_s
            ok = parts.get("success")
            took = parts.get("duration")
            kind = kinds.get(dep)
            out[dep] = ProbeSample(ok[1] if ok and fresh and now - ok[0] <= self.max_staleness_s else None,
                                   took[1] if took and now - took[0] <= self.max_staleness_s else None, at,
                                   kind[1] if kind and now - kind[0] <= self.max_staleness_s else None)
        return out

    def dependency_probe_history(self, target: TargetRef, start: datetime,
                                 end: datetime) -> dict[str, list[ProbeSample]]:
        """Every distinct exporter sample in (start, end], oldest first (T-0046).

        `query_range` timestamps are evaluation times, so pair each series with `timestamp(series)` and retain the
        source scrape time. Five-second evaluations ensure each configured 15-second scrape is observed between
        scheduler ticks; repeated evaluations of the same scrape are collapsed. The exporter remains the only probe.
        """
        base = self._url(target.host)
        names = ("dependency_probe_success", "dependency_probe_duration_s", "dependency_probe_error")
        exprs = {name: Template(self.signals[name]).substitute(host=target.host, kind=target.kind, name=target.name, mounts="")
                 for name in names}

        def query(expr: str) -> list[dict]:
            try:
                response = httpx.get(f"{base}/api/v1/query_range", params={
                    "query": expr, "start": start.timestamp(), "end": end.timestamp(),
                    "step": f"{self.LINK_HISTORY_STEP_S}s",
                }, timeout=8)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise MetricsUnavailable(f"prometheus at {base}: {type(exc).__name__}") from exc
            return response.json().get("data", {}).get("result", [])

        def grid(rows: list[dict], dimensions: tuple[str, ...]) -> dict[tuple[str, ...], dict[float, float]]:
            out: dict[tuple[str, ...], dict[float, float]] = {}
            for row in rows:
                labels = row.get("metric") or {}
                key = tuple(labels.get(label, "") for label in dimensions)
                for evaluated_at, value in row.get("values", []):
                    out.setdefault(key, {})[round(float(evaluated_at), 3)] = float(value)
            return out

        raw_success = grid(query(exprs["dependency_probe_success"]), ("dependency",))
        source_success = grid(query(f"timestamp({exprs['dependency_probe_success']})"), ("dependency",))
        raw_duration = grid(query(exprs["dependency_probe_duration_s"]), ("dependency",))
        source_duration = grid(query(f"timestamp({exprs['dependency_probe_duration_s']})"), ("dependency",))
        raw_error = grid(query(exprs["dependency_probe_error"]), ("dependency", "kind"))
        source_error = grid(query(f"timestamp({exprs['dependency_probe_error']})"), ("dependency", "kind"))

        start_ts, end_ts = start.timestamp(), end.timestamp()
        result: dict[str, list[ProbeSample]] = {}
        for (dependency,), success_points in raw_success.items():
            source_points = source_success.get((dependency,), {})
            duration_points = raw_duration.get((dependency,), {})
            duration_times = source_duration.get((dependency,), {})
            seen: set[float] = set()
            samples = []
            for evaluated_at in sorted(success_points):
                source_at = source_points.get(evaluated_at)
                if source_at is None or not start_ts < source_at <= end_ts or source_at in seen:
                    continue
                seen.add(source_at)
                duration = duration_points.get(evaluated_at)
                if duration is not None and not math.isclose(duration_times.get(evaluated_at, -1), source_at,
                                                             rel_tol=0, abs_tol=0.001):
                    duration = None
                error_kind = next((kind for (dep, kind), points in raw_error.items()
                                   if dep == dependency and points.get(evaluated_at) is not None
                                   and math.isclose(source_error.get((dep, kind), {}).get(evaluated_at, -1), source_at,
                                                    rel_tol=0, abs_tol=0.001)), None)
                samples.append(ProbeSample(success_points[evaluated_at], duration,
                                           datetime.fromtimestamp(source_at, timezone.utc), error_kind))
            if samples:
                result[dependency] = samples
        return result


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
