"""The owner's question to a function, end to end (J2 sync 4, C4; D147 to D149; owner rule R2).

The whole app runs for real, as in tests/e2e (the harness is imported from there): uvicorn thread, SQLite, the engine as its own process playing J2's mock, and the
REAL connector router over the fake `claude` and `codex` of tests/fakes. A team makes its first run (about 3 s, once); then the owner asks its functions questions
through `POST /api/ask`, J2's route, which the engine answers through the orchestrator's port (`AgentAsk`). What one story of asks left behind is looked at test by test:

  identity   no pick of its own          -> a model answer, the policy's model and effort, one ledger row on the session
  audit      its own pick set in its pill -> a model answer on that model and effort (the flags of the call are the proof)
  priority   no model can answer          -> the answer from the records, the reason in `note`, both lines stored, the failed call booked
  validator  code, no session of its own  -> the records, nothing stored, no call
  coordination  the owner's limit is used up -> the records with the limit's words, both lines stored, no call

and an app with no model at all answers from the records and says so. The question and its answer are lines of the function's own chat (what the node panel
reads), J2's records feed (what J2's panel reads) is not changed by asking, and the event stream carries both lines."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

E2E = Path(__file__).resolve().parents[1] / "e2e"            # the end-to-end harness: that folder has no __init__.py, so it is put on sys.path by name
if str(E2E) not in sys.path:
    sys.path.append(str(E2E))
from harness import FakeCliBin, LiveApp, new_team_script, run_new_team  # noqa: E402

from sutra_app.library.types import overhead_atom_id  # noqa: E402
from sutra_app.orchestrator.testing.scripted import ScriptedConnector  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a real engine process and the fake claude and codex are POSIX (D104)")

QUESTIONS = {
    "identity": "What did you decide and why?",
    "audit": "Why did you pass the site?",
    "priority": "What did you put first?",
    "validator": "What did you check?",
    "coordination": "Who builds what, and in which order?",
}
REPLIES = {"identity": "Identity says it was the brief.", "audit": "Audit says every item passed."}
NO_MODEL = "No model is connected."


def asked_words(sid_lines: list[dict]) -> list[tuple]:
    return [(m["role"], m["who"], m["ask"]) for m in sid_lines if m.get("ask")]


@dataclass
class Story:
    live: LiveApp
    cli: FakeCliBin
    task: str
    run: str
    sessions: dict[str, str]
    answers: dict[str, tuple[int, dict]] = field(default_factory=dict)         # who -> (status, body)
    calls: dict[str, list[dict]] = field(default_factory=dict)                  # who -> the fake CLI calls its question made
    activity_before: dict = field(default_factory=dict)
    activity_after: dict = field(default_factory=dict)

    def lines(self, who: str) -> list[dict]:
        return [m for m in self.live.messages(self.sessions[who]) if m.get("ask")]

    def ledger(self, who: str) -> list[Any]:
        return self.live.rows("SELECT * FROM usage_ledger WHERE session_id = ? AND purpose = 'agent_chat' ORDER BY id", self.sessions[who])

    def body(self, who: str) -> dict:
        return self.answers[who][1]


def ask(live: LiveApp, who: str, question: str, run: str, **extra: Any) -> tuple[int, dict]:
    response = live.post("/api/ask?dept=web", {"who": who, "q": question, "run": run, **extra})
    return response.status_code, response.json()


@pytest.fixture(scope="module")
def story(tmp_path_factory):
    root = tmp_path_factory.mktemp("ask")
    cli = FakeCliBin(root)
    cli.push("claude", *new_team_script())
    # the claude model calls in order: three of the chat agent (decide, change, assign), then the owner's questions: identity and audit are answered, priority gets
    # a usage limit (and codex too), after which the next ones would fail; coordination is held back by the owner's limit before it reaches a model
    cli.sequence["claude"] = "ok,ok,ok,ok,ok,quota"
    cli.sequence["codex"] = "quota"
    live = LiveApp(root, cli=cli, connector_name="auto", offline=False).start()
    try:
        journey = run_new_team(live, script=[])
        run = journey.run_id
        sessions = {who: live.session_of(f"web.{who}") for who in ("identity", "adaptation", "priority", "coordination", "audit")}
        found = Story(live, cli, journey.task, run, sessions)
        found.activity_before = live.get("/api/activity", dept="web", who="identity", run=run)

        def step(who: str, push: str | None = None) -> None:
            if push is not None:
                cli.push("claude", push)
            mark = len(cli.calls())
            found.answers[who] = ask(live, who, QUESTIONS[who], run)
            found.calls[who] = cli.calls()[mark:]

        step("identity", REPLIES["identity"])
        pick = live.http.put(f"/api/chats/{sessions['audit']}/choice", json={"provider": "claude", "model": "haiku", "effort": "low"})
        assert pick.status_code == 200, pick.text                                       # the agent's own pill: claude, haiku, low
        step("audit", REPLIES["audit"])
        step("priority")
        step("validator")
        limit = live.http.put("/api/limits", json={"monthly_usd": 0.02})              # the three chat calls and two answers cost more than that
        assert limit.status_code == 200 and limit.json()["spend"]["level"] == "over", limit.text
        step("coordination")
        assert live.http.put("/api/limits", json={"monthly_usd": None}).status_code == 200
        found.activity_after = live.get("/api/activity", dept="web", who="identity", run=run)
        yield found
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()


def flag(argv: list, name: str) -> str:
    return argv[argv.index(name) + 1]


# ---- a model answer is a turn of the function's own session ---------------------------------------------------------------------------------------

def test_a_function_with_no_pick_of_its_own_answers_on_the_policys_model_and_effort(story):
    status, body = story.answers["identity"]
    assert status == 200 and body["who"] == "identity" and body["from"] == "model" and "note" not in body
    assert json.loads(body["answer"]) == REPLIES["identity"]                           # the fake prints the queued JSON as the reply's text
    assert body["session_id"] == story.sessions["identity"]
    call, = story.calls["identity"]
    assert (call["cli"], call["op"], call["scenario"]) == ("claude", "print", "ok")
    assert (flag(call["argv"], "--model"), flag(call["argv"], "--effort"), flag(call["argv"], "--max-budget-usd")) == ("sonnet", "low", "0.25")
    assert "You are Client Lead (identity), one function of the J2 team that built this run." in flag(call["argv"], "--system-prompt")
    assert call["stdin"].startswith("YOUR RECORDS\n") and call["stdin"].rstrip().endswith("QUESTION\n" + QUESTIONS["identity"])    # J2's own prompt, J2's records


def test_the_question_and_the_answer_are_lines_of_the_function_session_the_node_panel_reads(story):
    body = story.body("identity")
    q, a = story.lines("identity")
    assert (q["role"], q["who"], q["text"], q["ask"], q["id"]) == ("user", "user", QUESTIONS["identity"], "q", body["question_id"])
    assert (a["role"], a["who"], a["text"], a["ask"], a["id"]) == ("agent", "identity", body["answer"], "model", body["answer_id"])
    assert q["task_id"] == a["task_id"] == story.task and q["session_id"] == a["session_id"] == story.sessions["identity"]
    refs = [story.live.one("SELECT src_ref FROM chat_messages WHERE id = ?", i) for i in (q["id"], a["id"])]
    assert refs[0].startswith("ask:") and refs[1] == refs[0] + ":model"
    session = story.live.get(f"/api/chats/{story.sessions['identity']}")
    assert session["writable"] is False                                                # still the function's read-only log: only the ask port writes in it
    assert not (story.live.run_dir(story.task) / "node_context.json").exists()         # a question is not a note: the engine never hears of it


def test_one_ledger_row_carries_the_session_the_function_the_purpose_and_the_runs_overhead_atom(story):
    row, = story.ledger("identity")
    assert (row["provider"], row["purpose"], row["fn"], row["session_id"], row["node_id"], row["task_id"], row["dept_id"]) == (
        "claude", "agent_chat", "identity", story.sessions["identity"], "web.identity", story.task, "web")
    assert (row["atom_id"], row["ok"], row["how"], row["usd"], row["tokens_in"], row["tokens_out"]) == (overhead_atom_id(story.run), 1, "text", 0.01, 120, 30)
    mine = {a["agent"]: a for a in story.live.get("/api/teams/web/agents", run=story.run)}["identity"]
    assert mine["usage"]["calls"] == 1 and mine["usage"]["usd"] == 0.01                # the Agents tab counts it under the function
    page = story.live.get("/api/usage", session_id=story.sessions["identity"])
    assert [r["purpose"] for r in page["rows"] if r["purpose"] == "agent_chat"] == ["agent_chat"] and page["totals"]["usd"] >= 0.01


# ---- its own pick ---------------------------------------------------------------------------------------------------------------------------------

def test_a_function_with_its_own_pick_answers_on_it(story):
    status, body = story.answers["audit"]
    assert status == 200 and body["from"] == "model" and json.loads(body["answer"]) == REPLIES["audit"]
    call, = story.calls["audit"]
    assert (flag(call["argv"], "--model"), flag(call["argv"], "--effort")) == ("haiku", "low")           # the pick of the Audit's pill, not the policy's
    assert "Quality Reviewer (audit)" in flag(call["argv"], "--system-prompt")
    row, = story.ledger("audit")
    assert (row["fn"], row["session_id"], row["ok"]) == ("audit", story.sessions["audit"], 1)
    assert json.loads(row["detail_json"])["attempts"][0]["effort"] == "low" and json.loads(row["detail_json"])["note"] is None      # no "your choice could not run"
    agents = {a["agent"]: a for a in story.live.get("/api/teams/web/agents", run=story.run)}
    assert agents["audit"]["effective"] == {"provider": "claude", "model": "haiku", "effort": "low", "source": "own"}
    assert agents["identity"]["effective"]["source"] == "default"                      # another function is not given Audit's pick


# ---- a model that cannot answer -------------------------------------------------------------------------------------------------------------------------

def test_when_no_model_can_answer_the_records_do_and_the_reason_is_in_the_note(story):
    status, body = story.answers["priority"]
    assert status == 200 and body["from"] == "records" and body["answer"].startswith("From the records:")
    assert body["note"].startswith("The model could not answer (") and body["note"].endswith("this is from the records only.")
    assert body["session_id"] == story.sessions["priority"] and body["question_id"] < body["answer_id"]
    assert [(c["cli"], c["scenario"]) for c in story.calls["priority"]] == [("claude", "quota"), ("codex", "quota")]
    assert [(role, who, part) for role, who, part in asked_words(story.lines("priority"))] == [("user", "user", "q"), ("agent", "priority", "records")]
    row, = story.ledger("priority")
    assert (row["ok"], row["fn"], row["session_id"], row["purpose"], row["atom_id"]) == (0, "priority", story.sessions["priority"], "agent_chat", overhead_atom_id(story.run))


# ---- no session of its own, and the owner's limit -------------------------------------------------------------------------------------------------------------------------

def test_the_validator_is_code_so_it_answers_from_the_records_with_no_line_and_no_call(story):
    status, body = story.answers["validator"]
    assert status == 200 and body["from"] == "records" and body["who"] == "validator" and "session_id" not in body and "note" not in body
    assert story.calls["validator"] == []
    assert story.live.rows("SELECT count(*) FROM chat_messages WHERE src_ref LIKE 'ask:%' AND text LIKE ?", "%" + QUESTIONS["validator"] + "%")[0][0] == 0


def test_the_owners_limit_holds_the_model_back_and_its_words_are_the_note(story):
    status, body = story.answers["coordination"]
    assert status == 200 and body["from"] == "records" and body["note"].startswith("waiting: this month's spending limit is used up")
    assert story.calls["coordination"] == [] and story.ledger("coordination") == []
    assert asked_words(story.lines("coordination")) == [("user", "user", "q"), ("agent", "coordination", "records")]


# ---- the other door is shut, and the records feed is J2's -------------------------------------------------------------------------------------------------------------------------

def test_what_the_route_refuses(story):
    live = story.live
    assert ask(live, "nobody", "x", story.run) == (400, {"error": "not a function"})
    assert ask(live, "audit", "x" * 2001, story.run) == (400, {"error": "question too long"})
    assert ask(live, "audit", "   ", story.run) == (200, {"who": "audit", "answer": "", "from": "records"})        # J2's own answer to nothing: nothing stored
    assert live.http.post("/api/ask?dept=web", json={"who": "audit", "q": "x"}, headers={"X-Sutra-Token": "wrong"}).status_code == 401
    assert [m["text"] for m in story.lines("audit")] == [QUESTIONS["audit"], story.body("audit")["answer"]]


def test_asking_changes_nothing_in_the_records_j2s_panel_reads(story):
    assert story.activity_before["found"] is True and story.activity_before == story.activity_after
    assert QUESTIONS["identity"] not in json.dumps(story.activity_after)


def test_the_event_stream_carried_both_lines_of_each_question_in_order(story):
    frames = [f["data"] for f in story.live.sse.snapshot() if f["type"] == "chat.message" and f["data"]["message"].get("ask")]
    mine = {who: [(f["message"]["ask"], f["message"]["who"]) for f in frames if f["session_id"] == story.sessions[who]]
            for who in ("identity", "audit", "priority", "coordination", "validator")}
    assert mine == {"identity": [("q", "user"), ("model", "identity")], "audit": [("q", "user"), ("model", "audit")],
                    "priority": [("q", "user"), ("records", "priority")], "coordination": [("q", "user"), ("records", "coordination")], "validator": []}


# ---- an app with no model ----------------------------------------------------------------------------------------------------------------------------------------------------------

def test_an_app_with_no_model_answers_from_the_records_says_so_and_stores_both_lines(tmp_path):
    live = LiveApp(tmp_path, connector=ScriptedConnector()).start()                    # the stub router: offline
    try:
        journey = run_new_team(live)
        sid = live.session_of("web.audit")
        status, body = ask(live, "audit", QUESTIONS["audit"], journey.run_id)
        assert status == 200 and body["from"] == "records" and body["note"] == NO_MODEL and body["session_id"] == sid
        assert body["answer"].startswith("From the records:") or "records" in body["answer"]
        lines = [m for m in live.messages(sid) if m.get("ask")]
        assert [(m["role"], m["who"], m["ask"]) for m in lines] == [("user", "user", "q"), ("agent", "audit", "records")]
        assert [m["id"] for m in lines] == [body["question_id"], body["answer_id"]]
        assert live.one("SELECT count(*) FROM usage_ledger WHERE purpose = 'agent_chat'") == 0          # no model was asked, not even a stub row
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()
