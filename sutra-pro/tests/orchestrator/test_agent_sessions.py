"""A chat session of its own for every agent, new for each run (D130): a function agent's session rolls at its first event of a run, a builder's step
session is stamped and titled, the owner's pick goes with the chat, invariants I1 and I8 hold and a replay changes nothing."""
from __future__ import annotations

import json

import pytest
from orchestrator.test_tasks import TEnv, ev, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.connectors.models import Pick
from sutra_app.library.types import FUNCTIONS
from sutra_app.orchestrator.chat_v2 import ChatArchive, ChatChoices
from sutra_app.orchestrator.errors import AppError


def go(t: TEnv, task_id: str, *events: dict):
    t.write_events(task_id, *events)
    return t.drain(task_id)


def active(t: TEnv, node_id: str) -> str:
    rows = t.sql("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", node_id).fetchall()
    assert len(rows) == 1, f"I1: {node_id} has {len(rows)} active sessions"
    assert t.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", node_id) == rows[0][0]               # and the node names it
    assert json.loads(t.one("SELECT body FROM graph_nodes WHERE id = ?", node_id))["chat_session_id"] == rows[0][0]
    return rows[0][0]


def session(t: TEnv, sid: str):
    return t.sql("SELECT status, run_id, title, pinned, pinned_model, pinned_effort FROM chat_sessions WHERE id = ?", sid).fetchone()


def lines(t: TEnv, sid: str) -> list[str]:
    return [m.text for m in t.chats.messages(sid)]


def usage(call_ref, fn="identity", step="J2.a", **over):
    base = dict(fn=fn, step=step, atom=None, provider="claude", model="sonnet", purpose="agent_turn", usd=0.01, tokens_in=100, tokens_out=20,
                seconds=2.0, ok=True, how="native", call_ref=call_ref)
    return ev("usage", **{**base, **over})


def second_run(t: TEnv) -> tuple[str, str]:
    """A first run in which Identity and Audit spoke, ended; then a second run of the same team. Returns (first task, second task)."""
    first = t.started(title="Cafe page")
    go(t, first, ev("say", id=1, who="identity", text="Reading the brief", next="adaptation"), ev("say", id=2, who="audit", text="Nothing wrong", next="identity"))
    t.projector.mark_ended(first, "done", "ok")
    second = t.new(text="Now the menu page", title="Menu page").id
    t.run(t.service.start_ready())
    go(t, second, ev("run.started", pid=t.row(second).pid, schema="events/1", mock=True, seed="none"))
    return first, second


def test_a_used_function_session_rolls_at_the_agents_first_event_of_the_next_run(tenv):  # noqa: F811
    first, second = second_run(tenv)
    run1, run2 = tenv.row(first).run_id, tenv.row(second).run_id
    old = active(tenv, "web.identity")
    assert session(tenv, old)["run_id"] == run1 and session(tenv, old)["title"] == "Identity · Cafe page"
    go(tenv, second, ev("node", fn="identity", status="running", detail="reading", calls=1, seconds=0.1))
    new = active(tenv, "web.identity")
    assert new != old and session(tenv, old)["status"] == "archived" and session(tenv, old)["run_id"] == run1       # the past run's chat stays readable
    assert lines(tenv, old) == ["Reading the brief"] and lines(tenv, new) == []
    assert (session(tenv, new)["status"], session(tenv, new)["run_id"], session(tenv, new)["title"]) == ("active", run2, "Identity · Menu page")
    assert tenv.one("SELECT writable FROM chat_sessions WHERE id = ?", new) == 0
    made = [e.data for e in tenv.env.events.events if e.type == "agent.session" and e.data["agent"] == "identity"]
    assert made[-1] == {"session_id": new, "node_id": "web.identity", "agent": "identity", "run_id": run2, "rolled_from": old}
    assert any(e.type == "chat.archived" and e.data["session_id"] == old for e in tenv.env.events.events)
    go(tenv, second, ev("say", id=1, who="identity", text="Planning the menu", next="adaptation"), usage(f"{run2}:1"))
    assert active(tenv, "web.identity") == new and lines(tenv, new) == ["Planning the menu"]                      # once per run: the second event does not roll again
    assert tenv.one("SELECT session_id FROM usage_ledger WHERE call_ref = ?", f"{run2}:1") == new                 # the usage row is charged to this run's session
    audit_old = [r[0] for r in tenv.sql("SELECT id FROM chat_sessions WHERE node_id = 'web.audit' AND run_id = ?", run1)]
    assert len(audit_old) == 1                                                                                      # an agent that has not spoken yet keeps its session, for now


def test_an_unused_session_is_only_stamped_so_nothing_churns(tenv):  # noqa: F811
    task = tenv.started(title="Cafe page")
    before = tenv.one("SELECT count(*) FROM chat_sessions")
    sid = active(tenv, "web.priority")
    assert session(tenv, sid)["run_id"] is None
    go(tenv, task, ev("node", fn="priority", status="running", detail="pricing", calls=1, seconds=0.1))
    assert active(tenv, "web.priority") == sid and session(tenv, sid)["run_id"] == tenv.row(task).run_id and session(tenv, sid)["title"] == "Priority · Cafe page"
    assert tenv.one("SELECT count(*) FROM chat_sessions") == before


def test_the_owners_pick_goes_with_the_chat_when_it_rolls_and_choices_json_names_the_new_run_the_same_way(tenv):  # noqa: F811
    first = tenv.started()
    go(tenv, first, ev("say", id=1, who="audit", text="Checked", next="identity"))
    old = active(tenv, "web.audit")
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set_pick(tx, old, "claude", "haiku", "low")
    tenv.projector.mark_ended(first, "done", "ok")
    second = tenv.new(text="again")
    tenv.run(tenv.service.start_ready())
    go(tenv, second.id, ev("say", id=1, who="audit", text="Checking again", next="identity"))
    new = active(tenv, "web.audit")
    assert new != old and ChatChoices(tenv.db).pick(new) == Pick(provider="claude", model="haiku", effort="low") and session(tenv, old)["pinned_model"] == "haiku"
    assert json.loads((tenv.run_dir(second.id) / "choices.json").read_text())["agents"]["audit"]["model"] == "haiku"          # from the carried pick at start


def test_a_builders_step_session_is_stamped_with_the_run_and_titled_by_the_workflow(tenv):  # noqa: F811
    task = tenv.started()
    run = tenv.row(task).run_id
    go(tenv, task, ev("step", step="W-5", name="Footer", status="idle", reads=["W-9"]), ev("step", step="team:Product Analyst", name="Product Analyst", status="running"))
    node = lambda ref: tenv.one("SELECT id FROM graph_nodes WHERE task_id = ? AND step_ref = ?", task, ref)         # noqa: E731
    w5, w9, role, whole = (active(tenv, node(r)) for r in ("W-5", "W-9", "team:Product Analyst", "task"))
    assert (session(tenv, w5)["run_id"], session(tenv, w5)["title"]) == (run, "W-5 · Footer")
    assert session(tenv, w9)["title"] == "W-9" and session(tenv, role)["title"] == "team:Product Analyst · Product Analyst"          # a step made by a reference only is titled by its ref
    go(tenv, task, ev("step", step="W-9", name="Contact form", status="running"))
    assert active(tenv, node("W-9")) == w9 and session(tenv, w9)["title"] == "W-9 · Contact form"                       # its name arrives with its own step event
    assert session(tenv, whole)["run_id"] == run
    go(tenv, task, ev("say", id=1, who="W-5", text="Footer done"))
    assert lines(tenv, w5) == ["Footer done"] and active(tenv, node("W-5")) == w5                                       # a builder never rolls: its node belongs to this run
    ever = [e.data for e in tenv.env.events.events if e.type == "agent.session"]
    assert {"session_id": w5, "node_id": node("W-5"), "agent": "W-5", "run_id": run} in ever and not any(d["agent"] == "task" for d in ever)


def test_a_replay_after_a_roll_adds_nothing(tenv):  # noqa: F811
    first, second = second_run(tenv)
    go(tenv, second, ev("say", id=1, who="identity", text="Planning the menu", next="adaptation"))
    new = active(tenv, "web.identity")
    sessions = tenv.one("SELECT count(*) FROM chat_sessions")
                                                                                              # the file is read again from the top
    with tenv.db.tx() as tx:
        tx.conn.execute("UPDATE tasks SET events_offset = 0 WHERE id = ?", (second,))
    tenv.drain(second)
    assert active(tenv, "web.identity") == new and lines(tenv, new) == ["Planning the menu"] and tenv.one("SELECT count(*) FROM chat_sessions") == sessions


def test_every_active_agent_session_of_a_live_run_carries_its_run_after_the_agents_first_event(tenv):  # noqa: F811
    first, second = second_run(tenv)
    run = tenv.row(second).run_id
    go(tenv, second, *[ev("node", fn=fn, status="running", detail="x", calls=1, seconds=0.1) for fn in FUNCTIONS],
       ev("step", step="W-1", name="Menu", status="running"), ev("say", id=1, who="W-1", text="working"))
    for fn in FUNCTIONS:
        sid = active(tenv, f"web.{fn}")                                                                                # I1 per node
        assert session(tenv, sid)["run_id"] == run, f"I8: {fn}"
    for (node_id,) in tenv.sql("SELECT id FROM graph_nodes WHERE task_id = ? AND kind = 'step'", second).fetchall():
        assert session(tenv, active(tenv, node_id))["run_id"] == run
    assert tenv.one("SELECT count(*) FROM chat_sessions WHERE node_id LIKE 'web.%' AND status = 'active'") == len(FUNCTIONS)


def test_an_agent_chat_of_a_past_run_stays_in_the_archive(tenv):  # noqa: F811
    first, second = second_run(tenv)
    go(tenv, second, ev("node", fn="identity", status="running", detail="x", calls=1, seconds=0.1))
    old = tenv.one("SELECT id FROM chat_sessions WHERE node_id = 'web.identity' AND status = 'archived'")
    with tenv.db.tx() as tx, pytest.raises(AppError) as caught:
        ChatArchive(tenv.db, tenv.graph).unarchive(tx, old)
    assert caught.value.code == "rules" and active(tenv, "web.identity") != old


# ---- the list of a team's agents and per-session usage ----------------------------------------------------------------------------------

def agents_api(t: TEnv):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sutra_app.orchestrator.api import agent_chats, usage as usage_api
    from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
    from sutra_app.orchestrator.redact import Redactor
    from sutra_app.orchestrator.services import Services
    app = FastAPI()
    services = Services(settings=t.settings, version="t", db=t.db, redact=Redactor(None, environ={}))
    services.tasks, services.usage = t.service, t.usage
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    for module in (agent_chats, usage_api):
        app.include_router(module.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


def test_the_list_of_a_teams_agents_per_run_with_usage_pick_and_state(tenv):  # noqa: F811
    first, second = second_run(tenv)
    run1, run2 = tenv.row(first).run_id, tenv.row(second).run_id
    go(tenv, second, ev("node", fn="identity", status="running", detail="x", calls=1, seconds=0.1), ev("step", step="W-1", name="Menu", status="running"),
       usage(f"{run2}:1"), usage(f"{run2}:2", fn="W-1", step="W-1", atom="W-1.a1"))
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set_pick(tx, active(tenv, "web.identity"), "claude", "haiku", "low")
        tenv.store.set_pick(tx, second, Pick(provider="claude", model="opus"))
    client = agents_api(tenv)
    now = client.get("/api/teams/web/agents").json()                                  # the live run by default
    assert [r["agent"] for r in now] == ["identity", "adaptation", "priority", "coordination", "audit", "W-1"]
    identity, w1 = now[0], now[-1]
    assert (identity["kind"], identity["label"], identity["run_id"], identity["live"], identity["status"]) == ("function", "Identity", run2, True, "active")
    assert identity["own"] == {"provider": "claude", "model": "haiku", "effort": "low"} and identity["effective"]["source"] == "own"
    assert identity["usage"]["calls"] == 1 and identity["usage"]["tokens_in"] == 100
    assert (w1["kind"], w1["label"], w1["title"], w1["live"], w1["run_id"]) == ("step", "Menu", "W-1 · Menu", True, run2)
    assert w1["own"] is None and w1["effective"] == {"provider": "claude", "model": "opus", "effort": None, "source": "run"}      # no own pick: the run's applies whole
    assert w1["run_pick"] == {"provider": "claude", "model": "opus", "effort": None} and w1["task_id"] == second
    past = client.get("/api/teams/web/agents", params={"run": run1}).json()           # the first run: the function sessions it rolled, read only
    assert [r["agent"] for r in past] == ["identity", "audit"] and all(r["run_id"] == run1 and not r["live"] for r in past)
    assert [r["status"] for r in past] == ["archived", "active"]                       # Audit has not spoken in the second run: its session is still the first run's
    assert [r["usage"]["calls"] for r in past] == [0, 0]
    assert client.get("/api/teams/web/agents", params={"run": "j2-20200101-000000-aaaa"}).status_code == 404 and client.get("/api/teams/nowhere/agents").status_code == 404
    other = client.get("/api/teams/sales/agents").json()                              # a team that never ran: its five function sessions, no run
    assert [r["agent"] for r in other] == list(FUNCTIONS) and all(r["run_id"] is None and not r["live"] for r in other)


def test_an_agents_usage_names_its_calls_by_purpose_and_they_add_up_to_its_totals(tenv):  # noqa: F811
    """D159: `usage.by_purpose` is `{purpose: {calls, usd}}` for each purpose the agent's session was charged for, on a function's row and on a builder's; the purposes add up to
    the totals the row always had, a stub call is in neither, and an agent that has not called has an empty mapping (every row has the key)."""
    from sutra_app.connectors.usage import UsageIn
    task = tenv.started()
    run = tenv.row(task).run_id
    go(tenv, task, ev("node", fn="priority", status="running", detail="x", calls=1, seconds=0.1), ev("step", step="W-1", name="Menu", status="running"),
       usage(f"{run}:1", fn="priority", step="J2.c"), usage(f"{run}:2", fn="priority", step="J2.c"),                         # two turns of Priority
       usage(f"{run}:3", fn="priority", step="J2.c", purpose="judge", usd=0.02),                                             # the late judge scores what it registered
       usage(f"{run}:4", fn="priority", step="J2.c", purpose="plan", provider="codex", usd=None, tokens_in=5, tokens_out=1),   # Codex: tokens, no dollars
       usage(f"{run}:5", fn="priority", step="J2.c", purpose="summary", provider="stub", usd=None),                          # a stub call counts nowhere
       usage(f"{run}:6", fn="adaptation", step="J2.b", usd=0.03),
       usage(f"{run}:7", fn="W-1", step="W-1", atom="W-1.a1"))
    priority_sid = active(tenv, "web.priority")
    tenv.usage.record(UsageIn(provider="claude", model="sonnet", purpose="agent_chat", usd=0.0625, tokens_in=300, tokens_out=60, how="native", fn="priority", task_id=task,
                              session_id=priority_sid, call_ref="r:question-1"))                                             # a function's answer to a question asked in its chat (D147)
    rows = {r["agent"]: r for r in agents_api(tenv).get("/api/teams/web/agents").json()}
    priority = rows["priority"]["usage"]
    assert priority["by_purpose"] == {"agent_chat": {"calls": 1, "usd": 0.0625}, "agent_turn": {"calls": 2, "usd": 0.02}, "judge": {"calls": 1, "usd": 0.02},
                                      "plan": {"calls": 1, "usd": None}}
    assert {k: priority[k] for k in ("calls", "usd", "tokens_in", "tokens_out")} == {"calls": 5, "usd": 0.1025, "tokens_in": 605, "tokens_out": 121}      # the totals a row always had
    assert set(priority) == {"calls", "usd", "tokens_in", "tokens_out", "by_purpose"}
    assert sum(c["calls"] for c in priority["by_purpose"].values()) == priority["calls"]
    assert round(sum(c["usd"] or 0 for c in priority["by_purpose"].values()), 6) == priority["usd"]
    assert rows["adaptation"]["usage"]["by_purpose"] == {"agent_turn": {"calls": 1, "usd": 0.03}}
    assert rows["W-1"]["usage"]["by_purpose"] == {"agent_turn": {"calls": 1, "usd": 0.01}} and rows["W-1"]["usage"]["calls"] == 1      # a builder's row is the same shape
    assert rows["audit"]["usage"] == {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None, "by_purpose": {}}
    assert all(set(r["usage"]) == {"calls", "usd", "tokens_in", "tokens_out", "by_purpose"} for r in rows.values())
    assert [(g["key"], g["calls"]) for g in agents_api(tenv).get("/api/usage/summary", params={"by": "purpose", "session_id": priority_sid}).json()["groups"]] == [
        ("agent_chat", 1), ("agent_turn", 2), ("judge", 1), ("plan", 1)]                                                       # the summary route reads the same rows


def test_a_codex_only_purpose_has_calls_and_no_dollars_and_a_row_with_none_has_no_dollars_at_all(tenv):  # noqa: F811
    task = tenv.started()
    run = tenv.row(task).run_id
    go(tenv, task, ev("node", fn="audit", status="running", detail="x", calls=1, seconds=0.1),
       usage(f"{run}:1", fn="audit", step="J2.g", provider="codex", usd=None, tokens_in=40, tokens_out=8),
       usage(f"{run}:2", fn="audit", step="J2.g", provider="codex", usd=None, tokens_in=10, tokens_out=2, purpose="judge"))
    audit = {r["agent"]: r for r in agents_api(tenv).get("/api/teams/web/agents").json()}["audit"]["usage"]
    assert audit == {"calls": 2, "usd": None, "tokens_in": 50, "tokens_out": 10,
                     "by_purpose": {"agent_turn": {"calls": 1, "usd": None}, "judge": {"calls": 1, "usd": None}}}


def test_usage_by_session_and_the_session_filter(tenv):  # noqa: F811
    task = tenv.started()
    run = tenv.row(task).run_id
    go(tenv, task, ev("node", fn="identity", status="running", detail="x", calls=1, seconds=0.1), usage(f"{run}:1"), usage(f"{run}:2", tokens_in=50),
       usage(f"{run}:3", fn="audit", step="J2.g"))
    client = agents_api(tenv)
    identity, audit = active(tenv, "web.identity"), active(tenv, "web.audit")
    groups = {g["key"]: g for g in client.get("/api/usage/summary", params={"by": "session"}).json()["groups"]}
    assert groups[identity]["calls"] == 2 and groups[identity]["tokens_in"] == 150 and groups[audit]["calls"] == 1
    one = client.get("/api/usage/summary", params={"by": "session", "session_id": identity}).json()["groups"]
    assert [(g["key"], g["calls"]) for g in one] == [(identity, 2)]
    rows = client.get("/api/usage", params={"session_id": audit}).json()
    assert len(rows["rows"]) == 1 and rows["rows"][0]["session_id"] == audit and rows["totals"]["calls"] == 1
