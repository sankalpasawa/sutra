"""The shared world of the contract tests: the real orchestrator side (database, stores, task service, projector) wired into one
`Services`, the engine's routes mounted on it, and every router of the app collected by name. Fixtures and helpers only; the one
test here proves that the world is the real thing and not a fake that agrees with itself.

The other `test_contract_*` modules import `world`, `World` and the helpers by name from here."""
from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.conftest import clock, db, events, ids, settings  # noqa: F401  (fixtures used by name)
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.connectors.api import build_api_router
from sutra_app.connectors.factory import build_router as build_connector_router
from sutra_app.engine.api import build_router as build_engine_router
from sutra_app.engine.api import mount as mount_engine
from sutra_app.ops import api as ops_api
from sutra_app.ops import attention_api, update_api, welcome
from sutra_app.orchestrator.api import agent_chats, atoms, chart, chat, departments, events as events_api, graph, insight, limits, recurring, rules_notes, tasks, usage
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class, require_token
from sutra_app.orchestrator.departments import DepartmentStore
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services
from sutra_app.ui import routes as ui_routes

REPO = Path(__file__).resolve().parents[2]
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOKEN_HEADER = "X-Sutra-Token"


@dataclass
class World:
    t: TEnv
    services: Services
    app: FastAPI
    client: TestClient
    routers: dict[str, Any]          # name -> APIRouter, one per section that serves routes
    connector_router: Any

    @property
    def auth(self) -> dict[str, str]:
        return {TOKEN_HEADER: self.t.settings.token}


def route_table(router) -> dict[tuple[str, str], Any]:
    """{(METHOD, path): APIRoute} of one router; HEAD and OPTIONS are not routes of their own."""
    table = {}
    for route in router.routes:
        for method in route.methods - {"HEAD", "OPTIONS"}:
            table[(method, route.path)] = route
    return table


def dependency_calls(route) -> set[Callable]:
    """Every dependency callable of a route, route-level and nested."""
    found: set[Callable] = set()

    def walk(dependant) -> None:
        for sub in dependant.dependencies:
            if sub.call is not None:
                found.add(sub.call)
            walk(sub)
    walk(route.dependant)
    return found


@pytest.fixture
def world(tenv) -> Iterator[World]:  # noqa: F811
    t = tenv
    redact = Redactor(None, environ={})
    services = Services(settings=t.settings, version="test", db=t.db, redact=redact)
    services.tasks, services.usage, services.atoms, services.graph = t.service, t.usage, t.atoms, t.graph
    services.chats, services.projector, services.watcher, services.launcher = t.chats, t.projector, t.watcher, t.launcher
    services.department = DepartmentStore(t.db, t.settings.data_dir).row
    services.resolve_run = t.service.resolve_run
    services.deliver_to_department = t.service.deliver_to_department
    services.stop_live = t.service.stop_live
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.services = services
    install_error_handlers(app, redacted_response_class(redact))
    mount_engine(app, services)
    routers: dict[str, Any] = {"engine": build_engine_router(services)}
    for name, module in (("agent_chats", agent_chats), ("attention", attention_api), ("atoms", atoms), ("chart", chart), ("chat", chat), ("departments", departments), ("events", events_api),
                         ("graph", graph), ("insight", insight), ("limits", limits), ("recurring", recurring), ("rules_notes", rules_notes), ("tasks", tasks), ("usage", usage), ("welcome", welcome), ("update", update_api)):
        routers[name] = module.build_router()
        app.include_router(routers[name])
    routers["ops"] = ops_api.router                     # GAP-CONSOLE: the owner console's routes, which console_view.js calls
    app.include_router(routers["ops"])
    connector_router = build_connector_router(t.settings.model_copy(update={"offline": True}), usage_sink=t.usage)
    routers["connectors"] = build_api_router(router=connector_router, write_guard=services.require_token)
    routers["ui"] = ui_routes.build_router(token=t.settings.token, department=services.department, version="test")
    client = TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)
    try:
        yield World(t, services, app, client, routers, connector_router)
    finally:
        connector_router.close()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_the_world_is_the_real_orchestrator_with_the_engine_routes_on_it(world):
    """Not a fake that agrees with itself: real stores, the real token guard, the real department lookup."""
    assert world.services.require_token is require_token
    assert world.services.department("web").name == "Web"
    assert world.services.department("nowhere") is None
    assert inspect.ismethod(world.services.resolve_run) and inspect.ismethod(world.services.stop_live)
    assert world.client.get("/api/runs", params={"dept": "web"}).json() == {"live": "", "runs": []}
