"""The five POST routes (work package E4, engine design 7.1 rows 26-30, F3 and F9, S1-contracts-04): say, output, reset and the
two memory clears. The orchestrator is the fake services of conftest; `page.json` is the real file."""
import json
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import views
from sutra_app.engine.api import commands, ctx as ctxmod, mount
from sutra_app.engine.api.ports import is_busy
from sutra_app.engine.spec import EngineSettings

TOKEN = {"X-Sutra-Token": "fake-token-fake-token-0123"}


@pytest.fixture
def api(fake_services):
    svc = fake_services
    svc.add_department("web")
    svc.add_department("sales")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, svc)
    return SimpleNamespace(svc=svc, client=TestClient(app, raise_server_exceptions=False), data=svc.data_dir,
                           page=lambda dept="web": ctxmod.read_page(svc.data_dir, dept))


def publish(svc, ref, output="website", status="waiting"):
    folder = svc.data_dir / ref.dir
    snap = views.idle_snapshot(EngineSettings(), views.MemoryPaths(str(folder / "l"), str(folder / "p")), ref.run_id)
    (folder / "snapshot.json").write_text(json.dumps({**snap, "status": status, "saved": None}))
    (folder / "live.json").write_text(json.dumps({**views.EMPTY_LIVE, "pid": os.getpid(), "output": output}))


# ---- the token ------------------------------------------------------------------------------------------------------
def test_every_write_needs_the_token_before_anything_else(api):
    for path in ("/api/say", "/api/playbooks/clear", "/api/lessons/clear", "/api/output", "/api/reset"):
        assert api.client.post(path + "?dept=web", json={"text": "x"}).status_code == 401
        assert api.client.post(path + "?dept=web", json={"text": "x"}, headers={"X-Sutra-Token": "wrong"}).status_code == 401
        assert api.client.post(path, json={}).status_code == 401, "the token comes before the dept check"
    assert api.svc.deliveries == [] and api.svc.stops == [] and not api.page().next_settings


# ---- say (F3) -------------------------------------------------------------------------------------------------------
def test_say_delivers_the_trimmed_text_to_the_department(api):
    got = api.client.post("/api/say?dept=web", json={"text": "  a cafe site  "}, headers=TOKEN)
    assert (got.status_code, got.json()) == (200, {"ok": True})
    assert api.svc.deliveries == [{"dept_id": "web", "text": "a cafe site", "scope_id": None, "settings": None}]


def test_say_with_no_text_is_400_empty_and_delivers_nothing(api):
    for body in ({}, {"text": ""}, {"text": "   "}, {"text": 5}, {"other": 1}):
        got = api.client.post("/api/say?dept=web", json=body, headers=TOKEN)
        assert (got.status_code, got.json()) == (400, {"error": "empty"}), body
    assert api.client.post("/api/say?dept=web", content=b"", headers=TOKEN).json() == {"error": "empty"}      # J2: raw or b"{}"
    assert api.svc.deliveries == []


def test_a_body_that_is_not_a_json_object_is_400_bad_json(api):
    for raw in (b"[1]", b'"text"', b"{torn", b"null"):
        got = api.client.post("/api/say?dept=web", content=raw, headers={**TOKEN, "Content-Type": "application/json"})
        assert (got.status_code, got.json()) == (400, {"error": "bad json"}), raw


def test_a_body_nested_thousands_deep_is_400_bad_json_on_every_post_not_a_500(api):
    """QA: 3000 nested objects made json.loads raise RecursionError and every POST answered 500 `internal` with a traceback in the log."""
    nested = b'{"a":' * 3000 + b"1" + b"}" * 3000
    for path in ("/api/say", "/api/output", "/api/reset", "/api/playbooks/clear", "/api/lessons/clear"):
        got = api.client.post(path + "?dept=web", content=nested, headers={**TOKEN, "Content-Type": "application/json"})
        assert (got.status_code, got.json()) == (400, {"error": "bad json"}), path
    assert api.svc.deliveries == []


def test_say_while_the_team_works_is_409_ok_false(api):
    api.svc.busy = True
    got = api.client.post("/api/say?dept=web", json={"text": "more"}, headers=TOKEN)
    assert (got.status_code, got.json()) == (409, {"ok": False})
    assert len(api.svc.deliveries) == 1                       # it was tried once; the orchestrator refused it


def test_only_the_orchestrators_busy_is_an_answer_any_other_error_is_a_500(api):
    class Boom(Exception):
        pass

    def explode(*a, **k):
        raise Boom("database gone")
    api.svc.deliver_to_department = explode
    assert api.client.post("/api/say?dept=web", json={"text": "x"}, headers=TOKEN).status_code == 500


def test_is_busy_knows_the_orchestrators_busy_and_not_a_locked_store():
    from sutra_app.orchestrator.errors import Busy, StoreBusy
    assert is_busy(Busy()) and not is_busy(StoreBusy()) and not is_busy(ValueError("busy"))
    assert is_busy(type("FakeBusy", (Exception,), {})()) and is_busy(type("Sub", (Busy,), {})())


def test_the_start_pages_output_choice_goes_with_the_first_delivery_and_is_then_cleared(api):
    assert api.client.post("/api/output?dept=web", json={"type": "prd"}, headers=TOKEN).status_code == 200
    got = api.client.post("/api/say?dept=web", json={"text": "write a PRD"}, headers=TOKEN)
    assert got.status_code == 200 and api.svc.deliveries[0]["settings"] == {"J2_OUTPUT": "prd"}
    assert api.page().next_settings == {}


def test_the_output_choice_survives_an_answer_and_a_busy_refusal(api):
    api.client.post("/api/output?dept=web", json={"type": "hld"}, headers=TOKEN)
    api.svc.add_run("web", status="waiting_user")                # a waiting task: the delivery is an answer, not a new task
    assert api.client.post("/api/say?dept=web", json={"text": "yes"}, headers=TOKEN).status_code == 200
    assert api.page().next_settings == {"J2_OUTPUT": "hld"}
    api.svc.busy = True
    assert api.client.post("/api/say?dept=web", json={"text": "yes"}, headers=TOKEN).status_code == 409
    assert api.page().next_settings == {"J2_OUTPUT": "hld"}


def test_say_ignores_run_and_does_not_touch_another_teams_page(api):
    api.client.post("/api/output?dept=sales", json={"type": "lld"}, headers=TOKEN)
    assert api.client.post("/api/say?dept=web&run=nonsense", json={"text": "x"}, headers=TOKEN).status_code == 200
    assert api.page("sales").next_settings == {"J2_OUTPUT": "lld"}


# ---- output (F9) ----------------------------------------------------------------------------------------------------
def test_output_is_accepted_while_the_page_has_no_run(api):
    got = api.client.post("/api/output?dept=web", json={"type": "prd"}, headers=TOKEN)
    assert (got.status_code, got.json()) == (200, {"ok": True, "output": "prd"})
    assert api.page().next_settings == {"J2_OUTPUT": "prd"}
    assert api.client.post("/api/output?dept=web", json={"type": "Website "}, headers=TOKEN).json()["output"] == "website"
    assert api.client.post("/api/output?dept=web", json={"type": "nonsense"}, headers=TOKEN).json()["output"] == "website"
    assert api.client.post("/api/output?dept=web", json={}, headers=TOKEN).json() == {"ok": True, "output": "website"}


def test_output_after_a_message_is_409_and_names_the_runs_output(api):
    ref = api.svc.add_run("web")
    publish(api.svc, ref, output="prd")
    got = api.client.post("/api/output?dept=web", json={"type": "hld"}, headers=TOKEN)
    assert (got.status_code, got.json()) == (409, {"ok": False, "output": "prd"})
    assert api.page().next_settings == {}
    api.svc.add_run("sales")                                     # no snapshot yet: the page's own choice, else the website
    assert api.client.post("/api/output?dept=sales", json={"type": "hld"}, headers=TOKEN).json() == {"ok": False, "output": "website"}


def test_output_is_allowed_again_after_a_reset(api):
    ref = api.svc.add_run("web")
    publish(api.svc, ref)
    assert api.client.post("/api/output?dept=web", json={"type": "prd"}, headers=TOKEN).status_code == 409
    assert api.client.post("/api/reset?dept=web", headers=TOKEN).status_code == 200
    assert api.client.post("/api/output?dept=web", json={"type": "prd"}, headers=TOKEN).status_code == 200


# ---- reset (F9, S1-contracts-04) ------------------------------------------------------------------------------------
def test_reset_while_a_task_runs_is_409_and_touches_nothing(api):
    api.svc.add_run("web", status="running")
    api.svc.stop_result = False
    got = api.client.post("/api/reset?dept=web", headers=TOKEN)
    assert (got.status_code, got.json()) == (409, {"ok": False})
    assert api.svc.stops == ["web"] and api.page().since_run is None


def test_reset_when_nothing_runs_marks_the_latest_run_and_answers_200(api):
    api.svc.add_run("web", run_id="j2-20261104-100001-aaaa")
    latest = api.svc.add_run("web", run_id="j2-20261104-100002-bbbb")
    got = api.client.post("/api/reset?dept=web", headers=TOKEN)
    assert (got.status_code, got.json()) == (200, {"ok": True})
    assert api.page().since_run == latest.run_id and api.svc.stops == ["web"]
    assert api.page("sales").since_run is None


def test_reset_of_a_team_with_no_run_is_200_and_marks_nothing(api):
    assert api.client.post("/api/reset?dept=web", headers=TOKEN).json() == {"ok": True}
    assert api.page().since_run is None
    assert not (api.data / "departments" / "web" / "page.json").exists()


def test_reset_keeps_the_output_choice_and_deletes_no_history(api):
    ref = api.svc.add_run("web", files={"chat.jsonl": "{}\n"})
    ctxmod.write_page(api.data, "web", next_settings={"J2_OUTPUT": "prd"})
    api.client.post("/api/reset?dept=web", headers=TOKEN)
    assert api.page().next_settings == {"J2_OUTPUT": "prd"}
    assert (api.data / ref.dir / "chat.jsonl").exists()


# ---- memory clears --------------------------------------------------------------------------------------------------
def test_lessons_and_playbooks_clear_remove_the_teams_own_files_only(api):
    for dept in ("web", "sales"):
        memory = api.data / "departments" / dept / "memory"
        memory.mkdir(parents=True)
        (memory / "lessons.jsonl").write_text('{"id": "L-1"}\n{"id": "L-2"}\n')
        (memory / "playbooks.jsonl").write_text('{"id": "P-1"}\n')
    assert api.client.post("/api/lessons/clear?dept=web", headers=TOKEN).json() == {"ok": True, "cleared": 2}
    assert api.client.post("/api/playbooks/clear?dept=web", headers=TOKEN).json() == {"ok": True, "cleared": 1}
    web, sales = (api.data / "departments" / d / "memory" for d in ("web", "sales"))
    assert not (web / "lessons.jsonl").exists() and not (web / "playbooks.jsonl").exists()
    assert (sales / "lessons.jsonl").exists() and (sales / "playbooks.jsonl").exists()
    assert api.client.post("/api/lessons/clear?dept=web", headers=TOKEN).json() == {"ok": True, "cleared": 0}


def test_the_commands_object_is_per_team(api):
    one = commands.DeptCommands(api.svc, "web")
    assert one.set_output("prd") == (True, "prd") and one.reset() is True
    assert api.page("web").next_settings == {"J2_OUTPUT": "prd"} and api.page("sales").next_settings == {}
