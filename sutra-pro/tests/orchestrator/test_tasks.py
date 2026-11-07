"""TaskService, TaskStore and the run launcher (ORCH-6): run folder, queueing and caps, delivery, overrides, the stop ladder, the
child environment, shutdown. `TEnv` builds the whole task side on top of the chart `Env`; the other ORCH-6 test files import it."""
import asyncio
import json
import os
import signal
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from orchestrator.test_chart_store import Env

from sutra_app.connectors.env import PASS_NAMES
from sutra_app.engine.spec import TaskSpec
from sutra_app.orchestrator.atoms import AtomStore
from sutra_app.orchestrator.errors import AppError, Busy, NotFound, ReadOnly
from sutra_app.orchestrator.models import RunSpec
from sutra_app.orchestrator.projector import Projector
from sutra_app.orchestrator.runs import (
    STOP_GRACE_S, TERM_GRACE_S, ProcessLauncher, RunWatcher, child_environment, inbox_line_count, run_has_ended,
)
from sutra_app.orchestrator.tasks import TaskGraph, TaskService, TaskStore
from sutra_app.orchestrator.testing import FakeClock
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher, ev
from sutra_app.orchestrator.usage import UsageStore


def arun(coro, env=None):
    """Run a coroutine to completion; the watchers of `env` (if given) finish their current look before the loop goes away."""
    async def main():
        try:
            return await coro
        finally:
            if env is not None:
                await env.watcher.close()
    return asyncio.run(main())


class TEnv:
    """The task side over a bootstrapped chart: stores, projector, watcher, service and a launcher (FakeLauncher by default)."""

    def __init__(self, env: Env, settings, clock, *, launcher=None, **setting_changes) -> None:
        self.env = env
        self.settings = settings.model_copy(update=setting_changes) if setting_changes else settings
        self.db, self.graph, self.chats, self.clock = env.db, env.graph, env.chats, clock
        self.ids = env.chart._ids
        self.store = TaskStore(env.db, self.settings.data_dir)
        self.taskgraph = TaskGraph(self.store, env.graph, ids=self.ids)
        self.atoms = AtomStore(env.db, chats=env.chats, graph=env.graph)
        self.usage = UsageStore(env.db, chats=env.chats)
        self.projector = Projector(env.db, graph=env.graph, chats=env.chats, atoms=self.atoms, usage=self.usage, store=self.store,
                                   taskgraph=self.taskgraph, clock=clock)
        self.launcher = launcher if launcher is not None else FakeLauncher({"*": [{"hold": True}]})
        self.wclock = FakeClock(start=1793786405, step=0)           # the watcher's idea of 'now': it stands still until a test advances it
        self.watcher = RunWatcher(self.projector, self.store, self.launcher, interval=0.01, clock=self.wclock)
        self.service = TaskService(env.db, store=self.store, graph=env.graph, chats=env.chats, taskgraph=self.taskgraph, projector=self.projector,
                                   launcher=self.launcher, settings=self.settings, watcher=self.watcher, clock=clock, ids=self.ids)
        self.watcher.after_drain = self.service.start_ready

    # ---- helpers -------------------------------------------------------------------------------------------------------------

    def run(self, coro):
        return arun(coro, self)

    def new(self, dept: str = "web", text: str = "Build a landing page for my cafe", **kw):
        with self.db.tx() as tx:
            return self.service.create(tx, dept_id=dept, text=text, **kw)

    def row(self, task_id: str):
        return self.store.row(task_id)

    def status(self, task_id: str) -> str:
        return self.store.row(task_id).status

    def run_dir(self, task_id: str) -> Path:
        return self.store.run_dir_of(self.store.row(task_id))

    def events_of(self, task_id: str) -> list[dict]:
        return [json.loads(line) for line in (self.run_dir(task_id) / "events.jsonl").read_text().splitlines() if line.strip()]

    def write_events(self, task_id: str, *events: dict) -> None:
        with open(self.run_dir(task_id) / "events.jsonl", "ab") as handle:
            for event in events:
                line = {"at": "2026-11-04T10:00:00Z", **event}
                handle.write((json.dumps(line) + "\n").encode())

    def drain(self, task_id: str):
        return self.projector.drain(task_id)

    def sql(self, text: str, *args):
        return self.db.conn().execute(text, args)

    def one(self, text: str, *args):
        row = self.sql(text, *args).fetchone()
        return row[0] if row is not None else None

    async def start(self, task_id: str | None = None) -> list[str]:
        started = await self.service.start_ready()
        return started

    def started(self, dept: str = "web", text: str = "Build a landing page for my cafe", **kw) -> str:
        """Create a task, start it (fake launcher) and apply run.started: the task is `running`."""
        task = self.new(dept, text, **kw)

        async def go() -> None:
            await self.service.start_ready()
            self.write_events(task.id, ev("run.started", pid=self.row(task.id).pid, schema="events/1", mock=True, seed="none"))
            self.drain(task.id)
        self.run(go())
        return task.id


@pytest.fixture
def tenv(db, settings, clock, events):
    return TEnv(Env(db, settings, clock, events).build(), settings, clock)


def tenv_with(db, settings, clock, events, **kw) -> TEnv:
    return TEnv(Env(db, settings, clock, events).build(), settings, clock, **kw)


# ---- create ----------------------------------------------------------------------------------------------------------------------

def test_create_makes_a_queued_task_and_its_step_node(tenv):
    task = tenv.new(title="Cafe page")
    assert (task.status, task.dept_id, task.dept_name, task.title) == ("queued", "web", "Web", "Cafe page")
    node = tenv.graph.get(next(r[0] for r in tenv.sql("SELECT id FROM graph_nodes WHERE task_id = ?", task.id)))
    assert (node.kind, node.step_ref, node.state, node.parent_id, node.label) == ("step", "task", "not_made", "web", "Cafe page")
    assert node.chat_session_id and tenv.one("SELECT writable FROM chat_sessions WHERE id = ?", node.chat_session_id) == 0
    assert "task.updated" in [e.type for e in tenv.env.events.events]


def test_create_title_defaults_to_the_first_words_of_the_text(tenv):
    assert tenv.new(text="  Write   the\nmenu page  ").title == "Write the menu page"


def test_create_refuses_bad_settings_with_422_and_stores_nothing(tenv):
    before = tenv.one("SELECT count(*) FROM tasks")
    for bad in ({"J2_SEND_MODE": "live"}, {"J2_OUTPUT": "pdf"}, {"J2_BUDGET": "0"}, {"J2_FIXES": "2"}):
        with pytest.raises(AppError) as caught:
            tenv.new(settings=bad)
        assert caught.value.code == "validation"
    assert tenv.one("SELECT count(*) FROM tasks") == before


def test_create_stores_the_seven_allowed_settings(tenv):
    task = tenv.new(settings={"J2_OUTPUT": "prd", "J2_BUDGET": "50", "J2_FIXES": "1"})
    assert json.loads(tenv.one("SELECT settings_json FROM tasks WHERE id = ?", task.id)) == {"J2_BUDGET": "50", "J2_FIXES": "1", "J2_OUTPUT": "prd"}


def test_create_unknown_department_is_404_and_empty_text_is_422(tenv):
    with pytest.raises(NotFound):
        tenv.new(dept="nowhere")
    with pytest.raises(AppError) as caught:
        tenv.new(text="   ")
    assert caught.value.code == "validation"


def test_create_scope_must_be_a_division_under_the_department(tenv):
    assert tenv.new(scope_id="menu").scope_node_id == "menu"
    for bad in ("leads", "web", "nobody"):                      # a division of another team, the team itself, nothing
        with pytest.raises(AppError) as caught:
            tenv.new(scope_id=bad)
        assert caught.value.details["violations"][0]["path"] == "scope_id"


def test_create_follows_needs_a_task_of_the_same_department_that_has_a_run(tenv):
    first = tenv.started()
    follow = tenv.new(text="Now the menu", follows=first)
    row = tenv.row(follow.id)
    assert (row.parent_task_id, row.seed_from) == (first, tenv.row(first).run_id)
    other = tenv.new(dept="sales", text="Quote")
    for bad in (other.id, "tsk_000000000999"):
        with pytest.raises(AppError):
            tenv.new(follows=bad)
    queued = tenv.new(text="queued, no run yet")
    with pytest.raises(AppError) as caught:
        tenv.new(follows=queued.id)
    assert caught.value.details["violations"][0]["code"] == "no_run"


def test_create_with_unfinished_dependency_is_blocked_and_with_a_failed_one_cancelled(tenv):
    a = tenv.new(text="first")
    b = tenv.new(dept="sales", text="second", depends_on=[a.id])
    assert b.status == "blocked" and b.depends_on == [a.id]
    assert tenv.graph.get(tenv.one("SELECT id FROM graph_nodes WHERE task_id = ?", b.id)).state == "not_made"
    with tenv.db.tx() as tx:
        tenv.store.update(tx, a.id, status="crashed", ended_at=tx.now(), outcome="x")
    c = tenv.new(dept="sales", text="third", depends_on=[a.id])
    assert c.status == "cancelled" and "did not finish" in c.outcome
    with pytest.raises(AppError):
        tenv.new(depends_on=["tsk_000000000999"])


# ---- starting: the run folder, caps, the queue --------------------------------------------------------------------------------------

def test_run_folder_modes_and_task_json(tenv):
    task = tenv.new(text="Build a page", framing="The owner runs a cafe", settings={"J2_OUTPUT": "prd"}, scope_id="menu")
    started = tenv.run(tenv.service.start_ready())
    assert started == [task.id]
    run_dir = tenv.run_dir(task.id)
    assert run_dir.parent == tenv.settings.data_dir / "departments" / "web" / "runs"
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    for name in ("task.json", "inbox.jsonl", "events.jsonl"):
        assert stat.S_IMODE((run_dir / name).stat().st_mode) == 0o600, name
    assert (run_dir / "inbox.jsonl").read_bytes() == b"" and (run_dir / "events.jsonl").read_bytes() == b""
    assert not list(run_dir.glob(".*.tmp"))
    spec = RunSpec.model_validate_json((run_dir / "task.json").read_text())
    assert (spec.run_id, spec.task_id, spec.dept_id, spec.dept_label, spec.scope_id, spec.scope_label) == (run_dir.name, task.id, "web", "Web", "menu", "Menu")
    assert (spec.user_text, spec.framing, spec.settings.J2_OUTPUT, spec.connector) == ("Build a page", "The owner runs a cafe", "prd", "auto")
    engine_view = TaskSpec.model_validate_json((run_dir / "task.json").read_text())
    assert engine_view.run_id == spec.run_id and engine_view.settings == {"J2_OUTPUT": "prd"}


def test_start_marks_starting_stores_the_pid_and_the_step_node_runs(tenv):
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    row = tenv.row(task.id)
    assert (row.status, row.run_id is not None, row.started_at is not None, row.last_event_at == row.started_at) == ("starting", True, True, True)
    assert row.pid and row.pid >= 2_000_000_000
    node = tenv.graph.get(tenv.one("SELECT id FROM graph_nodes WHERE task_id = ?", task.id))
    assert node.state == "running"
    assert tenv.graph.get("web").state == "running"                                # aggregate: a live task


def test_offline_setting_gives_the_stub_connector(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, offline=True)
    task = t.new()
    t.run(t.service.start_ready())
    assert RunSpec.model_validate_json((t.run_dir(task.id) / "task.json").read_text()).connector == "stub"


def test_upstream_lists_the_files_of_finished_dependencies(tenv):
    first = tenv.started()
    (tenv.run_dir(first) / "menu.html").write_text("<html>")
    (tenv.run_dir(first) / "goal.json").write_text("{}")
    tenv.write_events(first, ev("run.ended", status="done", outcome="ok"))
    tenv.drain(first)
    second = tenv.new(dept="sales", text="Quote it", depends_on=[first])
    tenv.run(tenv.service.start_ready())
    spec = RunSpec.model_validate_json((tenv.run_dir(second.id) / "task.json").read_text())
    assert [(u.dept_id, u.run_id, u.files) for u in spec.upstream] == [("web", tenv.row(first).run_id, ["goal.json", "menu.html"])]


def test_one_live_task_per_department_the_second_is_queued(tenv):
    a = tenv.new(text="one")
    b = tenv.new(text="two")
    assert tenv.run(tenv.service.start_ready()) == [a.id]
    assert tenv.status(b.id) == "queued"
    assert "waiting for the team" in tenv.graph.get(tenv.one("SELECT id FROM graph_nodes WHERE task_id = ?", b.id)).detail


def test_max_runs_holds_tasks_back_and_says_why(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, max_runs=1)
    a, b = t.new(dept="web", text="one"), t.new(dept="sales", text="two")
    assert t.run(t.service.start_ready()) == [a.id]
    assert t.status(b.id) == "queued"
    assert t.graph.get(t.one("SELECT id FROM graph_nodes WHERE task_id = ?", b.id)).detail == "waiting for a free slot (1 teams working)"


def test_a_waiting_run_frees_its_max_runs_slot(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, max_runs=1)
    a, b = t.new(dept="web", text="one"), t.new(dept="sales", text="two")
    t.run(t.service.start_ready())
    t.write_events(a.id, ev("run.started", pid=1, schema="events/1", mock=True, seed="none"),
                   ev("say", id=1, who="identity", text="What is it called?", to_user=True, act="ASK_REQUESTER", next="user"))
    result = t.drain(a.id)
    assert result.freed_slot and t.status(a.id) == "waiting_user"
    assert t.run(t.service.start_ready()) == [b.id]
    assert t.status(b.id) == "starting"


def test_max_live_counts_waiting_runs_too(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, max_runs=2, max_live=2)
    a, b, c = t.new(dept="web", text="one"), t.new(dept="sales", text="two"), None
    t.run(t.service.start_ready())
    t.write_events(a.id, ev("say", id=1, who="identity", text="Q?", to_user=True, act="ASK_REQUESTER", next="user"))
    t.drain(a.id)
    assert t.status(a.id) == "waiting_user" and t.status(b.id) == "starting"
    with t.db.tx() as tx:
        tx.conn.execute("UPDATE tasks SET status='queued' WHERE id = ?", (b.id,))        # pretend b is still waiting for a slot
    t.env.apply(*[__import__("factories_org").dept_op("$ops", "Ops")])
    c = t.new(dept="ops", text="three")
    assert t.run(t.service.start_ready()) == [b.id]            # max_live 2: a waits (1) + b starts (2)
    assert t.status(c.id) == "queued"                         # a third live process is held back
    assert "free slot" in t.graph.get(t.one("SELECT id FROM graph_nodes WHERE task_id = ?", c.id)).detail


def test_blocked_task_starts_after_its_dependency_is_done(tenv):
    a = tenv.new(text="first")
    b = tenv.new(dept="sales", text="second", depends_on=[a.id])
    tenv.run(tenv.service.start_ready())
    assert tenv.status(b.id) == "blocked"
    tenv.write_events(a.id, ev("run.started", pid=1, schema="events/1", mock=True, seed="none"), ev("run.ended", status="done", outcome="fine"))
    tenv.drain(a.id)
    assert tenv.status(b.id) == "queued"
    assert tenv.run(tenv.service.start_ready()) == [b.id]


def test_a_dependency_that_crashed_cancels_the_dependants(tenv):
    a = tenv.new(text="first")
    b = tenv.new(dept="sales", text="second", depends_on=[a.id])
    c = tenv.new(dept="sales", text="third", depends_on=[b.id])
    tenv.run(tenv.service.start_ready())
    tenv.projector.mark_ended(a.id, "crashed", "boom")
    assert (tenv.status(b.id), tenv.status(c.id)) == ("cancelled", "cancelled")
    assert tenv.row(b.id).outcome == "waiting task first did not finish"


def test_a_spawn_failure_crashes_that_task_only(tenv):
    tenv.launcher.fail_with = OSError("no such interpreter")
    a = tenv.new(text="one")
    b = tenv.new(dept="sales", text="two")
    assert tenv.run(tenv.service.start_ready()) == [a.id, b.id]
    for t in (a, b):
        row = tenv.row(t.id)
        assert row.status == "crashed" and row.outcome.startswith("could not start: ")
    assert tenv.graph.get("web").state == "fault"


def test_a_spawn_failure_names_the_file_not_the_folder_for_the_owner(tenv):
    """gap chart-insight: the owner-facing 'could not start' line carries file names; the data folder and the home stay out of it."""
    tenv.launcher.fail_with = OSError(f"[Errno 2] No such file or directory: '{tenv.settings.data_dir}/departments/web/python3'")
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert tenv.row(task.id).outcome == "could not start: [Errno 2] No such file or directory: 'python3'"


# ---- the child environment ------------------------------------------------------------------------------------------------------------

def test_child_env_allowlist():
    environ = {name: f"v-{name}" for name in PASS_NAMES}
    environ.update(CODEX_HOME="/h/.codex", CLAUDE_CONFIG_DIR="/h/.claude", PYTHONPATH="/x", SHELL="/bin/zsh", TERM="xterm",
                   SUTRA_TOKEN="secret-token-123456", SUTRA_DATA_DIR="/data", SUTRA_OFFLINE="1", SUTRA_MY_KEY="no", ANTHROPIC_API_KEY="k",
                   GITHUB_TOKEN="g", OPENAI_API_KEY="o", AWS_SECRET_ACCESS_KEY="s", UNRELATED="x")
    env = child_environment({"J2_OUTPUT": "prd", "J2_BUDGET": "9"}, environ)
    for name in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "PYTHONPATH", "SHELL", "TERM", "PATH", "HOME", "XDG_CONFIG_HOME", "HTTPS_PROXY", "SSL_CERT_FILE"):
        assert name in env, name
    assert (env["SUTRA_DATA_DIR"], env["SUTRA_OFFLINE"], env["J2_OUTPUT"], env["J2_BUDGET"]) == ("/data", "1", "prd", "9")
    for name in ("SUTRA_TOKEN", "SUTRA_MY_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "UNRELATED"):
        assert name not in env, name


def test_child_env_never_passes_a_secret_looking_name_even_from_settings():
    env = child_environment({"J2_OVERRIDE_KEY": "x", "J2_OUTPUT": "prd"}, {})
    assert env == {"J2_OUTPUT": "prd"}


# ---- delivery: the owner writes in a department chat ----------------------------------------------------------------------------------

def ask(tenv, task_id: str, text: str = "What is the business called?\nOption 1: Sweet Bean\nOption 2: Other", say_id: int = 1) -> None:
    tenv.write_events(task_id, ev("say", id=say_id, who="identity", text=text, to_user=True, act="ASK_REQUESTER", pause="info", next="user"))
    tenv.drain(task_id)


def dept_messages(tenv, dept: str = "web"):
    return tenv.chats.messages(tenv.graph.get(dept).chat_session_id)


def test_an_answer_goes_to_the_waiting_team_and_the_question_is_answered(tenv):
    task = tenv.started()
    ask(tenv, task)
    assert tenv.status(task) == "waiting_user" and tenv.graph.get("web.identity").state == "waiting_on_you"
    result = tenv.service.deliver_to_department("web", "  Sweet Bean, in Leeds  ")
    assert (result.delivered, result.task_id) == ("answer", task)
    inbox = [json.loads(line) for line in (tenv.run_dir(task) / "inbox.jsonl").read_text().splitlines()]
    assert len(inbox) == 1 and (inbox[0]["n"], inbox[0]["kind"], inbox[0]["text"]) == (1, "user", "Sweet Bean, in Leeds")
    assert tenv.row(task).status == "running" and tenv.row(task).inbox_seq == 1
    question, answer = dept_messages(tenv)[-2:]
    assert (question.kind, question.answered_by, answer.id, answer.who, answer.text, answer.task_id) == ("question", answer.id, result.message_id, "user", "Sweet Bean, in Leeds", task)
    identity = tenv.graph.get("web.identity")
    assert (identity.state, identity.wait_on) == ("running", None)
    assert tenv.chats.needs_you() == []


def test_a_working_team_is_409_busy_and_nothing_is_written(tenv):
    task = tenv.started()
    before = tenv.one("SELECT count(*) FROM chat_messages")
    with pytest.raises(Busy):
        tenv.service.deliver_to_department("web", "hello?")
    assert tenv.one("SELECT count(*) FROM chat_messages") == before and inbox_line_count(tenv.run_dir(task)) == 0


def test_no_live_task_makes_a_follow_up_that_continues_from_the_old_run(tenv):
    first = tenv.started()
    tenv.write_events(first, ev("run.ended", status="done", outcome="Done."))
    tenv.drain(first)
    result = tenv.service.deliver_to_department("web", "Make the logo bigger", scope_id="menu", settings={"J2_OUTPUT": "prd"})
    assert result.delivered == "follow_up" and result.task_id != first
    new = tenv.row(result.task_id)
    assert (new.status, new.parent_task_id, new.seed_from, new.scope_node_id, new.title) == ("queued", first, tenv.row(first).run_id, "menu", "Make the logo bigger")
    assert new.settings == {"J2_OUTPUT": "prd"} and dept_messages(tenv)[-1].task_id == new.id
    with pytest.raises(Busy):                                                   # the follow-up is waiting to start: no second one
        tenv.service.deliver_to_department("web", "and more")
    tenv.run(tenv.service.start_ready())
    spec = RunSpec.model_validate_json((tenv.run_dir(new.id) / "task.json").read_text())
    assert (spec.seed_from, spec.parent_run_id) == (tenv.row(first).run_id, tenv.row(first).run_id)


def test_followup_seed_from_is_the_latest_run_that_has_a_folder(tenv):
    first = tenv.started()
    tenv.write_events(first, ev("run.ended", status="done", outcome="Done."))
    tenv.drain(first)
    second = tenv.new(text="second", follows=first)
    tenv.run(tenv.service.start_ready())
    tenv.write_events(second.id, ev("run.ended", status="stopped", outcome="stopped"))
    tenv.drain(second.id)
    import shutil
    shutil.rmtree(tenv.run_dir(second.id))                                      # its folder is gone: seed from the one before
    result = tenv.service.deliver_to_department("web", "carry on")
    assert tenv.row(result.task_id).seed_from == tenv.row(first).run_id and tenv.row(result.task_id).parent_task_id == second.id


def reset_after(tenv, run_id: str | None, raw: str | None = None) -> None:
    """What the engine's reset leaves for the team: `page.json.since_run` (engine/api/ctx.py `write_page`)."""
    page = tenv.settings.data_dir / "departments" / "web" / "page.json"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(raw if raw is not None else json.dumps({"since_run": run_id, "next_settings": {}}))


def finished_run(tenv) -> str:
    task = tenv.started()
    tenv.write_events(task, ev("run.ended", status="done", outcome="Done."))
    tenv.drain(task)
    return task


def test_a_brief_written_after_a_reset_starts_a_fresh_run_not_a_change_request(tenv):
    """QA dept-run P2: '+ New run' showed a blank page but the next brief was seeded from the run the owner had just left."""
    first = finished_run(tenv)
    reset_after(tenv, tenv.row(first).run_id)                                   # the engine's reset wrote the marker
    result = tenv.service.deliver_to_department("web", "A brand new website for a dental clinic")
    new = tenv.row(result.task_id)
    assert result.delivered == "follow_up" and (new.seed_from, new.parent_task_id) == (None, None)
    tenv.run(tenv.service.start_ready())
    spec = RunSpec.model_validate_json((tenv.run_dir(new.id) / "task.json").read_text())
    assert (spec.seed_from, spec.parent_run_id) == (None, None) and spec.user_text == "A brand new website for a dental clinic"
    assert tenv.row(first).status == "done" and tenv.run_dir(first).is_dir()      # history is kept


def test_the_reset_marker_covers_only_the_runs_before_it(tenv):
    first = finished_run(tenv)
    reset_after(tenv, tenv.row(first).run_id)
    second = tenv.service.deliver_to_department("web", "A brand new website for a dental clinic").task_id
    tenv.run(tenv.service.start_ready())
    tenv.write_events(second, ev("run.ended", status="done", outcome="Done."))
    tenv.drain(second)
    third = tenv.row(tenv.service.deliver_to_department("web", "Make the header darker").task_id)
    assert (third.seed_from, third.parent_task_id) == (tenv.row(second).run_id, second)      # a later message continues the new run


def test_a_reset_by_the_chat_path_starts_fresh_too(tenv):
    first = finished_run(tenv)
    reset_after(tenv, tenv.row(first).run_id)
    delivery = tenv.service.deliver(tenv.graph.get("web").chat_session_id, "A brand new website for a dental clinic")
    assert (tenv.row(delivery.task_id).seed_from, tenv.row(delivery.task_id).parent_task_id) == (None, None)


def test_the_engines_own_reset_command_leaves_the_marker_this_service_reads(tenv):
    """The two halves together: `DeptCommands.reset` (engine/api/commands.py) then `DeptCommands.say`, over the real TaskService."""
    from types import SimpleNamespace

    from sutra_app.engine.api.commands import DeptCommands
    first = finished_run(tenv)
    services = SimpleNamespace(data_dir=tenv.settings.data_dir, stop_live=tenv.service.stop_live, resolve_run=tenv.service.resolve_run,
                               deliver_to_department=tenv.service.deliver_to_department)
    commands = DeptCommands(services, "web")
    assert commands.reset() is True
    assert commands.say("A brand new website for a dental clinic") is True
    new = tenv.store.latest_in(tenv.db.conn(), "web")
    assert new.id != first and new.user_text == "A brand new website for a dental clinic" and (new.seed_from, new.parent_task_id) == (None, None)


@pytest.mark.parametrize("raw", ["{not json", "[]", '{"since_run": 7}', '{"since_run": null}', '{"next_settings": {}}'])
def test_a_page_file_without_a_usable_marker_changes_nothing(tenv, raw):
    first = finished_run(tenv)
    reset_after(tenv, None, raw)
    new = tenv.row(tenv.service.deliver_to_department("web", "Make the logo bigger").task_id)
    assert (new.seed_from, new.parent_task_id) == (tenv.row(first).run_id, first)


def test_a_question_left_open_by_a_reset_is_closed_but_not_carried_into_the_fresh_run(tenv):
    task = tenv.started()
    ask(tenv, task, "Which colours?\nOption 1: Green\nOption 2: Blue")
    tenv.projector.mark_ended(task, "stopped", "reset by you")
    reset_after(tenv, tenv.row(task).run_id)
    question = [m for m in dept_messages(tenv) if m.kind == "question"][0]
    result = tenv.service.deliver_to_department("web", "A brand new website for a dental clinic")
    row = tenv.row(result.task_id)
    assert (row.framing, row.seed_from, row.parent_task_id) == ("", None, None)
    assert [m for m in dept_messages(tenv) if m.id == question.id][0].answered_by == result.message_id


def test_retry_has_no_seed(tenv):
    first = tenv.started(settings={"J2_FIXES": "1"})
    tenv.projector.mark_ended(first, "crashed", "boom")
    new = tenv.run(tenv.service.retry(first))
    row = tenv.row(new.id)
    assert (new.status, row.parent_task_id, row.seed_from, row.user_text, row.settings) == ("starting", first, None, tenv.row(first).user_text, {"J2_FIXES": "1"})
    spec = RunSpec.model_validate_json((tenv.run_dir(new.id) / "task.json").read_text())
    assert (spec.seed_from, spec.parent_run_id) == (None, tenv.row(first).run_id)
    assert spec.framing.startswith("This is attempt 2 of this request.") and "Attempt 1 crashed: boom" in spec.framing      # told, not seeded


def test_retry_only_after_a_task_that_ended_badly(tenv):
    running = tenv.started()
    finished = tenv.started(dept="sales", text="x")
    tenv.projector.mark_ended(finished, "done", "ok")
    for task_id in (running, finished):
        with pytest.raises(Busy):
            tenv.run(tenv.service.retry(task_id))
    with pytest.raises(NotFound):
        tenv.run(tenv.service.retry("tsk_000000000999"))


def test_orphaned_question_framing(tenv):
    task = tenv.started()
    ask(tenv, task, "Which colours?\nOption 1: Green\nOption 2: Blue")
    tenv.projector.mark_ended(task, "stopped", "the app was closed")                  # the team ended while it waited for the owner
    question = [m for m in dept_messages(tenv) if m.kind == "question"][0]
    result = tenv.service.deliver_to_department("web", "Green please")
    assert result.delivered == "follow_up"
    row = tenv.row(result.task_id)
    assert row.framing == "Earlier the team asked the owner: Which colours?\nOption 1: Green\nOption 2: Blue"
    assert tenv.chats.messages(tenv.graph.get("web").chat_session_id)[0].id == question.id
    assert [m for m in dept_messages(tenv) if m.id == question.id][0].answered_by == result.message_id


def test_empty_text_and_unknown_team(tenv):
    with pytest.raises(AppError) as caught:
        tenv.service.deliver_to_department("web", "   ")
    assert caught.value.code == "validation"
    with pytest.raises(NotFound):
        tenv.service.deliver_to_department("nowhere", "hi")
    with pytest.raises(AppError):
        tenv.service.deliver_to_department("web", "hi", settings={"J2_SEND_MODE": "live"})


def test_deliver_by_session_uses_the_department_or_the_division_scope(tenv):
    web = tenv.graph.get("web").chat_session_id
    menu = tenv.graph.get("menu").chat_session_id
    delivery = tenv.service.deliver(menu, "More about the menu")
    assert delivery.delivered == "follow_up" and tenv.row(delivery.task_id).scope_node_id == "menu" and tenv.row(delivery.task_id).dept_id == "web"
    for read_only in (tenv.graph.get("web.identity").chat_session_id, "cs_org", tenv.graph.get(tenv.one("SELECT id FROM graph_nodes WHERE task_id = ?", delivery.task_id)).chat_session_id):
        with pytest.raises(ReadOnly):
            tenv.service.deliver(read_only, "hi")
    with pytest.raises(NotFound):
        tenv.service.deliver("cs_ffffffffffff", "hi")
    tenv.sql("UPDATE chat_sessions SET status = 'archived', writable = 0 WHERE id = ?", web)
    with pytest.raises(ReadOnly):
        tenv.service.deliver(web, "hi")


# ---- the owner override ----------------------------------------------------------------------------------------------------------------

KEY = "owner-key-0123456789"


def with_key(db, settings, clock, events) -> TEnv:
    from pydantic import SecretStr
    return tenv_with(db, settings, clock, events, override_key=SecretStr(KEY))


def whole_database_and_files(t: TEnv) -> str:
    text = "\n".join(line for line in t.db.conn().iterdump())
    for path in t.settings.data_dir.rglob("*"):
        if path.is_file() and path.name != "db.sqlite3" and not path.name.endswith(("-wal", "-shm")):
            text += path.read_text(errors="replace")
    return text


def test_override_waiting_only(db, settings, clock, events):
    t = with_key(db, settings, clock, events)
    task = t.started()
    ask(t, task)
    result = t.service.deliver_to_department("web", f"  {KEY} budget +5 ")
    assert result.delivered == "answer"
    inbox = json.loads((t.run_dir(task) / "inbox.jsonl").read_text())
    assert (inbox["kind"], inbox["cmd"]) == ("override", "budget +5") and "text" not in inbox
    assert dept_messages(t)[-1].text == "Owner override sent"
    assert t.status(task) == "running"
    question = [m for m in dept_messages(t) if m.kind == "question"][0]
    assert question.answered_by is None                                          # an override does not answer the team's question


def test_override_never_creates_a_task_and_a_busy_team_says_so(db, settings, clock, events):
    t = with_key(db, settings, clock, events)
    before = t.one("SELECT count(*) FROM tasks")
    with pytest.raises(Busy):                                                     # no live task at all
        t.service.deliver_to_department("web", f"{KEY} ship")
    assert t.one("SELECT count(*) FROM tasks") == before
    task = t.started()
    with pytest.raises(Busy):                                                     # a working team
        t.service.deliver_to_department("web", f"{KEY} ship")
    assert t.one("SELECT count(*) FROM tasks") == before + 1 and inbox_line_count(t.run_dir(task)) == 0
    note = dept_messages(t)[-1]
    assert (note.kind, note.text) == ("note", "Owner override needs a team that is waiting for you.")


def test_override_key_not_stored(db, settings, clock, events):
    t = with_key(db, settings, clock, events)
    task = t.started()
    ask(t, task)
    t.service.deliver_to_department("web", f"{KEY} drop W-3")
    with pytest.raises(Busy):
        t.service.deliver_to_department("sales", f"{KEY} ship")
    assert KEY not in whole_database_and_files(t)


def test_a_bare_override_key_is_refused_and_a_near_miss_is_plain_text(db, settings, clock, events):
    t = with_key(db, settings, clock, events)
    task = t.started()
    ask(t, task)
    with pytest.raises(AppError) as caught:
        t.service.deliver_to_department("web", KEY)
    assert caught.value.code == "validation"
    assert t.service.deliver_to_department("web", KEY[:-1] + "X ship").delivered == "answer"
    assert json.loads((t.run_dir(task) / "inbox.jsonl").read_text())["kind"] == "user"


# ---- stop, reset, resolve_run ------------------------------------------------------------------------------------------------------------

def test_stop_live_waiting(tenv):
    task = tenv.started()
    ask(tenv, task)
    queued = tenv.new(dept="web", text="queued behind")
    assert tenv.service.stop_live("web") is True
    assert tenv.row(task).status == "stopped" and tenv.row(task).outcome in ("reset by you", "stopped by you")
    assert tenv.row(queued.id).status == "cancelled" and tenv.row(queued.id).outcome == "reset by you"
    assert tenv.launcher.alive(tenv.row(task).pid) is False


def test_stop_live_running_untouched(tenv):
    task = tenv.started()
    queued = tenv.new(dept="web", text="queued behind")
    assert tenv.service.stop_live("web") is False
    assert (tenv.status(task), tenv.status(queued.id)) == ("running", "queued")
    assert tenv.launcher.stopped == []


def test_stop_live_nothing_live_true(tenv):
    assert tenv.service.stop_live("web") is True


def test_stop_live_cancels_queued(tenv):
    a = tenv.new(text="a")
    b = tenv.new(dept="sales", text="blocked", depends_on=[a.id])
    assert tenv.service.stop_live("web") is True
    assert (tenv.status(a.id), tenv.status(b.id)) == ("cancelled", "cancelled")
    assert tenv.run(tenv.service.start_ready()) == []                      # a reset page must not start a queued task later


def test_stop_a_running_task_through_the_ladder(tenv):
    task = tenv.started()
    out = tenv.run(tenv.service.stop(task))
    assert (out.status, out.outcome) == ("stopped", "stopped by you")
    assert tenv.launcher.stopped == [tenv.row(task).pid]
    assert tenv.graph.get("web").state == "idle"


def test_stop_when_the_team_ignores_the_stop_line_the_task_is_stopped_by_you(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, launcher=FakeLauncher({"*": [{"ignore_stop": True}, {"hold": True}]}, stop_grace=0.05))
    task = t.started()
    out = t.run(t.service.stop(task))
    assert (out.status, out.outcome) == ("stopped", "stopped by you")
    assert not t.launcher.alive(t.row(task).pid)


def test_stop_a_queued_task_cancels_it_and_a_finished_one_is_busy(tenv):
    a = tenv.started()
    b = tenv.new(text="queued")
    assert tenv.run(tenv.service.stop(b.id)).status == "cancelled"
    tenv.projector.mark_ended(a, "done", "ok")
    with pytest.raises(Busy):
        tenv.run(tenv.service.stop(a))


def test_stopping_starts_the_next_queued_task(tenv):
    a = tenv.started()
    b = tenv.new(text="next")
    tenv.run(tenv.service.stop(a))
    assert tenv.status(b.id) == "starting"


def test_resolve_run(tenv):
    first = tenv.started()
    tenv.projector.mark_ended(first, "done", "ok")
    second = tenv.started()
    r1, r2 = tenv.row(first).run_id, tenv.row(second).run_id
    assert tenv.service.resolve_run(r1, "web").task_id == first
    assert tenv.service.resolve_run(None, "web").run_id == r2                     # the live task wins over a newer-looking finished one
    tenv.projector.mark_ended(second, "done", "ok")
    ref = tenv.service.resolve_run(None, "web")
    assert ref.run_id == r2 and ref.dir == f"departments/web/runs/{r2}" and ref.status == "done"
    assert tenv.service.resolve_run(r1, "sales") is None                         # another department's run
    assert tenv.service.resolve_run("j2-nope", "web") is None and tenv.service.resolve_run(None, "sales") is None


def test_shutdown_stops_waiting_runs_as_the_app_was_closed(tenv):
    a = tenv.started()
    ask(tenv, a)
    b = tenv.started(dept="sales", text="Quote it")
    tenv.run(tenv.service.shutdown())
    for task_id in (a, b):
        row = tenv.row(task_id)
        assert row.status == "stopped" and not tenv.launcher.alive(row.pid)
        assert row.outcome in ("the app was closed", "stopped by you")
    assert tenv.status(a) != "crashed"


# ---- the real launcher ------------------------------------------------------------------------------------------------------------------

HOLDOUT = """
import os, signal, sys, time
run_dir = sys.argv[1]
def on_term(signum, frame):
    open(os.path.join(run_dir, "got_term"), "w").write("term")
signal.signal(signal.SIGTERM, on_term)           # ignores the stop line (never reads the inbox) and SIGTERM
open(os.path.join(run_dir, "ready"), "w").write(str(os.getpid()))
while True:
    time.sleep(0.05)
"""


def spawn_holdout(run_dir: Path):
    import subprocess
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "inbox.jsonl").write_bytes(b"")
    (run_dir / "events.jsonl").write_bytes(b"")
    proc = subprocess.Popen([sys.executable, "-c", HOLDOUT, str(run_dir)], start_new_session=True)
    threading.Thread(target=proc.wait, daemon=True).start()                      # reap it the moment it dies (a zombie still answers kill -0)
    for _ in range(200):
        if (run_dir / "ready").exists():
            break
        time.sleep(0.01)
    return proc


def test_stop_ladder_order(tmp_path):
    """A process that ignores the stop line and SIGTERM: the ladder sends the stop line, then SIGTERM to the group, then SIGKILL."""
    proc = spawn_holdout(tmp_path / "run")
    launcher = ProcessLauncher()
    started = time.monotonic()
    try:
        arun(launcher.stop(tmp_path / "run", proc.pid, stop_grace=0.3, term_grace=0.3))
        elapsed = time.monotonic() - started
        assert proc.wait(timeout=5) == -signal.SIGKILL                          # it was killed, not asked nicely
        assert (tmp_path / "run" / "got_term").read_text() == "term"           # SIGTERM came first and was ignored
        stop_line = json.loads((tmp_path / "run" / "inbox.jsonl").read_text())
        assert stop_line["kind"] == "stop" and stop_line["n"] == 1
        assert elapsed >= 0.6                                                  # both graces were used
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_stop_ladder_ends_at_once_when_run_ended_and_the_process_exits(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "inbox.jsonl").write_bytes(b"")
    (run / "events.jsonl").write_text('{"t":"run.ended","status":"stopped","at":"2026-11-04T10:00:00Z"}\n')
    import subprocess
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"], start_new_session=True)
    threading.Thread(target=proc.wait, daemon=True).start()
    launcher = ProcessLauncher()
    assert run_has_ended(run)
    arun(launcher.stop(run, proc.pid, stop_grace=5, term_grace=5))
    assert proc.wait(timeout=5) == 0                                           # it left by itself: no signal was needed


def test_stop_ladder_constants():
    assert (STOP_GRACE_S, TERM_GRACE_S) == (8.0, 4.0)


def test_the_process_launcher_runs_the_fake_engine_process_end_to_end(db, settings, clock, events, tmp_path):
    script = tmp_path / "script.json"
    script.write_text(json.dumps([
        {"emit": ev("run.started", schema="events/1", mock=True, seed="none")},
        {"emit": ev("say", id=1, who="identity", text="Name?", to_user=True, act="ASK_REQUESTER", next="user")},
        {"wait_inbox": 1},
        {"emit": ev("run.ended", status="done", outcome="all done")}]))
    launcher = ProcessLauncher(module="sutra_app.orchestrator.testing.fake_engine", extra_env={"SUTRA_FAKE_SCRIPT": str(script)})
    t = tenv_with(db, settings, clock, events, launcher=launcher)
    task = t.new()

    async def go():
        await t.service.start_ready()
        pid = t.row(task.id).pid
        assert pid and launcher.alive(pid)
        for _ in range(600):                                                   # the child needs a moment to import and write its question
            await t.watcher.drain(task.id)
            if t.status(task.id) == "waiting_user":
                break
            await asyncio.sleep(0.05)
        assert t.status(task.id) == "waiting_user" and t.row(task.id).pid == pid
        await run_in_thread(t.service.deliver_to_department, "web", "Sweet Bean")
        for _ in range(600):
            await t.watcher.drain(task.id)
            if t.status(task.id) == "done":
                break
            await asyncio.sleep(0.05)
    t.run(go())
    assert (t.status(task.id), t.row(task.id).outcome) == ("done", "all done")
    assert (t.run_dir(task.id) / "run.stderr.log").exists() and stat.S_IMODE((t.run_dir(task.id) / "run.stdout.log").stat().st_mode) == 0o600


async def run_in_thread(fn, *args):
    from sutra_app.orchestrator.db import run_blocking
    return await run_blocking(fn, *args)


def test_alive_uses_the_handle_for_a_spawned_pid_and_kill_zero_for_others(tmp_path):
    launcher = ProcessLauncher()
    assert launcher.alive(None) is False and launcher.alive(0) is False and launcher.alive(2_000_000_000) is False
    assert launcher.alive(os.getpid()) is True                                  # not spawned by us: os.kill(pid, 0)
    assert "python" in launcher.command_of(os.getpid()).lower() and launcher.command_of(2_000_000_000) == ""


def test_send_numbers_the_inbox_lines(tmp_path):
    launcher = ProcessLauncher()
    (tmp_path / "inbox.jsonl").write_bytes(b"")
    assert [launcher.send(tmp_path, {"kind": "user", "text": "a"}), launcher.send(tmp_path, {"kind": "user", "text": "b", "n": 99})] == [1, 2]
    assert [json.loads(x)["n"] for x in (tmp_path / "inbox.jsonl").read_text().splitlines()] == [1, 2]
