"""The schema router (library design section 13; S3-web-03, S3-web-15; work package L8): `GET /api/schemas`,
`GET /api/schemas/{family}/{version}` and `POST /api/schemas/validate` with the orchestrator's error envelope and the write
guard on the POST. The app here is built the way the server builds it: the orchestrator's real `require_token` as the guard
and its `install_error_handlers`, so a refused token is the envelope the browser sees."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sutra_app.library.all  # noqa: F401  (the full registry)
from sutra_app.library import api
from sutra_app.library.gate import GATE, MAX_PAYLOAD_BYTES
from sutra_app.library.registry import REGISTRY, RegistryError
from sutra_app.orchestrator.api.deps import install_error_handlers, require_token

TOKEN = "t0ken-for-the-schema-tests"
AUTH = {"X-Sutra-Token": TOKEN}
GOOD_EDGE_FREE = {"kind": "department", "id": "sales", "home_dir": "departments/sales", "ts_created": 1}


def make_app(**router_args) -> FastAPI:
    app = FastAPI()
    app.state.services = SimpleNamespace(settings=SimpleNamespace(token=TOKEN))
    install_error_handlers(app)
    app.include_router(api.build_api_router(write_guard=require_token, **router_args))
    return app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(make_app(), base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


def envelope(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code and isinstance(body["error"]["message"], str) and isinstance(body["error"]["details"], dict)
    return body["error"]


# ============================================ the reads carry no token ======================================================
def test_the_list_names_every_family_with_its_versions_and_kinds(client):
    response = client.get("/api/schemas")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/json")
    families = {f["family"]: f for f in response.json()["families"]}
    assert set(families) >= set(REGISTRY.families()) - {"chat_session", "chat_message", "usage_record", "work_task"}
    assert families["atom"] == {"family": "atom", "versions": [1], "kinds": ["atom"]}
    assert families["node"]["kinds"] == ["root", "department", "division", "step", "identity", "adaptation", "priority",
                                         "coordination", "audit"]
    assert [f["family"] for f in response.json()["families"]] == sorted(f["family"] for f in response.json()["families"])


def test_a_schema_is_the_registrys_json_schema(client):
    response = client.get("/api/schemas/atom/1")
    assert response.status_code == 200 and response.json() == REGISTRY.json_schema("atom", 1)
    assert response.json()["type"] == "object" and "id" in response.json()["properties"]


def test_the_version_may_be_written_as_the_export_file_names_it(client):
    assert client.get("/api/schemas/atom/v1").json() == client.get("/api/schemas/atom/1").json()


def test_a_family_name_with_dots_is_found(client):
    assert client.get("/api/schemas/template.run/1").status_code == 200


def test_a_schema_that_does_not_exist_is_404_unknown_schema_with_the_versions_there_are(client):
    error = envelope(client.get("/api/schemas/atom/9"), 404, "unknown_schema")
    assert error["details"] == {"family": "atom", "version": "9", "versions": [1]}
    assert envelope(client.get("/api/schemas/no_such_family/1"), 404, "unknown_schema")["details"]["versions"] == []
    for version in ("x", "v", "-1", "1.5", "123456789", ""):
        if version:
            envelope(client.get(f"/api/schemas/atom/{version}"), 404, "unknown_schema")


def test_the_reads_need_no_token_and_the_validate_route_does_not_answer_a_get(client):
    assert client.get("/api/schemas").status_code == 200
    assert client.get("/api/schemas/validate").status_code in (404, 405)


# ============================================ the write guard ===============================================================
def test_validate_without_the_token_is_401_in_the_envelope(client):
    body = {"family": "department", "payload": GOOD_EDGE_FREE}
    envelope(client.post("/api/schemas/validate", json=body), 401, "bad_token")
    envelope(client.post("/api/schemas/validate", json=body, headers={"X-Sutra-Token": "wrong"}), 401, "bad_token")


def test_the_factory_demands_a_callable_write_guard():
    with pytest.raises(TypeError):
        api.build_api_router()                                        # required, keyword only
    with pytest.raises(TypeError):
        api.build_api_router(write_guard=None)
    with pytest.raises(TypeError):
        api.build_api_router(write_guard="require_token")
    assert api.build_router is api.build_api_router


def test_the_guard_is_on_the_post_only():
    router = api.build_api_router(write_guard=require_token)
    by_method = {(r.path, m): bool(r.dependencies) for r in router.routes for m in r.methods}
    assert by_method == {("/api/schemas", "GET"): False, ("/api/schemas/{family}/{version}", "GET"): False,
                         ("/api/schemas/validate", "POST"): True}


# ============================================ validate ======================================================================
def post(client, body, **kw):
    return client.post("/api/schemas/validate", json=body, headers=AUTH, **kw)


def test_a_good_payload_is_ok_with_the_sha_the_gate_gives(client):
    response = post(client, {"family": "department", "payload": GOOD_EDGE_FREE})
    assert response.status_code == 200 and response.json() == {"ok": True, "sha256": GATE.check("department", GOOD_EDGE_FREE).sha256}


def test_the_version_is_optional_and_may_be_given(client):
    assert post(client, {"family": "department", "version": 1, "payload": GOOD_EDGE_FREE}).json()["ok"] is True


def test_a_bad_payload_is_422_validation_with_every_violation(client):
    error = envelope(post(client, {"family": "department", "payload": {**GOOD_EDGE_FREE, "id": "X", "home_dir": "/abs"}}),
                     422, "validation")
    violations = error["details"]["violations"]
    assert {v["path"] for v in violations} >= {"id", "home_dir"}
    assert all(set(v) == {"path", "code", "message"} for v in violations)


def test_an_unknown_family_or_version_is_422_with_the_gates_words(client):
    first = envelope(post(client, {"family": "nope", "payload": {}}), 422, "validation")
    assert first["details"]["violations"][0]["code"] == "unknown_family"
    second = envelope(post(client, {"family": "department", "version": 7, "payload": GOOD_EDGE_FREE}), 422, "validation")
    assert second["details"]["violations"][0]["code"] == "unknown_version"


def test_a_payload_over_1_mib_is_413_in_the_same_envelope(client):
    big = {"family": "run_file.object", "payload": {"content": {"k": "x" * (MAX_PAYLOAD_BYTES + 10)}}}
    error = envelope(post(client, big), 413, "payload_too_large")
    assert error["details"]["limit"] == MAX_PAYLOAD_BYTES


def test_a_payload_over_the_limit_but_inside_the_body_room_is_refused_by_the_gate(client):
    payload = {"content": {"k": "x" * (MAX_PAYLOAD_BYTES + 500)}}
    assert MAX_PAYLOAD_BYTES < len(json.dumps(payload)) < api.MAX_BODY_BYTES
    error = envelope(post(client, {"family": "run_file.object", "payload": payload}), 413, "payload_too_large")
    assert error["details"]["violations"][0]["code"] == "payload_too_large"


def test_a_payload_just_under_the_limit_is_judged_by_its_shape(client):
    response = post(client, {"family": "run_file.object", "payload": {"content": {"k": "x" * (MAX_PAYLOAD_BYTES - 200)}}})
    assert response.status_code == 200


def test_a_body_over_the_limit_plus_its_room_is_refused_unparsed(client):
    body = b'{"family": "run_file.object", "payload": {"content": {"k": "' + b"x" * (MAX_PAYLOAD_BYTES + 20_000) + b'"}}}'
    error = envelope(client.post("/api/schemas/validate", content=body, headers={**AUTH, "content-type": "application/json"}),
                     413, "payload_too_large")
    assert error["details"]["size"] == len(body)


@pytest.mark.parametrize("raw,code,path", [
    (b"not json", "not_json", ""),
    (b"[]", "not_an_object", ""),
    (b'{"payload": {}}', "family", "family"),
    (b'{"family": "", "payload": {}}', "family", "family"),
    (b'{"family": "department"}', "payload", "payload"),
    (b'{"family": "department", "payload": []}', "payload", "payload"),
    (b'{"family": "department", "payload": {}, "version": true}', "version", "version"),
    (b'{"family": "department", "payload": {}, "version": "1"}', "version", "version"),
    (b'{"family": "department", "payload": {}, "extra": 1}', "extra_forbidden", "extra"),
])
def test_a_malformed_request_is_422_in_the_envelope_not_fastapis_detail_list(client, raw, code, path):
    response = client.post("/api/schemas/validate", content=raw, headers={**AUTH, "content-type": "application/json"})
    error = envelope(response, 422, "validation")
    assert (error["details"]["violations"][0]["code"], error["details"]["violations"][0]["path"]) == (code, path)


def test_a_family_name_over_120_characters_is_refused(client):
    assert envelope(post(client, {"family": "a" * 121, "payload": {}}), 422, "validation")


def test_the_router_can_serve_another_registry(toy_factory):
    toys = toy_factory()
    local = TestClient(make_app(registry=toys.registry), base_url="http://127.0.0.1:8780")
    assert {f["family"] for f in local.get("/api/schemas").json()["families"]} == {"thing", "pair", "doc"}
    assert local.post("/api/schemas/validate", json={"family": "thing", "payload": {"name": "x"}}, headers=AUTH).json()["ok"] is True
    assert local.post("/api/schemas/validate", json={"family": "department", "payload": GOOD_EDGE_FREE}, headers=AUTH).status_code == 422


def test_a_registry_programming_error_is_500_internal_and_leaks_nothing():
    class Broken:
        def check(self, *args, **kwargs):
            raise RegistryError("unknown_kind", "secret detail of the registry")

    app = TestClient(make_app(gate=Broken()), base_url="http://127.0.0.1:8780")
    response = app.post("/api/schemas/validate", json={"family": "department", "payload": GOOD_EDGE_FREE}, headers=AUTH)
    error = envelope(response, 500, "internal")
    assert "secret detail" not in json.dumps(error) and "unknown_kind" in error["message"]
