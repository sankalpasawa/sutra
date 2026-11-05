"""Scenario 4 (GAP-E2E, G05): the server dies, the owner stops a team, an engine hangs. Real processes all the way.

  * the server is killed in the middle of a run (uvicorn stops WITHOUT the stop ladders: the engine processes live on); a new
    server on the same data folder reconciles: the live run is re-attached, the lines written while nobody watched are projected,
    every event lands exactly once, the run ends Done;
  * a run that ended while the server was down is settled at the next start;
  * a real `stop` ends the engine through the ladder (stop line, then signals) with NO atom left open (G01b);
  * an engine that hangs (SIGSTOP) is flagged 'no signal' by the watcher and, after the 30 s of silence the clock says have passed,
    declared crashed by the next start, which runs the ladder on it (identity proven from `ps`): the process is gone.

The clock is `ControlledClock` (wall time plus an offset the test moves), the poll is 50 ms (`SUTRA_WATCH_MS`), so nothing waits 30 s.
"""
import os
import signal
import time

import pytest
from harness import ANSWER, ControlledClock, LiveApp, atoms_left_open, new_team_script
from harness import pid_alive as alive
from sutra_app.orchestrator.runs import append_inbox
from sutra_app.orchestrator.testing.scripted import ScriptedConnector


def asked(live: LiveApp) -> str:
    """The owner's first message; returns the task once its team waits for the owner."""
    mid = live.say("I need a landing page for my coffee shop", *new_team_script())
    task = live.task_of_message(mid)
    live.until("Identity's question", lambda: live.task_status(task) == "waiting_user")
    return task


def projected_once(live: LiveApp, task: str) -> None:
    """The invariants of 'every event is projected once', read from the database against the engine's own file."""
    events = live.events_of(task)
    path = live.run_dir(task) / "events.jsonl"
    assert live.task_row(task)["events_offset"] == path.stat().st_size                              # every byte was read, none twice
    usage = [e for e in events if e["t"] == "usage"]
    rows = live.rows("SELECT call_ref FROM usage_ledger WHERE task_id = ?", task)
    assert len(rows) == len({r["call_ref"] for r in rows}) == len(usage)
    refs = [r["src_ref"] for r in live.rows("SELECT src_ref FROM chat_messages WHERE task_id = ? AND src_ref IS NOT NULL", task)]
    assert len(refs) == len(set(refs)) > 10                                                         # no chat line was posted twice
    atoms = live.rows("SELECT id FROM atoms WHERE task_id = ?", task)
    ledger = live.rows("SELECT atom_id FROM atom_ledger")
    assert len({a["id"] for a in atoms}) == len(atoms) and len({r["atom_id"] for r in ledger}) == len(ledger)
    assert live.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 0


def test_step6_a_server_killed_in_the_middle_of_a_run_is_replaced_and_every_event_is_projected_once(tmp_path):
    first = LiveApp(tmp_path, connector=ScriptedConnector(), mock_delay=0.12).start()
    second = None
    try:
        task = asked(first)
        assert first.write(first.session_of("web"), ANSWER).status_code == 200                      # the run works on, slowly
        first.until("work to start", lambda: first.one("SELECT count(*) FROM atoms WHERE task_id = ?", task) >= 3)
        pid = first.task_row(task)["pid"]
        before = first.task_row(task)["events_offset"]
        first.crash()                                                                                # no ladder: nothing is signalled or settled
        assert alive(pid) and first.task_status(task) in ("running", "waiting_user")
        second = LiveApp(tmp_path, connector=ScriptedConnector(), mock_delay=0.12).start()
        assert second.services.reconciled.reattached == [task] and second.services.reconciled.crashed == []
        assert second.task_row(task)["pid"] == pid and second.services.watcher.watching() == [task]
        second.ended(task)
        assert second.task_row(task)["events_offset"] > before
        projected_once(second, task)
        assert [c["status"] for c in second.cards("done")] == ["done"] and len(second.cards("done")) == 1
        summary_events = second.events_of(task)
        assert summary_events[-1]["t"] == "run.ended" and sum(e["t"] == "run.started" for e in summary_events) == 1
        assert second.one("SELECT display FROM atoms WHERE node_id = 'web.audit' ORDER BY ts_open DESC LIMIT 1") == "closed"
        assert second.sse.types()[0] == "server.hello" and second.get("/api/needs-you") == []
    finally:
        for live in (second, first):
            if live is not None:
                try:
                    if live.started:
                        live.stop()
                finally:
                    live.kill_engines()


def test_a_run_that_ended_while_the_server_was_down_is_settled_at_the_next_start(tmp_path):
    first = LiveApp(tmp_path, connector=ScriptedConnector()).start()
    second = None
    try:
        task = asked(first)
        run_dir = first.run_dir(task)
        first.crash()
        append_inbox(run_dir, {"kind": "user", "text": ANSWER})                                      # the answer, written by hand: nobody is serving
        first.until("the engine to finish alone", lambda: any(e["t"] == "run.ended" for e in first.events_of(task)), 60)
        assert first.task_status(task) == "waiting_user"                                             # the database still believes it waits
        second = LiveApp(tmp_path, connector=ScriptedConnector()).start()
        assert second.services.reconciled.settled == [task] and second.services.reconciled.reattached == []
        assert second.task_status(task) == "done"
        projected_once(second, task)
        assert len(second.cards("done")) == 1
    finally:
        for live in (second, first):
            if live is not None:
                try:
                    if live.started:
                        live.stop()
                finally:
                    live.kill_engines()


def test_step6_a_real_stop_of_a_team_that_waits_ends_the_engine_through_the_ladder_with_no_atom_open(tmp_path):
    with LiveApp(tmp_path, connector=ScriptedConnector()) as live:
        task = asked(live)
        pid = live.task_row(task)["pid"]
        assert live.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 1                    # Identity's manual atom waits with the question
        mark = len(live.sse.snapshot())
        started = time.time()
        response = live.post(f"/api/tasks/{task}/stop")
        assert response.status_code == 200 and response.json()["status"] == "stopped" and response.json()["outcome"].startswith("Stopped")
        assert time.time() - started < 12 and not live.until("the process to leave", lambda: not alive(pid), 15) is None
        events = live.events_of(task)
        assert events[-1]["t"] == "run.ended" and events[-1]["status"] == "stopped"                  # the engine said so itself, in time
        assert live.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 0
        assert atoms_left_open(events) == [] and any(e["t"] == "atom" and e["atom"]["status"] == "abandoned" for e in events)       # G01b: the engine closed its own books
        manual = live.rows("SELECT display FROM atoms WHERE node_id = 'web.identity' AND task_id = ?", task)
        assert [r["display"] for r in manual].count("abandoned") >= 1
        assert live.one("SELECT status FROM atom_ledger WHERE node_id = 'web.identity' ORDER BY seq DESC LIMIT 1") == "abandoned"
        types = [f["type"] for f in live.sse.snapshot()[mark:]]
        assert "atom.updated" in types and "task.updated" in types
        assert live.one("SELECT state FROM graph_nodes WHERE id = 'web.identity'") == "idle"
        assert [n["kind"] for n in live.get("/api/needs-you")] == ["question"]                       # the unanswered question stays until the owner's next line
        assert live.write(live.session_of("web"), "Never mind the question, start again").json()["delivered"] == "follow_up"
        assert live.one("SELECT answered_by FROM chat_messages WHERE kind = 'question' ORDER BY id LIMIT 1") is not None
        [done] = live.cards("done")
        assert (done["task_id"], done["status"]) == (task, "stopped")
        again = live.post(f"/api/tasks/{task}/stop")
        assert again.status_code == 409 and again.json()["error"]["code"] == "busy"


def test_step6_a_real_stop_in_the_middle_of_work_leaves_no_atom_open(tmp_path):
    with LiveApp(tmp_path, connector=ScriptedConnector(), mock_delay=0.3) as live:
        task = asked(live)
        assert live.write(live.session_of("web"), ANSWER).status_code == 200
        live.until("a function atom to be open", lambda: live.one("SELECT count(*) FROM atoms WHERE display = 'open' AND schema = 'atom/1'") >= 1
                   or live.one("SELECT count(*) FROM atoms WHERE display = 'open' AND node_id != 'web.identity'") >= 1)
        pid = live.task_row(task)["pid"]
        assert live.post(f"/api/tasks/{task}/stop").json()["status"] == "stopped"
        live.until("the process to leave", lambda: not alive(pid), 15)
        assert live.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 0
        assert atoms_left_open(live.events_of(task)) == [] and live.events_of(task)[-1]["t"] == "run.ended"
        assert live.one("SELECT count(*) FROM atom_ledger") == live.one("SELECT count(*) FROM atoms")      # every atom reached the log


def test_closing_the_app_runs_the_ladder_on_a_waiting_team_and_the_next_start_finds_nothing_to_fix(tmp_path):
    first = LiveApp(tmp_path, connector=ScriptedConnector()).start()
    second = None
    try:
        task = asked(first)
        pid = first.task_row(task)["pid"]
        first.stop()
        assert not alive(pid) and first.task_status(task) == "stopped"
        assert first.task_row(task)["outcome"].startswith("Stopped") and first.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 0
        second = LiveApp(tmp_path, connector=ScriptedConnector()).start()
        assert second.services.reconciled.all() == [] and second.task_status(task) == "stopped"
    finally:
        for live in (second, first):
            if live is not None:
                try:
                    if live.started:
                        live.stop()
                finally:
                    live.kill_engines()


def test_step6_a_hung_engine_is_flagged_then_declared_crashed_after_30_seconds_of_silence(tmp_path):
    clock = ControlledClock()
    first = LiveApp(tmp_path, connector=ScriptedConnector(), clock=clock, stop_grace=0.5, term_grace=0.5).start()
    second = None
    try:
        task = asked(first)
        pid = first.task_row(task)["pid"]
        first.until("a heartbeat", lambda: first.task_row(task)["last_event_at"] is not None)
        os.killpg(os.getpgid(pid), signal.SIGSTOP)                                                    # the engine hangs: no more lines
        clock.jump(40)                                                                                # 40 s later, as far as the server can tell
        first.until("the 'no signal' flag",
                    lambda: "no signal for" in (first.one("SELECT detail FROM graph_nodes WHERE kind = 'step' AND task_id = ?", task) or ""))
        assert first.task_status(task) == "waiting_user" and alive(pid)                              # a silent but live process is never touched
        first.crash()
        second = LiveApp(tmp_path, connector=ScriptedConnector(), clock=clock, stop_grace=0.5, term_grace=0.5).start()
        report = second.services.reconciled
        assert report.signalled == [task] and report.crashed == [task] and report.reattached == []
        assert second.task_status(task) == "crashed" and not alive(pid)                               # the ladder reached a stopped process: SIGKILL
        assert second.task_row(task)["outcome"] == "the app was closed while it ran and the team stopped answering"
        assert second.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 0
        crash = [m for m in second.messages(second.session_of("web")) if m["kind"] == "error"]
        assert len(crash) == 1 and [c["status"] for c in second.cards("done")] == ["crashed"]
    finally:
        for live in (second, first):
            if live is not None:
                try:
                    if live.started:
                        live.stop()
                finally:
                    live.kill_engines()


@pytest.mark.slow
def test_step6_a_hung_engine_is_declared_crashed_after_thirty_real_seconds_without_the_clock_hook(tmp_path):
    first = LiveApp(tmp_path, connector=ScriptedConnector(), stop_grace=0.5, term_grace=0.5).start()
    second = None
    try:
        task = asked(first)
        pid = first.task_row(task)["pid"]
        os.killpg(os.getpgid(pid), signal.SIGSTOP)
        first.crash()
        quiet = first.task_row(task)["last_event_at"]
        time.sleep(max(0.0, quiet + 31 - time.time()))                                                # the real SILENT_AFTER_S plus a margin
        second = LiveApp(tmp_path, connector=ScriptedConnector(), stop_grace=0.5, term_grace=0.5).start()
        assert second.services.reconciled.signalled == [task] and second.task_status(task) == "crashed" and not alive(pid)
    finally:
        for live in (second, first):
            if live is not None:
                try:
                    if live.started:
                        live.stop()
                finally:
                    live.kill_engines()
