"""Graph routes (ORCH-4): shapes validated against the response models, query rules, error bodies, reads without a token."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_graph_store import World, tid

from sutra_app.library.node import step_node_id
from sutra_app.orchestrator.api import graph as graph_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.models import GraphView, NodeDetail
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services


@pytest.fixture
def world(db, clock):
    return World(db, clock)


def make_client(world, settings, *, graph="store", redact=None) -> TestClient:
    app = FastAPI()
    services = Services(settings=settings, version="test", db=world.db, redact=redact or Redactor(None, environ={}))
    services.graph = world.store if graph == "store" else None
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(graph_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def client(world, settings):
    return make_client(world, settings)


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and set(body["error"]) == {"code", "message", "details"}
    return body["error"]


# ---- GET /api/graph ---------------------------------------------------------------------------------------------------------------------

def test_the_graph_defaults_to_the_chart_level_and_matches_the_response_model(client, world):
    response = client.get("/api/graph")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/json")
    view = GraphView.model_validate(response.json())
    assert [n.id for n in view.nodes] == ["root", "sales", "leads", "quotes", "web", "menu"]
    assert view.chart_version == 1 and view.version == int(world.sql("SELECT value FROM meta WHERE key='graph_version'").fetchone()[0])
    assert {"src", "dst", "kind", "label"} == set(response.json()["edges"][0])


def test_the_full_level_adds_function_nodes_whose_meta_is_stats_and_wait_on(client):
    body = client.get("/api/graph", params={"level": "full"}).json()
    nodes = {n["id"]: n for n in body["nodes"]}
    assert "web.identity" in nodes and set(nodes["web.identity"]["meta"]) == {"stats", "wait_on"}
    assert set(nodes["web.identity"]["meta"]["stats"]) == {"calls", "seconds", "tokens_in", "tokens_out", "atoms_open", "atoms_closed", "atoms_failed", "atoms_total"}
    assert nodes["web.identity"]["kind"] == "function" and nodes["web.identity"]["fn"] == "identity"
    assert {"id", "kind", "label", "status", "detail", "chat_session_id", "org_node_id", "dept_id", "task_id", "fn", "step_ref", "version", "meta"} == set(nodes["web"])


def test_dept_and_task_narrow_the_graph(client, world):
    a, b = world.task(1, "web", "done"), world.task(2, "web", "running")
    ids = [n["id"] for n in client.get("/api/graph", params={"level": "full", "dept": "web", "task": b}).json()["nodes"]]
    assert step_node_id(b, "task") in ids and step_node_id(a, "task") not in ids and "sales" not in ids and ids[0] == "root"


@pytest.mark.parametrize("params", [{"level": "deep"}, {"dept": "bad id"}, {"task": "x" * 121}, {"dept": ""}])
def test_bad_query_values_are_422_validation(client, params):
    error = error_of(client.get("/api/graph", params=params), 422, "validation")
    assert error["details"]["violations"]


def test_an_unknown_department_or_task_is_404(client):
    error_of(client.get("/api/graph", params={"dept": "nope"}), 404, "not_found")
    error_of(client.get("/api/graph", params={"dept": "menu"}), 404, "not_found")             # a division is not a team
    error_of(client.get("/api/graph", params={"task": tid(77)}), 404, "not_found")


# ---- GET /api/graph/nodes/{id} ---------------------------------------------------------------------------------------------------------

def test_node_detail_of_a_function_node(client, world):
    world.atom("web.identity", "open", n=1)
    response = client.get("/api/graph/nodes/web.identity")
    assert response.status_code == 200
    detail = NodeDetail.model_validate(response.json())
    body = response.json()
    assert set(body) == {"node", "session", "atoms", "usage_total", "task", "archived_chats"}
    assert set(body["node"]["meta"]) == {"goal", "task", "context", "constraints", "wait_on", "hands_to", "stats"}
    assert body["node"]["meta"]["stats"]["atoms_total"] == 1 and detail.atoms[0].state == "open" and "schema" in body["atoms"][0]
    assert detail.session.id == detail.node.chat_session_id and body["task"] is None and body["archived_chats"] == []


def test_node_detail_of_a_step_carries_its_task(client, world):
    t = world.task(1, "web", "running")
    body = client.get(f"/api/graph/nodes/{step_node_id(t, 'task')}").json()
    assert body["node"]["kind"] == "step" and body["task"]["id"] == t and body["task"]["status"] == "running"


def test_an_unknown_node_is_404_and_a_malformed_id_is_422(client):
    error_of(client.get("/api/graph/nodes/web.nothing"), 404, "not_found")
    error_of(client.get("/api/graph/nodes/" + "a" * 121), 422, "validation")
    error_of(client.get("/api/graph/nodes/web identity"), 422, "validation")


# ---- rules of the router -------------------------------------------------------------------------------------------------------------------

def test_reads_need_no_token_and_the_router_has_no_write_route(client):
    assert client.get("/api/graph").status_code == 200 and client.get("/api/graph/nodes/web").status_code == 200
    methods = {m for route in graph_api.router.routes for m in route.methods}
    assert methods <= {"GET", "HEAD"}
    assert client.post("/api/graph").status_code == 405 and client.delete("/api/graph/nodes/web").status_code == 405


def test_the_routes_are_exactly_the_two_of_the_design():
    assert sorted(route.path for route in graph_api.router.routes) == ["/api/graph", "/api/graph/nodes/{node_id}"]


def test_a_secret_in_a_label_is_redacted_in_both_bodies(world, settings):
    secret = "sk-live-0123456789abcdef"
    world.sql("UPDATE graph_nodes SET label = ?, detail = ? WHERE id IN ('web', 'web.identity')", f"Web {secret}", f"asks for {secret}")
    client = make_client(world, settings, redact=Redactor(None, environ={}, extra=[secret]))
    assert secret not in client.get("/api/graph", params={"level": "full"}).text
    assert secret not in client.get("/api/graph/nodes/web.identity").text
    assert "[redacted]" in client.get("/api/graph/nodes/web.identity").text


def test_a_secret_from_the_environment_is_redacted_even_with_a_plain_redact_function(world, settings, monkeypatch):
    monkeypatch.setenv("SOME_API_KEY", "env-secret-value-1234")
    world.sql("UPDATE graph_nodes SET detail = 'env-secret-value-1234' WHERE id = 'web'")
    client = make_client(world, settings, redact=lambda text: text)               # no `scrub`: the response class still removes it
    assert "env-secret-value-1234" not in client.get("/api/graph/nodes/web").text


def test_without_a_graph_store_the_route_answers_internal(world, settings):
    error_of(make_client(world, settings, graph=None).get("/api/graph"), 500, "internal")
