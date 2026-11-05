"""The turn runner (ORCH-7): the queue, T0 to T9, approvals, the code template lines and the cards, the failures F1 to F5.
Everything runs offline against `ScriptedConnector` and the fake launcher."""
import asyncio
import json

import pytest
from orchestrator.test_chat_agent import (
    AgentEnv, add_dept, add_div, assignments, change_reply, decide, draft,
)

from sutra_app.library.types import overhead_atom_id
from sutra_app.orchestrator.agent import planner
from sutra_app.orchestrator.agent.runner import TurnHooks, TurnRunner
from sutra_app.orchestrator.chart import ChangeFailed
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import ChatChoice, Event
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

ORG = "cs_org"
SECRET_SENTENCE = "ZZZ the model wrote this sentence for the owner"


class RunnerEnv(AgentEnv):
    def __init__(self, db, settings, clock, events, script=(), **runner_kw) -> None:
        super().__init__(db, settings, clock, events, script)
        self.hooked: list[tuple] = []
        hooks = TurnHooks(on_phase=lambda m, p: self.hooked.append(("phase", m, p)), on_done=lambda m: self.hooked.append(("done", m)),
                          on_error=lambda m, s: self.hooked.append(("error", m, s)))
        self.runner = TurnRunner(
            db=db, chart=self.chart, chats=self.chats, tasks=self.service, agent=self.agent, connector=self.connector, hooks=hooks,
            publish=lambda type_, data: events([Event(seq=0, at=iso_z(clock.now()), type=type_, data=data)]), **runner_kw)
        self.events = events

    # ---- driving -----------------------------------------------------------------------------------------------------------

    def say(self, text: str, **kw):
        async def go():
            accepted = await self.runner.post_user_message(ORG, text, **kw)
            await self.runner.wait_idle()
            return accepted
        return self.run(go())

    def go(self, coro_factory):
        async def go():
            result = await coro_factory()
            await self.runner.wait_idle()
            return result
        return self.run(go())

    # ---- reading ---------------------------------------------------------------------------------------------------------------

    def messages(self, session=ORG):
        return self.chats.messages(session)

    def sutra(self):
        """What Sutra said in the org chat: ('line', text) or ('card', type)."""
        return [("card", m.card.type) if m.kind == "card" else (m.kind, m.text) for m in self.messages() if m.who == "sutra"]

    def user_state(self, mid: int) -> str:
        return self.chats.message(mid).state

    def cards(self, kind: str):
        return [m.card for m in self.messages() if m.kind == "card" and m.card.type == kind]

    def tasks_of(self, request: str):
        return [r for r in self.sql("SELECT * FROM tasks WHERE request_id = ? ORDER BY created_at, rowid", request)]

    def types(self):
        return self.events.types()


@pytest.fixture
def renv(db, settings, clock, events):
    return RunnerEnv(db, settings, clock, events)


def renv_with(db, settings, clock, events, *script, **kw) -> RunnerEnv:
    return RunnerEnv(db, settings, clock, events, script, **kw)


def merge_reply(into="quotes", *sources):
    return change_reply({"op": "merge", "into": into, "sources": list(sources or ["leads"])})


# ============================================ the happy paths ================================================================

def test_a_reuse_request_runs_one_call_and_hands_the_work_to_the_team(renv):
    renv.connector.push(decide(why=SECRET_SENTENCE))
    accepted = renv.say("I need a landing page for my coffee shop.")
    assert (accepted.message_id, accepted.turn) == (renv.one("SELECT min(id) FROM chat_messages WHERE role='user'"), "started")
    assert renv.user_state(accepted.message_id) == "ok"
    assert renv.sutra() == [("text", planner.LINES["greeting"]), ("text", "I gave this to the Web team."), ("card", "task")]
    [task] = renv.tasks_of(f"req-{accepted.message_id}")
    assert (task["dept_id"], task["title"], task["framing"], task["user_text"]) == ("web", "Cafe page", "Build the cafe landing page.", "I need a landing page for my coffee shop.")
    change = renv.sql("SELECT * FROM chart_changes ORDER BY seq DESC").fetchone()
    assert (change["kind"], change["status"], change["actor"], change["task_id"], change["task_title"]) == ("reuse", "applied", "chat_agent", f"req-{accepted.message_id}", "Cafe page")
    assert task["change_id"] == change["id"]


def test_the_owner_words_are_the_first_line_of_the_teams_chat(renv):
    renv.connector.push(decide())
    accepted = renv.say("I need a landing page for my coffee shop.")
    [task] = renv.tasks_of(f"req-{accepted.message_id}")
    session = renv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")
    lines = [m for m in renv.messages(session) if m.role == "user"]
    assert [(m.who, m.text, m.task_id) for m in lines] == [("user", "I need a landing page for my coffee shop.", task["id"])]
    assert renv.one("SELECT src_ref FROM chat_messages WHERE id = ?", lines[0].id) == f"req:{accepted.message_id}:{task['id']}"


def test_an_add_request_makes_the_team_and_says_so_in_a_template(renv):
    renv.connector.push(decide(change="add", reuse=(), why=SECRET_SENTENCE),
                        change_reply(add_dept("$cafe", "Cafe", "Coffee shop menus"), reason=SECRET_SENTENCE),
                        assignments(draft("a1", "cafe", brief=SECRET_SENTENCE)))
    accepted = renv.say("Plan my coffee shop launch")
    assert renv.connector.calls and [c.step for c in renv.connector.calls] == ["decide", "change", "assign"]
    assert renv.sutra()[-3:] == [("text", "I set up a Cafe team and gave it your request."), ("card", "chart_change"), ("card", "task")]
    card = renv.cards("chart_change")[-1]
    assert card.decision == "add" and [(a.id, a.name, a.kind) for a in card.added] == [("cafe", "Cafe", "department")] and not card.pending
    assert renv.one("SELECT count(*) FROM departments WHERE id = 'cafe'") == 1 and renv.tasks_of(f"req-{accepted.message_id}")[0]["dept_id"] == "cafe"
    assert renv.cards("task")[-1].dept_name == "Cafe" and renv.cards("task")[-1].status in ("starting", "queued", "running")


def test_event_order_of_a_new_team(renv):
    renv.connector.push(decide(change="add", reuse=()), change_reply(add_dept("$cafe", "Cafe", "Coffee")), assignments(draft("a1", "cafe")))
    renv.events.batches.clear()
    renv.say("Plan my coffee shop launch")
    types = renv.types()
    wanted = ["chat.message", "chat.turn", "chat.turn", "chat.turn", "chat.turn", "chart.changed", "graph.updated", "task.updated", "chat.message", "chat.turn"]
    positions, at = [], 0
    for kind in wanted:
        at = types.index(kind, at)
        positions.append(at)
        at += 1
    turns = [e.data["phase"] for e in renv.events.events if e.type == "chat.turn"]
    assert turns == ["reading_chart", "consulting_library", "planning", "applying", "handing_off", "done"]
    assert all(e.data["session_id"] == ORG and e.data["turn"] == e.data["message_id"] for e in renv.events.events if e.type == "chat.turn")


def test_org_chat_has_no_model_prose(renv):
    secret = SECRET_SENTENCE
    renv.connector.push(
        decide(why=secret, assignments=[draft(brief=secret, title="Cafe page")]),                                             # reuse
        decide(change="add", reuse=(), why=secret), change_reply(add_dept("$cafe", "Cafe", "Coffee"), reason=secret),
        assignments(draft("a1", "cafe", brief=secret)),                                                                       # add
        decide("chart_request", "rearrange", reuse=(), why=secret), change_reply({"op": "rename", "node": "menu", "name": "Menus", "purpose": None}, reason=secret),
        decide("status", "none", reuse=(), why=secret), decide("smalltalk", "none", reuse=(), why=secret),
        decide("clarify", "none", reuse=("web",), why=secret))
    for text in ("A page please", "Plan my coffee shop launch", "Rename Menu to Menus", "How are things?", "Thanks!", "Do the thing"):
        renv.say(text)
    said = [m for m in renv.messages() if m.who == "sutra"]
    assert len(said) >= 10
    for m in said:
        assert m.kind == "card" or planner.matches_template(m.text), m.text
        assert secret not in (m.text or "") and secret not in json.dumps(m.card.model_dump() if m.card else {})
    assert not any(secret in m.text for m in renv.messages())


# ============================================ the other outcomes =============================================================

def test_status_is_built_by_code_from_the_chart_and_tasks(renv):
    renv.connector.push(decide(), decide("status", "none", reuse=()))
    renv.say("A page please")
    renv.say("How are things?")
    last = renv.sutra()[-1]
    assert last[0] == "text" and last[1].splitlines()[0] == planner.STATUS_HEADER
    assert '- Web: ' in last[1] and '"Cafe page"' in last[1] and "- Sales: nothing yet." in last[1]
    assert len(renv.connector.calls) == 2


def test_smalltalk_gets_the_fixed_line(renv):
    renv.connector.push(decide("smalltalk", "none", reuse=()))
    renv.say("Thanks!")
    assert renv.sutra()[-1] == ("text", planner.LINES["smalltalk"])
    assert renv.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0


def test_clarify_posts_a_choice_card_and_a_pick_hands_the_request_over(renv):
    renv.connector.push(decide("clarify", "none", reuse=("quotes", "web"), why="two fit"))
    first = renv.say("Do the thing for me")
    [card] = renv.cards("choice")
    assert card.question == "Which team fits best?" and [(o.id, o.label) for o in card.options] == [
        ("quotes", "Quotes"), ("web", "Web"), ("sales", "Sales"), ("none", "None of these")]
    card_id = max(m.id for m in renv.messages() if m.kind == "card")
    second = renv.say("Quotes", choice=ChatChoice(message_id=card_id, option="quotes"))
    assert len(renv.connector.calls) == 1                                       # the pick needs no model
    assert any(m.role == "user" and m.text == "Quotes" for m in renv.messages()) and renv.user_state(second.message_id) == "ok"
    [task] = renv.tasks_of(f"req-{first.message_id}")
    assert (task["dept_id"], task["scope_node_id"], task["user_text"]) == ("sales", "quotes", "Do the thing for me")
    assert renv.sutra()[-2:] == [("text", "I gave this to the Sales team."), ("card", "task")]
    with pytest.raises(AlreadyDecided):                                            # the same button twice
        renv.say("Quotes", choice=ChatChoice(message_id=card_id, option="Quotes"))


def test_none_of_these_gets_the_smalltalk_line(renv):
    renv.connector.push(decide("clarify", "none", reuse=("web",), why="x"))
    renv.say("Do the thing")
    card_id = max(m.id for m in renv.messages() if m.kind == "card")
    renv.say("None of these", choice=ChatChoice(message_id=card_id, option="none"))
    assert renv.sutra()[-1] == ("text", planner.LINES["smalltalk"]) and renv.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0


def test_a_choice_that_names_no_button_or_no_card_is_refused(renv):
    renv.connector.push(decide("clarify", "none", reuse=("web",), why="x"))
    renv.say("Do the thing")
    card_id = max(m.id for m in renv.messages() if m.kind == "card")
    with pytest.raises(AppError, match="not one of the buttons"):
        renv.say("x", choice=ChatChoice(message_id=card_id, option="sales-ish"))
    with pytest.raises(AppError, match="no buttons"):
        renv.say("x", choice=ChatChoice(message_id=1, option="web"))
    with pytest.raises(AppError, match="no buttons"):
        renv.say("x", choice=ChatChoice(message_id=9999, option="web"))


def test_assignments_are_created_in_dependency_order_and_blocked_until_done(renv):
    renv.connector.push(decide(change="none", reuse=(), assignments=[
        draft("a1", "web", title="Page", depends_on=["a2"]), draft("a2", "sales", title="Quote")]))
    first = renv.say("Quote and page")
    rows = renv.tasks_of(f"req-{first.message_id}")
    assert [r["title"] for r in rows] == ["Quote", "Page"]
    assert json.loads(rows[1]["depends_on"]) == [rows[0]["id"]] and rows[1]["status"] == "blocked"
    assert [c.title for c in renv.cards("task")[-2:]] == ["Quote", "Page"]
    assert renv.sutra()[-3][1] == "I gave this to the Sales and Web team."


def test_a_follows_without_a_run_starts_fresh(renv):
    earlier = renv.new("web", "Earlier work")                                         # queued: no run folder yet
    renv.connector.push(decide(assignments=[draft("a1", "web", follows=earlier.id)]))
    first = renv.say("More of the same")
    [row] = renv.tasks_of(f"req-{first.message_id}")
    assert row["dept_id"] == "web" and row["parent_task_id"] is None


def test_move_merge_split_rename_have_their_lines(renv):
    renv.connector.push(
        decide("chart_request", "rearrange", reuse=()), change_reply({"op": "move", "node": "menu", "to_parent": "sales"}),
        decide("chart_request", "rearrange", reuse=()), change_reply({"op": "rename", "node": "menu", "name": "Menus", "purpose": None}),
        decide("chart_request", "rearrange", reuse=()), change_reply({"op": "rename", "node": "menu", "name": None, "purpose": "Dishes"}))
    renv.say("Move Menu to Sales")
    assert renv.sutra()[-2:] == [("text", "I moved Menu under Sales."), ("card", "chart_change")]
    card = renv.cards("chart_change")[-1]
    assert [(m.id, m.from_name, m.to_name) for m in card.moved] == [("menu", "Web", "Sales")]
    renv.say("Call it Menus")
    assert renv.sutra()[-2:] == [("text", "I renamed Menu to Menus."), ("card", "chart_change")]
    renv.say("Change its purpose")
    assert renv.sutra()[-2][1] == "I updated the purpose of Menus."
    assert renv.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0


def test_a_new_division_with_work_for_it(renv):
    renv.connector.push(decide(change="add", reuse=()), change_reply(add_div("$blog", "Blog", "web", "Posts")), assignments(draft("a1", "web", scope="blog")))
    first = renv.say("Start a blog")
    [task] = renv.tasks_of(f"req-{first.message_id}")
    assert task["scope_node_id"] == "blog"
    assert renv.sutra()[-3:] == [("text", "I set up a Blog team and gave it your request. I gave this to the Web team."),
                                 ("card", "chart_change"), ("card", "task")]


# ============================================ approvals =======================================================================

def merge_request(renv, text="Merge Leads into Quotes"):
    renv.connector.push(decide("chart_request", "rearrange", reuse=(), why=SECRET_SENTENCE), merge_reply("quotes", "leads"))
    return renv.say(text)


def test_a_merge_asks_first_and_changes_nothing(renv):
    before = renv.chart.head().sha256
    first = merge_request(renv)
    [card] = renv.cards("approval")
    assert card.question == "Merge Leads into Quotes? Their chats and history stay available." and [(o.id, o.label) for o in card.options] == [("yes", "Yes"), ("no", "No")]
    assert renv.chart.head().sha256 == before and renv.user_state(first.message_id) == "ok"
    [pending] = renv.chart.pending()
    assert pending.task_id == f"req-{first.message_id}"
    assert renv.chart.record(pending.id).plan["message_id"] == first.message_id
    assert renv.chats.needs_you()[0].kind == "approval"


def test_a_bare_yes_applies_it_with_no_model_call(renv):
    first = merge_request(renv)
    calls = len(renv.connector.calls)
    accepted = renv.say("Yes")
    assert len(renv.connector.calls) == calls and accepted.turn == "started" and renv.user_state(accepted.message_id) == "ok"
    assert renv.chart.pending() == [] and renv.chart.head().model.node("leads") is None
    assert renv.sutra()[-2:] == [("text", "I merged Leads into Quotes."), ("card", "chart_change")]
    card = renv.cards("chart_change")[-1]
    assert [(a.id, a.name, a.into_name) for a in card.archived] == [("leads", "Leads", "Quotes")]
    assert renv.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0 and first.message_id


@pytest.mark.parametrize("word", ["no", "Nope", "cancel", "leave it"])
def test_a_bare_no_leaves_the_chart(renv, word):
    merge_request(renv)
    before = renv.chart.head().sha256
    renv.say(word)
    assert renv.chart.head().sha256 == before and renv.sutra()[-1] == ("text", "Okay, I left the chart as it was.")
    assert renv.chart.pending() == []


def test_yes_is_only_an_answer_while_exactly_one_change_waits(renv):
    renv.connector.push(decide("smalltalk", "none", reuse=()))
    renv.say("yes")                                                                  # nothing waits: it goes to the model
    assert len(renv.connector.calls) == 1


def test_the_card_buttons_answer_too_and_a_second_click_is_refused(renv):
    merge_request(renv)
    card_id = max(m.id for m in renv.messages() if m.kind == "card")
    accepted = renv.say("Yes", choice=ChatChoice(message_id=card_id, option="yes"))
    assert any(m.role == "user" and m.text == "Yes" for m in renv.messages())
    assert renv.chart.head().model.node("leads") is None and renv.user_state(accepted.message_id) == "ok"
    with pytest.raises(AlreadyDecided) as info:
        renv.say("Yes", choice=ChatChoice(message_id=card_id, option="Yes"))
    assert info.value.result.status == "applied"


def test_a_merge_for_a_task_asks_stage_c_after_the_yes(renv):
    renv.connector.push(decide("new_task", "rearrange", reuse=(), why=SECRET_SENTENCE), merge_reply("quotes", "leads"))
    first = renv.say("Merge leads into quotes and write the price list")
    assert len(renv.connector.calls) == 2 and renv.cards("approval")
    renv.connector.push(assignments(draft("a1", "sales", title="Price list", scope="quotes")))
    renv.say("yes")
    assert [c.step for c in renv.connector.calls] == ["decide", "change", "assign"]
    assert renv.connector.calls[2].context["atom_id"] == overhead_atom_id(f"req-{first.message_id}")
    [task] = renv.tasks_of(f"req-{first.message_id}")
    assert (task["dept_id"], task["scope_node_id"], task["title"]) == ("sales", "quotes", "Price list")
    texts = [t for kind, t in renv.sutra() if kind == "text"]
    assert texts[-1] == "I merged Leads into Quotes. I gave this to the Sales team."
    assert renv.sutra()[-2:] == [("card", "chart_change"), ("card", "task")]


def test_the_route_decision_finishes_the_request_like_a_yes(renv):
    renv.connector.push(decide("new_task", "rearrange", reuse=()), merge_reply("quotes", "leads"), assignments(draft("a1", "sales", title="Price list")))
    first = renv.say("Merge leads into quotes and write the price list")
    [pending] = renv.chart.pending()
    result = renv.go(lambda: renv.runner.decide(pending.id, True))
    assert result.status == "applied" and renv.tasks_of(f"req-{first.message_id}")[0]["title"] == "Price list"
    with pytest.raises(AlreadyDecided):
        renv.go(lambda: renv.runner.decide(pending.id, True))


def test_yes_after_the_chart_moved_is_refused_with_the_reason(renv):
    merge_request(renv)
    renv.env.apply(add_dept_op("Zed"))
    renv.say("yes")
    assert renv.sutra()[-1] == ("text", "I did not change anything: The chart changed since you were asked, so nothing was changed.")
    assert renv.chart.head().model.node("leads") is not None and renv.chart.pending() == []


def add_dept_op(name):
    from factories_org import add_op
    return add_op("$z", "department", name, "root", f"{name} things")


def test_a_decision_nobody_planned_posts_nothing_in_the_org_chat(renv):
    from factories_org import make_change
    from sutra_app.library.gate import GATE
    change = GATE.check("chart_change", make_change(renv.chart.head().model, __import__("factories_org").merge_op("quotes", "leads"),
                                                    id=renv.chart.next_change_id(), task_id="req-90"))
    renv.chart.apply(change, actor="user", ctx=renv.env.ctx("By hand", message_id=90))
    before = len(renv.messages())
    [pending] = renv.chart.pending()
    renv.go(lambda: renv.runner.decide(pending.id, True))
    assert len(renv.messages()) == before and renv.chart.head().model.node("leads") is None


# ============================================ the queue ========================================================================

def test_requests_wait_in_order_and_the_seventh_is_refused(renv):
    async def scenario():
        gate = asyncio.Event()
        order = []

        async def slow(call):
            await gate.wait()
            order.append(call.prompt.split("OWNER REQUEST:\n")[1].split("\n")[0])
            return decide("smalltalk", "none", reuse=())
        renv.connector.push(*[slow] * 6)
        accepted = [await renv.runner.post_user_message(ORG, f"request {i}") for i in range(1, 7)]
        assert [a.turn for a in accepted] == ["started"] + ["queued"] * 5
        with pytest.raises(AppError) as info:
            await renv.runner.post_user_message(ORG, "request 7")
        assert (info.value.code, info.value.status) == ("too_many_pending", 429)
        assert renv.runner.busy
        gate.set()
        await renv.runner.wait_idle()
        assert order == [f"request {i}" for i in range(1, 7)]
        assert not renv.runner.busy
    renv.run(scenario())
    assert renv.sql("SELECT count(*) FROM chat_messages WHERE role='user'").fetchone()[0] == 6
    assert renv.sql("SELECT count(*) FROM chat_messages WHERE role='user' AND state='ok'").fetchone()[0] == 6


def test_phases_follow_the_turn(renv):
    seen = []

    def spy(call):
        seen.append(renv.chats.phase(ORG))
        return decide()
    renv.connector.push(spy)
    renv.say("A page please")
    assert seen == ["planning"] and renv.chats.phase(ORG) == "working"
    assert ("phase", renv.one("SELECT min(id) FROM chat_messages WHERE role='user'"), "planning") in renv.hooked
    assert renv.hooked[-1][0] == "done"


# ============================================ failures =========================================================================

def test_f1_unavailable_changes_nothing_and_retry_works(renv):
    from sutra_app.orchestrator.agent.ports import ConnectorFailure
    renv.connector.push(ConnectorFailure("unavailable", "no cli"))
    renv.connector.set_status({"stub": {"installed": True, "signed_in": True}})
    sha = renv.chart.head().sha256
    first = renv.say("A page please")
    assert renv.chart.head().sha256 == sha and renv.user_state(first.message_id) == "error"
    last = [m for m in renv.messages() if m.who == "sutra"][-1]
    assert last.kind == "error" and last.text == "I can't reach Claude or Codex right now (no cli). Nothing was changed."
    assert renv.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0 and renv.hooked[-1][0] == "error"
    assert [e.data["phase"] for e in renv.events.events if e.type == "chat.turn"][-1] == "error"
    renv.connector.push(decide())
    again = renv.go(lambda: renv.runner.retry(ORG))
    assert again.message_id == first.message_id and renv.user_state(first.message_id) == "ok"
    assert renv.tasks_of(f"req-{first.message_id}")


def test_f1_names_why_from_the_status(renv):
    from sutra_app.orchestrator.agent.ports import ConnectorFailure
    def down(call):
        renv.connector.set_status({"claude": {"installed": True, "signed_in": False}, "codex": {"installed": False}})
        raise ConnectorFailure("auth")
    renv.connector.push(down)
    renv.say("A page please")
    assert [m for m in renv.messages() if m.who == "sutra"][-1].text.startswith("I can't reach Claude or Codex right now (Claude is signed out; Codex is not installed).")


def test_the_preflight_refuses_before_storing_anything(renv):
    renv.connector.set_status({"claude": {"installed": False}, "codex": {"installed": False}})
    before = len(renv.messages())
    with pytest.raises(AppError) as info:
        renv.say("A page please")
    assert (info.value.code, info.value.status) == ("cli_missing", 503) and len(renv.messages()) == before
    renv.connector.set_status({"claude": {"installed": True, "signed_in": False}})
    with pytest.raises(AppError) as info:
        renv.say("A page please")
    assert info.value.code == "provider_unavailable"
    renv.connector.set_status({})
    with pytest.raises(AppError, match="no connector is set up"):
        renv.say("A page please")


def test_the_preflight_does_not_stop_an_answer_to_a_pending_change(renv):
    merge_request(renv)
    renv.connector.set_status({"claude": {"installed": False}})
    renv.say("no")
    assert renv.sutra()[-1] == ("text", "Okay, I left the chart as it was.")


def test_only_the_org_chat_and_real_text_are_accepted(renv):
    with pytest.raises(AppError, match="only the org chat"):
        renv.go(lambda: renv.runner.post_user_message("cs_000000000001", "hi"))
    with pytest.raises(AppError, match="write something"):
        renv.go(lambda: renv.runner.post_user_message(ORG, "   "))
    with pytest.raises(AppError, match="only the org chat"):
        renv.go(lambda: renv.runner.retry("cs_000000000001"))


def test_retry_needs_a_failed_request(renv):
    with pytest.raises(NotFound):
        renv.go(lambda: renv.runner.retry(ORG))
    renv.connector.push(decide("smalltalk", "none", reuse=()))
    renv.say("Thanks")
    with pytest.raises(NotFound):
        renv.go(lambda: renv.runner.retry(ORG))


def test_bad_replies_then_a_good_one_still_make_a_normal_line(renv):
    renv.connector.push({"x": 1}, {"y": 2}, decide())
    renv.say("A page please")
    assert renv.sutra()[-2:] == [("text", "I gave this to the Web team."), ("card", "task")] and len(renv.connector.calls) == 3


def test_three_bad_replies_use_the_keywords_and_say_so_in_the_log(renv):
    renv.connector.push({"x": 1}, {"y": 2}, {"z": 3})
    first = renv.say("Landing page for my websites")
    assert renv.sutra()[-2:] == [("text", "I gave this to the Web team."), ("card", "task")]
    change = renv.sql("SELECT reason FROM chart_changes ORDER BY seq DESC").fetchone()
    assert change["reason"].endswith("(planned by keywords)")


def test_no_clear_team_after_three_bad_replies_asks_the_owner(renv):
    renv.connector.push({"x": 1}, {"y": 2}, {"z": 3})
    renv.say("xyzzy")
    assert renv.sutra()[-2:] == [("text", planner.LINES["none"]), ("card", "choice")]
    assert [o.id for o in renv.cards("choice")[-1].options] == ["web", "sales", "none"]


def test_f4_a_chart_that_keeps_moving_asks_to_send_it_again(renv):
    def move(call):
        renv.env.apply(add_dept_op(f"Zed{renv.env.n}"))
        return decide(change="add", reuse=())

    def plan(call):
        return change_reply(add_dept("$cafe", "Cafe", "Coffee"))
    renv.connector.push(move, plan, move, plan)
    first = renv.say("Plan something")
    last = [m for m in renv.messages() if m.who == "sutra"][-1]
    assert (last.kind, last.text) == ("error", planner.LINES["stale"]) and renv.user_state(first.message_id) == "error"


def test_f5_a_failed_save_is_reported_and_nothing_changes(renv, monkeypatch):
    def broken(*args, **kw):
        raise ChangeFailed("chg-0099", "disk full")
    monkeypatch.setattr(renv.chart, "apply", broken)
    renv.connector.push(decide())
    first = renv.say("A page please")
    last = [m for m in renv.messages() if m.who == "sutra"][-1]
    assert (last.kind, last.text) == ("error", "I could not save that. Nothing was changed.") and renv.user_state(first.message_id) == "error"
    assert renv.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0


def test_a_busy_division_is_told_in_the_rules_words(renv):
    renv.new("sales", "Quotes work", scope_id="quotes")
    renv.connector.push(decide("chart_request", "rearrange", reuse=()), change_reply({"op": "move", "node": "quotes", "to_parent": "web"}))
    first = renv.say("Move quotes under web")
    assert renv.sutra()[-1] == ("text", "Quotes is busy with Quotes work") and renv.user_state(first.message_id) == "ok"


def test_an_unexpected_error_is_reported_and_the_queue_goes_on(renv):
    renv.connector.push(KeyError("bug"), decide("smalltalk", "none", reuse=()))
    first = renv.say("one")
    last = [m for m in renv.messages() if m.who == "sutra"][-1]
    assert (last.kind, last.text) == ("error", planner.LINES["failed"]) and renv.user_state(first.message_id) == "error"
    second = renv.say("two")
    assert renv.user_state(second.message_id) == "ok"


def test_a_team_that_cannot_be_given_the_work_is_reported(renv, monkeypatch):
    real = renv.service.create

    def refuse(*a, **kw):
        raise AppError("not_found", "that team was not found")
    monkeypatch.setattr(renv.service, "create", refuse)
    renv.connector.push(decide())
    first = renv.say("A page please")
    last = [m for m in renv.messages() if m.who == "sutra"][-1]
    assert (last.kind, last.text) == ("error", "I could not start that work: that team was not found") and renv.user_state(first.message_id) == "error"
    assert real


def test_the_connector_sees_no_secret_from_the_owner(db, settings, clock, events):
    secret = "sk-live-0123456789abcdef"
    env = renv_with(db, settings, clock, events, decide("smalltalk", "none", reuse=()))
    env.agent._redact = env.runner._redact = lambda text: text.replace(secret, "[redacted]")
    env.say(f"my key is {secret}")
    assert secret not in env.connector.calls[0].prompt and not any(secret in m.text for m in env.messages())
    assert any("[redacted]" in m.text for m in env.messages() if m.role == "user")


def test_close_stops_the_worker(renv):
    renv.connector.push(decide("smalltalk", "none", reuse=()))

    async def go():
        await renv.runner.post_user_message(ORG, "hi")
        await renv.runner.wait_idle()
        await renv.runner.close()
        assert renv.runner._worker is None and not renv.runner.busy
    renv.run(go())


def test_every_model_call_of_a_request_is_charged_to_its_overhead_key(renv):
    renv.connector.sink = renv.usage.record                                    # what the router's sink does in the server
    renv.connector.push(decide(change="add", reuse=()), change_reply(add_dept("$cafe", "Cafe", "Coffee")), assignments(draft("a1", "cafe")))
    first = renv.say("Plan my coffee shop launch")
    rows = renv.sql("SELECT * FROM usage_ledger ORDER BY id").fetchall()
    assert len(rows) == 3 and renv.runner.agent.connector.records_usage
    assert {r["atom_id"] for r in rows} == {overhead_atom_id(f"req-{first.message_id}")}
    assert {(r["node_id"], r["session_id"], r["purpose"], r["fn"]) for r in rows} == {("root", ORG, "chat_plan", "chat_agent")}
    assert renv.sql("SELECT count(*) FROM usage_ledger WHERE atom_id IS NULL").fetchone()[0] == 0


def test_the_next_request_sees_the_conversation_so_far(renv):
    renv.connector.push(decide(), decide("smalltalk", "none", reuse=()))
    renv.say("A page please")
    renv.say("Thanks")
    prompt = renv.connector.calls[1].prompt
    assert "Owner: A page please" in prompt and "Sutra: I gave this to the Web team." in prompt and "Owner: Thanks" not in prompt.split("CONVERSATION")[1].split("PENDING")[0]
    assert "OWNER REQUEST:\nThanks" in prompt


def test_a_pending_change_is_named_in_the_next_prompt(renv):
    merge_request(renv)
    renv.connector.push(decide("smalltalk", "none", reuse=()))
    renv.say("What was that about?")
    pending = renv.connector.calls[-1].prompt.split("PENDING:\n")[1].split("\nOWNER REQUEST")[0]
    assert pending.startswith("chg-") and "Merged Leads into Quotes" in pending and "waiting for the owner's yes or no" in pending


def two_pending(renv):
    from factories_org import make_change, merge_op

    from sutra_app.library.gate import GATE
    for n in (91, 92):
        change = GATE.check("chart_change", make_change(renv.chart.head().model, merge_op("quotes", "leads"), id=renv.chart.next_change_id(), task_id=f"req-{n}"))
        renv.chart.apply(change, actor="user", ctx=renv.env.ctx("By hand", message_id=n))
    assert len(renv.chart.pending()) == 2


def test_a_yes_is_not_an_answer_while_two_changes_wait(renv):
    two_pending(renv)
    renv.connector.push(decide("smalltalk", "none", reuse=()))
    renv.say("yes")                                                                  # which one? it goes to the model like any text
    assert len(renv.connector.calls) == 1 and len(renv.chart.pending()) == 2
    assert "waiting for the owner's yes or no" in renv.connector.calls[0].prompt


def test_a_yes_with_two_waiting_still_needs_a_connector(renv):
    two_pending(renv)
    renv.connector.set_status({})
    with pytest.raises(AppError) as info:
        renv.say("yes")
    assert info.value.code == "provider_unavailable"


def test_a_button_in_another_chat_is_not_a_button_of_the_org_chat(renv):
    from sutra_app.library.gate import GATE
    session = renv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")
    card = {"type": "choice", "question": "Which?", "options": [{"id": "web", "label": "Web"}]}
    with renv.db.tx() as tx:
        posted = renv.chats.post(tx, session, GATE.check("chat_message", dict(
            kind="card", session_id=session, role="agent", who="identity", card=card, src_ref="req:1:choice", at=tx.now()), ctx=tx.ctx))
    with pytest.raises(AppError, match="no buttons"):
        renv.say("Web", choice=ChatChoice(message_id=posted.id, option="web"))


def test_a_chart_that_moves_just_before_the_apply_is_planned_again(renv):
    moved = []

    def move_once(message_id, phase):
        if phase == "applying" and not moved:
            moved.append(renv.env.apply(add_dept_op("Zed")))

    renv.runner.hooks.on_phase = move_once
    renv.connector.push(decide(), decide())
    base = renv.one("SELECT max(seq) FROM chart_changes")
    first = renv.say("A page please")
    assert len(renv.connector.calls) == 2 and renv.user_state(first.message_id) == "ok"
    assert [r["status"] for r in renv.sql("SELECT status FROM chart_changes WHERE seq > ? AND kind = 'reuse' ORDER BY seq", base)] == ["stale", "applied"]
    assert len(renv.tasks_of(f"req-{first.message_id}")) == 1
