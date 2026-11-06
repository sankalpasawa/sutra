"""`AsyncConnector`: the orchestrator's `ConnectorPort` over a `Router` (connectors design 3.10, ORCH 3.5).

    async call_json(prompt, *, schema, tools, timeout, function, step, context) -> (dict, usd | None, how)
    status() -> {provider: {installed, signed_in, detail, ..., health: {state, until, reason}, quota: {...} | None}}
                                       `health` is the HealthState object (the shape Settings reads from /api/health); `account`
                                       is left out (PII, CN-7)
    records_usage                      True when the router has a usage sink: the router then writes the ledger row of every
                                       call, so the orchestrator's `TurnRunner` and `NodeAsk` write none of their own

The tag of a call is built from the arguments, never from the orchestrator's string step:

    step              -> tag.stage         (`tag.step` stays the J2 step number, 0 here)
    function          -> tag.function
    context.purpose   -> tag.purpose
    context.task_id   -> tag.task_id
    context.atom_id   -> tag.atom          (the request's overhead key; S4-fnodes-07)
    context.session_id / node_id -> RouteContext.session_id / node_id

Errors are the router's `ConnectorError`s; each carries `.kind` (unavailable | auth | quota | timeout | bad_output).
"""
import asyncio
from typing import Any, Mapping, Optional, Sequence

from pydantic import ValidationError

from sutra_app.engine.port import CallTag

from .errors import InvalidJsonError, InvalidRequestError
from .models import JsonRequest, RouteContext
from .router import Router

__all__ = ["AsyncConnector", "build_tag"]


def build_tag(function: str, step: Optional[str], context: Optional[Mapping[str, Any]]) -> CallTag:
    """The `CallTag` of one orchestrator call. Unknown context keys are ignored; a purpose that is not `^[a-z_]{1,24}$` raises
    InvalidRequestError."""
    ctx = context or {}
    fields: dict[str, Any] = {"function": function, "stage": step or None}
    if ctx.get("purpose"):
        fields["purpose"] = ctx["purpose"]
    if ctx.get("task_id"):
        fields["task_id"] = ctx["task_id"]
    if ctx.get("atom_id"):
        fields["atom"] = ctx["atom_id"]
    try:
        return CallTag(**fields)
    except ValidationError as e:
        why = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
        raise InvalidRequestError(f"the call tag is not valid: {why}") from None


class AsyncConnector:
    def __init__(self, router: Router) -> None:
        self.router = router

    @property
    def records_usage(self) -> bool:
        return self.router.usage_sink is not None

    async def call_json(self, prompt: str, *, schema: Optional[dict] = None, tools: Sequence[str] = (), timeout: float = 120.0,
                        function: str = "chat_agent", step: str = "plan",
                        context: Optional[Mapping[str, str]] = None) -> tuple[dict, Optional[float], str]:
        ctx = context or {}
        route = RouteContext(tag=build_tag(function, step, ctx), session_id=ctx.get("session_id") or None,
                             node_id=ctx.get("node_id") or None)
        req = JsonRequest(user=prompt, ctx=route, schema=schema, tools=tuple(tools), timeout_s=timeout)
        result = await asyncio.to_thread(self.router.call_json, req)
        if not isinstance(result.value, dict):
            raise InvalidJsonError("reply: the JSON is not an object", provider=result.turn.provider)
        return result.value, result.usd, result.how

    def status(self) -> Mapping[str, Mapping[str, Any]]:
        """Per provider, from cached facts (a status command runs only when its cache is older than 30 s; no model call)."""
        out: dict[str, Mapping[str, Any]] = {}
        for name in self.router.connectors:
            s = self.router.provider_summary(name)
            out[name] = {"installed": s.installed, "signed_in": s.signed_in, "detail": s.detail, "method": s.method,
                         "billing": s.billing, "plan": s.plan, "plan_label": s.plan_label, "version": s.version, "health": s.health.model_dump(mode="json"),
                         "quota": s.quota.model_dump(mode="json") if s.quota is not None else None}
        return out
