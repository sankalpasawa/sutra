"""A function's model-backed answer is a turn of its own agent session (J2 sync 4, D147 to D149; owner rule R2): `AgentAsk.turn` and `AskTurn`.

What is proved, with the real stores of `TEnv` and a real `Router` over named stubs (and, for the flags and the stdin of a real call, the fake `claude` and `codex`):
the turn exists only for one of the five functions that has a session stamped with that run (an archived one counts); the call is a call of THAT session with the
pick of its own cascade (own, then run, then team, `default` passes none), booked with the session, the node, the function, the purpose `agent_chat` and the run's
overhead atom; the text the model gets is scrubbed with an audit row in replace mode and so are the stored lines; the owner's limit and an offline router make
`can_ask` False with the words the owner reads and no call is ever made; one question at a time per session; the lines are stored once; every failure of the model
side is an `AskFailed`, and only that."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest
from connectors.test_router_pick import Named, policy
from orchestrator.test_tasks import TEnv, ev, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.config import Settings
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.egress import Egress
from sutra_app.connectors.models import ConnectorConfig, Pick
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import ReplyBook, StubConnector
from sutra_app.connectors.usage import UsageIn
from sutra_app.library.types import overhead_atom_id
from sutra_app.orchestrator.agent_ask import (
    ASK_MAX_CALLS, ASK_MAX_USD, ASK_TIMEOUT_S, ASK_REF, BUSY_TEXT, NO_MODEL, AgentAsk, AskTurn,
)
from sutra_app.orchestrator.agent_sessions import team_agents
from sutra_app.orchestrator.chat_v2 import ChatChoices
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.limits import Limits
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.wiring import build_services

FAKES = Path(__file__).resolve().parents[1] / "fakes"
SECRET = "hunter2hunter2"                                   # the value of an environment variable named like a secret: the app's own
CREDENTIAL = "sk-proj-REPRO1234567890abcdefghij"            # the shape of an API key
QUESTION = "Why was W-3 scored below the gate?"
SYSTEM = "You are Quality Reviewer (audit), one function of the J2 team that built this run."
RECORDS = "Judge W-3 scored 0.71 and named the missing footer."
ANSWER = "W-3 scored 0.71 because the footer was missing."


def ask_failed():
    """The refusal of the engine's route (engine/api/ports.py): imported by the test as the port imports it, where it is needed."""
    from sutra_app.engine.api.ports import AskFailed
    return AskFailed


class Port:
    """What `AgentAsk` asks of the chat port: the policy's default pick of an agent."""

    def __init__(self, default: Pick | None = None) -> None:
        self.default = default if default is not None else Pick(provider="claude", model="sonnet", effort="high")
        self.asked: list[str] = []

    def default_pick(self, function: str = "") -> Pick:
        self.asked.append(function)
        return self.default


def session_of(t: TEnv, node_id: str) -> str:
    return t.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", node_id)


def stamp(t: TEnv, task_id: str, *functions: str) -> None:
    """These functions worked in the run: their sessions are stamped with it (what the Projector does at an agent's first event)."""
    with t.db.tx() as tx:
        for name in functions:
            t.taskgraph.sessions.open(tx, t.row(task_id), f"web.{name}")


def spend(t: TEnv, usd: float) -> None:
    t.usage.record(UsageIn(provider="claude", model="sonnet", purpose="agent_turn", usd=usd, how="text"))


class Rig:
    """An `AgentAsk` over the real stores of `tenv`, a router of two named stubs that books to the real ledger, and a spy on what the router is asked."""

    def __init__(self, t: TEnv, tmp_path: Path, *, answer: str = ANSWER, offline: bool = False, connector: str = "auto", port: Port | None = None,
                 router: bool = True) -> None:
        self.t, self.tmp = t, tmp_path
        cfg = ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", claude_exe=sys.executable, codex_exe=sys.executable)
        book = lambda: ReplyBook().set("*", "*", answer)                       # noqa: E731
        self.claude, self.codex = Named("claude", cfg, book=book()), Named("codex", cfg, book=book())
        connectors = {"claude": self.claude, "codex": self.codex}
        if offline or connector == "stub":
            connectors["stub"] = StubConnector(cfg)
        self.events: list = []
        self.redactor = Redactor(None, environ={"MY_API_TOKEN": SECRET})
        self.router = Router(connectors, policy(), usage_sink=t.usage, events=lambda ty, d: self.events.append((ty, d)), sleep=lambda s: None, rng=lambda: 0.0,
                             offline=offline, connector=connector)
        self.egress_path = tmp_path / "egress.jsonl"
        self.router.egress = Egress(self.egress_path, self.redactor)
        self.sent: list = []
        real = self.router.ask

        def spy(req, on_progress=None):
            self.sent.append(req)
            return real(req, on_progress)

        self.router.ask = spy
        self.port = port if port is not None else Port()
        self.limits = Limits(tmp_path / "limits.json", t.db, quotas=lambda: {}, clock=t.clock)
        self.asking = AgentAsk(db=t.db, tasks=t.service, chats=t.chats, router=self.router if router else None, chat_port=self.port, limits=self.limits,
                               redact=self.redactor, clock=t.clock)

    def turn(self, dept="web", run=None, agent="audit") -> AskTurn | None:
        return self.asking.turn(dept, run, agent)

    def audit_rows(self) -> list[dict]:
        try:
            return [json.loads(line) for line in self.egress_path.read_text().splitlines() if line.strip()]
        except OSError:
            return []

    def ledger(self, session_id: str):
        return self.t.usage.rows(session_id=session_id, include_stub=True)[0]


@pytest.fixture
def task(tenv):  # noqa: F811
    """A running run in which identity, priority and audit have worked (adaptation and coordination have not)."""
    found = tenv.started()
    stamp(tenv, found, "identity", "priority", "audit")
    return found


@pytest.fixture
def rig(tenv, tmp_path):  # noqa: F811
    return Rig(tenv, tmp_path)


def run_of(t: TEnv, task_id: str) -> str:
    return t.row(task_id).run_id


def turn_of(rig: Rig, task_id: str, agent: str = "audit") -> AskTurn:
    found = rig.turn("web", run_of(rig.t, task_id), agent)
    assert found is not None
    return found


def converse(turn: AskTurn, question: str = QUESTION, user: str | None = None, source: str = "model") -> tuple[str, dict]:
    """What `DeptCommands.ask` does around J2's `answer`: begin, ask with J2's three-argument call, end in a finally."""
    turn.begin(question)
    text = None
    try:
        text = turn.ask(SYSTEM, user if user is not None else f"YOUR RECORDS\n{RECORDS}\n\nQUESTION\n{question}", lambda: "From the records: " + RECORDS,
                        max_tokens=700, effort="low")
    finally:
        stored = turn.end(text, source)
    return text, stored


# ---- which turns exist ---------------------------------------------------------------------------------------------------------------

def test_a_turn_exists_only_for_a_function_with_a_session_stamped_with_a_run_of_the_team(tenv, rig, task):  # noqa: F811
    run = run_of(tenv, task)
    assert all(rig.turn("web", run, who) is not None for who in ("identity", "priority", "audit"))
    for who in ("validator", "W-3", "chat_agent", "web", "task", "", "nobody"):
        assert rig.turn("web", run, who) is None
    assert rig.turn("web", run, "adaptation") is None and rig.turn("web", run, "coordination") is None          # they never worked in this run
    assert rig.turn("web", None, "audit") is None and rig.turn("web", "", "audit") is None
    assert rig.turn("sales", run, "audit") is None and rig.turn("nowhere", run, "audit") is None                  # a run is the team's own
    assert rig.turn("web", "j2-20261104-100000-ffff", "audit") is None


def test_a_function_that_works_later_in_the_run_gets_its_turn_from_then_on(tenv, rig, task):  # noqa: F811
    run = run_of(tenv, task)
    assert rig.turn("web", run, "coordination") is None
    stamp(tenv, task, "coordination")
    assert rig.turn("web", run, "coordination") is not None


def test_the_turn_is_the_function_nodes_session_of_that_run(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    assert (turn.session_id, turn.node_id, turn.task_id, turn.run_id, turn.dept_id, turn.agent) == (
        session_of(tenv, "web.audit"), "web.audit", task, run_of(tenv, task), "web", "audit")
    assert (turn.can_ask, turn.reason) == (True, "")
    assert turn_of(rig, task, "identity").session_id == session_of(tenv, "web.identity") != turn.session_id


def test_a_past_runs_archived_session_takes_the_question_and_the_new_run_has_its_own(tenv, rig):  # noqa: F811
    first = tenv.started(title="Cafe page")
    tenv.write_events(first, ev("say", id=1, who="audit", text="Nothing wrong", next="identity"))
    tenv.drain(first)
    old = session_of(tenv, "web.audit")
    tenv.projector.mark_ended(first, "done", "ok")
    second = tenv.new(text="Menu page please", title="Menu page").id
    tenv.run(tenv.service.start_ready())
    tenv.write_events(second, ev("run.started", pid=tenv.row(second).pid, schema="events/1", mock=True, seed="none"))
    tenv.drain(second)
    stamp(tenv, second, "audit")                                          # the audit's first line of the second run rolls its session
    new = session_of(tenv, "web.audit")
    assert new != old and tenv.chats.session(old).status == "archived" and tenv.chats.session(new).status == "active"
    past = rig.turn("web", run_of(tenv, first), "audit")
    assert past is not None and past.session_id == old and past.task_id == first
    _, stored = converse(past)
    assert [(m.who, m.text, m.ask) for m in tenv.chats.messages(old)] == [
        ("audit", "Nothing wrong", None), ("user", QUESTION, "q"), ("audit", ANSWER, "model")] and stored["session_id"] == old
    assert tenv.chats.messages(new) == [] and rig.turn("web", run_of(tenv, second), "audit").session_id == new


# ---- the pick: own, then run, then team; default passes none --------------------------------------------------------------------------------

def test_the_call_carries_the_pick_of_the_sessions_own_cascade_and_default_passes_none(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    audit, team = session_of(tenv, "web.audit"), session_of(tenv, "web")
    converse(turn)
    assert rig.sent[-1].ctx.pick is None and rig.port.asked[-1] == "audit"                                   # nobody chose: the policy decides
    assert rig.ledger(audit)[-1].provider == "claude" and (rig.ledger(audit)[-1].detail or {}).get("note") is None     # and no "your choice could not run" note
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set_pick(tx, team, "claude", "haiku", "low")
    converse(turn)
    assert rig.sent[-1].ctx.pick == Pick(provider="claude", model="haiku", effort="low")                    # the team's pill
    assert rig.claude.got[-1] == {"model": "haiku", "effort": "low"}
    with tenv.db.tx() as tx:
        tenv.store.set_pick(tx, task, Pick(provider="codex", model="gpt-5.6-luna", effort="medium"))
    converse(turn)
    assert rig.sent[-1].ctx.pick == Pick(provider="codex", model="gpt-5.6-luna", effort="medium")           # the run's, over the team's
    assert rig.codex.got[-1] == {"model": "gpt-5.6-luna", "effort": "medium"}
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set_pick(tx, audit, "claude", "sonnet", "max")
    converse(turn)
    assert rig.sent[-1].ctx.pick == Pick(provider="claude", model="sonnet", effort="max")                   # the agent's own, over both
    assert rig.claude.got[-1] == {"model": "sonnet", "effort": "max"}
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set_pick(tx, audit, None, None, None)
    converse(turn)
    assert rig.sent[-1].ctx.pick == Pick(provider="codex", model="gpt-5.6-luna", effort="medium")           # cleared: the run's again


def test_another_function_is_not_given_the_audits_pick(tenv, rig, task):  # noqa: F811
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set_pick(tx, session_of(tenv, "web.audit"), "codex", "gpt-5.6-terra", "xhigh")
    converse(turn_of(rig, task, "identity"))
    assert rig.sent[-1].ctx.pick is None and rig.ledger(session_of(tenv, "web.identity"))[-1].provider == "claude"
    converse(turn_of(rig, task, "audit"))
    assert rig.sent[-1].ctx.pick == Pick(provider="codex", model="gpt-5.6-terra", effort="xhigh") and rig.codex.got[-1]["effort"] == "xhigh"


def test_a_pick_that_cannot_run_falls_back_to_the_policy_with_the_usual_note(tenv, rig, task):  # noqa: F811
    rig.codex.signed_in = False
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set_pick(tx, session_of(tenv, "web.audit"), "codex", "gpt-5.6-luna", "low")
    text, _ = converse(turn_of(rig, task))
    row = rig.ledger(session_of(tenv, "web.audit"))[-1]
    assert text == ANSWER and row.provider == "claude"
    assert row.detail["note"] == "your choice for audit (codex) could not run: not signed in; claude answered"
    assert rig.claude.got[-1] == {"model": "sonnet", "effort": "low"}                                        # the policy's model; the request's own effort


# ---- the call is booked to the session --------------------------------------------------------------------------------------------------------

def test_one_usage_row_carries_the_session_the_function_the_purpose_and_the_runs_overhead_atom(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    text, _ = converse(turn)
    rows = rig.ledger(turn.session_id)
    row, = rows
    assert text == ANSWER and (row.session_id, row.node_id, row.fn, row.purpose, row.task_id, row.dept_id) == (
        turn.session_id, "web.audit", "audit", "agent_chat", task, "web")
    assert (row.atom_id, row.ok, row.provider, row.how) == (overhead_atom_id(run_of(tenv, task)), True, "claude", "text")
    assert len(rig.sent) == 1 and tenv.usage.rows(task_id=task, include_stub=True)[0][-1].id == row.id
    mine, = [a for a in team_agents(tenv.db.conn(), tenv.store, "web", None) if a["agent"] == "audit"]
    assert mine["usage"]["calls"] == 1 and all(a["usage"]["calls"] == 0 for a in team_agents(tenv.db.conn(), tenv.store, "web", None) if a["agent"] != "audit")


def test_the_session_chip_follows_the_model_that_answered(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    converse(turn)
    session = tenv.chats.session(turn.session_id)
    assert session.connector == "claude" and session.writable is False          # booked like the function's own calls; still nobody else's to write in


def test_the_request_is_one_short_bounded_text_call_in_no_working_folder(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    before = rig.router._clock()
    converse(turn)
    req = rig.sent[-1]
    assert (req.kind, req.effort, req.timeout_s, req.images, req.tools) == ("text", "low", ASK_TIMEOUT_S, [], ())
    assert (ASK_MAX_CALLS, ASK_MAX_USD, ASK_TIMEOUT_S) == (2, 0.25, 120.0)
    a = req.ctx.allowance
    assert (a.max_calls, a.max_usd) == (2, 0.25) and before + 119 < a.deadline <= rig.router._clock() + 120
    tag = req.ctx.tag
    assert (tag.function, tag.purpose, tag.run_id, tag.dept_id, tag.task_id, tag.workspace, tag.atom) == (
        "audit", "agent_chat", run_of(tenv, task), "web", task, "none", overhead_atom_id(run_of(tenv, task)))
    assert (req.ctx.session_id, req.ctx.node_id) == (turn.session_id, "web.audit") and callable(req.scripted)
    assert req.scripted() == "From the records: " + RECORDS                                              # J2's `mock`: the records, never an invention
    turn2 = turn_of(rig, task, "priority")
    turn2.begin("another?")
    turn2.ask(SYSTEM, "u", None, effort="medium")
    assert rig.sent[-1].effort == "medium" and rig.sent[-1].scripted is None
    turn2.end(None, "records")
    turn2.begin("and?")
    turn2.ask(SYSTEM, "u", effort="loud")                                                                 # not an effort: the question stays short
    turn2.end(None, "records")
    assert rig.sent[-1].effort == "low"


def test_j2s_ask_call_works_with_its_keywords_and_without_them(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    assert turn.ask(SYSTEM, "u", lambda: "x", max_tokens=700, effort="low") == ANSWER
    assert turn.ask(SYSTEM, "u", lambda: "x") == ANSWER and turn.ask(SYSTEM, "u") == ANSWER


# ---- the text is scrubbed ----------------------------------------------------------------------------------------------------------------------

def test_a_credential_in_the_records_never_reaches_the_model_and_the_audit_row_is_in_replace_mode(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    records = f"The owner pasted {CREDENTIAL} and the token {SECRET} in the brief."
    system = SYSTEM + f" Remember {CREDENTIAL}."
    turn.begin(f"What did you do with {CREDENTIAL}?")
    turn.ask(system, f"YOUR RECORDS\n{records}\n\nQUESTION\nwhat did you do with {CREDENTIAL} and {SECRET}?", lambda: records)
    sent = rig.claude.calls[-1]
    for leaked in (CREDENTIAL, SECRET):
        assert leaked not in sent.prompt and leaked not in sent.system
    assert "[redacted" in sent.prompt and "[redacted" in sent.system and "The owner pasted" in sent.prompt
    replaced = [r for r in rig.audit_rows() if r["mode"] == "replace" and r["session"] == turn.session_id]
    assert replaced and replaced[0]["shapes"].get("openai-key") == 2 and replaced[0]["shapes"].get("secret-value") == 2
    assert CREDENTIAL not in rig.egress_path.read_text() and SECRET not in rig.egress_path.read_text()          # a row names shapes and counts, never a match


def test_the_stored_lines_are_scrubbed_too(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    turn.begin(f"Did you keep {CREDENTIAL}?")
    turn.end(f"Yes: {SECRET} and {CREDENTIAL} are in the records.", "records")
    q, a = tenv.chats.messages(turn.session_id)
    for line in (q, a):
        assert CREDENTIAL not in line.text and SECRET not in line.text and "[redacted" in line.text
    assert q.text.startswith("Did you keep ") and a.text.startswith("Yes: ")


def test_a_router_without_an_egress_is_no_gap(tenv, tmp_path, task):  # noqa: F811
    rig = Rig(tenv, tmp_path)
    rig.router.egress = None
    turn = turn_of(rig, task)
    turn.begin("q?")
    turn.ask(SYSTEM, f"records {CREDENTIAL} {SECRET}")
    assert CREDENTIAL not in rig.claude.calls[-1].prompt and SECRET not in rig.claude.calls[-1].prompt


def test_the_failure_reason_the_owner_reads_is_one_clean_line_without_a_secret(tenv, rig, task):  # noqa: F811
    rig.claude.fail_next("invalid_request", message=f"boom {SECRET}\nsecond line " + "x" * 600)         # neither retried nor handed to the next provider
    turn = turn_of(rig, task)
    turn.begin("q?")
    with pytest.raises(ask_failed()) as failed:
        turn.ask(SYSTEM, "u")
    reason = failed.value.reason
    assert SECRET not in reason and "\n" not in reason and reason.startswith("boom [redacted] second line") and len(reason) <= 300


# ---- limits: the owner's, and the router's own --------------------------------------------------------------------------------------------------

def test_the_owners_limit_holds_the_model_back_and_its_words_are_the_reason(tenv, rig, task):  # noqa: F811
    rig.limits.update(monthly_usd=1.0)
    spend(tenv, 2.0)
    turn = turn_of(rig, task)
    assert turn.can_ask is False and turn.reason.startswith("waiting: this month's spending limit is used up") and "$2 of $1" in turn.reason
    turn.begin(QUESTION)
    with pytest.raises(ask_failed()) as refused:
        turn.ask(SYSTEM, "u")
    assert refused.value.reason == turn.reason and rig.sent == []                                         # refused without a call
    stored = turn.end("From the records: x", "records")
    assert [(m.ask, m.who) for m in tenv.chats.messages(turn.session_id)] == [("q", "user"), ("records", "audit")] and stored["answer_id"]
    rig.limits.update(monthly_usd=None)
    assert turn_of(rig, task).can_ask is True


def test_an_offline_router_never_answers_but_both_lines_are_stored_all_the_same(tenv, tmp_path, task):  # noqa: F811
    rig = Rig(tenv, tmp_path, offline=True)
    turn = turn_of(rig, task)
    assert (turn.can_ask, turn.reason) == (False, NO_MODEL) and NO_MODEL == "No model is connected."
    turn.begin(QUESTION)
    with pytest.raises(ask_failed()) as refused:
        turn.ask(SYSTEM, "u")
    assert refused.value.reason == NO_MODEL and rig.sent == [] and rig.claude.calls == [] and rig.codex.calls == []
    stored = turn.end("From the records: x", "records")
    assert [(m.ask, m.text) for m in tenv.chats.messages(turn.session_id)] == [("q", QUESTION), ("records", "From the records: x")]
    assert stored == {"session_id": turn.session_id, "question_id": tenv.chats.messages(turn.session_id)[0].id,
                      "answer_id": tenv.chats.messages(turn.session_id)[1].id}
    assert rig.ledger(turn.session_id) == []


def test_a_stub_only_app_is_offline_too(tenv, tmp_path, task):  # noqa: F811
    rig = Rig(tenv, tmp_path, connector="stub")
    assert rig.router.mode == "offline" and turn_of(rig, task).can_ask is False


def test_an_app_with_no_router_or_no_chat_port_cannot_ask(tenv, tmp_path, task):  # noqa: F811
    assert Rig(tenv, tmp_path, router=False).turn("web", run_of(tenv, task), "audit").can_ask is False
    no_port = Rig(tenv, tmp_path)
    no_port.asking.chat_port = None
    turn = no_port.turn("web", run_of(tenv, task), "audit")
    assert (turn.can_ask, turn.reason) == (False, NO_MODEL)


# ---- one question at a time per session ----------------------------------------------------------------------------------------------------------

def test_a_second_question_while_one_is_answered_is_busy_and_stores_nothing(tenv, rig, task):  # noqa: F811
    first, second = turn_of(rig, task), turn_of(rig, task)                  # two requests make two turns of the one session
    first.begin("one?")
    assert rig.asking.asking(first.session_id) is True
    with pytest.raises(AppError) as busy:
        second.begin("two?")
    assert (busy.value.code, busy.value.status, busy.value.message) == ("busy", 409, BUSY_TEXT)
    with pytest.raises(AppError) as again:
        first.begin("one again?")                                              # not twice on one turn, either
    assert again.value.code == "busy"
    assert [m.text for m in tenv.chats.messages(first.session_id)] == ["one?"]
    first.end("An answer.", "records")
    assert rig.asking.asking(first.session_id) is False
    second.begin("two?")
    second.end("Another.", "records")
    assert [(m.ask, m.text) for m in tenv.chats.messages(first.session_id)] == [("q", "one?"), ("records", "An answer."), ("q", "two?"), ("records", "Another.")]


def test_another_functions_session_is_not_held_by_a_question_to_this_one(tenv, rig, task):  # noqa: F811
    audit, priority = turn_of(rig, task, "audit"), turn_of(rig, task, "priority")
    audit.begin("one?")
    priority.begin("two?")                                                      # no refusal
    assert rig.asking.asking(audit.session_id) and rig.asking.asking(priority.session_id)
    audit.end(None, "records")
    priority.end(None, "records")
    assert not rig.asking.asking(audit.session_id) and not rig.asking.asking(priority.session_id)


def test_the_mark_is_released_when_the_answer_is_not_stored_and_when_a_question_cannot_be_stored(tenv, rig, task, monkeypatch):  # noqa: F811
    turn = turn_of(rig, task)
    turn.begin("one?")
    assert turn.end(None, "records") == {} and rig.asking.asking(turn.session_id) is False       # an unexpected error: nothing stored, the mark is gone
    assert [m.text for m in tenv.chats.messages(turn.session_id)] == ["one?"]
    turn = turn_of(rig, task)
    with pytest.raises(AppError):
        turn.begin("   ")                                                                         # an empty question takes no mark and stores nothing
    assert rig.asking.asking(turn.session_id) is False
    real = rig.asking._post
    monkeypatch.setattr(rig.asking, "_post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the store is closed")))
    with pytest.raises(RuntimeError):
        turn.begin("two?")
    assert rig.asking.asking(turn.session_id) is False
    monkeypatch.setattr(rig.asking, "_post", real)
    turn.begin("three?")
    turn.end("x", "records")


def test_two_questions_at_the_same_moment_let_exactly_one_in(tenv, rig, task):  # noqa: F811
    turns = [turn_of(rig, task) for _ in range(6)]
    barrier = threading.Barrier(len(turns))
    results: list = []

    def go(turn: AskTurn) -> None:
        barrier.wait()
        try:
            results.append(("in", turn.begin(f"q from {id(turn)}")))
        except AppError as exc:
            results.append((exc.code, None))

    threads = [threading.Thread(target=go, args=(t,)) for t in turns]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(r[0] for r in results) == ["busy"] * 5 + ["in"] and len(tenv.chats.messages(turns[0].session_id)) == 1


# ---- the two lines -----------------------------------------------------------------------------------------------------------------------------------

def test_the_question_and_the_answer_are_lines_of_the_function_session_paired_by_one_id(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    tenv.env.events.batches.clear()
    text, stored = converse(turn)
    q, a = tenv.chats.messages(turn.session_id)
    assert text == ANSWER and stored == {"session_id": turn.session_id, "question_id": q.id, "answer_id": a.id}
    assert (q.role, q.who, q.kind, q.text, q.task_id, q.ask, q.steer) == ("user", "user", "text", QUESTION, task, "q", False)
    assert (a.role, a.who, a.kind, a.text, a.task_id, a.ask) == ("agent", "audit", "text", ANSWER, task, "model")
    token = tenv.one("SELECT src_ref FROM chat_messages WHERE id = ?", q.id)
    assert token.startswith(ASK_REF) and ":" not in token[len(ASK_REF):] and tenv.one("SELECT src_ref FROM chat_messages WHERE id = ?", a.id) == f"{token}:model"
    sent = [e for e in tenv.env.events.events if e.type == "chat.message"]
    assert [e.data["message"]["ask"] for e in sent] == ["q", "model"] and all(e.data["session_id"] == turn.session_id for e in sent)
    assert tenv.chats.session(turn.session_id).writable is False                                       # still the agent's read-only log: only this port writes in it
    assert not (tenv.run_dir(task) / "node_context.json").exists()                                      # a question is not a note: the engine never hears of it


def test_an_answer_from_the_records_is_labelled_so_and_two_questions_have_two_tokens(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    turn.begin("one?")
    turn.end("From the records: x", "records")
    again = turn_of(rig, task)
    again.begin("two?")
    again.end("From the records: y", "records")
    assert [m.ask for m in tenv.chats.messages(turn.session_id)] == ["q", "records", "q", "records"]
    refs = [tenv.one("SELECT src_ref FROM chat_messages WHERE id = ?", m.id) for m in tenv.chats.messages(turn.session_id)]
    assert refs[0] != refs[2] and refs[1] == refs[0] + ":records" and refs[3] == refs[2] + ":records"


def test_the_lines_are_stored_once_however_often_end_is_called(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    first = turn.begin("one?")
    stored = turn.end("An answer.", "model")
    assert turn.end("An answer.", "model") == stored and turn.end("Another answer.", "records") == stored and stored["question_id"] == first
    assert [m.text for m in tenv.chats.messages(turn.session_id)] == ["one?", "An answer."]
    assert len([e for e in tenv.env.events.events if e.type == "chat.message"]) == 2


def test_end_stores_nothing_without_a_question_an_answer_or_a_text(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    assert turn.end("An answer with no question", "model") == {}                                       # `begin` never ran
    assert tenv.chats.messages(turn.session_id) == []
    turn.begin("one?")
    assert turn.end("", "records") == {} and turn.end("   ", "records") == {}
    assert [m.text for m in tenv.chats.messages(turn.session_id)] == ["one?"] and rig.asking.asking(turn.session_id) is False


def test_an_answer_is_from_the_records_or_a_model_and_nothing_else(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    turn.begin("one?")
    with pytest.raises(ValueError):
        turn.end("An answer.", "guess")
    assert rig.asking.asking(turn.session_id) is False and [m.text for m in tenv.chats.messages(turn.session_id)] == ["one?"]


def test_a_very_long_line_is_stored_cut_not_refused(tenv, rig, task):  # noqa: F811
    turn = turn_of(rig, task)
    turn.begin("q?")
    turn.end("word " * 60_000, "records")
    stored = tenv.chats.messages(turn.session_id)[-1].text
    assert 99_000 < len(stored) <= 100_000 and stored.endswith("…")


def test_tokens_come_from_the_given_id_source_when_there_is_one(tenv, tmp_path, task):  # noqa: F811
    rig = Rig(tenv, tmp_path)
    rig.asking.ids = tenv.ids
    turn = turn_of(rig, task)
    turn.begin("one?")
    ref = tenv.one("SELECT src_ref FROM chat_messages WHERE id = ?", tenv.chats.messages(turn.session_id)[0].id)
    assert ref.startswith("ask:") and len(ref) == len("ask:") + 12 and not ref.startswith("ask:cs_")
    turn.end(None, "records")


# ---- everything the model side can do wrong is an AskFailed -----------------------------------------------------------------------------------

def test_no_provider_is_an_ask_failed_with_the_connectors_own_words(tenv, rig, task):  # noqa: F811
    rig.claude.signed_in = rig.codex.signed_in = False
    turn = turn_of(rig, task)
    turn.begin("q?")
    with pytest.raises(ask_failed()) as failed:
        turn.ask(SYSTEM, "u")
    assert "not signed in" in failed.value.reason and failed.value.__cause__ is not None
    assert rig.ledger(turn.session_id)[-1].ok is False                                                  # the failed request is booked all the same


def test_both_providers_out_of_quota_is_an_ask_failed(tenv, rig, task):  # noqa: F811
    rig.claude.fail_next("quota")
    rig.codex.fail_next("quota")
    turn = turn_of(rig, task)
    turn.begin("q?")
    with pytest.raises(ask_failed()) as failed:
        turn.ask(SYSTEM, "u")
    assert failed.value.reason and "\n" not in failed.value.reason
    assert rig.ledger(turn.session_id)[-1].ok is False and rig.ledger(turn.session_id)[-1].purpose == "agent_chat"


def test_one_retry_is_the_most_a_question_costs_so_the_next_provider_is_refused(tenv, rig, task):  # noqa: F811
    rig.claude.fail_next("overloaded", times=2)
    rig.codex.fail_next("overloaded", times=2)
    turn = turn_of(rig, task)
    turn.begin("q?")
    with pytest.raises(ask_failed()) as failed:
        turn.ask(SYSTEM, "u")
    assert failed.value.reason == "the envelope allows no more calls, money or time" and rig.codex.got == []         # claude, its retry, then the allowance says no
    assert len(rig.claude.got) == 2


def test_a_model_that_answers_with_nothing_is_an_ask_failed(tenv, tmp_path, task):  # noqa: F811
    rig = Rig(tenv, tmp_path, answer="   ")
    turn = turn_of(rig, task)
    turn.begin("q?")
    with pytest.raises(ask_failed()) as failed:
        turn.ask(SYSTEM, "u")
    assert failed.value.reason


def test_a_type_error_inside_the_model_side_is_an_ask_failed_and_never_a_type_error(tenv, rig, task, monkeypatch):  # noqa: F811
    """J2 answers a TypeError of `ask` by calling it again without its keywords: that second call would be a second, paid model call."""
    calls = []

    def boom(req, on_progress=None):
        calls.append(req)
        raise TypeError("boom")

    monkeypatch.setattr(rig.router, "ask", boom)
    turn = turn_of(rig, task)
    turn.begin("q?")
    with pytest.raises(ask_failed()) as failed:
        turn.ask(SYSTEM, "u")
    assert not isinstance(failed.value, TypeError) and "TypeError" in failed.value.reason and len(calls) == 1


def test_an_unreadable_pick_is_no_reason_to_refuse_a_question(tenv, rig, task, monkeypatch):  # noqa: F811
    import sutra_app.orchestrator.agent_ask as module
    monkeypatch.setattr(module, "effective", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the database is busy")))
    turn = turn_of(rig, task)
    turn.begin("q?")
    assert turn.ask(SYSTEM, "u") == ANSWER and rig.sent[-1].ctx.pick is None


# ---- the wiring ------------------------------------------------------------------------------------------------------------------------------------

def services_for(tmp_path, **changes):
    settings = Settings.load({}, data_dir=tmp_path / "data", token="t" * 24, env_file=tmp_path / "none.env", engine="fake", **changes)
    return build_services(settings)


def test_build_services_fills_the_slot_with_the_one_ports_turn_and_missing_is_unchanged(tmp_path):
    services = services_for(tmp_path)
    assert callable(services.agent_chat) and isinstance(services.agent_chat.__self__, AgentAsk)
    port = services.agent_chat.__self__
    assert (port.router, port.chat_port, port.limits, port.chats, port.tasks, port.db) == (
        services.connector_router, services.chat_port, services.limits, services.chats, services.tasks, services.db)
    assert port.redact is services.redact and "agent_chat" not in services.missing()
    services.db.migrate()
    assert services.agent_chat("web", "j2-20261104-100000-ab12", "audit") is None and services.agent_chat("web", None, "identity") is None
    services.db.close()


def test_an_app_with_an_injected_connector_has_a_stub_router_and_so_never_asks_a_model(tmp_path):
    from sutra_app.orchestrator.testing.scripted import ScriptedConnector
    settings = Settings.load({}, data_dir=tmp_path / "data", token="t" * 24, env_file=tmp_path / "none.env", engine="fake")
    services = build_services(settings, connector=ScriptedConnector([]))
    assert services.connector_router.mode == "offline"
    assert services.agent_chat.__self__._can_ask(None, "web") == (False, NO_MODEL)               # decided before any store is read
    services.db.close()


# ---- the real connectors over the fake claude and codex ------------------------------------------------------------------------------------------

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the fake claude, codex and gh are POSIX shell wrappers")


def real_rig(tenv, tmp_path, **env):
    state = tmp_path / "fake-state"
    extra = {"FAKE_CLI_STATE": str(state), "FAKE_PYTHON": sys.executable, "FAKE_MAX_SECONDS": "20", "FAKE_CLI_SEQUENCE": "ok_plain",
             "FAKE_REPLY_TEXT": "The fake answer.", "FAKE_COST_USD": "0.01", **env}
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=str(FAKES / "claude"), codex_exe=str(FAKES / "codex"),
                          gh_exe=str(FAKES / "gh"), python=sys.executable, extra_env=extra)
    redactor = Redactor(None, environ={"MY_API_TOKEN": SECRET})
    router = Router({"claude": ClaudeConnector(cfg), "codex": CodexConnector(cfg)}, policy(), usage_sink=tenv.usage, sleep=lambda s: None)
    router.egress = Egress(tmp_path / "egress.jsonl", redactor)
    asking = AgentAsk(db=tenv.db, tasks=tenv.service, chats=tenv.chats, router=router, chat_port=Port(),
                      limits=Limits(tmp_path / "limits.json", tenv.db, quotas=lambda: {}, clock=tenv.clock), redact=redactor, clock=tenv.clock)
    return asking, router, state


def model_calls(state: Path, cli: str) -> list[dict]:
    try:
        lines = (state / "calls.jsonl").read_text().splitlines()
    except OSError:
        return []
    return [rec for rec in map(json.loads, filter(str.strip, lines)) if rec.get("cli") == cli and rec.get("kind") == "call"]


def flag(argv: list, name: str) -> str:
    return argv[argv.index(name) + 1]


@POSIX_ONLY
def test_over_the_real_claude_connector_the_picked_model_and_effort_are_the_flags_and_no_credential_reaches_its_input(tenv, tmp_path, task):  # noqa: F811
    asking, router, state = real_rig(tenv, tmp_path)
    try:
        with tenv.db.tx() as tx:
            ChatChoices(tenv.db).set_pick(tx, session_of(tenv, "web.audit"), "claude", "haiku", "low")
        turn = asking.turn("web", run_of(tenv, task), "audit")
        turn.begin("what about the key?")
        text = turn.ask(SYSTEM + f" {CREDENTIAL}", f"YOUR RECORDS\nthe owner pasted {CREDENTIAL} and {SECRET}\n\nQUESTION\nwhat about the key?")
        turn.end(text, "model")
        call, = model_calls(state, "claude")
        assert text == "The fake answer." and (flag(call["argv"], "--model"), flag(call["argv"], "--effort")) == ("haiku", "low")
        everything = json.dumps([call["stdin"], call["argv"]])                  # the user text is the input, the system text is a flag of the call
        assert CREDENTIAL not in everything and SECRET not in everything and "[redacted" in call["stdin"] and "[redacted" in " ".join(call["argv"])
        assert "the owner pasted" in call["stdin"] and "one function of the J2 team" in " ".join(call["argv"])
        row, = tenv.usage.rows(session_id=turn.session_id)[0]
        assert (row.provider, row.purpose, row.fn, row.session_id, row.ok) == ("claude", "agent_chat", "audit", turn.session_id, True) and row.usd == 0.01
    finally:
        router.close()


@POSIX_ONLY
def test_over_the_real_connectors_a_codex_pick_goes_to_codex_and_the_policys_choice_to_claude(tenv, tmp_path, task):  # noqa: F811
    asking, router, state = real_rig(tenv, tmp_path)
    try:
        with tenv.db.tx() as tx:
            ChatChoices(tenv.db).set_pick(tx, session_of(tenv, "web.identity"), "codex", None, "medium")
        picked = asking.turn("web", run_of(tenv, task), "identity")
        picked.begin("q?")
        picked.ask(SYSTEM, "u")
        picked.end(None, "records")
        plain = asking.turn("web", run_of(tenv, task), "priority")
        plain.begin("q?")
        plain.ask(SYSTEM, "u")
        plain.end(None, "records")
        codex, = model_calls(state, "codex")
        claude, = model_calls(state, "claude")
        assert 'model_reasoning_effort="medium"' in codex["argv"] and flag(claude["argv"], "--model") == "sonnet" and flag(claude["argv"], "--effort") == "low"
    finally:
        router.close()
