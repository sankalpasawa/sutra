"""The six POST routes (work package E4, engine design 7.1 rows 26-30, F3 and F9, S1-contracts-04; J2 sync 4, D147): say, ask, output,
reset and the two memory clears. The orchestrator is the fake services of conftest; `page.json` is the real file. A question
(`/api/ask`) is J2's own `answer` over a run folder; the function's chat turn is a fake that records what the route asks of it."""
import json
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import views
from sutra_app.engine.api import commands, ctx as ctxmod, mount
from sutra_app.engine.api.ports import AskFailed, is_busy
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
    for path in ("/api/say", "/api/ask", "/api/playbooks/clear", "/api/lessons/clear", "/api/output", "/api/reset"):
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
    for path in ("/api/say", "/api/ask", "/api/output", "/api/reset", "/api/playbooks/clear", "/api/lessons/clear"):
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


# ---- ask (J2 sync 4, D147 to D149): a question to one function about a run ------------------------------------------------
QUESTION = "Why was W-3 scored below the gate?"
RECORDS = [{"meta": True, "run": "x", "output": "website"},
           {"id": 1, "who": "user", "t": "2026-11-04T10:00:00", "text": "A site for Brew Lab"},
           {"id": 2, "who": "adaptation", "t": "2026-11-04T10:00:05", "text": "I scored W-3 below the gate, so I revised it."}]


def with_records(api, dept="web", rows=RECORDS, **kw):
    """A saved run whose chat holds a line of Adaptation's: enough for J2's `activity` to find the function."""
    return api.svc.add_run(dept, files={"chat.jsonl": "\n".join(json.dumps(r) for r in rows) + "\n"}, **kw)


class FakeTurn:
    """What `services.agent_chat` hands out: it records every call the route makes, in order, and does what it is told."""

    def __init__(self, *, can_ask=True, reason="", reply="Because its checks did not pass.", fail=None, busy=False, boom=False):
        self.can_ask, self.reason, self.reply, self.fail, self.busy, self.boom = can_ask, reason, reply, fail, busy, boom
        self.session_id, self.node_id, self.task_id, self.run_id, self.dept_id, self.agent = "cs_a", "gn_a", "tsk_a", "j2-x", "web", "adaptation"
        self.log = []

    def begin(self, question):
        self.log.append(("begin", question))
        if self.busy:
            from sutra_app.orchestrator.errors import Busy
            raise Busy("This chat is answering another question")
        return 11

    def ask(self, system, user, records_only, max_tokens=700, effort="low"):
        self.log.append(("ask", system, user, records_only(), max_tokens, effort))
        if self.boom:
            raise RuntimeError("the port broke")
        if self.fail:
            raise AskFailed(self.fail)
        return self.reply

    def end(self, answer, source):
        self.log.append(("end", answer, source))
        return {} if answer is None else {"session_id": "cs_a", "question_id": 11, "answer_id": 12}

    def calls(self, name):
        return [row for row in self.log if row[0] == name]


def port_of(api, turn):
    """`services.agent_chat` that offers `turn` and remembers what it was asked for."""
    asked = []

    def agent_chat(dept_id, run_id, agent):
        asked.append((dept_id, run_id, agent))
        return turn
    api.svc.agent_chat = agent_chat
    return asked


def ask(api, body=None, dept="web", **kw):
    return api.client.post(f"/api/ask?dept={dept}", json=body if body is not None else {"who": "adaptation", "q": QUESTION}, headers=TOKEN, **kw)


def test_a_question_with_no_chat_port_is_answered_from_the_records_and_nothing_is_stored(api):
    with_records(api)
    got = ask(api)
    assert got.status_code == 200 and set(got.json()) == {"who", "answer", "from"}
    body = got.json()
    assert body["who"] == "adaptation" and body["from"] == "records"
    assert body["answer"].startswith("From the records:") and "I scored W-3 below the gate" in body["answer"]


def test_a_function_with_a_chat_turn_is_asked_through_the_turn_and_both_lines_are_stored(api):
    ref = with_records(api)
    turn = FakeTurn()
    asked = port_of(api, turn)
    got = ask(api, {"who": "adaptation", "q": "  Why was W-3   scored\nbelow the gate?  "})
    assert got.status_code == 200
    assert got.json() == {"who": "adaptation", "answer": "Because its checks did not pass.", "from": "model",
                          "session_id": "cs_a", "question_id": 11, "answer_id": 12}
    assert asked == [("web", ref.run_id, "adaptation")], "the turn is asked for by team, run and function"
    assert [row[0] for row in turn.log] == ["begin", "ask", "end"]
    assert turn.log[0] == ("begin", QUESTION), "the question is stored as the owner wrote it, its white space collapsed"
    _, system, user, records_only, max_tokens, effort = turn.calls("ask")[0]
    assert "Strategist (adaptation)" in system and user.endswith(f"QUESTION\n{QUESTION}") and "I scored W-3 below the gate" in user
    assert records_only.startswith("From the records:") and (max_tokens, effort) == (700, "low")
    assert turn.calls("end") == [("end", "Because its checks did not pass.", "model")]


def test_a_function_without_a_session_of_its_own_is_answered_from_the_records_and_nothing_is_stored(api):
    with_records(api)
    asked = port_of(api, None)                                   # the port says the function never worked in the run (or it is the validator)
    got = ask(api)
    assert got.status_code == 200 and set(got.json()) == {"who", "answer", "from"} and got.json()["from"] == "records"
    assert [who for _, _, who in asked] == ["adaptation"]
    assert ask(api, {"who": "validator", "q": QUESTION}).json()["answer"] == "This run recorded nothing for validator."
    assert [who for _, _, who in asked] == ["adaptation", "validator"], "the port decides about the validator, the route does not"


def test_a_model_that_cannot_answer_falls_back_to_the_records_with_the_reason_and_the_turn_is_ended(api):
    with_records(api)
    turn = FakeTurn(fail="the provider did not answer in time")
    port_of(api, turn)
    body = ask(api).json()
    assert body["from"] == "records" and body["answer"].startswith("From the records:")
    assert body["note"] == "The model could not answer (the provider did not answer in time); this is from the records only."
    assert (body["session_id"], body["question_id"], body["answer_id"]) == ("cs_a", 11, 12)
    assert [row[0] for row in turn.log] == ["begin", "ask", "end"] and turn.calls("end")[0][2] == "records"
    assert turn.calls("end")[0][1] == body["answer"], "the line stored is the answer the owner was shown"


def test_a_turn_that_cannot_ask_gives_the_records_and_its_reason_and_still_stores_both_lines(api):
    with_records(api)
    turn = FakeTurn(can_ask=False, reason="No model is connected.")
    port_of(api, turn)
    body = ask(api).json()
    assert body["from"] == "records" and body["note"] == "No model is connected." and body["answer_id"] == 12
    assert [row[0] for row in turn.log] == ["begin", "end"], "the model is never asked when the turn says it cannot"
    assert turn.calls("end")[0][2] == "records"


def test_an_unexpected_error_stores_no_answer_releases_the_turn_and_is_a_500(api):
    with_records(api)
    turn = FakeTurn(boom=True)
    port_of(api, turn)
    got = ask(api)
    assert got.status_code == 500
    assert [row[0] for row in turn.log] == ["begin", "ask", "end"] and turn.calls("end") == [("end", None, "records")]


def test_a_chat_that_is_answering_another_question_is_409_busy_and_the_turn_is_not_ended(api):
    with_records(api)
    turn = FakeTurn(busy=True)
    port_of(api, turn)
    got = ask(api)
    assert (got.status_code, got.json()) == (409, {"error": "busy"})
    assert [row[0] for row in turn.log] == ["begin"], "begin failed: there is nothing to release and nothing was asked"


def test_only_the_busy_refusal_is_an_answer_any_other_error_of_begin_is_a_500(api):
    with_records(api)
    turn = FakeTurn()
    turn.begin = lambda question: (_ for _ in ()).throw(ValueError("database gone"))
    port_of(api, turn)
    assert ask(api).status_code == 500


def test_a_who_that_is_not_one_of_the_six_functions_is_400_not_a_function_and_nothing_is_asked_of_the_port(api):
    with_records(api)
    asked = port_of(api, FakeTurn())
    for who in ("nobody", "", "W-3", "Adaptation", None, 5, ["audit"]):
        got = ask(api, {"who": who, "q": QUESTION})
        assert (got.status_code, got.json()) == (400, {"error": "not a function"}), who
    assert ask(api, {"q": QUESTION}).json() == {"error": "not a function"}
    assert asked == []
    for who in ("identity", "adaptation", "priority", "coordination", "audit", "validator"):
        assert ask(api, {"who": who, "q": QUESTION}).status_code == 200, who


def test_a_question_longer_than_a_note_is_400_and_one_of_exactly_that_length_is_taken(api):
    with_records(api)
    asked = port_of(api, FakeTurn())
    got = ask(api, {"who": "adaptation", "q": "x" * (views.ASK_CHARS + 1)})
    assert (got.status_code, got.json()) == (400, {"error": "question too long"}) and asked == []
    assert ask(api, {"who": "adaptation", "q": " " + "x" * views.ASK_CHARS + " "}).status_code == 200, "white space around it does not count"


def test_an_empty_question_is_j2s_own_empty_answer_and_stores_nothing(api):
    with_records(api)
    asked = port_of(api, FakeTurn())
    for q in ("", "   \n ", None):
        got = ask(api, {"who": "adaptation", "q": q})
        assert (got.status_code, got.json()) == (200, {"who": "adaptation", "answer": "", "from": "records"}), q
    assert ask(api, {"who": "adaptation"}).json()["answer"] == ""
    assert asked == [], "no turn is made for a question that is not one"


def test_the_run_asked_about_is_the_one_named_when_it_is_the_teams_else_the_run_the_page_shows(api):
    old = with_records(api, rows=RECORDS[:2] + [{"id": 2, "who": "adaptation", "t": "2026-11-04T10:00:05", "text": "The OLD run's W-3 line, scored low."}])
    new = with_records(api, run_id="j2-20261104-110000-ffff")
    other = with_records(api, dept="sales")
    asked = port_of(api, None)
    named = ask(api, {"who": "adaptation", "q": QUESTION, "run": old.run_id}).json()["answer"]
    assert "OLD run's W-3 line" in named and asked[-1] == ("web", old.run_id, "adaptation")
    for run in ("", None, "nonsense", other.run_id, "j2-unknown", "../" + old.run_id):
        body = {"who": "adaptation", "q": QUESTION} if run is None else {"who": "adaptation", "q": QUESTION, "run": run}
        got = ask(api, body).json()["answer"]
        assert "OLD run's" not in got and "I scored W-3" in got, run
        assert asked[-1] == ("web", new.run_id, "adaptation"), run               # the page's run: the latest of the team, never another team's


def test_a_team_with_no_run_gets_j2s_nothing_recorded_answer_and_the_port_is_not_asked(api):
    asked = port_of(api, FakeTurn())
    got = ask(api)
    assert (got.status_code, got.json()) == (200, {"who": "adaptation", "answer": "This run recorded nothing for Strategist.", "from": "records"})
    assert asked == []


def test_a_question_about_a_run_after_a_reset_still_reads_that_run_when_it_is_named(api):
    old = with_records(api)
    api.client.post("/api/reset?dept=web", headers=TOKEN)                 # the page is idle now, the run stays in the history
    assert "I scored W-3" not in ask(api).json()["answer"], "no run is shown: nothing recorded"
    assert "I scored W-3" in ask(api, {"who": "adaptation", "q": QUESTION, "run": old.run_id}).json()["answer"]


def test_an_archived_team_cannot_be_asked_and_the_port_is_not_reached(api):
    api.svc.add_department("old", archived=True)
    with_records(api, dept="old")
    asked = port_of(api, FakeTurn())
    got = ask(api, dept="old")
    assert got.status_code == 403 and got.json()["error"]["code"] == "read_only" and asked == []


def test_a_question_to_another_team_never_reads_this_teams_records(api):
    with_records(api, dept="sales")
    got = ask(api).json()                                                  # the web team has no run
    assert got["answer"] == "This run recorded nothing for Strategist."


def test_the_commands_object_asks_through_the_port_and_without_it(api):
    ref = with_records(api)
    cmd = commands.DeptCommands(api.svc, "web")
    assert cmd.ask("adaptation", QUESTION, "")["from"] == "records"
    turn = FakeTurn()
    port_of(api, turn)
    assert cmd.ask("adaptation", QUESTION, ref.run_id)["from"] == "model"
    with pytest.raises(views.AskBusy):
        port_of(api, FakeTurn(busy=True))
        cmd.ask("adaptation", QUESTION, "")
