"""`/api/connectors/*`: the HTTP face of the connector layer (connectors design 5.6 and 6, S3-web-03, S3-web-15).

    app.include_router(build_api_router(router=router, write_guard=services.require_token))

`write_guard` is a REQUIRED keyword argument (S3-web-03): leaving it out is a `TypeError` at build time, so no deployment can
mount unguarded write routes by forgetting it. Every PUT, POST and DELETE depends on it (`Services.require_token`: header
`X-Sutra-Token`, Origin check); reads need no token. The router carries the `/api/connectors` prefix.

Errors leave in the orchestrator's envelope `{"error": {"code", "message", "details"}}` (S3-web-15); `message` is the sentence
the person reads (`user_message()` of a `ConnectorError`) and `details.kind` holds the error kind for those. The HTTP status of
a `ConnectorError` follows its kind: cli_missing, auth and unavailable 503, quota 429, timeout 504, bad_output 502, and
422 for `invalid_request` and `policy_invalid`. The write guard's own refusals (`bad_token`, `bad_origin`) are the orchestrator's
`AppError`, answered by the app's handler. Bodies go through the app's redacting JSON response.

Routes (GET unless noted): status, models, policy (GET, PUT), `{provider}/test` (POST), `codex/sign-in` (POST), `codex/sign-in/{id}`
(GET, DELETE), `sessions/{session_id}/provider` (PUT), tools, mediated (GET) and `mediated/refresh` (POST).

Decisions taken here (docs/notes/CN-9.md): a stored policy is also adopted by the running router (order, rules, timeouts, and the
sandbox and rate card of Codex), so status and file never disagree; the Test button runs through a router restricted to the
tested provider that shares the policy, health book and usage sink (a fallback answering would mislead), and its usage row has
purpose `connector_test`; offline mode refuses test, sign-in and a mediated refresh because they would start a CLI.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from sutra_app.engine.port import CallTag
from sutra_app.orchestrator.api.deps import RedactedJSONResponse
from sutra_app.orchestrator.errors import error_body

from .env import child_env
from .errors import ConnectorError, InvalidRequestError, PolicyInvalidError
from .models import AskRequest, Provider, RouteContext
from .policy import write_policy
from .router import Router
from .tools.github_tools import gh_env
from .tools.mediated import MediatedConnectors, RefreshTooSoon
from .tools.profiles import PROFILES, tool_catalog, tools_status

__all__ = ["build_api_router", "PREFIX", "TEST_PROMPT", "MAX_POLICY_BYTES", "status_for"]

PREFIX = "/api/connectors"
TEST_PROMPT = "Reply with the single word ok"
TEST_TIMEOUT_S = 120.0
MAX_POLICY_BYTES = 256 * 1024
_STATUS_BY_KIND = {"unavailable": 503, "auth": 503, "quota": 429, "timeout": 504, "bad_output": 502}
_STATUS_BY_CODE = {"invalid_request": 422, "policy_invalid": 422, "envelope_exceeded": 429, "cancelled": 409, "cli_missing": 503}


class ApiFailure(Exception):
    """A refusal of this module, answered in the envelope with its own code and status."""

    def __init__(self, status: int, code: str, message: str, details: Optional[dict] = None, headers: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details = dict(details or {})
        self.headers = dict(headers or {})


def status_for(err: ConnectorError) -> int:
    """The HTTP status of a connector error: by code where the code says more than the kind, else by kind."""
    return _STATUS_BY_CODE.get(err.code) or _STATUS_BY_KIND.get(err.kind, 503)


def _failure_of(err: ConnectorError) -> ApiFailure:
    if isinstance(err, PolicyInvalidError):
        details: dict[str, Any] = {"kind": err.kind, "errors": list(err.detail.get("errors", []))}
    else:
        shown = err.as_dict()
        details = {"kind": err.kind, "provider": err.provider, "retryable": err.retryable, "detail": shown["detail"],
                   "resets_at": err.resets_at}
    return ApiFailure(status_for(err), err.code, err.user_message(), details)


class ConnectorRoute(APIRoute):
    """Turns `ApiFailure` and every `ConnectorError` raised by a handler into the error envelope."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ConnectorError as err:
                failure = _failure_of(err)
            except ApiFailure as err:
                failure = err
            return RedactedJSONResponse(status_code=failure.status, content=error_body(failure.code, failure.message, failure.details),
                                        headers=failure.headers or None)
        return handler


class _Pin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Optional[Provider]


def _offline(router: Router, what: str) -> ApiFailure:
    return ApiFailure(409, "offline", f"{what} is not available while the app runs offline (no CLI is started)", {"kind": "unavailable"})


def _data_dir(router: Router):
    for connector in router.connectors.values():
        return connector.cfg.data_dir
    raise ApiFailure(503, "provider_unavailable", "No connector is configured", {"kind": "unavailable"})


def _adopt_policy(router: Router, policy) -> None:
    """The running router follows the stored policy. Routing decisions read `router.policy` on every call; Codex keeps its sandbox
    and rate card on the connector. Concurrency caps keep the value they were created with until restart."""
    router.policy = policy
    router.policy_source = "file"
    router.policy_error = None
    codex = router.connectors.get("codex")
    if codex is not None and "codex" in policy.providers:
        codex.rates = dict(policy.rates.get("codex", {}))                       # type: ignore[attr-defined]
        codex.sandbox = policy.providers["codex"].sandbox or "read-only"        # type: ignore[attr-defined]


def _restricted(router: Router, provider: str) -> Router:
    """A router for ONE provider that shares the policy, the health book, the usage sink and the events of `router`."""
    kw: dict[str, Any] = {}
    for name, attr in (("sleep", "_sleep"), ("clock", "_clock"), ("rng", "_rng"), ("events", "_events")):
        if hasattr(router, attr):
            kw[name] = getattr(router, attr)
    return Router({provider: router.connectors[provider]}, router.policy, usage_sink=router.usage_sink, health=router.health,
                  connector=provider, policy_source=router.policy_source, policy_error=router.policy_error, **kw)


def build_api_router(*, router: Router, write_guard: Callable[..., Any], mediated: Optional[MediatedConnectors] = None) -> APIRouter:
    """The `/api/connectors` routes over `router`. `write_guard` is required (`Services.require_token`). `mediated` is for tests;
    by default it is built from the connectors' configuration."""
    if not callable(write_guard):
        raise TypeError("write_guard must be a callable FastAPI dependency (Services.require_token)")
    api = APIRouter(prefix=PREFIX, route_class=ConnectorRoute, default_response_class=RedactedJSONResponse, tags=["connectors"])
    guard = [Depends(write_guard)]
    held: dict[str, Optional[MediatedConnectors]] = {"m": mediated}

    def cfg_of_router():
        for connector in router.connectors.values():
            return connector.cfg
        raise ApiFailure(503, "provider_unavailable", "No connector is configured", {"kind": "unavailable"})

    def mediated_connectors() -> MediatedConnectors:
        if held["m"] is None:
            held["m"] = MediatedConnectors(cfg_of_router())
        return held["m"]                                    # type: ignore[return-value]

    def connector_of(name: str):
        found = router.connectors.get(name)
        if found is None:
            raise ApiFailure(404, "not_found", f"{name} is not a configured provider", {"kind": "unavailable"})
        return found

    def codex_of():
        if router.mode == "offline":
            raise _offline(router, "Codex sign-in")
        found = router.connectors.get("codex")
        if found is None:
            raise ApiFailure(503, "provider_unavailable", "Codex is not configured (check the routing policy and SUTRA_CONNECTOR)",
                             {"kind": "unavailable"})
        return found

    # ---- reads ------------------------------------------------------------------------------------------------------------
    @api.get("/status", summary="Mode, policy, and each provider's sign-in, health, quota and today's use")
    def get_status(refresh: bool = False) -> dict:
        body = router.status(refresh=refresh).model_dump(mode="json")
        if router.mode == "offline":
            body["tools"] = {"sutra": True, "github": False}
        else:
            cfg = cfg_of_router()
            body["tools"] = tools_status(cfg, env={**gh_env(), **child_env("gh", cfg.extra_env)})
        body["mediated"] = f"{PREFIX}/mediated"
        return body

    @api.get("/models", summary="The models a provider offers")
    def get_models(provider: Optional[str] = None) -> dict:
        if provider is not None:
            return {"models": [m.model_dump(mode="json") for m in connector_of(provider).models()]}
        models: list[dict] = []
        for name, connector in router.connectors.items():
            try:
                models += [{**m.model_dump(mode="json"), "provider": name} for m in connector.models()]
            except ConnectorError:
                continue                                  # a provider that cannot list (not signed in) is left out of the union
        return {"models": models}

    @api.get("/policy", summary="The routing policy in force")
    def get_policy() -> dict:
        return router.policy.model_dump(mode="json")

    @api.get("/tools", summary="The read-only tools the models may use")
    def get_tools() -> dict:
        return {"profiles": list(PROFILES), "tools": tool_catalog("sutra+github")}

    @api.get("/mediated", summary="Gmail, Drive and Slack as Claude holds them (observed, never implemented)")
    def get_mediated() -> dict:
        return mediated_connectors().snapshot()

    @api.get("/codex/sign-in/{sign_in_id}", summary="Where a Codex sign-in stands")
    def get_sign_in(sign_in_id: str) -> dict:
        codex = codex_of()
        try:
            state = codex.sign_in_poll(sign_in_id)            # type: ignore[attr-defined]
        except InvalidRequestError as err:
            raise ApiFailure(404, "not_found", err.user_message(), {"kind": "unavailable"}) from None
        if state.get("state") == "signed_in":
            _signed_in(router)
        return state

    # ---- writes (all behind the guard) ------------------------------------------------------------------------------------
    @api.put("/policy", dependencies=guard, summary="Store a new routing policy (validated first)")
    async def put_policy(request: Request) -> dict:
        body = await request.body()
        if len(body) > MAX_POLICY_BYTES:
            raise ApiFailure(422, "policy_invalid", f"The routing policy is larger than {MAX_POLICY_BYTES // 1024} KB",
                             {"kind": "unavailable", "errors": ["policy: too large"]})
        policy = await run_in_threadpool(write_policy, _data_dir(router), body)    # PolicyInvalidError becomes the 422 envelope
        _adopt_policy(router, policy)
        return policy.model_dump(mode="json")

    @api.post("/{provider}/test", dependencies=guard, summary="One tiny call to check that a provider answers")
    def post_test(provider: str) -> dict:
        if router.mode == "offline":
            raise _offline(router, "The connector test")
        connector_of(provider)
        started = time.monotonic()
        req = AskRequest(user=TEST_PROMPT, kind="text", effort="low", timeout_s=TEST_TIMEOUT_S,
                         ctx=RouteContext(tag=CallTag(function="connectors", purpose="connector_test")))
        turn = _restricted(router, provider).ask(req)
        return {"ok": True, "provider": turn.provider, "model": turn.model, "seconds": round(time.monotonic() - started, 1),
                "tokens_in": turn.usage.input_total, "tokens_out": turn.usage.output_tokens, "usd": turn.usd,
                "reply": turn.text.strip()[:80]}

    @api.post("/codex/sign-in", dependencies=guard, summary="Start the Codex device sign-in")
    def post_sign_in() -> dict:
        return codex_of().begin_sign_in().as_dict()       # type: ignore[attr-defined]

    @api.delete("/codex/sign-in/{sign_in_id}", dependencies=guard, status_code=204, response_class=Response,
                summary="Stop a pending Codex sign-in")
    def delete_sign_in(sign_in_id: str) -> Response:
        try:
            codex_of().cancel_sign_in(sign_in_id)         # type: ignore[attr-defined]
        except InvalidRequestError as err:
            raise ApiFailure(404, "not_found", err.user_message(), {"kind": "unavailable"}) from None
        return Response(status_code=204)

    @api.put("/sessions/{session_id}/provider", dependencies=guard, status_code=204, response_class=Response,
             summary="Pin a chat to a provider (or clear the pin with null)")
    def put_pin(session_id: str, body: _Pin = Body(...)) -> Response:
        router.chat_pin(session_id, body.provider)        # InvalidRequestError (bad id, unknown provider) becomes the 422 envelope
        return Response(status_code=204)

    @api.post("/mediated/refresh", dependencies=guard, summary="Ask Claude now which connectors it holds (at most once a minute)")
    def post_mediated_refresh() -> dict:
        if router.mode == "offline":
            raise _offline(router, "Checking Claude's connectors")
        try:
            return mediated_connectors().refresh()
        except RefreshTooSoon as err:
            wait = max(1, int(err.retry_after_s + 0.999))
            raise ApiFailure(429, "refresh_too_soon", str(err), {"kind": "rate_limited", "retry_after_s": wait},
                             {"Retry-After": str(wait)}) from None

    return api


def _signed_in(router: Router) -> None:
    """A finished Codex sign-in: forget the cached `signed out` and tell the page (`connector.health`)."""
    router.health.forget_auth("codex")
    state = router.health.state("codex")
    router._emit("connector.health", {"provider": "codex", "state": state.state, "until": state.until, "reason": state.reason})
