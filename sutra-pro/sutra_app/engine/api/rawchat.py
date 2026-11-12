"""The Raw AI chat routes (Sutra's own, not J2 rows): the debugger's list of a run's AI calls and the live tail of its agents.

    GET /api/calls?dept=&run=&offset=&limit=&q=   `rawchat.call_list` of the run: metadata and previews only; the full text of one call is
                                                   `/api/call?dept=&run=&id=` (J2's row 5)
    GET /api/agent-live?dept=&run=                 `rawchat.live_tail` of the run: what each working agent has written so far

Both read like every J2 GET: `?dept=` names the team (400, 404 as J2's routes), `?run=` a saved run of that team, else the team's current
run, else idle (empty answers). Reads need no token, as every GET of the engine; the bodies are redacted by `to_response`.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from .. import rawchat
from .ctx import build_ctx, first_values
from .reply import json_reply, to_response

__all__ = ["PATHS", "add_routes"]

PATHS = ("/api/calls", "/api/agent-live")          # not `ROUTES`: that name is the J2 rows (path, view) the traceability script reads


def _folder(ctx):
    return ctx.dir if ctx.dir else None


def add_routes(router: APIRouter, services, dept_dep) -> None:
    def calls(request: Request, dept: str = Depends(dept_dep)) -> Response:
        q = first_values(request)
        ctx = build_ctx(services, dept, q.get("run"))
        body = rawchat.call_list(_folder(ctx), q.get("offset"), q.get("limit"), q.get("q", ""))
        body.update(run=ctx.run_id or "", mode=ctx.mode, live=ctx.mode == "live" and bool(ctx.alive))
        return to_response(json_reply(body), services.redact)

    def agent_live(request: Request, dept: str = Depends(dept_dep)) -> Response:
        q = first_values(request)
        ctx = build_ctx(services, dept, q.get("run"))
        body = rawchat.live_tail(_folder(ctx))
        body.update(run=ctx.run_id or "", live=ctx.mode == "live" and bool(ctx.alive))
        return to_response(json_reply(body), services.redact)

    router.get("/api/calls", response_class=Response)(calls)
    router.get("/api/agent-live", response_class=Response)(agent_live)
