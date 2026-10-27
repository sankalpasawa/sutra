"""interface_http.py -- how a route says a write the interface refused (PRD A1.4, A1.20).

A write that does not fit the interface (layer_schema.SchemaFault, raised in refuse mode) is 422 NOT_IN_SCHEMA with its first
three faults, from whichever route met it. Two doors, one answer: `install(app)` registers the handler for the whole app (any
router a route of which writes through the sink, app.py's), and `InterfaceRoute` is the route class of a router that must
answer the same inside an app of a test's own making, where no handler is registered (an APIRouter has none of its own). The
routers that write through the sink (website_api, j2_api, j2ui_api, dept_api, org2_api) take the route class; app.py installs
the handler, so a router that is added later and writes is covered before it asks.

The same route class puts the department's versions in hand (W3-PINS, PRD A1.18): a route with a {ref} runs inside
engine_runtime.pinned(ref), so the definitions it reads (engine_def, all_steps, step_def) are those of the versions the
department's own record pins, whichever router the route is on.
"""
import contextlib

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

import layer_schema as S

FAULTS_SHOWN = 3


def refusal(exc):
    """The 422 answer for an S.SchemaFault: {detail: {code: 'NOT_IN_SCHEMA', faults: [the first three]}}."""
    return JSONResponse(status_code=422, content={"detail": {"code": "NOT_IN_SCHEMA", "faults": exc.faults[:FAULTS_SHOWN]}})


async def handle(request, exc):
    """The app-wide handler (app.add_exception_handler(S.SchemaFault, handle))."""
    return refusal(exc)


def install(app):
    """Register the handler on `app`, once for every route it serves."""
    app.add_exception_handler(S.SchemaFault, handle)
    return app


def department_pins(ref):
    """The context a route with a {ref} runs in: the versions that department's record pins (engine_runtime.pinned), and the
    default set for a route with no ref, a ref that is no department, or a runtime that cannot be asked."""
    if not ref:
        return contextlib.nullcontext()
    try:
        import engine_runtime
        return engine_runtime.pinned(str(ref))
    except Exception:  # noqa: BLE001 -- a request is never refused for want of its pins: it reads the default definitions
        return contextlib.nullcontext()


class InterfaceRoute(APIRoute):
    """A route that answers a SchemaFault with refusal(), inside any app the router is included in, and that runs in its
    department's versions (department_pins)."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            with department_pins(request.path_params.get("ref")):
                try:
                    return await handler(request)
                except S.SchemaFault as exc:
                    return refusal(exc)
        return guarded
