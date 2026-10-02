"""Settings and the composition root — the ONLY place that assembles concrete adapters (v1.8 §2.3 rule 14)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from argus.adapters.outbound.config_adapters import PrometheusMetrics, TfidfRunbooks, YamlInventory
from argus.adapters.outbound.llm import OpenAIChat, OpenAIResponses
from argus.adapters.outbound.sqlite_store import SqliteStore
from argus.application.invoke_capability import InvokeCapability
from argus.capabilities.catalog import build_catalog
from argus.capabilities.redaction import Redactor
from argus.detectors.classes import CLASSES
from argus.orchestration.runner import SkeletonRunner
from argus.orchestration.strategies import EvidencePackStrategy, ModelLoopStrategy, PlanThenReasonStrategy
from argus.policy.engine import PolicyEngine
from argus.tooling.dispatch import DirectProvider, Dispatcher
from argus.tooling.executors import ExecutorRegistry, PrometheusClient, TargetAgentClient
from argus.tooling.model_harness import ModelHarness

EXECUTOR_KINDS = ("docker_read", "host_probe", "network_probe", "prometheus")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


@dataclass
class Settings:
    config_dir: Path = field(default_factory=lambda: Path(os.getenv("ARGUS_CONFIG_DIR", "config")))
    secrets_dir: Path = field(default_factory=lambda: Path(os.getenv("ARGUS_SECRETS_DIR", "/run/argus-secrets")))
    runbooks_dir: Path = field(default_factory=lambda: Path(os.getenv(
        "ARGUS_RUNBOOKS_DIR", str(Path(__file__).resolve().parents[3] / "RunbooksLab" / "runbooks"))))
    runbooks_commit: str | None = field(default_factory=lambda: os.getenv("ARGUS_RUNBOOKS_COMMIT") or None)
    db_path: str = field(default_factory=lambda: os.getenv("ARGUS_DB", "argus.db"))
    db_backend: str = field(default_factory=lambda: os.getenv("ARGUS_DB_BACKEND", "sqlite"))   # sqlite | postgres
    pg_host: str = field(default_factory=lambda: os.getenv("ARGUS_PG_HOST", "argus-v18-postgres"))
    pg_db: str = field(default_factory=lambda: os.getenv("ARGUS_PG_DB", "argus"))
    pg_user: str = field(default_factory=lambda: os.getenv("ARGUS_PG_USER", "argus_runtime"))
    llm_model: str = field(default_factory=lambda: os.getenv("ARGUS_LLM_MODEL", "gpt-5.6-luna"))
    llm_base_url: str | None = field(default_factory=lambda: os.getenv("ARGUS_LLM_BASE_URL") or None)
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("ARGUS_LLM_TIMEOUT", "120")))
    llm_temperature: str | None = field(default_factory=lambda: os.getenv("ARGUS_LLM_TEMPERATURE") or None)
    llm_api: str = field(default_factory=lambda: os.getenv("ARGUS_LLM_API", "responses"))   # responses | chat
    llm_reasoning_effort: str | None = field(default_factory=lambda: os.getenv("ARGUS_LLM_REASONING_EFFORT") or None)
    max_reads_per_step: int = field(default_factory=lambda: int(os.getenv("ARGUS_MAX_READS_PER_STEP", "2")))
    max_steps: int = field(default_factory=lambda: int(os.getenv("ARGUS_MAX_STEPS", "8")))
    metrics_max_staleness_s: int = field(default_factory=lambda: int(os.getenv("ARGUS_METRICS_MAX_STALENESS", "90")))
    jwt_ttl_min: int = field(default_factory=lambda: int(os.getenv("ARGUS_JWT_TTL_MIN", "30")))

    def secret(self, rel: str) -> str | None:
        return _read(self.secrets_dir / rel)

    def pg_conninfo(self) -> str:
        from psycopg.conninfo import make_conninfo
        pw = self.secret("db_password")
        if not pw:
            raise SystemExit(f"missing credential {self.secrets_dir}/db_password")
        return make_conninfo(host=self.pg_host, dbname=self.pg_db, user=self.pg_user, password=pw,
                             connect_timeout=10, application_name="argus-v18-agent")


def make_store(s: Settings):
    """The system of record: Postgres in v1.8 (Phase 5); SQLite stays for offline tests and rollback."""
    if s.db_backend == "postgres":
        from argus.adapters.outbound.postgres_store import PostgresStore
        return PostgresStore(s.pg_conninfo())
    if s.db_backend == "sqlite":
        return SqliteStore(s.db_path)
    raise SystemExit(f"ARGUS_DB_BACKEND must be 'postgres' or 'sqlite', not {s.db_backend!r}")


@dataclass
class App:
    settings: Settings
    store: Any                          # SqliteStore | PostgresStore (same interface)
    inventory: YamlInventory
    policy: PolicyEngine
    runner: SkeletonRunner
    catalogue: DirectProvider
    jwt_key: str
    alertmanager_token: str | None
    llm_configured: bool


def build(settings: Settings | None = None, llm=None, metrics=None, executors: ExecutorRegistry | None = None,
          store=None, require_credentials: bool = True) -> App:
    s = settings or Settings()
    inv_text = (s.config_dir / "inventory.yaml").read_text(encoding="utf-8")
    pol_text = (s.config_dir / "policy.yaml").read_text(encoding="utf-8")
    signals = yaml.safe_load((s.config_dir / "signals.yaml").read_text(encoding="utf-8"))
    inventory = YamlInventory(inv_text)
    policy = PolicyEngine(yaml.safe_load(pol_text), pol_text)
    specs = build_catalog()

    # --- startup validation: every reference must resolve, or Argus refuses to start ----------------
    errors = []
    for spec in specs:
        if not policy.capability_known(spec.name):
            continue  # not allowed ⇒ refused at call time (fail closed); not an error
        if spec.executor not in EXECUTOR_KINDS:
            errors.append(f"{spec.name}: unknown executor {spec.executor}")
    for cap in policy.capabilities:
        if cap not in {sp.name for sp in specs}:
            errors.append(f"policy names unknown capability {cap}")
    for c in CLASSES:
        for sig in c.required_signals:
            if sig not in signals:
                errors.append(f"class {c.name} needs unknown signal {sig}")
    creds: dict[tuple[str, str], str] = {}
    for h in inventory.hosts():
        for ex in h.executors:
            if ex not in EXECUTOR_KINDS:
                errors.append(f"host {h.name}: unknown executor {ex}")
            if ex == "prometheus":
                continue
            tok = s.secret(f"{h.name}/{ex}_token")
            if tok is None and require_credentials:
                errors.append(f"missing credential {s.secrets_dir}/{h.name}/{ex}_token")
            elif tok is not None:
                creds[(h.name, ex)] = tok
    if errors:
        raise SystemExit("startup validation failed:\n  " + "\n  ".join(errors))

    redactor = Redactor()
    if executors is None:
        executors = ExecutorRegistry()
        for kind in ("docker_read", "host_probe", "network_probe"):
            executors.register(kind, lambda url, tok: TargetAgentClient(url, tok))
        executors.register("prometheus", lambda url, tok: PrometheusClient(url, tok, signals))
    store = store or make_store(s)
    catalogue = DirectProvider(specs, Dispatcher(inventory, executors, creds, redactor))
    invoke = InvokeCapability(catalogue, policy, inventory, store, store, redactor)

    llm_configured = llm is not None
    if llm is None:
        key = s.secret("openai_api_key") or os.getenv("OPENAI_API_KEY")
        if key:
            extra = {"temperature": float(s.llm_temperature)} if s.llm_temperature else {}
            if s.llm_api == "chat":
                llm = OpenAIChat(key, s.llm_model, s.llm_base_url, s.llm_timeout_s, extra)
            elif s.llm_api == "responses":
                if s.llm_reasoning_effort:
                    extra["reasoning"] = {"effort": s.llm_reasoning_effort}
                llm = OpenAIResponses(key, s.llm_model, s.llm_base_url, s.llm_timeout_s, extra)
            else:
                raise SystemExit(f"ARGUS_LLM_API must be 'responses' or 'chat', not {s.llm_api!r}")
            llm_configured = True
    harness = ModelHarness(llm) if llm is not None else None
    strategies = {"evidence_pack": EvidencePackStrategy(), "model_loop": ModelLoopStrategy(harness),
                  "plan_then_reason": PlanThenReasonStrategy(harness)}
    for c in CLASSES:
        if c.strategy not in strategies:
            raise SystemExit(f"class {c.name} names unknown strategy {c.strategy}")
    knowledge = TfidfRunbooks(str(s.runbooks_dir), s.runbooks_commit and f"commit {s.runbooks_commit}")
    for c in CLASSES:
        missing = [r for r in c.runbook_ids + c.branch_runbook_ids if r not in knowledge.ids]
        if missing:
            raise SystemExit(f"class {c.name} references runbooks missing from the library: {missing}")
    runner = SkeletonRunner(memory=store, audit=store, inventory=inventory,
                            metrics=metrics or PrometheusMetrics(inventory, signals, s.metrics_max_staleness_s),
                            knowledge=knowledge, notifier=store, invoke=invoke, events=store,
                            strategies=strategies, offered_specs=[sp for sp in specs if policy.capability_known(sp.name)],
                            redactor=redactor, policy_version=policy.version,
                            max_tool_level=policy.max_tool_level, max_reads_per_step=s.max_reads_per_step,
                            max_steps_cap=s.max_steps)
    jwt_key = s.secret("jwt_signing_key") or os.getenv("ARGUS_JWT_KEY") or ""
    if len(jwt_key) < 32:
        raise SystemExit("jwt_signing_key missing or shorter than 32 characters")
    return App(settings=s, store=store, inventory=inventory, policy=policy, runner=runner, catalogue=catalogue,
               jwt_key=jwt_key, alertmanager_token=s.secret("alertmanager_token"), llm_configured=llm_configured)
