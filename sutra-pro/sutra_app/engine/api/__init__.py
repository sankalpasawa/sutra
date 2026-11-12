"""The engine's FastAPI adapter: J2's 28 data routes at the root with `?dept=`, plus the two engine-settings routes
(work package E4, engine design 4.9, 7.1 and 7.2).

    mount(app, services)    the plug-in call of the orchestrator (ORCH 3.5): registers the routes ONCE
    build_router(services)  the same routes as an APIRouter, for tests

The adapter is thin: `views.py` holds the one implementation of the handlers, `ctx.py` says which team and run a request is
about, `reply.py` turns a `Reply` into a response (redaction, charset, the security headers and the generated-content sandbox).
It serves no page, no static file and no cookie, and has no default team: `sutra_app.ui` serves the pages (S3-web-01).
"""
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from . import commands, files, library, rawchat, run_views, settings, state
from .ctx import dept_dependency
from .ports import DeptLike, EngineServices
from .reply import EngineError, error_response

__all__ = ["mount", "build_router", "EngineServices", "DeptLike", "MOUNT_MARK"]

MOUNT_MARK = "sutra_engine_api_mounted"


def _route_class(redact):
    class EngineRoute(APIRoute):
        """Turns a refusal raised by a dependency or a view (`EngineError`) into its own response, with the same headers."""

        def get_route_handler(self):
            original = super().get_route_handler()

            async def handler(request):
                try:
                    return await original(request)
                except EngineError as exc:
                    return error_response(exc, redact)
            return handler

    return EngineRoute


def build_router(services) -> APIRouter:
    router = APIRouter(route_class=_route_class(services.redact))
    dept_dep = dept_dependency(services)
    for module in (state, run_views, library, files, commands):
        module.add_routes(router, services, dept_dep)
    rawchat.add_routes(router, services, dept_dep)        # Sutra's own: the Raw AI chat debugger (/api/calls, /api/agent-live)
    settings.add_routes(router, services)
    return router


def mount(app: FastAPI, services: EngineServices) -> None:
    if getattr(app.state, MOUNT_MARK, False):
        raise RuntimeError("the engine routes are already mounted on this app")
    app.include_router(build_router(services))
    setattr(app.state, MOUNT_MARK, True)
