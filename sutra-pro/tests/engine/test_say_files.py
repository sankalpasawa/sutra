"""D451, T5: files on `POST /api/say` (the start box and every "Tell the team" route). FR-2 the files travel with the words, FR-3 a send is all or nothing.

Two layers. The engine adapter over the fake services of conftest checks the body's shape and what the port is handed. The real orchestrator (`world`, test_contract_world) checks that the ids are
resolved in the store, that they are kept on the task, and that a refusal stores nothing. No model is called.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from contracts.test_contract_world import World, world  # noqa: F401  (a fixture)
from orchestrator.conftest import clock, db, events, ids, settings  # noqa: F401  (fixtures the world is built on)
from orchestrator.test_tasks import tenv  # noqa: F401  (a fixture)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.connectors.attachments import AttachmentStore
from sutra_app.engine.api import mount

TOKEN = {"X-Sutra-Token": "fake-token-fake-token-0123"}
A, B = "a" * 64, "b" * 64


@pytest.fixture
def api(fake_services):
    svc = fake_services
    svc.add_department("web")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, svc)
    return SimpleNamespace(svc=svc, client=TestClient(app, raise_server_exceptions=False))


def say(api, **body):
    return api.client.post("/api/say?dept=web", json={"text": "read the spec", **body}, headers=TOKEN)


# ---- the adapter ---------------------------------------------------------------------------------------------------------------------

def test_files_in_the_body_reach_the_port_in_order(api):
    got = say(api, files=[{"id": A, "name": "spec.docx"}, {"id": B, "name": "sheet.csv"}])
    assert (got.status_code, got.json()) == (200, {"ok": True})
    assert api.svc.deliveries[-1]["input_files"] == [{"id": A, "name": "spec.docx"}, {"id": B, "name": "sheet.csv"}]


def test_a_body_without_files_is_handed_to_the_port_exactly_as_before(api):
    say(api)
    say(api, files=[])
    assert all("input_files" not in d for d in api.svc.deliveries)


@pytest.mark.parametrize("files", ["spec.docx", {"id": A}, [{"id": A}], [{"id": "short", "name": "x.txt"}], [{"id": A, "name": 5}], [A], [{"id": A, "name": "x", "extra": 1}],
                                   [{"id": A, "name": "x.txt"}] * 11])
def test_a_files_field_of_the_wrong_shape_is_400_and_nothing_is_delivered(api, files):
    got = say(api, files=files)
    assert got.status_code == 400 and got.json() == {"error": "files must be a list of {id, name}, at most 10"}
    assert api.svc.deliveries == []


# ---- the real orchestrator -----------------------------------------------------------------------------------------------------------

def stored(world: World, name: str, blob: bytes) -> dict:
    ref = AttachmentStore(world.t.settings.data_dir).save(name, blob)
    return {"id": ref.id, "name": ref.name}


def counts(world: World) -> tuple[int, int]:
    return world.t.one("SELECT count(*) FROM tasks"), world.t.one("SELECT count(*) FROM chat_messages")


def test_two_stored_files_are_kept_on_the_task_the_say_creates(world):
    files = [stored(world, "spec.txt", b"the spec"), stored(world, "sheet.csv", b"a,b\n1,2\n")]
    got = world.client.post("/api/say?dept=web", json={"text": "read these", "files": files}, headers=world.auth)
    assert (got.status_code, got.json()) == (200, {"ok": True})
    (row,) = world.t.sql("SELECT id, input_files_json FROM tasks WHERE dept_id = 'web'").fetchall()
    kept = json.loads(row["input_files_json"])
    assert [(f["id"], f["name"], f["kind"]) for f in kept] == [(files[0]["id"], "spec.txt", "text"), (files[1]["id"], "sheet.csv", "text")]


def test_the_owners_line_in_the_team_chat_records_the_files_for_the_receipt(world):
    files = [stored(world, "spec.txt", b"the spec")]
    world.client.post("/api/say?dept=web", json={"text": "read this", "files": files}, headers=world.auth)
    meta = json.loads(world.t.one("SELECT meta_json FROM chat_messages WHERE role = 'user' ORDER BY id DESC LIMIT 1"))
    (shown,) = meta["attachments"]
    assert (shown["id"], shown["name"], shown["kind"], shown["sent"], shown["chars"]) == (files[0]["id"], "spec.txt", "text", "given", 8)


def test_an_unknown_file_id_is_404_and_nothing_at_all_is_stored(world):
    good = stored(world, "spec.txt", b"the spec")
    before = counts(world)
    got = world.client.post("/api/say?dept=web", json={"text": "read these", "files": [good, {"id": "0" * 64, "name": "gone.txt"}]}, headers=world.auth)
    assert got.status_code == 404 and got.json()["error"]["code"] == "not_found"
    assert counts(world) == before


def test_a_busy_team_refuses_and_stores_no_second_task(world):
    first = world.client.post("/api/say?dept=web", json={"text": "first"}, headers=world.auth)
    assert first.status_code == 200
    world.t.run(world.t.service.start_ready())
    files = [stored(world, "spec.txt", b"the spec")]
    before = counts(world)
    got = world.client.post("/api/say?dept=web", json={"text": "second", "files": files}, headers=world.auth)
    assert got.status_code == 409 and counts(world) == before


def test_files_with_an_answer_to_a_teams_question_are_refused_in_a_sentence_not_dropped(world):
    """OQ-6, decided: files in an answer are a later release. The send is refused whole (G4: a file is never dropped silently), the words are not sent as an answer either."""
    world.client.post("/api/say?dept=web", json={"text": "first"}, headers=world.auth)
    world.t.run(world.t.service.start_ready())
    row = world.t.sql("SELECT id FROM tasks").fetchone()
    world.t.sql("UPDATE tasks SET status = 'waiting_user' WHERE id = ?", row["id"])
    files = [stored(world, "spec.txt", b"the spec")]
    before = counts(world)
    got = world.client.post("/api/say?dept=web", json={"text": "my answer", "files": files}, headers=world.auth)
    assert got.status_code == 422 and "answer" in got.json()["error"]["message"] and "project" in got.json()["error"]["message"]
    assert counts(world) == before and world.t.status(row["id"]) == "waiting_user"


# ---- the task route takes the same files -----------------------------------------------------------------------------------------------

def test_post_tasks_with_files_keeps_them_and_an_unknown_id_is_404_with_no_task(world):
    files = [stored(world, "spec.txt", b"the spec")]
    got = world.client.post("/api/tasks", json={"dept_id": "web", "text": "read this", "files": files}, headers=world.auth)
    assert got.status_code == 201, got.text
    assert [f["name"] for f in json.loads(world.t.one("SELECT input_files_json FROM tasks WHERE id = ?", got.json()["id"]))] == ["spec.txt"]
    before = counts(world)
    bad = world.client.post("/api/tasks", json={"dept_id": "web", "text": "again", "files": [{"id": "0" * 64, "name": "gone.txt"}]}, headers=world.auth)
    assert bad.status_code == 404 and counts(world) == before
    assert world.client.post("/api/tasks", json={"dept_id": "web", "text": "x", "files": [{"id": "short", "name": "n"}]}, headers=world.auth).status_code == 422


# ---- a team chat's plain message takes the same files (E6) -----------------------------------------------------------------------------

def chat_client(world) -> TestClient:
    """The chat agent's router (POST /api/chats/{sid}/messages) over the same real services: the contract world does not mount it."""
    from sutra_app.orchestrator.api import agent as agent_api
    from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
    from sutra_app.orchestrator.redact import Redactor
    app = FastAPI()
    app.state.services = world.services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(agent_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


def test_a_team_chat_message_with_files_starts_a_run_that_is_given_them(world):
    sid = world.t.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")
    files = [stored(world, "spec.txt", b"the spec")]
    got = chat_client(world).post(f"/api/chats/{sid}/messages", json={"text": "read this", "files": files}, headers=world.auth)
    assert got.status_code == 200, got.text
    (row,) = world.t.sql("SELECT input_files_json FROM tasks WHERE dept_id = 'web'").fetchall()
    assert [f["name"] for f in json.loads(row["input_files_json"])] == ["spec.txt"]
    world.t.run(world.t.service.start_ready())
    task_id = got.json()["task_id"]
    assert (world.t.run_dir(task_id) / "inputs" / "attached" / "spec.txt").read_text() == "the spec"


def test_a_team_chat_message_with_an_unknown_file_is_404_and_stores_nothing(world):
    sid = world.t.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")
    before = counts(world)
    got = chat_client(world).post(f"/api/chats/{sid}/messages", json={"text": "read this", "files": [{"id": "0" * 64, "name": "gone.txt"}]}, headers=world.auth)
    assert got.status_code == 404 and counts(world) == before
