"""The capabilities of the agent sessions (engine design 3.3 and 3.5, D131, D133): each agent's own model and effort, and the live view of its work.

    AgentPicksCapability   `install` gives the process's model router a reader of `<run>/choices.json`, the file the server writes from the owner's
                           choices (`connectors/agent_picks.py` owns its shape for both sides). The router then asks it, per request, which provider,
                           model and effort the agent a call is tagged for should get; a change applies from that agent's next call.

This file depends on the registry (`capabilities/base.py`) only for the `Capability` base class and on the connector layer only inside `install`,
so the engine still imports without the connectors. Neither capability changes what a call says: they route it and watch it.
"""
import logging
from typing import Any, Optional

try:
    from .base import Capability
except ModuleNotFoundError as _missing:                    # pragma: no cover  (the registry is merged by another branch: stand alone until then)
    if _missing.name != f"{__package__}.base":
        raise

    class Capability:                                      # the same defaults as base.Capability: a capability overrides only what it adds
        name: str = ""

        def outputs(self) -> dict:
            return {}

        def install(self, ctx: Any) -> None:
            return None

        def tag(self, tag: Any, ctx: Any) -> dict:
            return {}

        def progress(self, tag: Any, event: dict) -> None:
            return None

        def addendum(self, fn: str, ctx: Any) -> str:
            return ""

        def select(self, brief: str, ctx: Any) -> Optional[Any]:
            return None

        def settings(self) -> list:
            return []

__all__ = ["AgentPicksCapability", "router_of", "CHOICES_FILE"]

log = logging.getLogger("sutra_app.engine.capabilities.agents")

CHOICES_FILE = "choices.json"          # = connectors.agent_picks.CHOICES_FILE (not imported: the engine must start without the connectors)


def router_of(ctx: Any) -> Optional[Any]:
    """The model router of this process, or None (mock mode and the stdlib adapter have none). The host configures `llm` with its port before the
    capabilities are installed, so the port is where a capability finds the router; a context that carries its own `router` or `port` wins."""
    router = getattr(ctx, "router", None)
    if router is None:
        router = getattr(getattr(ctx, "port", None), "router", None)
    if router is None:
        from .. import llm
        router = getattr(getattr(llm, "_PORT", None), "router", None)
    return router


def run_dir_of(ctx: Any) -> Any:
    paths = getattr(ctx, "paths", None)
    return getattr(paths, "run_dir", None)


class AgentPicksCapability(Capability):
    """Each agent of a run has its own provider, model and effort when the owner chose one (D131). The capability adds nothing to a call's text or
    tag: `install` sets `router.agent_pick`, and the router does the rest (`Router._plan`, `Plan.effort_for`)."""

    name = "agent-picks"

    def install(self, ctx: Any) -> None:
        router, run_dir = router_of(ctx), run_dir_of(ctx)
        if router is None or run_dir is None or not hasattr(router, "agent_pick"):
            return                                         # mock mode: no router, nothing to route
        from sutra_app.connectors.agent_picks import AgentPicks
        router.agent_pick = AgentPicks(run_dir / CHOICES_FILE).for_tag
