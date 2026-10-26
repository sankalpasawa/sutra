"""interface_http.py -- how a route says a write the interface refused (PRD A1.4, A1.20).

A write that does not fit the interface (layer_schema.SchemaFault, raised in refuse mode) is 422 NOT_IN_SCHEMA with its first
three faults, from whichever route met it. Two doors, one answer: `install(app)` registers the handler for the whole app (any
router a route of which writes through the sink, app.py's), and `InterfaceRoute` is the route class of a router that must
answer the same inside an app of a test's own making, where no handler is registered (an APIRouter has none of its own). The
routers that write through the sink (website_api, j2_api, j2ui_api, dept_api, org2_api) take the route class; app.py installs
the handler, so a router that is added later and writes is covered before it asks.
"""
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


class InterfaceRoute(APIRoute):
    """A route that answers a SchemaFault with refusal(), inside any app the router is included in."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                return await handler(request)
            except S.SchemaFault as exc:
                return refusal(exc)
        return guarded
