"""`POST /api/ops/update-check`: the Settings -> About button (gap package welcome-settings, item 2).

    POST /api/ops/update-check   -> {current, latest, newer, url, notes_url, how, kind, error, said}     needs the token (D81)

A POST on purpose: it makes an outbound request, so a page that was merely loaded (or a link, or an image tag) can never start it, and it needs the
launch token like every other write. The answer is always 200 with `error` set when GitHub could not be asked or understood (the page shows the
sentence, not an error page). Under `--offline` (or the stub connector) it is refused with 409 `offline` and the stub-mode sentence, and no request is
made. `said` is the one-line answer in the owner's words. The fetcher is `app.state.update_fetch` when a test sets one, else `update_check.default_fetch`.
"""
from fastapi import APIRouter, Depends, Request

from sutra_app.ops import update_check
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking
from sutra_app.orchestrator.errors import error_body

__all__ = ["build_router", "OFFLINE_WORDS"]

OFFLINE_WORDS = "Update check is not available while the app runs offline: it would need the internet, and offline mode makes no outside request."


def build_router() -> APIRouter:
    api = APIRouter(prefix="/api/ops", tags=["ops"])

    @api.post("/update-check", summary="Ask GitHub whether a newer Sutra Pro is out (downloads nothing)", dependencies=[Depends(require_token)])
    async def post_update_check(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        if services.settings.offline or services.settings.connector == "stub":
            return RedactedJSONResponse(error_body("offline", OFFLINE_WORDS), status_code=409)       # the connectors' own code for the same refusal
        fetch = getattr(request.app.state, "update_fetch", None)
        answer = await run_blocking(lambda: update_check.check(services.version, fetch=fetch))
        return RedactedJSONResponse({**answer.model_dump(), "said": update_check.sentence(answer)})

    return api
