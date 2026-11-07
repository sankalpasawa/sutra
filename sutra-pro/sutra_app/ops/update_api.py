"""The update routes: the Settings -> About button and the desktop app's automatic check (gap packages welcome-settings item 2 and autoupdate).

    POST /api/ops/update-check    -> {current, latest, newer, url, notes_url, how, kind, error, tag, assets, said}       needs the token (D81)
    POST /api/ops/update-plan     {auto?, platform?, arch?} -> the same + {channel, asset}                               needs the token
    GET  /api/ops/update-setting  -> {auto, chosen, default, desktop, offline, last}                                     an open read on loopback
    PUT  /api/ops/update-setting  {auto: bool} -> the same GET answer                                                    needs the token
    POST /api/ops/update-status   {state, version, message} -> the same GET answer                                       needs the token
    POST /api/ops/update-install  {can, why} -> the same GET answer                                                      needs the token

The two POSTs that ask GitHub are POSTs on purpose: they make an outbound request, so a page that was merely loaded (or a link, or an image tag) can
never start them, and they need the launch token like every other write. Each answers 200 with `error` set when GitHub could not be asked or understood
(the page shows the sentence, not an error page). Under `--offline` (or the stub connector) both are refused with 409 `offline` and the stub-mode
sentence, and no request is made. `said` is the one-line answer in the owner's words. The fetcher is `app.state.update_fetch` when a test sets one,
else `update_check.default_fetch`.

`update-plan` is what the desktop app's own timer asks (about a minute after launch, then every 6 hours): the answer of `update-check` plus the one
asset of that platform and architecture, so the versions, the channels (a beta install sees newer betas and stables, a stable install only stables) and
the feed's parsing have ONE implementation, here. With `auto: true` it is refused with 409 `update_off` and NO request while the owner's setting
"Check for updates automatically" is off; the desktop checks the setting first and the server enforces it again. Every plan records the "last check"
line the About group shows; the desktop adds its own as it goes (`update-status`: downloading, ready, failed, tell_only, installing). The desktop also says,
once at start (`update-install`), whether THIS copy can install an update itself or can only tell (an ad hoc or unsigned copy cannot tell who signed one);
the About group says which.

Nothing else here, and nothing at boot, makes a request. The setting and the last line are two `meta` rows (ops/update_state.py).
"""
import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from sutra_app.library.types import violation
from sutra_app.ops import update_check, update_state
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import error_body, validation_error

__all__ = ["build_router", "OFFLINE_WORDS", "OFF_WORDS", "UpdatePlanBody", "UpdateStatusBody", "UpdateSettingBody", "UpdateInstallBody"]

OFFLINE_WORDS = "Update check is not available while the app runs offline: it would need the internet, and offline mode makes no outside request."
OFF_WORDS = "Automatic update checks are switched off in Settings, About."
_NAME = r"^[a-z0-9_]{1,12}$"


class UpdatePlanBody(BaseModel):
    """`auto` says the desktop's timer is asking (the setting then has to be on); an owner's click leaves it out. platform and arch are Node's names."""

    model_config = ConfigDict(extra="forbid", strict=True)
    auto: bool = False
    platform: str | None = Field(None, pattern=_NAME)
    arch: str | None = Field(None, pattern=_NAME)


class UpdateSettingBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    auto: bool


class UpdateStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    state: str
    version: str | None = Field(None, max_length=40)
    message: str = Field("", max_length=update_state.MAX_MESSAGE)


class UpdateInstallBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    can: bool
    why: str = Field("", max_length=update_state.MAX_MESSAGE)


def _offline(services: Any) -> bool:
    return bool(services.settings.offline or services.settings.connector == "stub")


def _setting_answer(services: Any) -> dict[str, Any]:
    on, chosen = update_state.get_auto(services)
    return {"auto": on, "chosen": chosen, "default": True, "desktop": os.environ.get("SUTRA_PRO_DESKTOP") == "1", "offline": _offline(services),
            "last": update_state.get_last(services), "install": update_state.get_install(services)}


def _scrubbed(request: Request, content: Any) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(scrub(content) if callable(scrub) else content)


def _refuse(code: str, words: str) -> RedactedJSONResponse:
    return RedactedJSONResponse(error_body(code, words), status_code=409)          # `offline` and `update_off` are not in the orchestrator's table: the status is set here


def _remember(services: Any, answer: update_check.Answer) -> None:
    """The "last check" line of one answer, in the owner's words. A store that cannot be written never fails the check."""
    state = "error" if answer.error else ("available" if answer.newer else "up_to_date")
    words = update_check.sentence(answer) if state != "available" else f"Sutra Pro {answer.latest} is out."
    try:
        update_state.set_last(services, state, answer.latest if state == "available" else None, words)
    except Exception:                                                              # noqa: BLE001
        pass


def build_router() -> APIRouter:
    api = APIRouter(prefix="/api/ops", tags=["ops"])

    @api.post("/update-check", summary="Ask GitHub whether a newer Sutra Pro is out (downloads nothing)", dependencies=[Depends(require_token)])
    async def post_update_check(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        if _offline(services):
            return _refuse("offline", OFFLINE_WORDS)                               # the connectors' own code for the same refusal
        fetch = getattr(request.app.state, "update_fetch", None)
        answer = await run_blocking(lambda: update_check.check(services.version, fetch=fetch))
        await run_blocking(lambda: _remember(services, answer))
        return RedactedJSONResponse({**answer.model_dump(), "said": update_check.sentence(answer)})

    @api.post("/update-plan", summary="The desktop app's check: the answer of update-check plus the asset of its platform", dependencies=[Depends(require_token)])
    async def post_update_plan(request: Request, body: UpdatePlanBody) -> RedactedJSONResponse:
        services = services_of(request)
        if _offline(services):
            return _refuse("offline", OFFLINE_WORDS)
        if body.auto and not update_state.get_auto(services)[0]:
            return _refuse("update_off", OFF_WORDS)                                # the owner switched the automatic check off: no request
        fetch = getattr(request.app.state, "update_fetch", None)
        found = await run_blocking(lambda: update_check.plan(services.version, body.platform, body.arch, fetch=fetch))
        await run_blocking(lambda: _remember(services, found))
        return RedactedJSONResponse({**found.model_dump(), "said": update_check.sentence(found)})

    @api.get("/update-setting", summary="Whether the app checks for updates by itself, and the last check")
    async def get_update_setting(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        return _scrubbed(request, await run_blocking(lambda: _setting_answer(services)))

    @api.put("/update-setting", summary="Switch the automatic update check on or off", dependencies=[Depends(require_token)])
    async def put_update_setting(request: Request, body: UpdateSettingBody) -> RedactedJSONResponse:
        services = services_of(request)

        def save() -> dict[str, Any]:
            update_state.set_auto(services, body.auto)
            return _setting_answer(services)
        return _scrubbed(request, await run_blocking(save))

    @api.post("/update-status", summary="The desktop app reports where an update is (downloading, ready, failed, ...)", dependencies=[Depends(require_token)])
    async def post_update_status(request: Request, body: UpdateStatusBody) -> RedactedJSONResponse:
        services = services_of(request)
        if body.state not in update_state.STATES:
            words = f"state is one of {', '.join(update_state.STATES)}"
            raise validation_error([violation("state", "invalid", words)], words)

        def save() -> dict[str, Any]:
            update_state.set_last(services, body.state, body.version, body.message)
            return _setting_answer(services)
        return _scrubbed(request, await run_blocking(save))

    @api.post("/update-install", summary="The desktop app says whether this copy can install an update itself or only tells", dependencies=[Depends(require_token)])
    async def post_update_install(request: Request, body: UpdateInstallBody) -> RedactedJSONResponse:
        services = services_of(request)

        def save() -> dict[str, Any]:
            update_state.set_install(services, body.can, body.why)
            return _setting_answer(services)
        return _scrubbed(request, await run_blocking(save))

    return api
