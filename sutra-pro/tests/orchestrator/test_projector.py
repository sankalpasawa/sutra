"""The Projector, the RunWatcher and reconcile (ORCH-6): every event of the run protocol becomes the rows of orchestrator 5.6, a replay
changes nothing, a dead process is a crash, a silent one is only flagged, and the start-up pass settles what the last run left."""
import json
from pathlib import Path

import pytest
from orchestrator.test_tasks import TEnv, dept_messages, ev, tenv, tenv_with  # noqa: F401  (tenv is a fixture)

from sutra_app.library.types import FUNCTIONS
from sutra_app.orchestrator.runs import ReconcileReport, reconcile
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher

START = ev("run.started", schema="events/1", mock=True, seed="none")


def go(t: TEnv, task_id: str, *events: dict):
    t.write_events(task_id, *events)
    return t.drain(task_id)


def session_texts(t: TEnv, node_id: str) -> list[tuple[str, str, str]]:
    return [(m.who, m.kind, m.text) for m in t.chats.messages(t.graph.get(node_id).chat_session_id)]


def edge_rows(t: TEnv, kind: str):
    return [(r["from_id"], r["to_id"], r["label"]) for r in t.sql("SELECT * FROM graph_edges WHERE kind = ? ORDER BY id", kind)]


def step_id(t: TEnv, task_id: str, ref: str) -> str:
    return t.one("SELECT id FROM graph_nodes WHERE task_id = ? AND step_ref = ?", task_id, ref)


# ---- run.started, heartbeat, offsets --------------------------------------------------------------------------------------------------

def test_run_started_makes_the_task_running_and_stores_the_pid(tenv):
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    pid = tenv.row(task.id).pid
    result = go(tenv, task.id, {**START, "pid": 777})
    row = tenv.row(task.id)
    assert (row.status, row.pid, result.applied) == ("running", 777, 1)
    assert tenv.graph.get(step_id(tenv, task.id, "task")).state == "running" and tenv.graph.get("web").state == "running"
    assert pid != 777 and "task.updated" in [e.type for e in tenv.env.events.events]


def test_heartbeat_sets_last_event_at_from_the_event_time(tenv):
    task = tenv.started()
    go(tenv, task, ev("heartbeat", at="2026-11-04T10:30:15Z"))
    assert tenv.row(task).last_event_at == 1793788215                           # event time, not the time of reading


def test_the_offset_commits_with_the_events_and_a_partial_last_line_waits(tenv):
    task = tenv.started()
    base = tenv.row(task).events_offset
    path = tenv.run_dir(task) / "events.jsonl"
    line = json.dumps({"t": "heartbeat", "at": "2026-11-04T10:00:07Z"}) + "\n"
    with open(path, "ab") as f:
        f.write(line.encode() + b'{"t":"heartbeat","at":"2026-11-04T1')       # one whole line and half of the next
    first = tenv.drain(task)
    assert first.applied == 1 and tenv.row(task).events_offset == base + len(line)
    with open(path, "ab") as f:
        f.write(b'0:00:09Z"}\n')
    second = tenv.drain(task)
    assert second.applied == 1 and tenv.row(task).last_event_at == 1793786409
    assert tenv.drain(task).applied == 0


def test_an_offset_resume_after_a_restart_applies_each_line_once(tenv):
    task = tenv.started()
    go(tenv, task, ev("say", id=1, who="adaptation", text="I propose three workflows", next="priority"))
    restarted = TEnv(tenv.env, tenv.settings, tenv.clock, launcher=tenv.launcher)               # a new Projector over the same database
    assert restarted.projector.drain(task).applied == 0
    assert [m for m in session_texts(tenv, "web.adaptation") if m[0] == "adaptation"] == [("adaptation", "text", "I propose three workflows")]


def test_a_file_shorter_than_the_offset_is_replayed_and_changes_nothing(tenv):
    task = tenv.started()
    go(tenv, task, ev("say", id=1, who="identity", text="Welcome", to_user=True, next="user"),
       ev("node", fn="priority", status="running", detail="pricing", calls=2, seconds=1.5, tokens={"input": 10, "output": 5}),
       ev("usage", fn="priority", step="J2.c", atom=None, provider="stub", model="m", purpose="agent_turn", usd=0.0, tokens_in=10,
          tokens_out=5, seconds=1.0, ok=True, how="stub", call_ref="r:1"))
    snapshot = lambda: (tenv.one("SELECT count(*) FROM chat_messages"), tenv.one("SELECT count(*) FROM usage_ledger"), tenv.graph.get("web.priority").version)
    before = snapshot()
    tenv.sql("UPDATE tasks SET events_offset = 999999 WHERE id = ?", task)
    tenv.projector.drain(task)                                                  # offset beyond the end: start again from 0
    assert snapshot() == before
    assert tenv.row(task).events_offset == (tenv.run_dir(task) / "events.jsonl").stat().st_size


def test_duplicate_lines_are_idempotent(tenv):
    task = tenv.started()
    line = ev("say", id=3, who="audit", text="Found nothing wrong", next="identity")
    usage = ev("usage", fn="audit", step="J2.g", atom=None, provider="stub", model="m", purpose="agent_turn", usd=0.0, tokens_in=1, tokens_out=1,
               seconds=0.1, ok=True, how="stub", call_ref="r:9")
    go(tenv, task, line, usage, line, usage)
    assert len([m for m in session_texts(tenv, "web.audit") if m[0] == "audit"]) == 1
    assert tenv.one("SELECT count(*) FROM usage_ledger WHERE call_ref = 'r:9'") == 1
    assert edge_rows(tenv, "speaks_to") == [("web.audit", "web.identity", "1")]


def test_unknown_types_bad_lines_and_unknown_fields_are_skipped_with_a_note(tenv):
    task = tenv.started()
    path = tenv.run_dir(task) / "events.jsonl"
    with open(path, "ab") as f:
        f.write(b'{"t":"session","at":"2026-11-04T10:00:00Z"}\nnot json at all\n')
        f.write(json.dumps(ev("heartbeat", at="2026-11-04T10:00:00Z", future_field=1)).encode() + b"\n")
        f.write(json.dumps(ev("say", at="2026-11-04T10:00:00Z", id=1, who="audit", text="still applied", next="identity")).encode() + b"\n")
    result = tenv.drain(task)
    assert (result.applied, result.skipped) == (2, 2)
    notes = [t for (_, kind, t) in session_texts(tenv, "web.identity") if kind == "note"]
    assert any("unknown_type" in n for n in notes) and any("not_json" in n for n in notes) and any("future_field" in n for n in notes)
    assert ("audit", "text", "still applied") in session_texts(tenv, "web.audit")
    tenv.sql("UPDATE tasks SET events_offset = 0 WHERE id = ?", task)
    tenv.drain(task)
    assert len([t for (_, kind, t) in session_texts(tenv, "web.identity") if kind == "note"]) == len(notes)        # noted once


def test_a_batch_with_a_bad_event_in_the_middle_still_applies_the_rest(tenv):
    task = tenv.started()
    result = go(tenv, task, ev("say", id=1, who="audit", text="before", next="identity"),
                ev("node", fn="adaptation", status="running", detail="ok"),
                ev("say", id=2, who="audit", text="", next="identity"),
                ev("say", id=3, who="audit", text="after", next="identity"))
    assert (result.applied, result.skipped) == (3, 1)
    texts = [t for (who, kind, t) in session_texts(tenv, "web.audit") if who == "audit"]
    assert texts == ["before", "after"]
    assert any("Skipped a say event" in t for (_, kind, t) in session_texts(tenv, "web.identity") if kind == "note")


# ---- say ---------------------------------------------------------------------------------------------------------------------------

def test_say_routes_each_voice_to_its_session(tenv):
    task = tenv.started()
    go(tenv, task,
       ev("say", id=1, who="identity", text="Hello owner", to_user=True, next="user"),
       ev("say", id=2, who="identity", text="Hand-off to the team", next="adaptation"),
       ev("say", id=3, who="adaptation", text="Proposal", next="priority"),
       ev("say", id=4, who="validator", text="Stamp: 2 problems", next="coordination"),
       ev("say", id=5, who="validator", text="No next"),
       ev("say", id=6, who="system", text="Charter accepted"),
       ev("say", id=7, who="W-2", text="Builder line"))
    assert ("identity", "text", "Hello owner") in session_texts(tenv, "web")
    assert ("identity", "text", "Hand-off to the team") in session_texts(tenv, "web.identity") and ("identity", "text", "Hello owner") not in session_texts(tenv, "web.identity")
    assert ("adaptation", "text", "Proposal") in session_texts(tenv, "web.adaptation")
    assert ("validator", "text", "Stamp: 2 problems") in session_texts(tenv, "web.coordination")
    assert ("validator", "text", "No next") in session_texts(tenv, "web.identity")
    assert ("system", "text", "Charter accepted") in session_texts(tenv, "web.identity")
    assert ("W-2", "text", "Builder line") in session_texts(tenv, step_id(tenv, task, "W-2"))
    assert all(m.role != "user" for m in dept_messages(tenv))                       # the owner's own lines are never in events.jsonl


def test_a_question_makes_the_team_wait_and_posts_the_needs_you_card(tenv):
    task = tenv.started()
    result = go(tenv, task, ev("say", id=1, who="identity", text="Name?\nOption 1: Sweet Bean\nOption 2: Other", to_user=True, act="ASK_REQUESTER", pause="info", next="user"))
    assert result.freed_slot
    assert tenv.status(task) == "waiting_user"
    identity = tenv.graph.get("web.identity")
    assert (identity.state, identity.wait_on) == ("waiting_on_you", "you")
    assert tenv.graph.get("web").state == "waiting_on_you" and tenv.graph.get("root").state == "waiting_on_you"
    question = dept_messages(tenv)[-1]
    assert (question.kind, question.pause) == ("question", "info")
    card = [m for m in tenv.chats.messages("cs_org") if m.card is not None][-1].card
    assert (card.type, card.dept_id, card.dept_name, card.question_message_id) == ("needs_you", "web", "Web", question.id)
    assert card.options == ["Sweet Bean", "Other"]
    assert [n.message_id for n in tenv.chats.needs_you()] == [question.id]
    assert "needs_you.changed" in [e.type for e in tenv.env.events.events]


def test_a_say_between_functions_counts_on_a_speaks_to_edge(tenv):
    task = tenv.started()
    go(tenv, task, ev("say", id=1, who="adaptation", text="one", next="priority"), ev("say", id=2, who="adaptation", text="two", next="priority"),
       ev("say", id=3, who="priority", text="back", next="adaptation"), ev("say", id=4, who="validator", text="v", next="priority"),
       ev("say", id=5, who="identity", text="to owner", to_user=True, next="user"))
    edges = {(a, b): label for a, b, label in edge_rows(tenv, "speaks_to")}
    assert edges == {("web.adaptation", "web.priority"): "2", ("web.priority", "web.adaptation"): "1"}
    stored = json.loads(tenv.one("SELECT body FROM graph_edges WHERE id = 'speaks_to:web.adaptation>web.priority'"))
    assert (stored["n"], stored["source"]["file"], stored["source"]["field"]) == (2, "chat.jsonl", "next")


# ---- node and step -----------------------------------------------------------------------------------------------------------------

def test_a_node_event_fills_state_wait_on_and_stats_and_never_goal_task_or_context(tenv):
    task = tenv.started()
    before = tenv.graph.get("web.priority")
    go(tenv, task, ev("node", fn="priority", status="waiting", detail="waiting for Adaptation", calls=4, seconds=12.5, wait_on="adaptation",
                      tokens={"input": 1200, "output": 340}, task={"id": "t-3", "kind": "x", "summary": "s", "state": "running", "set_by": "y"},
                      context=["chat: 3 messages"]))
    after = tenv.graph.get("web.priority")
    assert (after.state, after.detail, after.wait_on) == ("waiting", "waiting for Adaptation", "adaptation")
    assert (after.stats.calls, after.stats.seconds, after.stats.tokens.input, after.stats.tokens.output) == (4, 12.5, 1200, 340)
    assert (after.goal, after.task, after.context) == (before.goal, before.task, before.context)
    meta = tenv.graph.node("web.priority").node.meta
    assert set(meta) == {"goal", "task", "context", "constraints", "wait_on", "hands_to", "stats"} and meta["stats"]["tokens_in"] == 1200
    wire = [n for n in tenv.graph.view(level="full").nodes if n.id == "web.priority"][0]
    assert set(wire.meta) == {"stats", "wait_on"}


def test_a_waiting_node_always_has_wait_on_and_other_states_clear_it(tenv):
    task = tenv.started()
    go(tenv, task, ev("node", fn="audit", status="waiting_on_you", detail="needs the owner"))
    assert tenv.graph.get("web.audit").wait_on == "you"
    go(tenv, task, ev("node", fn="audit", status="waiting", detail="no target named"))
    assert tenv.graph.get("web.audit").wait_on == "identity"                     # the fallback when the event names nobody
    go(tenv, task, ev("node", fn="audit", status="running", detail="reviewing"))
    assert tenv.graph.get("web.audit").wait_on is None
    go(tenv, task, ev("node", fn="audit", status="waiting", detail="w", wait_on="W-4"))
    assert tenv.graph.get("web.audit").wait_on == "W-4"


def test_node_tokens_are_kept_when_a_later_event_has_none(tenv):
    task = tenv.started()
    go(tenv, task, ev("node", fn="audit", status="running", detail="a", calls=1, seconds=1.0, tokens={"input": 7, "output": 3}))
    go(tenv, task, ev("node", fn="audit", status="idle", detail="b", calls=2, seconds=2.0))
    stats = tenv.graph.get("web.audit").stats
    assert (stats.calls, stats.tokens.input, stats.tokens.output) == (2, 7, 3)


def test_a_node_event_for_a_step_makes_the_step_node(tenv):
    task = tenv.started()
    go(tenv, task, ev("node", step="W-1", status="running", detail="writing the menu page"))
    node = tenv.graph.get(step_id(tenv, task, "W-1"))
    assert (node.kind, node.state, node.detail, node.label, node.parent_id, node.step_ref) == ("step", "running", "writing the menu page", "W-1", step_id(tenv, task, "task"), "W-1")
    assert tenv.one("SELECT count(*) FROM chat_sessions WHERE node_id = ? AND status = 'active'", node.id) == 1
    assert tenv.one("SELECT version FROM graph_nodes WHERE id = ?", node.id) == 1
    go(tenv, task, ev("node", step="W-1", status="filed", detail="done"))
    assert tenv.graph.get(node.id).state == "filed" and tenv.one("SELECT version FROM graph_nodes WHERE id = ?", node.id) == 2


def test_a_step_event_names_the_node_and_draws_one_depends_on_edge_per_pair(tenv):
    task = tenv.started()
    go(tenv, task,
       ev("step", step="W-1", name="Brand guide", status="filed", handoff=["W-2", "W-3"], reads=[]),
       ev("step", step="W-2", name="Menu page", parent="W-1", status="running", handoff=[], reads=["W-1"]),
       ev("step", step="W-3", name="Home page", status="idle", handoff=[], reads=["W-1", "W-2"], rework="W-2"),
       ev("step", step="team:Product Analyst", name="Product Analyst", status="running"))
    w = {ref: step_id(tenv, task, ref) for ref in ("W-1", "W-2", "W-3")}
    assert (tenv.graph.get(w["W-1"]).label, tenv.graph.get(w["W-1"]).state) == ("Brand guide", "filed")
    assert tenv.graph.get(w["W-2"]).parent_id == w["W-1"] and tenv.graph.get(w["W-3"]).parent_id == step_id(tenv, task, "task")
    assert edge_rows(tenv, "depends_on") == sorted([(w["W-2"], w["W-1"], "reads"), (w["W-3"], w["W-1"], "reads"), (w["W-3"], w["W-2"], "revises")],
                                                   key=lambda e: f"depends_on:{e[0]}>{e[1]}")
    assert edge_rows(tenv, "handoff") == [] and tenv.one("SELECT count(*) FROM graph_edges WHERE kind = 'step'") == 0
    source = json.loads(tenv.one("SELECT body FROM graph_edges WHERE id = ?", f"depends_on:{w['W-2']}>{w['W-1']}"))["source"]
    assert (source["file"], source["workflow"], source["field"], source["value"]) == ("workflows.json", "W-2", "reads", "W-1")
    assert tenv.graph.get(step_id(tenv, task, "team:Product Analyst")).label == "Product Analyst"


def test_a_step_that_reads_a_later_step_creates_a_placeholder_for_it(tenv):
    task = tenv.started()
    go(tenv, task, ev("step", step="W-5", name="Footer", status="idle", reads=["W-9"]))
    assert tenv.graph.get(step_id(tenv, task, "W-9")).label == "W-9"
    go(tenv, task, ev("step", step="W-9", name="Contact form", status="running"))
    assert tenv.graph.get(step_id(tenv, task, "W-9")).label == "Contact form"
    assert len(edge_rows(tenv, "depends_on")) == 1


# ---- usage -------------------------------------------------------------------------------------------------------------------------

def usage(call_ref: str, fn: str = "priority", step: str | None = "J2.c", atom: str | None = None, **over) -> dict:
    base = dict(fn=fn, step=step, atom=atom, provider="claude", model="sonnet", purpose="agent_turn", usd=0.01, tokens_in=100, tokens_out=20,
                seconds=2.0, ok=True, how="native", call_ref=call_ref)
    return ev("usage", **{**base, **over})


def test_a_usage_line_becomes_a_ledger_row_with_its_links(tenv):
    task = tenv.started()
    run = tenv.row(task).run_id
    go(tenv, task, ev("step", step="W-1", name="Menu", status="running"),
       usage(f"{run}:1", atom="a-0123456789-01"), usage(f"{run}:2", fn="W-1", step="W-1", atom="W-1.a1"),
       usage("r:3", fn="reviewer", step="J2.h", atom="a-aaaaaaaaaa-01"))
    rows = {r["call_ref"]: r for r in tenv.sql("SELECT * FROM usage_ledger")}
    fn_row, builder, helper = rows[f"{run}:1"], rows[f"{run}:2"], rows["r:3"]
    assert (fn_row["node_id"], fn_row["task_id"], fn_row["dept_id"], fn_row["atom_id"], fn_row["session_id"]) == \
        ("web.priority", task, "web", "a-0123456789-01", tenv.graph.get("web.priority").chat_session_id)
    assert (builder["node_id"], builder["atom_id"], builder["fn"], builder["step"]) == (step_id(tenv, task, "W-1"), f"{run}:W-1.a1", "W-1", "W-1")
    assert (helper["node_id"], helper["session_id"], helper["fn"]) == (None, None, "reviewer")
    assert "usage.recorded" in [e.type for e in tenv.env.events.events]


def test_a_usage_line_for_a_builder_before_its_step_exists_has_no_node(tenv):
    task = tenv.started()
    go(tenv, task, usage("r:1", fn="W-4", step="W-4", atom="W-4.a1"))
    assert tenv.one("SELECT node_id FROM usage_ledger WHERE call_ref = 'r:1'") is None


def test_a_usage_line_that_is_not_a_usage_row_is_noted_not_stored(tenv):
    task = tenv.started()
    result = go(tenv, task, usage("r:1", how="telepathy"))
    assert result.skipped == 1 and tenv.one("SELECT count(*) FROM usage_ledger") == 0
    assert any("usage line is not a usage row" in t for (_, kind, t) in session_texts(tenv, "web.identity") if kind == "note")


# ---- run.ended ---------------------------------------------------------------------------------------------------------------------

def test_run_ended_done_settles_the_task_the_nodes_and_posts_a_done_card(tenv):
    task = tenv.started()
    go(tenv, task, ev("step", step="W-1", name="Menu", status="running"), ev("step", step="W-2", name="Home", status="filed"),
       ev("step", step="W-3", name="Footer", status="idle"), ev("node", fn="priority", status="running", detail="pricing"))
    result = go(tenv, task, ev("run.ended", status="done", outcome="The site is workable."))
    row = tenv.row(task)
    assert (row.status, row.outcome, result.ended, result.freed_slot) == ("done", "The site is workable.", True, True)
    assert row.ended_at is not None and row.ended_at >= row.started_at
    assert [tenv.graph.get(step_id(tenv, task, r)).state for r in ("task", "W-1", "W-2", "W-3")] == ["filed", "done_unchecked", "filed", "idle"]
    assert all(tenv.graph.get(f"web.{fn}").state == "idle" for fn in FUNCTIONS) and tenv.graph.get("web").state == "idle"
    assert tenv.graph.get("web").detail.startswith("last: Build a landing page")
    card = tenv.chats.messages("cs_org")[-1].card
    assert (card.type, card.task_id, card.dept_name, card.status, card.outcome) == ("done", task, "Web", "done", "The site is workable.")
    assert not any(m.kind == "error" for m in dept_messages(tenv))
    assert tenv.drain(task).ended                                              # a finished task is left alone


@pytest.mark.parametrize("status,step_word,node_word", [("done_with_open_items", "left_open", "left_open"), ("stopped", "left_open", "left_open"),
                                                        ("crashed", "left_open", "fault")])
def test_run_ended_other_ends_settle_steps_as_left_open(tenv, status, step_word, node_word):
    task = tenv.started()
    go(tenv, task, ev("step", step="W-1", name="Menu", status="running"), ev("step", step="W-3", name="Footer", status="idle"))
    go(tenv, task, ev("run.ended", status=status, outcome="", **({"code": "internal"} if status == "crashed" else {})))
    assert tenv.status(task) == status
    assert tenv.graph.get(step_id(tenv, task, "W-1")).state == step_word and tenv.graph.get(step_id(tenv, task, "W-3")).state == "not_made"
    assert tenv.graph.get(step_id(tenv, task, "task")).state == {"done_with_open_items": "left_open", "stopped": "left_open", "crashed": "fault"}[status]
    assert tenv.row(task).outcome                                               # an empty outcome gets a default sentence


def test_a_crash_says_so_in_the_department_chat(tenv):
    task = tenv.started()
    go(tenv, task, ev("run.ended", status="crashed", outcome="ModelError: quota", code="quota"))
    last = dept_messages(tenv)[-1]
    assert (last.kind, last.who, last.text) == ("error", "sutra", "Something went wrong. Try again.")
    assert tenv.graph.get("web").state == "fault"


def test_run_ended_starts_the_blocked_dependants_and_a_failure_cancels_them(tenv):
    a = tenv.started()
    b = tenv.new(dept="sales", text="after a", depends_on=[a])
    c = tenv.started(dept="ops" if False else "sales", text="x") if False else None
    go(tenv, a, ev("run.ended", status="done", outcome="ok"))
    assert tenv.status(b.id) == "queued"
    d = tenv.started(dept="web", text="second web")
    e = tenv.new(dept="sales", text="after d", depends_on=[d])
    go(tenv, d, ev("run.ended", status="stopped", outcome="stopped"))
    assert tenv.status(e.id) == "cancelled"
    assert c is None


def test_nothing_after_run_ended_is_applied(tenv):
    task = tenv.started()
    path = tenv.run_dir(task) / "events.jsonl"
    with open(path, "ab") as f:
        for e in (ev("run.ended", status="done", outcome="ok"), ev("say", id=1, who="audit", text="late", next="identity")):
            f.write((json.dumps({"at": "2026-11-04T10:00:00Z", **e}) + "\n").encode())
    result = tenv.drain(task)
    assert result.ended and ("audit", "text", "late") not in session_texts(tenv, "web.audit")


# ---- crash detection, silence, the watcher ---------------------------------------------------------------------------------------------

def test_crash_pid_gone(tenv):
    task = tenv.started()
    pid = tenv.row(task).pid
    (tenv.run_dir(task) / "run.stderr.log").write_text("Traceback...\nValueError: boom\nOPENAI_API_KEY=sk-secretsecretsecret\n")
    tenv.watcher.redact = lambda text: text.replace("sk-secretsecretsecret", "[redacted]")
    tenv.launcher.kill(pid)
    assert tenv.run(tenv.watcher.tick(task)) is True
    row = tenv.row(task)
    assert row.status == "crashed" and row.outcome.startswith("the team process stopped unexpectedly (exit code -9): ")
    assert "ValueError: boom" in row.outcome and "sk-secret" not in row.outcome and "[redacted]" in row.outcome
    assert len(row.outcome) <= 2000
    assert dept_messages(tenv)[-1].text == "Something went wrong. Try again."


def test_a_crash_card_names_files_not_this_machines_folders_and_the_log_keeps_the_whole_tail(tenv):
    """gap chart-insight: the 2 KB the owner reads says 'tools.py', never the home or the data folder; run.stderr.log is not touched."""
    task = tenv.started()
    home_file = str(Path.home() / ".local" / "share" / "uv" / "tools" / "sutra-pro" / "lib" / "tools.py")
    data_file = str(tenv.run_dir(task) / "build" / "index.html")
    tail = f'Traceback...\n  File "{home_file}", line 12, in run\nFileNotFoundError: {data_file}.\nrelative build/v1/index.html on 5/6/2026 and /home/about\n'
    (tenv.run_dir(task) / "run.stderr.log").write_text(tail)
    tenv.launcher.kill(tenv.row(task).pid)
    assert tenv.run(tenv.watcher.tick(task)) is True
    said = tenv.row(task).outcome
    assert 'File "tools.py", line 12, in run' in said and "FileNotFoundError: index.html." in said
    assert str(Path.home()) not in said and str(tenv.settings.data_dir) not in said
    assert "build/v1/index.html on 5/6/2026 and /home/about" in said                      # a relative path, a date and a site's page stay
    assert (tenv.run_dir(task) / "run.stderr.log").read_text() == tail                    # the log keeps the full tail


def test_a_process_that_wrote_its_last_lines_as_it_died_is_not_a_crash(tenv):
    task = tenv.started()
    tenv.write_events(task, ev("run.ended", status="done", outcome="finished just before"))
    tenv.launcher.kill(tenv.row(task).pid)
    assert tenv.run(tenv.watcher.tick(task)) is True
    assert (tenv.status(task), tenv.row(task).outcome) == ("done", "finished just before")


def test_silent_alive_not_killed_but_flagged(tenv):
    task = tenv.started()
    pid = tenv.row(task).pid
    tenv.wclock.advance(120)
    assert tenv.run(tenv.watcher.tick(task)) is False
    node = tenv.graph.get(step_id(tenv, task, "task"))
    assert node.detail.startswith("no signal for ") and node.detail.endswith(" s")
    assert tenv.status(task) == "running" and tenv.launcher.alive(pid) and tenv.launcher.stopped == []
    go(tenv, task, ev("heartbeat", at="2026-11-04T10:00:00Z"))                   # a line arrives: the flag goes away
    assert tenv.graph.get(step_id(tenv, task, "task")).detail == ""


def test_a_task_within_thirty_seconds_is_not_flagged(tenv):
    task = tenv.started()
    assert tenv.run(tenv.watcher.tick(task)) is False
    assert tenv.graph.get(step_id(tenv, task, "task")).detail == ""


def test_the_watcher_projects_in_the_background_and_starts_the_next_task(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, max_runs=1, launcher=FakeLauncher({"*": [
        {"emit": ev("run.started", schema="events/1", mock=True, seed="none")}, {"emit": ev("say", id=1, who="audit", text="hello", next="identity")},
        {"emit": ev("run.ended", status="done", outcome="fine")}]}))
    a, b = t.new(dept="web", text="one"), t.new(dept="sales", text="two")

    async def go_():
        await t.service.start_ready()
        for _ in range(400):
            if t.status(b.id) == "done":
                break
            await asyncio.sleep(0.02)
    import asyncio
    t.run(go_())
    assert (t.status(a.id), t.status(b.id)) == ("done", "done")
    assert ("audit", "text", "hello") in session_texts(t, "web.audit")


# ---- reconcile ---------------------------------------------------------------------------------------------------------------------------

def do_reconcile(t: TEnv) -> tuple[ReconcileReport, list]:
    published = []

    async def main():
        return await reconcile(tasks=t.store, projector=t.projector, watcher=t.watcher, launcher=t.launcher,
                               publish=lambda type, data: published.append((type, data)), clock=t.wclock)
    return t.run(main()), published


def test_reconcile_settles_a_run_that_ended_while_the_app_was_down(tenv):
    task = tenv.started()
    tenv.write_events(task, ev("say", id=1, who="audit", text="last words", next="identity"), ev("run.ended", status="done", outcome="done while closed"))
    tenv.launcher.kill(tenv.row(task).pid)
    report, published = do_reconcile(tenv)
    assert report.settled == [task] and tenv.status(task) == "done" and tenv.row(task).outcome == "done while closed"
    assert ("audit", "text", "last words") in session_texts(tenv, "web.audit")
    assert published == [("server.resync", {"reason": "restart"})]


def test_reconcile_reattach(tenv):
    task = tenv.started()
    tenv.write_events(task, ev("heartbeat"))
    report, _ = do_reconcile(tenv)
    assert report.reattached == [task] and tenv.status(task) == "running"
    assert tenv.row(task).events_offset == (tenv.run_dir(task) / "events.jsonl").stat().st_size


def test_reconcile_stale_alive_with_identity(tenv):
    task = tenv.started()
    pid = tenv.row(task).pid
    tenv.wclock.advance(300)
    report, _ = do_reconcile(tenv)
    assert report.signalled == [task] and report.crashed == [task] and tenv.launcher.stopped == [pid]
    row = tenv.row(task)
    assert row.status == "crashed" and row.outcome == "the app was closed while it ran and the team stopped answering"


def test_reconcile_pid_reuse_not_signalled(tenv):
    task = tenv.started()
    tenv.launcher.commands[tenv.row(task).pid] = "/usr/bin/some-other-program --run-dir /elsewhere"
    tenv.wclock.advance(300)
    report, _ = do_reconcile(tenv)
    assert report.untouched == [task] and tenv.launcher.stopped == [] and tenv.launcher.alive(tenv.row(task).pid)
    assert tenv.status(task) == "crashed"


def test_reconcile_a_missing_pid_is_crashed_and_its_open_atoms_abandoned(tenv):
    task = tenv.started()
    tenv.launcher.kill(tenv.row(task).pid)
    report, _ = do_reconcile(tenv)
    assert report.crashed == [task]
    assert (tenv.status(task), tenv.row(task).outcome) == ("crashed", "the app was closed while it ran")
    assert tenv.graph.get("web").state == "fault"


def test_reconcile_starting_without_events(tenv):
    silent = tenv.new(text="never wrote a line")
    tenv.run(tenv.service.start_ready())
    assert tenv.status(silent.id) == "starting"
    tenv.wclock.advance(300)
    other = tenv.new(dept="sales", text="no pid at all")
    tenv.run(tenv.service.start_ready())
    tenv.sql("UPDATE tasks SET pid = NULL WHERE id = ?", other.id)
    report, _ = do_reconcile(tenv)
    assert set(report.crashed) == {silent.id, other.id} and report.signalled == [silent.id]
    assert tenv.row(other.id).outcome == "could not start" and tenv.row(silent.id).status == "crashed"


def test_reconcile_leaves_tasks_that_have_no_process_alone(tenv):
    done = tenv.started(dept="sales", text="x")
    tenv.projector.mark_ended(done, "done", "ok")
    queued = tenv.new(text="waiting its turn")
    report, published = do_reconcile(tenv)
    assert report.all() == [] and tenv.status(queued.id) == "queued" and published


# ---- chunking, apply(), the watcher's life ---------------------------------------------------------------------------------------------

def test_a_big_file_is_read_in_chunks_and_a_partial_tail_does_not_loop(tenv, monkeypatch):
    from sutra_app.orchestrator import projector as projector_module
    monkeypatch.setattr(projector_module, "MAX_CHUNK_BYTES", 200)
    task = tenv.started()
    lines = [ev("say", id=i, who="audit", text=f"line number {i}", next="identity") for i in range(1, 9)]
    tenv.write_events(task, *lines)
    with open(tenv.run_dir(task) / "events.jsonl", "ab") as f:
        f.write(b'{"t":"heartbeat"')                                           # half a line at the end
    first = tenv.drain(task)
    assert first.more is True and first.applied < 8
    tenv.run(tenv.watcher.drain(task))                                         # drains until the end of the file, then stops (no endless loop)
    assert [t for (who, kind, t) in session_texts(tenv, "web.audit") if who == "audit"] == [f"line number {i}" for i in range(1, 9)]


def test_a_line_longer_than_the_chunk_is_read_whole(tenv, monkeypatch):
    from sutra_app.orchestrator import projector as projector_module
    monkeypatch.setattr(projector_module, "MAX_CHUNK_BYTES", 100)
    task = tenv.started()
    big = "x" * 900
    go(tenv, task, ev("say", id=1, who="audit", text=big, next="identity"))
    assert ("audit", "text", big) in session_texts(tenv, "web.audit")


def test_a_line_over_the_hard_limit_is_skipped_and_noted(tenv, monkeypatch):
    from sutra_app.orchestrator import projector as projector_module
    monkeypatch.setattr(projector_module, "MAX_CHUNK_BYTES", 50)
    monkeypatch.setattr(projector_module, "MAX_LINE_BYTES", 200)
    task = tenv.started()
    with open(tenv.run_dir(task) / "events.jsonl", "ab") as f:
        f.write(b"y" * 500 + b"\n")
    result = tenv.drain(task)
    assert result.skipped == 1 and any("bytes long" in t for (_, kind, t) in session_texts(tenv, "web.identity") if kind == "note")
    assert tenv.row(task).events_offset > 0


def test_apply_takes_parsed_events_inside_a_transaction(tenv):
    from sutra_app.orchestrator.models import parse_event
    task = tenv.started()
    row = tenv.row(task)
    events = [parse_event({"at": "2026-11-04T10:00:00Z", **ev("say", id=1, who="audit", text="direct", next="identity")}),
              parse_event({"at": "2026-11-04T10:00:00Z", **ev("node", fn="audit", status="running", detail="hi")})]
    with tenv.db.tx() as tx:
        batch = tenv.projector.apply(tx, row, events)
    assert batch.changed and ("audit", "text", "direct") in session_texts(tenv, "web.audit") and tenv.graph.get("web.audit").state == "running"


def test_unwatch_and_close_end_the_watcher_loops_gracefully(tenv):
    async def go_():
        task = tenv.new()
        await tenv.service.start_ready()
        assert tenv.watcher.watching() == [task.id]
        tenv.watcher.unwatch(task.id)
        await asyncio.sleep(0.1)
        assert tenv.watcher.watching() == []
        tenv.watcher.watch(task.id)
        assert tenv.watcher.watching() == [task.id]
        await tenv.watcher.close()
        assert tenv.watcher.watching() == []
    import asyncio
    tenv.run(go_())


def test_a_loop_bound_service_starts_a_follow_up_by_itself_and_stop_live_works_from_a_worker_thread(tenv):
    first = tenv.started()
    tenv.write_events(first, ev("say", id=1, who="identity", text="Q?", to_user=True, act="ASK_REQUESTER", next="user"))
    tenv.drain(first)

    async def go_():
        import asyncio

        from sutra_app.orchestrator.db import run_blocking
        tenv.service.bind_loop(asyncio.get_running_loop())
        assert await run_blocking(tenv.service.stop_live, "web") is True              # a worker thread: the ladder runs on the server loop
        assert tenv.status(first) == "stopped"
        delivery = await run_blocking(tenv.service.deliver_to_department, "web", "carry on please")
        for _ in range(200):
            if tenv.status(delivery.task_id) == "starting":
                break
            await asyncio.sleep(0.02)
        assert tenv.status(delivery.task_id) == "starting"
    tenv.run(go_())


def test_a_spawn_error_text_is_redacted(tenv):
    tenv.service.redact = lambda text: text.replace("hunter2-secret", "[redacted]")
    tenv.launcher.fail_with = OSError("cannot run with token hunter2-secret")
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert tenv.row(task.id).outcome == "could not start: cannot run with token [redacted]"


def test_the_task_store_refuses_unknown_columns_and_invalid_rows(tenv):
    from sutra_app.library.gate import GateError
    task = tenv.new()
    with tenv.db.tx() as tx:
        with pytest.raises(ValueError):
            tenv.store.update(tx, task.id, dept_id="sales")
        with pytest.raises(GateError):
            tenv.store.update(tx, task.id, status="running")                  # a running task has a run id
        with pytest.raises(GateError):
            tenv.store.update(tx, task.id, status="done", ended_at=None)      # a finished task has an end time
