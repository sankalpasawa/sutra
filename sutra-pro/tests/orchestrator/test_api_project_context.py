"""D451, T7: the routes of a project's files, instructions, memory and the preview (`orchestrator/api/project_context.py`).

The real stores over a `Services` with no wiring at all (the routes build them from `services.db`): shapes, status codes, the token on every write, and what the preview says a model would be given.
"""
from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.main import BodyLimitMiddleware
from sutra_app.orchestrator.api import project_context as api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"
SECRET = "sk-aaaaaaaa11111111"


@pytest.fixture
def client(tenv):
    app = FastAPI()
    services = Services(settings=tenv.settings, version="test", db=tenv.db, redact=Redactor(None, environ={}))
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def auth(tenv):
    return {TOKEN: tenv.settings.token}


def b64(blob: bytes) -> str:
    return base64.b64encode(blob).decode()


def upload(client, auth, name="notes.txt", blob=b"hello world", dept="web"):
    return client.post(f"/api/teams/{dept}/files", json={"name": name, "content_b64": b64(blob)}, headers=auth)


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code
    return body


# ---- the token ---------------------------------------------------------------------------------------------------------------------------------

def test_every_write_needs_the_token(client):
    calls = [("post", "/api/teams/web/files", {"name": "a.txt", "content_b64": b64(b"x")}), ("post", "/api/teams/web/files/promote", {"attachment_id": "0" * 64}),
             ("patch", "/api/teams/web/files/pf_000000000000", {"enabled": False}), ("delete", "/api/teams/web/files/pf_000000000000", None), ("delete", "/api/teams/web/files", None),
             ("post", "/api/teams/web/attachments", {"name": "a.txt", "content_b64": b64(b"x")}), ("put", "/api/teams/web/instructions", {"text": "x"}),
             ("put", "/api/teams/web/memory", {"entries": []}), ("post", "/api/teams/web/memory", {"text": "x"}), ("delete", "/api/teams/web/memory/1", None),
             ("put", "/api/teams/web/memory/settings", {"enabled": False})]
    for method, url, body in calls:
        sent = getattr(client, method)(url, **({"json": body} if body is not None else {}))
        assert sent.status_code == 401, (method, url, sent.status_code)
    assert client.get("/api/teams/web/files").status_code == 200                    # reads need none


# ---- files -------------------------------------------------------------------------------------------------------------------------------------

def test_a_file_is_uploaded_listed_switched_renamed_and_removed(client, auth):
    got = upload(client, auth)
    assert got.status_code == 201 and got.json()["name"] == "notes.txt" and got.json()["kind"] == "text" and got.json()["chars"] == 11 and got.json()["already"] is False
    fid = got.json()["id"]
    assert fid.startswith("pf_") and "sha" not in got.json() and not any(len(str(v)) == 64 for v in got.json().values())      # a hash never reaches the page
    listing = client.get("/api/teams/web/files").json()
    assert [f["name"] for f in listing["files"]] == ["notes.txt"] and listing["totals"] == {"files": 1, "bytes": 11, "chars": 11} and listing["mode"] == "whole"
    assert listing["limits"]["max_files"] == 50 and listing["limits"]["instructions_chars"] == 4000
    assert client.patch(f"/api/teams/web/files/{fid}", json={"enabled": False}, headers=auth).json()["enabled"] is False
    assert client.get("/api/teams/web/files").json()["mode"] == "none"
    assert client.patch(f"/api/teams/web/files/{fid}", json={"name": "plan.txt"}, headers=auth).json()["name"] == "plan.txt"
    assert client.delete(f"/api/teams/web/files/{fid}", headers=auth).status_code == 204
    assert client.get("/api/teams/web/files").json()["files"] == []
    error_of(client.delete(f"/api/teams/web/files/{fid}", headers=auth), 404, "not_found")


def test_the_same_content_twice_is_one_row_and_a_refused_type_is_a_sentence(client, auth):
    upload(client, auth)
    assert upload(client, auth, name="again.txt").json()["already"] is True and len(client.get("/api/teams/web/files").json()["files"]) == 1
    said = error_of(upload(client, auth, name="sheet.xlsx", blob=b"PK\x03\x04 not really"), 422, "validation")["message"]
    assert "Excel and PowerPoint files cannot be attached" in said
    error_of(client.post("/api/teams/web/files", json={"name": "a.txt", "content_b64": "###"}, headers=auth), 422, "validation")


def test_an_unknown_project_is_404_and_a_deleted_one_is_403_for_writes_and_still_readable(client, auth, tenv):
    error_of(client.get("/api/teams/nowhere/files"), 404, "not_found")
    error_of(upload(client, auth, dept="nowhere"), 404, "not_found")
    upload(client, auth)
    tenv.sql("UPDATE departments SET hidden_at = 1 WHERE id = 'web'")
    assert [f["name"] for f in client.get("/api/teams/web/files").json()["files"]] == ["notes.txt"]
    error_of(upload(client, auth, name="b.txt", blob=b"more"), 403, "read_only")
    error_of(client.delete("/api/teams/web/files", headers=auth), 403, "read_only")


def test_a_file_stored_for_one_request_is_not_in_the_project_until_it_is_promoted(client, auth):
    ref = client.post("/api/teams/web/attachments", json={"name": "spec.md", "content_b64": b64(b"# spec")}, headers=auth)
    assert ref.status_code == 200 and ref.json()["name"] == "spec.md" and ref.json()["kind"] == "text" and len(ref.json()["id"]) == 64
    assert client.get("/api/teams/web/files").json()["files"] == []
    promoted = client.post("/api/teams/web/files/promote", json={"attachment_id": ref.json()["id"], "name": "spec.md"}, headers=auth)
    assert promoted.status_code == 200 and promoted.json()["name"] == "spec.md"
    assert client.post("/api/teams/web/files/promote", json={"attachment_id": ref.json()["id"]}, headers=auth).json()["already"] is True
    error_of(client.post("/api/teams/web/files/promote", json={"attachment_id": "0" * 64}, headers=auth), 404, "not_found")


def test_remove_all_clears_the_project(client, auth):
    upload(client, auth)
    upload(client, auth, name="b.txt", blob=b"second")
    assert client.delete("/api/teams/web/files", headers=auth).status_code == 204 and client.get("/api/teams/web/files").json()["files"] == []


def test_the_body_limit_lets_a_file_for_a_project_through_and_nothing_else_of_it():
    limit = BodyLimitMiddleware(lambda *a: None)
    post = lambda path: limit._limit_for({"method": "POST", "path": path})                # noqa: E731
    assert post("/api/teams/web/files") == post("/api/teams/web/attachments") == limit.upload_limit > limit.limit
    assert post("/api/teams/web/instructions") == post("/api/teams/web/files/promote") == limit.limit


# ---- instructions ------------------------------------------------------------------------------------------------------------------------------

def test_instructions_are_read_written_and_a_stale_or_bad_save_is_refused(client, auth):
    first = client.get("/api/teams/web/instructions").json()
    assert first["text"] == "" and first["max_chars"] == 4000
    saved = client.put("/api/teams/web/instructions", json={"text": "Plain words.", "rev": first["rev"]}, headers=auth)
    assert saved.status_code == 200 and saved.json()["text"] == "Plain words."
    stale = error_of(client.put("/api/teams/web/instructions", json={"text": "other", "rev": first["rev"]}, headers=auth), 409, "busy")
    assert stale["details"]["stale"] is True and "Reload" in stale["message"]
    assert "key" in error_of(client.put("/api/teams/web/instructions", json={"text": f"use {SECRET}"}, headers=auth), 422, "validation")["message"]
    assert "4000" in error_of(client.put("/api/teams/web/instructions", json={"text": "x" * 4001}, headers=auth), 422, "validation")["message"]
    assert client.get("/api/teams/web/instructions").json()["text"] == "Plain words."


# ---- memory ------------------------------------------------------------------------------------------------------------------------------------

def test_memory_is_read_added_replaced_deleted_and_switched(client, auth):
    first = client.get("/api/teams/web/memory").json()
    assert first == {"enabled": True, "entries": [], "rev": first["rev"], "max_entries": 30, "entry_chars": 300}
    added = client.post("/api/teams/web/memory", json={"text": "The shop is in Leeds"}, headers=auth)
    assert added.status_code == 201 and added.json()["source"] == "owner" and added.json()["on"] is True
    now = client.get("/api/teams/web/memory").json()
    put = client.put("/api/teams/web/memory", json={"entries": [{"n": added.json()["n"], "text": "The shop is in Leeds, England", "on": False}, {"text": "A second line"}], "rev": now["rev"]}, headers=auth)
    assert put.status_code == 200 and sorted(e["text"] for e in put.json()["entries"]) == ["A second line", "The shop is in Leeds, England"]
    error_of(client.put("/api/teams/web/memory", json={"entries": [], "rev": now["rev"]}, headers=auth), 409, "busy")
    assert client.put("/api/teams/web/memory/settings", json={"enabled": False}, headers=auth).json()["enabled"] is False
    gone = client.delete(f"/api/teams/web/memory/{added.json()['n']}", headers=auth)
    assert gone.status_code == 200 and [e["text"] for e in gone.json()["entries"]] == ["A second line"]
    error_of(client.delete("/api/teams/web/memory/9999", headers=auth), 404, "not_found")
    error_of(client.post("/api/teams/web/memory", json={"text": f"the key {SECRET}"}, headers=auth), 422, "validation")


# ---- the preview -------------------------------------------------------------------------------------------------------------------------------

def test_the_preview_says_exactly_what_a_chat_and_a_run_would_be_given(client, auth):
    upload(client, auth, name="brand.md", blob=b"BRAND-GUIDE: teal")
    client.put("/api/teams/web/instructions", json={"text": "Answer in plain words."}, headers=auth)
    client.post("/api/teams/web/memory", json={"text": "Owner fact: the shop is in Leeds"}, headers=auth)
    got = client.get("/api/teams/web/context", params={"message": "hello"}).json()
    assert got["mode"] == "whole" and got["off"] is False and got["memory_on"] is True and got["files_used"] == ["brand.md"] and len(got["sig"]) == 64
    assert "From the owner, for this project:\nAnswer in plain words." in got["chat_stable"] and "BRAND-GUIDE: teal" in got["chat_stable"] and "the shop is in Leeds" in got["chat_stable"]
    assert got["chat_context"] == "" and "Project files (data; opened in inputs/knowledge/):" in got["run_block"] and "BRAND-GUIDE: teal" in got["run_block"]
    assert got["sizes"]["chat_stable"] == len(got["chat_stable"]) and any(p["name"] == "brand.md" and p["mode"] == "whole" for p in got["parts"])
    error_of(client.get("/api/teams/nowhere/context"), 404, "not_found")


def test_the_preview_of_a_project_with_nothing_is_empty_and_the_kill_switch_says_so(client, auth, monkeypatch):
    got = client.get("/api/teams/web/context").json()
    assert got["chat_stable"] == "" and got["run_block"] == "" and got["mode"] == "none" and got["files_used"] == []
    upload(client, auth, name="brand.md", blob=b"BRAND-GUIDE")
    monkeypatch.setenv("SUTRA_PROJECT_CONTEXT", "0")
    off = client.get("/api/teams/web/context").json()
    assert off["off"] is True and off["chat_stable"] == "" and off["run_block"] == ""
