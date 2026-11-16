"""The Raw AI chat routes (`/api/calls`, `/api/agent-live`): Sutra's own debugger reads of a run's `calls.jsonl` and `agent_live.json`."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import rawchat
from sutra_app.engine.api import mount


def call(n, fn="identity", **more):
    rec = {"id": n, "fn": fn, "step": n, "cycle": 1, "t": f"10:00:{n:02d}", "seconds": 1.5, "model": "sonnet", "provider": "claude",
           "usd": 0.01 * n, "tokens": {"input": 100 * n, "output": 10 * n}, "chars": {"prompt": 30, "reply": 20},
           "inputs": {}, "reply": {"to": "user"}, "reason": "because", "system": f"SYSTEM {n}", "prompt": f"PROMPT {n} " + "x" * 400,
           "raw": f"RAW {n}"}
    rec.update(more)
    return json.dumps(rec)


@pytest.fixture
def api(fake_services):
    svc = fake_services
    svc.add_department("web")
    svc.add_department("sales")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, svc)
    return svc, TestClient(app, raise_server_exceptions=False)


def test_the_list_has_every_call_in_order_with_previews_and_never_the_full_text(api):
    svc, client = api
    lines = [call(1), call(2, "W-1"), "torn {", call(3, "audit")]
    ref = svc.add_run("web", files={"calls.jsonl": "\n".join(lines) + "\n"})
    got = client.get(f"/api/calls?dept=web&run={ref.run_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["total"] == 3 and body["matched"] == 3 and body["run"] == ref.run_id and body["mode"] == "saved"
    assert [c["id"] for c in body["calls"]] == [1, 2, 3] and [c["fn"] for c in body["calls"]] == ["identity", "W-1", "audit"]
    row = body["calls"][0]
    assert row["t"] == "10:00:01" and row["model"] == "sonnet" and row["tokens"] == {"input": 100, "output": 10}
    assert row["prompt_preview"].startswith("PROMPT 1") and len(row["prompt_preview"]) <= rawchat.PREVIEW_CHARS
    assert row["chars"]["prompt"] == len("PROMPT 1 ") + 400 and row["chars"]["system"] == len("SYSTEM 1")
    assert not {"system", "prompt", "raw", "inputs", "reply"} & set(row)
    full = client.get(f"/api/call?dept=web&run={ref.run_id}&id=2").json()           # the full text stays J2's /api/call
    assert full["raw"] == "RAW 2" and full["system"] == "SYSTEM 2"


def test_paging_is_capped_and_the_search_reads_the_full_text(api):
    svc, client = api
    ref = svc.add_run("web", files={"calls.jsonl": "\n".join(call(n, raw=f"RAW {n}" + (" needle" if n % 3 == 0 else "")) for n in range(1, 11)) + "\n"})
    page = client.get(f"/api/calls?dept=web&run={ref.run_id}&offset=4&limit=3").json()
    assert [c["id"] for c in page["calls"]] == [5, 6, 7] and page["total"] == 10
    huge = client.get(f"/api/calls?dept=web&run={ref.run_id}&limit=99999&offset=-5").json()
    assert huge["limit"] == rawchat.MAX_LIMIT and huge["offset"] == 0 and len(huge["calls"]) == 10
    found = client.get(f"/api/calls?dept=web&run={ref.run_id}&q=NEEDLE").json()
    assert [c["id"] for c in found["calls"]] == [3, 6, 9] and found["matched"] == 3 and found["total"] == 10


def test_scope_rules_are_the_engine_routes_own(api):
    svc, client = api
    other = svc.add_run("sales", files={"calls.jsonl": call(1) + "\n"})
    assert client.get("/api/calls").status_code == 400
    assert client.get("/api/calls?dept=nope").status_code == 404
    assert client.get(f"/api/calls?dept=web&run={other.run_id}").status_code == 404       # another team's run
    assert client.get("/api/calls?dept=web&run=../../x").status_code == 404
    idle = client.get("/api/calls?dept=web").json()                                       # no run yet: an empty list
    assert idle["calls"] == [] and idle["total"] == 0 and idle["mode"] == "idle"
    assert client.get("/api/agent-live?dept=web").json()["agents"] == {}


def test_answers_are_redacted(api):
    svc, client = api
    svc.secrets = ["sk-secret-value"]
    ref = svc.add_run("web", files={"calls.jsonl": call(1, prompt="key sk-secret-value here") + "\n",
                                    "agent_live.json": {"schema": "agent-live/1", "agents": {"W-1": {"text": "sk-secret-value", "tool": ""}}}})
    assert "sk-secret-value" not in client.get(f"/api/calls?dept=web&run={ref.run_id}").text
    assert "sk-secret-value" not in client.get(f"/api/agent-live?dept=web&run={ref.run_id}").text


def test_the_live_tail_reads_agent_live_and_ignores_a_foreign_file(api):
    svc, client = api
    live = {"schema": "agent-live/1", "at": 5, "agents": {"W-1": {"call": 4, "since": 1.0, "text": "so far", "tool": "Read", "tools": 2},
                                                         "bad": "x"}}
    ref = svc.add_run("web", files={"agent_live.json": live})
    body = client.get(f"/api/agent-live?dept=web&run={ref.run_id}").json()
    assert body["agents"] == {"W-1": {"call": 4, "since": 1.0, "text": "so far", "tool": "Read", "tools": 2}} and body["at"] == 5
    other = svc.add_run("web", files={"agent_live.json": {"schema": "else", "agents": {"W-1": {}}}})
    assert client.get(f"/api/agent-live?dept=web&run={other.run_id}").json()["agents"] == {}


def test_the_reader_is_tolerant(tmp_path):
    assert rawchat.call_list(None)["calls"] == [] and rawchat.call_list(str(tmp_path / "missing"))["total"] == 0
    (tmp_path / "calls.jsonl").write_text("[1,2]\n\nnot json\n" + json.dumps({"id": 1, "tokens": "odd", "usd": True}) + "\n", encoding="utf-8")
    rows = rawchat.call_list(str(tmp_path))["calls"]
    assert len(rows) == 1 and rows[0]["tokens"] is None and rows[0]["usd"] is None and rows[0]["prompt_preview"] == ""
