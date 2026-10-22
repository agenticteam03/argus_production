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
from argus.orchestration.graph_runner import GraphRunner
from argus.orchestration.runner import SkeletonRunner
from argus.orchestration.strategies import (BaselineStrategy, ConfirmThenReasonStrategy, EvidencePackStrategy,
                                           ModelLoopStrategy, PlanThenReasonStrategy)
from argus.policy.engine import PolicyEngine
from argus.tooling.dispatch import DirectProvider, Dispatcher
from argus.tooling.executors import ExecutorRegistry, KnowledgeClient, PrometheusClient, TargetAgentClient
from argus.tooling.model_harness import ModelHarness

EXECUTOR_KINDS = ("docker_read", "host_probe", "network_probe", "db_probe", "prometheus", "argus_internal")   # last: in-worker


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
        "ARGUS_RUNBOOKS_DIR", str(Path(__file__).resolve().parents[1] / "runbooks"))))   # argus/runbooks (D-002)
    runbooks_commit: str | None = field(default_factory=lambda: os.getenv("ARGUS_RUNBOOKS_COMMIT") or None)
    db_path: str = field(default_factory=lambda: os.getenv("ARGUS_DB", "argus.db"))
    db_backend: str = field(default_factory=lambda: os.getenv("ARGUS_DB_BACKEND", "sqlite"))   # sqlite | postgres
    pg_host: str = field(default_factory=lambda: os.getenv("ARGUS_PG_HOST", "argus-v18-postgres"))
    pg_db: str = field(default_factory=lambda: os.getenv("ARGUS_PG_DB", "argus"))
    pg_user: str = field(default_factory=lambda: os.getenv("ARGUS_PG_USER", "argus_runtime"))
    llm_model: str = field(default_factory=lambda: os.getenv("ARGUS_LLM_MODEL", "gpt-5.6-luna"))
    # ACR-0013: optional, filtered OTLP tracing to a self-hosted Langfuse; off by default. The project keys are the
    # secret files langfuse_public_key / langfuse_secret_key, mounted into the worker only.
    tracing_enabled: bool = field(default_factory=lambda: os.getenv("ARGUS_TRACING_ENABLED", "0") == "1")
    tracing_endpoint: str = field(default_factory=lambda: os.getenv(
        "ARGUS_TRACING_ENDPOINT", "http://argus-v18-langfuse-web:3000/api/public/otel/v1/traces"))
    # ACR-0013 C: the operator-facing Langfuse UI (loopback / tunnel; never public). Unset: the incident view has no link.
    langfuse_ui_url: str = field(default_factory=lambda: os.getenv("ARGUS_LANGFUSE_UI_URL", "").rstrip("/"))
    langfuse_project_id: str = field(default_factory=lambda: os.getenv("ARGUS_LANGFUSE_PROJECT_ID", ""))
    llm_base_url: str | None = field(default_factory=lambda: os.getenv("ARGUS_LLM_BASE_URL") or None)
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("ARGUS_LLM_TIMEOUT", "120")))
    llm_temperature: str | None = field(default_factory=lambda: os.getenv("ARGUS_LLM_TEMPERATURE") or None)
    llm_api: str = field(default_factory=lambda: os.getenv("ARGUS_LLM_API", "responses"))   # responses | chat
    llm_reasoning_effort: str | None = field(default_factory=lambda: os.getenv("ARGUS_LLM_REASONING_EFFORT") or None)
    max_reads_per_step: int = field(default_factory=lambda: int(os.getenv("ARGUS_MAX_READS_PER_STEP", "2")))
    max_steps: int = field(default_factory=lambda: int(os.getenv("ARGUS_MAX_STEPS", "8")))
    runner: str = field(default_factory=lambda: os.getenv("ARGUS_RUNNER", "plain"))   # plain | langgraph (T-0013)
    # T-0021 (§12.5 TOOL_CATALOGUE): target-side reads in-process (direct) or in the MCP tools process (mcp)
    tool_catalogue: str = field(default_factory=lambda: os.getenv("ARGUS_TOOL_CATALOGUE", "direct"))
    # the whole command that starts the tools process (T-0021 step 3: the sudo launcher to the argus-tools UID);
    # empty = this interpreter, `-m argus.tooling.mcp.tools_server`
    tools_command: list[str] = field(default_factory=lambda: os.getenv("ARGUS_TOOLS_COMMAND", "").split())
    metrics_max_staleness_s: int = field(default_factory=lambda: int(os.getenv("ARGUS_METRICS_MAX_STALENESS", "90")))
    jwt_ttl_min: int = field(default_factory=lambda: int(os.getenv("ARGUS_JWT_TTL_MIN", "30")))
    # ACR-0001: browser origins allowed to call the API (a UI during development); empty = no CORS headers at all
    ui_origins: list[str] = field(default_factory=lambda: [o.strip() for o in os.getenv("ARGUS_UI_ORIGINS", "").split(",")
                                                           if o.strip()])
    # ACR-0011: the header the public edge (Nginx, argus-v18-ui) always sets; a login carrying it is read-only
    edge_header: str = field(default_factory=lambda: os.getenv("ARGUS_EDGE_HEADER", "X-Argus-Edge"))
    # §17.3 / ACR-0011: failed logins per username and per client address within the window, then a lockout
    login_max_per_user: int = field(default_factory=lambda: int(os.getenv("ARGUS_LOGIN_MAX_PER_USER", "5")))
    login_max_per_address: int = field(default_factory=lambda: int(os.getenv("ARGUS_LOGIN_MAX_PER_ADDRESS", "20")))
    login_window_s: int = field(default_factory=lambda: int(os.getenv("ARGUS_LOGIN_WINDOW_S", "900")))
    incidents_limit_cap: int = field(default_factory=lambda: int(os.getenv("ARGUS_INCIDENTS_LIMIT_CAP", "200")))
    # ACR-0017: the inventory host Argus runs on (the map marks it and draws its reads); unset = every host monitored
    home_host: str = field(default_factory=lambda: os.getenv("ARGUS_HOME_HOST", "").strip())
    # ACR-0012: investigations started with an `investigate` token (the UI); alerts and full tokens are not counted
    investigations_per_hour: int = field(default_factory=lambda: int(os.getenv("ARGUS_INVESTIGATIONS_PER_HOUR", "10")))
    investigations_queued_per_principal: int = field(
        default_factory=lambda: int(os.getenv("ARGUS_INVESTIGATIONS_QUEUED_PER_PRINCIPAL", "2")))
    investigations_queued_max: int = field(default_factory=lambda: int(os.getenv("ARGUS_INVESTIGATIONS_QUEUED_MAX", "20")))

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
    metrics: Any                        # MetricsPort: the detectors' reads, also for alert correlation (§6.4)
    jwt_key: str
    alertmanager_token: str | None
    llm_configured: bool
    incident_metrics: Any = None        # ACR-0017: the metric window around an incident (the UI's charts)
    topology: Any = None                # ACR-0017: the system map (inventory, signals, an incident's evidence)
    thresholds: Any = None              # ACR-0021: the UI's warning and critical lines (signals.yaml `thresholds:`)
    jwt_signing: Any = None             # ACR-0018: an Ed25519 private key; tokens are EdDSA, HS256 refused. None: HS256



def ed25519_signing_key(pem: str | None):
    """ACR-0018 §17.2: the API's token signing key, an Ed25519 private key in PEM (secret `jwt_ed25519_key`). None when
    the secret is absent (the lab's HS256 key is used). Any other key type refuses startup."""
    if not pem:
        return None
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    try:
        key = load_pem_private_key(pem.encode(), password=None)
    except ValueError:
        raise SystemExit("jwt_ed25519_key is not a PEM private key")
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("jwt_ed25519_key must be an Ed25519 private key")
    return key

def _credentials(s: Settings, inventory: YamlInventory, require: bool, errors: list[str],
                 load: bool = True) -> dict[tuple[str, str], str]:
    """Executor tokens. `load=False` (the worker in `mcp` mode, §12.6): validate the inventory, read no token."""
    creds: dict[tuple[str, str], str] = {}
    for h in inventory.hosts():
        for ex in h.executors:
            if ex not in EXECUTOR_KINDS:
                errors.append(f"host {h.name}: unknown executor {ex}")
            if ex == "prometheus" or not load:
                continue
            tok = s.secret(f"{h.name}/{ex}_token")
            if tok is None and require:
                errors.append(f"missing credential {s.secrets_dir}/{h.name}/{ex}_token")
            elif tok is not None:
                creds[(h.name, ex)] = tok
    return creds


def load_routing(config_dir: Path):
    """T-0042 (§15.2): `routing.yaml`, validated against the class families (fail closed: ValueError); no file = the
    default route only. The agent and the scheduler read it the same way."""
    from argus.policy.routing import Routing
    path = config_dir / "routing.yaml"
    if not path.exists():
        return Routing()
    return Routing.from_data(yaml.safe_load(path.read_text(encoding="utf-8")), {c.family for c in CLASSES})


def read_signals(config_dir: Path) -> dict:
    """`config/signals.yaml`: the PromQL templates by signal name. Its optional `thresholds:` map (ACR-0021, the UI's
    warning and critical lines) is never a template, so it is not returned here (`load_thresholds`)."""
    data = yaml.safe_load((config_dir / "signals.yaml").read_text(encoding="utf-8"))
    data.pop("thresholds", None)
    return data


def load_thresholds(config_dir: Path, signals: set[str]):
    """ACR-0021: the `thresholds:` map of signals.yaml, validated against the named signals (ValueError)."""
    from argus.application.thresholds import Thresholds
    data = yaml.safe_load((config_dir / "signals.yaml").read_text(encoding="utf-8"))
    return Thresholds.from_data(data.get("thresholds"), signals)


def load_ui_signals(config_dir: Path, signals: set[str]):
    """ACR-0017: `ui-incident-signals.yaml`, validated against the named signals and the classes (ValueError); no file =
    no series (the UI then hides its charts)."""
    from argus.application.incident_metrics import SignalList
    path = config_dir / "ui-incident-signals.yaml"
    if not path.exists():
        return SignalList()
    return SignalList.from_data(yaml.safe_load(path.read_text(encoding="utf-8")), signals, {c.name for c in CLASSES})


def tracing_sink(s: Settings, store):
    """ACR-0013: the runner's event sink. The store, unless tracing is enabled AND this process holds the Langfuse
    project keys (only the worker does): then the store plus filtered OTLP spans. Telemetry: never required."""
    pk, sk = s.secret("langfuse_public_key"), s.secret("langfuse_secret_key")
    if not (s.tracing_enabled and pk and sk):
        return store
    from argus.observability.tracing import OtlpExporter, TracingEventSink
    return TracingEventSink(store, OtlpExporter(s.tracing_endpoint, pk, sk))


def declared_paths(policy: dict | None, inventory: dict | None) -> list[str]:
    """The paths Argus itself declared, which the redactor leaves readable (#107 review): the inspection policy's
    `service_config` and `files` entries and the inventory's mounts (as directories; `/` is not one)."""
    out: set[str] = set()
    for entry in (((policy or {}).get("inspection") or {}).get("targets") or {}).values():
        for kind in ("service_config", "files"):
            out.update(p for p in (entry or {}).get(kind) or [] if isinstance(p, str))
    for t in (inventory or {}).get("targets") or []:
        out.update(m.rstrip("/") + "/" for m in t.get("mounts") or [] if isinstance(m, str) and m.rstrip("/"))
    return sorted(out)


def anomaly_inputs(thresholds, ui_signals) -> tuple[dict, dict]:
    """T-0047 H5: what `analysis.anomaly_summary` reads beside the templates: the warning line and direction per signal
    and the (signal, scope) list per class. Empty when either file is missing or refused (the read then says so)."""
    lines = {name: (t.warning, t.direction) for name in (thresholds.signals() if thresholds else [])
             for t in [thresholds.get(name)]}
    by_class = (ui_signals.by_class or {}) if ui_signals else {}
    return lines, {name: [(s.signal, s.scope) for s in specs] for name, specs in by_class.items()}


def load_anomaly_inputs(config_dir: Path, signals: set[str]) -> tuple[dict, dict]:
    """`anomaly_inputs` for a process that does not validate the files itself (the tools process); a refused file
    leaves its part empty (the worker's startup validation reports it)."""
    try:
        thresholds = load_thresholds(config_dir, signals)
    except ValueError:
        thresholds = None
    try:
        ui_signals = load_ui_signals(config_dir, signals)
    except ValueError:
        ui_signals = None
    return anomaly_inputs(thresholds, ui_signals)


def _target_executors(signals: dict, lines: dict | None = None, class_signals: dict | None = None) -> ExecutorRegistry:
    executors = ExecutorRegistry()
    for kind in ("docker_read", "host_probe", "network_probe", "db_probe"):
        executors.register(kind, lambda url, tok: TargetAgentClient(url, tok))
    executors.register("prometheus", lambda url, tok: PrometheusClient(url, tok, signals, lines=lines,
                                                                       class_signals=class_signals))
    return executors


def tools_dispatcher(s: Settings):
    """What the MCP tools process needs, and nothing more (§12.6): the catalogue, the inventory and a dispatcher
    holding the executor tokens. No database, no model key, no runbooks."""
    inv_text = (s.config_dir / "inventory.yaml").read_text(encoding="utf-8")
    inventory = YamlInventory(inv_text)
    signals = read_signals(s.config_dir)
    policy = yaml.safe_load((s.config_dir / "policy.yaml").read_text(encoding="utf-8"))
    errors: list[str] = []
    creds = _credentials(s, inventory, True, errors)
    if errors:
        raise SystemExit("tools process: startup validation failed:\n  " + "\n  ".join(errors))
    redactor = Redactor(declared_paths(policy, yaml.safe_load(inv_text)))
    lines, class_signals = load_anomaly_inputs(s.config_dir, set(signals))           # T-0047 H5
    return build_catalog(), Dispatcher(inventory, _target_executors(signals, lines, class_signals), creds, redactor,
                                       reload=lambda host, ex: s.secret(f"{host}/{ex}_token")), inventory


def make_metrics(s: Settings, inventory: YamlInventory) -> PrometheusMetrics:
    """The detectors' MetricsPort, for a process that does not `build` (the scheduler: alert correlation, §6.4)."""
    signals = read_signals(s.config_dir)
    return PrometheusMetrics(inventory, signals, s.metrics_max_staleness_s)


def make_llm(s: Settings):
    """The configured model (key from the secret file or OPENAI_API_KEY), or None when no key exists. Also used by
    the evaluation (T-0025 step 3) to give the replay harness the same model the worker uses."""
    key = s.secret("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    extra = {"temperature": float(s.llm_temperature)} if s.llm_temperature else {}
    if s.llm_api == "chat":
        return OpenAIChat(key, s.llm_model, s.llm_base_url, s.llm_timeout_s, extra)
    if s.llm_api == "responses":
        if s.llm_reasoning_effort:
            extra["reasoning"] = {"effort": s.llm_reasoning_effort}
        return OpenAIResponses(key, s.llm_model, s.llm_base_url, s.llm_timeout_s, extra)
    raise SystemExit(f"ARGUS_LLM_API must be 'responses' or 'chat', not {s.llm_api!r}")


def build(settings: Settings | None = None, llm=None, metrics=None, executors: ExecutorRegistry | None = None,
          store=None, require_credentials: bool = True, load_credentials: bool = True) -> App:
    """`load_credentials=False`: read no executor token (the api, which never investigates; T-0021 step 4)."""
    s = settings or Settings()
    inv_text = (s.config_dir / "inventory.yaml").read_text(encoding="utf-8")
    pol_text = (s.config_dir / "policy.yaml").read_text(encoding="utf-8")
    signals = read_signals(s.config_dir)
    inventory = YamlInventory(inv_text)
    policy = PolicyEngine(yaml.safe_load(pol_text), pol_text)
    specs = build_catalog()

    # --- startup validation: every reference must resolve, or Argus refuses to start ----------------
    errors = []
    routing = None                                   # T-0042 (§15.2): escalation routing, validated like the rest
    try:
        routing = load_routing(s.config_dir)
    except ValueError as e:
        errors.append(str(e))
    ranking = None                                   # ACR-0024 §3.3 (T-0047 H2): the hypotheses' score weights
    try:
        from argus.application.ranking import load_ranking
        ranking = load_ranking(s.config_dir)
    except ValueError as e:
        errors.append(str(e))
    ui_signals = None                                # ACR-0017: the incident charts' signal list, validated likewise
    try:
        ui_signals = load_ui_signals(s.config_dir, set(signals))
    except ValueError as e:
        errors.append(str(e))
    thresholds = None                                # ACR-0021: the gauges' lines, validated likewise
    try:
        thresholds = load_thresholds(s.config_dir, set(signals))
    except ValueError as e:
        errors.append(str(e))
    for spec in specs:
        if not policy.capability_known(spec.name):
            continue  # not allowed ⇒ refused at call time (fail closed); not an error
        if spec.executor not in EXECUTOR_KINDS:
            errors.append(f"{spec.name}: unknown executor {spec.executor}")
    for cap in policy.capabilities:
        if cap not in {sp.name for sp in specs}:
            errors.append(f"policy names unknown capability {cap}")
    errors += policy.inspection.errors_against_inventory(yaml.safe_load(inv_text))   # T-0019 batch 3a (§4.7)
    for c in CLASSES:
        for sig in c.required_signals:
            if sig not in signals:
                errors.append(f"class {c.name} needs unknown signal {sig}")
    if s.tool_catalogue not in ("direct", "mcp"):
        errors.append(f"ARGUS_TOOL_CATALOGUE must be 'direct' or 'mcp', not {s.tool_catalogue!r}")
    creds = _credentials(s, inventory, require_credentials, errors,
                         load=load_credentials and s.tool_catalogue != "mcp")
    if errors:
        raise SystemExit("startup validation failed:\n  " + "\n  ".join(errors))

    redactor = Redactor(declared_paths(yaml.safe_load(pol_text), yaml.safe_load(inv_text)))   # #107 review
    if executors is None:
        executors = _target_executors(signals, *anomaly_inputs(thresholds, ui_signals))   # T-0047 H5
    knowledge = TfidfRunbooks(str(s.runbooks_dir), s.runbooks_commit and f"commit {s.runbooks_commit}")
    store = store or make_store(s)
    if "argus_internal" not in executors.names():              # in-worker capabilities (knowledge.*)
        executors.register("argus_internal", lambda url, tok: KnowledgeClient(knowledge, store,   # T-0039: memory
                                                                              inventory, metrics))   # T-0046 L4
    if s.tool_catalogue == "mcp":       # target-side reads in the tools process, started on the first call
        from argus.tooling.mcp.client import child_client
        from argus.tooling.providers import McpCatalogue
        env = {"ARGUS_CONFIG_DIR": str(s.config_dir.resolve()), "ARGUS_SECRETS_DIR": str(s.secrets_dir)}
        if os.getenv("PYTHONPATH"):
            env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        catalogue = McpCatalogue(specs, Dispatcher(inventory, executors, {}, redactor),
                                 child_client(env, s.tools_command or None))
    else:
        catalogue = DirectProvider(specs, Dispatcher(inventory, executors, creds, redactor,
                                                     reload=lambda host, ex: s.secret(f"{host}/{ex}_token")))
    invoke = InvokeCapability(catalogue, policy, inventory, store, store, redactor)

    if llm is None:
        llm = make_llm(s)
    llm_configured = llm is not None
    events = tracing_sink(s, store)
    if llm is not None and hasattr(events, "model_span"):      # ACR-0013: model requests become spans too
        from argus.observability.tracing import TracingLLM
        llm = TracingLLM(llm, events)
    harness = ModelHarness(llm) if llm is not None else None
    strategies = {"evidence_pack": EvidencePackStrategy(), "model_loop": ModelLoopStrategy(harness),
                  "plan_then_reason": PlanThenReasonStrategy(harness),
                  "confirm_then_reason": ConfirmThenReasonStrategy(harness),     # E2E-5 (ACR-0007)
                  "baseline": BaselineStrategy()}          # §21.2: the deterministic baseline (T-0025)
    for c in CLASSES:
        if c.strategy not in strategies:
            raise SystemExit(f"class {c.name} names unknown strategy {c.strategy}")
    for c in CLASSES:
        missing = [r for r in c.runbook_ids + c.branch_runbook_ids if r not in knowledge.ids]
        if missing:
            raise SystemExit(f"class {c.name} references runbooks missing from the library: {missing}")
    runners = {"plain": SkeletonRunner, "langgraph": GraphRunner}
    if s.runner not in runners:
        raise SystemExit(f"ARGUS_RUNNER must be 'plain' or 'langgraph', not {s.runner!r}")
    extra = {}
    if s.runner == "langgraph" and hasattr(store, "checkpointer"):   # Postgres: checkpoints survive a restart
        extra["checkpointer"] = store.checkpointer()
    metrics = metrics or PrometheusMetrics(inventory, signals, s.metrics_max_staleness_s)
    runner = runners[s.runner](**extra, memory=store, audit=store, inventory=inventory, metrics=metrics,
                            knowledge=knowledge, notifier=store, invoke=invoke, events=events,
                            strategies=strategies, offered_specs=[sp for sp in specs if policy.capability_known(sp.name)],
                            redactor=redactor, policy_version=policy.version,
                            max_tool_level=policy.max_tool_level, max_reads_per_step=s.max_reads_per_step,
                            max_steps_cap=s.max_steps, routing=routing, ranking=ranking)
    jwt_key = s.secret("jwt_signing_key") or os.getenv("ARGUS_JWT_KEY") or ""
    if len(jwt_key) < 32:
        raise SystemExit("jwt_signing_key missing or shorter than 32 characters")
    jwt_signing = ed25519_signing_key(s.secret("jwt_ed25519_key"))
    from argus.application.incident_metrics import IncidentMetrics
    from argus.application.topology import Topology
    if s.home_host and inventory.host(s.home_host) is None:
        raise SystemExit(f"ARGUS_HOME_HOST {s.home_host!r} is not an inventory host")
    return App(settings=s, store=store, inventory=inventory, policy=policy, runner=runner, catalogue=catalogue,
               metrics=metrics, jwt_key=jwt_key, alertmanager_token=s.secret("alertmanager_token"), llm_configured=llm_configured,
               incident_metrics=IncidentMetrics(metrics, ui_signals, store=store, thresholds=thresholds,
                                                inventory=inventory),
               topology=Topology(inventory, metrics, store, s.home_host, thresholds=thresholds), thresholds=thresholds,
               jwt_signing=jwt_signing)
