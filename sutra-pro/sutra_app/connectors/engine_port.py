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
    CallTag, CompletionRequest, CompletionResult, ModelPort, PortInfo, PortSpec, PreflightResult,
)

from .base import ModelConnector
from .claude import ClaudeConnector
from .codex import CodexConnector
from .discover import connector_config
from .egress import Egress
from .errors import ConnectorError, NoProviderError
from .models import AskRequest, ConnectorConfig, RouteContext
from .policy import PolicyLoad, RoutingPolicy, load_policy
from .router import Router
from .stub import StubConnector
from .usage import UsageSink

__all__ = ["make_port", "port_from_config", "build_connectors", "RouterPort"]


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
    return RouterPort(router, mock=stub_only, tag=CallTag(run_id=spec.run_id, dept_id=spec.dept_id, task_id=spec.task_id))


class RouterPort:
    """The engine's `ModelPort` over a `Router`. `complete` is the router's own (the mapping lives there, connectors 3.10);
    this class adds `describe`, `preflight` and `close`."""

    def __init__(self, router: Router, *, mock: bool = False, tag: Optional[CallTag] = None) -> None:
        self.router = router
        self.mock = mock
        self._tag = tag or CallTag()

    def _probe_request(self) -> AskRequest:
        return AskRequest(user="preflight", ctx=RouteContext(tag=self._tag), kind="text")

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
        return self.router.complete(req, on_progress)

    def close(self) -> None:
        self.router.close()
