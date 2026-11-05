"""A planted secret never leaves in any body (work package E4, ENG-11, engine design 7.2, D71): every text reply goes through
`services.redact`; PNG and DOCX are raw. The routes are walked in live and saved mode over a run that holds the secret in its
chat, its calls, its page, its documents and its settings."""
import json
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import views
from sutra_app.engine.api import mount
from sutra_app.engine.spec import EngineSettings
from sutra_app.orchestrator.redact import Redactor

SECRET = "PLANTED-SECRET-VALUE-12345"
TOKEN = {"X-Sutra-Token": "fake-token-fake-token-0123"}
GET_PATHS = ["/api/state", "/api/runs", "/api/call?id=1", "/api/preview?atom=a", "/api/docs", "/api/map", "/api/plan", "/api/library",
             "/api/run-templates", "/api/artifacts", "/api/agent?who=identity", "/api/artifacts/tree", "/api/artifact?name=prd.md",
             "/api/artifact?name=site/v1.html", "/api/story", "/api/board", "/api/audits", "/api/refs", "/file/prd.md", "/site/latest",
             "/site/v1", "/api/engine/settings"]


@pytest.fixture
def api(fake_services):
    svc = fake_services
    svc.secrets = [SECRET]
    chat = [{"id": 1, "who": "user", "text": f"my key is {SECRET}"}]
    ref = svc.add_run("web", files={
        "chat.jsonl": json.dumps({"meta": True, "run": "x", "output": "prd"}) + "\n" + json.dumps(chat[0]) + "\n",
        "calls.jsonl": json.dumps({"id": 1, "fn": "identity", "reply": f"saw {SECRET}", "prompt": SECRET, "system": "s", "raw": SECRET}) + "\n",
        "summary.json": {"output_type": "prd", "brief": f"brief {SECRET}"}, "goal.json": {"goal": f"goal {SECRET}"},
        "site/v1.html": f"<p>{SECRET}</p>", "prd.md": f"# {SECRET}", "prd.docx": b"PK\x03" + SECRET.encode(),
        "site/shots/v1.png": b"\x89PNG" + SECRET.encode()})
    folder = svc.data_dir / ref.dir
    snap = views.idle_snapshot(EngineSettings(), views.MemoryPaths(str(folder / "l"), str(folder / "p")), ref.run_id)
    (folder / "snapshot.json").write_text(json.dumps({**snap, "status": "waiting", "saved": None, "chat": chat, "outcome": SECRET}))
    (folder / "live.json").write_text(json.dumps({**views.EMPTY_LIVE, "pid": os.getpid(), "sites": 1, "output": "prd", "doc": False}))
    (svc.data_dir / "departments" / "web" / "engine.json").write_text(json.dumps({"test_email": SECRET, "budget": 7}))
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, svc)
    return SimpleNamespace(svc=svc, ref=ref, client=TestClient(app, raise_server_exceptions=False))


def test_no_text_reply_of_any_route_contains_the_planted_secret(api):
    redacted = 0
    for path in GET_PATHS:
        for query in ("dept=web", f"dept=web&run={api.ref.run_id}"):
            got = api.client.get(path + ("&" if "?" in path else "?") + query)
            assert got.status_code in (200, 404), (path, query)
            assert SECRET.encode() not in got.content, (path, query)
            assert SECRET not in "".join(got.headers.values()), (path, query)
            redacted += b"[redacted]" in got.content
    assert redacted >= 10, "the secret must really have been in the data the routes read"


def test_the_routes_that_show_the_chat_the_call_and_the_page_redact_them(api):
    assert "[redacted]" in api.client.get("/api/state?dept=web").json()["chat"][0]["text"]
    assert "[redacted]" in api.client.get(f"/api/call?dept=web&id=1&run={api.ref.run_id}").json()["reply"]
    assert api.client.get("/site/latest?dept=web").text == "<p>[redacted]</p>"
    assert api.client.get(f"/api/artifact?dept=web&name=prd.md&run={api.ref.run_id}").text == "# [redacted]"
    assert api.client.get("/api/engine/settings?dept=web").json()["department"]["test_email"] == "[redacted]"


def test_png_and_docx_are_sent_raw_and_unchanged(api):
    run = f"dept=web&run={api.ref.run_id}"
    assert api.client.get(f"/shot/1?{run}").content == b"\x89PNG" + SECRET.encode()
    assert api.client.get(f"/file/prd.docx?{run}").content == b"PK\x03" + SECRET.encode()


def test_refusals_and_write_answers_are_redacted_too(api):
    api.svc.secrets = ["empty", "dept_required", "not_found", "bad json"]
    for got, word in ((api.client.post("/api/say?dept=web", json={}, headers=TOKEN), "empty"), (api.client.get("/api/state"), "dept_required"),
                      (api.client.get("/api/state?dept=zz"), "not_found")):
        assert word not in got.text and "[redacted]" in got.text


def test_the_orchestrators_redactor_hides_environment_secrets_in_every_reply(api):
    api.svc.redact = Redactor(environ={"MY_API_KEY": "sk-live-abcdef123456", "HOME": "/Users/x"})
    run = api.ref
    (api.svc.data_dir / run.dir / "site" / "v1.html").write_text("<p>sk-live-abcdef123456 at /Users/x</p>")
    got = api.client.get("/site/latest?dept=web")
    assert got.text == "<p>[redacted] at /Users/x</p>"
    (api.svc.data_dir / "departments" / "web" / "engine.json").write_text(json.dumps({"test_slack_target": "sk-live-abcdef123456"}))
    assert "sk-live" not in api.client.get("/api/engine/settings?dept=web").text
