"""The engine's model port: `make_port` and `RouterPort` (connectors design 3.10, D17).

    make_port(spec: PortSpec, *, usage_sink: UsageSink | None = None) -> ModelPort

is the ONLY definition of `make_port` (S1-contracts-02). `PortSpec` and `Allowance` come from `sutra_app.engine.port`; the
orchestrator's run spec never appears here. The engine host decides mock mode itself and then builds J2's `ScriptedPort` without importing this package;
otherwise it calls `make_port(PortSpec(mock=False, ...), usage_sink=EventUsageSink(...))` and then `port.preflight()`. A
`make_port(PortSpec(mock=True, ...))` still works: it gives a stub-only router, which is what the twin test runs against.

No `from __future__ import annotations` here on purpose: `inspect.signature(make_port)` shows real types.

`port_from_config` is `make_port` with the `ConnectorConfig` supplied by the caller (tests point the executables at the fakes). A live port gets the
same `Egress` as the app's router (`<data>/connectors/egress.jsonl`), in observe mode only (D109): every prompt of a department run leaves one
count-only audit row and goes out byte-identical; a stub-only port starts no process, so it writes no row.
A live `make_port` finds the CLIs as the app's own router does (`discover.connector_config`: the file the owner chose in Settings, PATH,
then the folders installers use; GAP-providers), so a department run uses the same file the Settings row and the chat use; a stub-only
port keeps the defaults. `build_connectors` is the one place that turns a policy into connector objects; the factory (CN-9) can use it as
well.
"""
from pathlib import Path
from typing import Callable, Optional

from sutra_app.engine.port import (
    CallTag, CompletionRequest, CompletionResult, ModelPort, PortInfo, PortSpec, PreflightResult, ToolGrant,
)

from .base import ModelConnector
from .claude import ClaudeConnector
from .codex import CodexConnector
from .discover import connector_config
from .egress import Egress
from .errors import ConnectorError, NoProviderError
from .models import AskRequest, ConnectorConfig, RouteContext
from .node_tools import NodeRights
from .policy import PolicyLoad, RoutingPolicy, load_policy
from .router import Router
from .stub import StubConnector
from .usage import UsageSink
from .workdir import WorkFolder

__all__ = ["make_port", "port_from_config", "build_connectors", "RouterPort", "PROBE_GRANT", "tools_provider_of", "builder_tools_line"]

# a grant only for planning: which connector would take a builder tools call (no process is started, nothing runs in its folder)
PROBE_GRANT = ToolGrant(tools=("Read",), allow=("Read",), cwd=".", root=".", usd=1.0, log_chars=1)


def tools_provider_of(router: Router, tag: Optional[CallTag] = None) -> Optional[str]:
    """The provider a builder tools call would go to now (D245), or None when none can take one. From cached status: no model call."""
    try:
        return router.plan(AskRequest(user="preflight", ctx=RouteContext(tag=tag or CallTag()), kind="text", run_tools=PROBE_GRANT)).order[0]
    except ConnectorError:
        return None


def builder_tools_line(router: Optional[Router], *, offline: bool, agent_tools: Optional[bool] = None, sandbox: Optional[bool] = None) -> str:
    """The startup line (D245): whether builders get tools in a run, with the Claude CLI or not at all, and whether the sandbox is on and why.
    `agent_tools` and `sandbox` are the engine settings a new run reads (`engine.json` and the J2_* environment; None: the engine's rule)."""
    from sutra_app.engine import llm
    if sandbox is not None:
        on, why = sandbox, f"J2_SANDBOX={int(sandbox)}"
    else:
        on, why = llm.sandbox_status(mock=offline, environ={})
    if agent_tools is False:
        tools = "off (J2_AGENT_TOOLS=0): J2 builds through its section path"
    elif offline:
        tools = "on (offline: J2's scripted general path)" if agent_tools else "off (offline: J2_AGENT_TOOLS=1 turns J2's scripted general path on)"
    else:
        provider = tools_provider_of(router) if router is not None else None
        tools = (f"on ({'the Claude CLI' if provider == 'claude' else provider})" if provider else
                 "off (no connector can run them: they need the Claude CLI, installed and signed in; Codex has no J2 tools path): "
                 "J2 builds through its section path")
    return f"Builder tools: {tools}. Sandbox: {'on' if on else 'off'} ({why})."


def build_connectors(cfg: ConnectorConfig, policy: RoutingPolicy, *, only: Optional[str] = None) -> dict[str, ModelConnector]:
    """The CLI connectors the policy lists (`only` limits it to one provider). Codex gets the policy's sandbox and its rate card."""
    found: dict[str, ModelConnector] = {}
    if only in (None, "claude") and "claude" in policy.providers:
        found["claude"] = ClaudeConnector(cfg)
    if only in (None, "codex") and "codex" in policy.providers:
        found["codex"] = CodexConnector(cfg, rates=policy.rates.get("codex", {}),
                                        sandbox=policy.providers["codex"].sandbox or "read-only")
    return found


def make_port(spec: PortSpec, *, usage_sink: UsageSink | None = None) -> ModelPort:
    """A router over the connectors that the policy and `spec.connector` allow, as the engine's `ModelPort`. `spec.mock` or
    `spec.connector == "stub"` gives a stub-only router (no process is ever started). The routing policy is read from
    `<spec.data_dir>/connectors/policy.json` when it validates, else the packaged default. A live port finds the CLIs as the app does
    (`discover.connector_config`), so the engine host runs the file the owner chose, or the one an installer put outside PATH."""
    data_dir = Path(spec.data_dir)
    stub_only = spec.mock or spec.connector == "stub"
    cfg = ConnectorConfig(data_dir=data_dir) if stub_only else connector_config(data_dir)
    return port_from_config(spec, cfg, usage_sink=usage_sink)


def live_cap_reader(data_dir: str, project_id: str) -> Callable[[], Optional[float]]:
    """A function that says what the next call of a step of `project_id` may spend: the shared arithmetic of `orchestrator/livecap.py`, read from the app's database read-only and the owner's limits file,
    each time it is called (never frozen). None when nothing limits it or when the database cannot be read (the step's own meter and the Conductor's tick still hold)."""
    import sqlite3
    import time
    from sutra_app.config import DB_FILENAME
    from sutra_app.orchestrator.limits import LIMITS_FILE, LimitsStore
    from sutra_app.orchestrator.livecap import call_cap

    def read() -> Optional[float]:
        path = Path(data_dir) / DB_FILENAME
        if not path.is_file():
            return None
        try:
            limit = LimitsStore(Path(data_dir) / LIMITS_FILE).load().monthly_usd
        except Exception:                                      # noqa: BLE001
            limit = None
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        try:
            return call_cap(conn, project_id, limit, time.time())
        finally:
            conn.close()
    return read


def port_from_config(spec: PortSpec, cfg: ConnectorConfig, *, usage_sink: UsageSink | None = None,
                     load: Optional[PolicyLoad] = None, **router_kw) -> "RouterPort":
    """`make_port` with the connector configuration given. `router_kw` goes to `Router` (tests inject a clock or a sleep)."""
    load = load or load_policy(spec.data_dir)
    stub_only = spec.mock or spec.connector == "stub"
    if stub_only:
        connectors: dict[str, ModelConnector] = {"stub": StubConnector(cfg)}
        mode = "stub"
    else:
        mode = spec.connector
        connectors = build_connectors(cfg, load.policy, only=None if mode == "auto" else mode)
    router = Router(connectors, load.policy, usage_sink=usage_sink, connector=mode, policy_source=load.source,
                    policy_error=load.error, **router_kw)
    if not stub_only:                                  # D109: J2's agents are observed, never edited: one audit row per prompt, byte-identical text
        router.egress = Egress(Path(spec.data_dir) / "connectors" / "egress.jsonl")
        router.folders = WorkFolder(spec.data_dir, cfg.resolved_work_root())      # D127: a call whose tag asks for the owner's folder gets it; read on every call
        if spec.slots:                                                            # SUTRA_NODES_SLOTS: the limit across processes (MAN-12)
            from .slots import SlotPool
            router.slots = SlotPool(Path(spec.data_dir) / "connectors" / "slots", {name: load.policy.max_concurrency(name) for name in connectors})
        router.node_scope = tuple(spec.scope)                                     # a step of a project edits only inside its scope (MAN-10)
        if spec.node and spec.project_id:                                         # D409: before each builder call the step reads what it may still spend, now, read-only
            router.live_cap = live_cap_reader(spec.data_dir, spec.project_id)
        router.node_rights = NodeRights(tuple(spec.node_tiers), spec.node_commands) if (spec.node or spec.node_tiers) else None   # a router made for a step's process narrows every builder call it gets, whatever the tag says (D380, D387)
    return RouterPort(router, mock=stub_only, tag=CallTag(run_id=spec.run_id, dept_id=spec.dept_id, task_id=spec.task_id), tools=tuple(spec.tools))


class RouterPort:
    """The engine's `ModelPort` over a `Router`. `complete` is the router's own (the mapping lives there, connectors 3.10);
    this class adds `describe`, `preflight` and `close`."""

    def __init__(self, router: Router, *, mock: bool = False, tag: Optional[CallTag] = None, tools: tuple[str, ...] = ()) -> None:
        self.router = router
        self.mock = mock
        self._tag = tag or CallTag()
        self._tools = tuple(tools)                       # a node's granted app tools: on its agent-turn calls only (MAN-8, D298)

    def _probe_request(self) -> AskRequest:
        return AskRequest(user="preflight", ctx=RouteContext(tag=self._tag), kind="text")

    def tools_provider(self) -> Optional[str]:
        """The provider a builder tools call would go to now (D245), or None when none can take one (the Claude CLI missing or signed out, a
        Codex-only or stub-only router): J2 then builds through its section path. From cached status: no model call."""
        if self.mock:
            return None
        return tools_provider_of(self.router, self._tag)

    def describe(self) -> PortInfo:
        """The provider and model of the first plan; both None when nothing is usable (preflight says why)."""
        try:
            plan = self.router.plan(self._probe_request())
        except ConnectorError:
            return PortInfo(provider=None, model=None, mock=self.mock)
        first = plan.order[0]
        return PortInfo(provider=first, model=plan.models[first], mock=self.mock)

    def preflight(self) -> PreflightResult:
        """Is a model usable? From cached status (a status command runs only when its cache is older than 30 s): no model call."""
        providers = []
        for name in self.router.connectors:
            summary = self.router.provider_summary(name)
            providers.append({"name": name, "installed": summary.installed, "signed_in": summary.signed_in, "detail": summary.detail})
        try:
            plan = self.router.plan(self._probe_request())
        except NoProviderError as e:
            return PreflightResult(ok=False, message=e.user_message(), providers=providers)
        first = plan.order[0]
        if self.mock:
            return PreflightResult(ok=True, message="the stub connector answers from a script: no model is called", providers=providers)
        return PreflightResult(ok=True, message=f"{first} is ready ({plan.models[first]})", providers=providers)

    def complete(self, req: CompletionRequest, on_progress: Optional[Callable[[dict], None]] = None) -> CompletionResult:
        if self._tools and req.run_tools is None:        # never on a builder-tools call: its tools are the grant's own
            return self.router.complete(req, on_progress, tools=self._tools)
        return self.router.complete(req, on_progress)

    def close(self) -> None:
        self.router.close()
