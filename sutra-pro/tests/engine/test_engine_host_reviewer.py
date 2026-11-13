"""The end-of-run reviewer (J2 sync 6, D179, patch P19): the host waits for J2's reviewer thread (capped by `reviewer_wait`), discards a late one with
`report_gen`, and the `reviewer` setting switches it off.

Two kinds of test. The join, the cap and the discard run over a fake run object that has what J2 gives the host (`review_thread`, `report_gen`), so
they need no model and no vendored tree. The end to end ones run the vendored J2 in mock mode with a scripted reviewer (`J2Run._review` replaced by a
slow, a raising or a counting one) and read the folder."""
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

from sutra_app.engine import hooks as hooks_module
from sutra_app.engine.host import loop
from sutra_app.engine.host.publisher import HostHooks
from sutra_app.engine.spec import EngineSettings
from test_engine_host import BREW_LAB, QUIET, Running, chat, events, j2, jsonl, trace   # noqa: F401  (fixtures and helpers)

AFTER_END = ("report.json", "report.md", "artifacts.json")
PLACEHOLDER = "The reviewer is writing its notes; they appear here when done."


# ---- the join, over a fake run ------------------------------------------------------------------------------------------------

class FakeHost(loop.Host):
    """A host with only what `_join_reviewer` and the excepthook read."""

    def __init__(self, run, settings=None):
        self.run, self.settings = run, settings or EngineSettings()
        self.stopping = threading.Event()
        self.lines = []
        self._reviewer_late = False
        self._thread_exc = None
        self._saved_hook = self._saved_sigterm = None

    def trace(self, type, data=None):
        self.lines.append((type, data))


def reviewer_thread(seconds, saved):
    """A thread that works for `seconds`, then does what J2's `_review_later` does: save only when its generation is still the current one."""
    run = SimpleNamespace(report_gen=1)
    gen = run.report_gen

    def work():
        time.sleep(seconds)
        if gen == run.report_gen:
            saved.append("saved")

    run.review_thread = threading.Thread(target=work, daemon=True)
    run.review_thread.start()
    return run


def test_a_reviewer_that_finishes_inside_the_wait_is_joined_and_its_notes_are_kept():
    saved = []
    run = reviewer_thread(0.05, saved)
    host = FakeHost(run, EngineSettings(reviewer_wait=5))
    started = time.monotonic()
    host._join_reviewer()
    assert saved == ["saved"] and run.report_gen == 1 and host.lines == [] and not host._reviewer_late
    assert time.monotonic() - started < 2, "it waited for the reviewer, not for the cap"


def test_a_reviewer_past_the_cap_is_discarded_by_the_counter_and_traced_once():
    saved = []
    run = reviewer_thread(1.0, saved)
    host = FakeHost(run, EngineSettings(reviewer_wait=0.1))
    started = time.monotonic()
    host._join_reviewer()
    assert time.monotonic() - started < 0.8, "the cap, plus the short settle, ended the wait"
    assert run.report_gen == 2 and host._reviewer_late
    assert [name for name, _ in host.lines] == ["reviewer.late"] and host.lines[0][1]["reviewer_wait"] == 0.1
    run.review_thread.join(3)
    assert saved == [], "the late reviewer saves nothing: J2's own supersede check"


def test_zero_means_do_not_wait_but_a_reviewer_already_done_is_not_late():
    saved = []
    run = reviewer_thread(0.6, saved)
    host = FakeHost(run, EngineSettings(reviewer_wait=0))
    started = time.monotonic()
    host._join_reviewer()
    assert time.monotonic() - started < loop.REVIEWER_SETTLE_S + 0.3 and run.report_gen == 2 and host._reviewer_late
    run.review_thread.join(3)
    assert saved == []
    done = SimpleNamespace(report_gen=1, review_thread=threading.Thread(target=lambda: None))
    done.review_thread.start()
    done.review_thread.join()
    quiet = FakeHost(done, EngineSettings(reviewer_wait=0))
    quiet._join_reviewer()
    assert done.report_gen == 1 and quiet.lines == []


def test_a_run_with_no_reviewer_thread_has_nothing_to_join():
    for run in (SimpleNamespace(), SimpleNamespace(review_thread=None, report_gen=3)):
        host = FakeHost(run)
        host._join_reviewer()
        assert host.lines == [] and getattr(run, "report_gen", 3) == 3


def test_a_stop_waits_no_longer_than_a_stop_does(monkeypatch):
    monkeypatch.setattr(loop, "STOP_WAIT_S", 0.1)
    saved = []
    run = reviewer_thread(1.0, saved)
    host = FakeHost(run, EngineSettings(reviewer_wait=60))
    host.stopping.set()
    started = time.monotonic()
    host._join_reviewer()
    assert time.monotonic() - started < 0.8 and host._reviewer_late


# ---- the hook ---------------------------------------------------------------------------------------------------------------------

def test_the_hook_is_true_for_null_hooks_and_follows_the_setting_for_event_hooks_and_the_host_wrapper(tmp_path):
    assert hooks_module.NullHooks().review_enabled() is True
    plain = hooks_module.EventHooks(SimpleNamespace(trace=lambda *a, **k: None), lambda: None)
    assert plain.review_enabled() is True
    plain.reviewer = False
    assert plain.review_enabled() is False
    wrapped = HostHooks(plain, SimpleNamespace(notify=lambda: None))
    assert wrapped.review_enabled() is False
    plain.reviewer = True
    assert wrapped.review_enabled() is True
    assert HostHooks(SimpleNamespace(), SimpleNamespace()).review_enabled() is True, "hooks without the method leave J2's reviewer on"


def test_the_excepthook_makes_a_reviewer_failure_a_trace_line_and_not_a_crashed_run():
    thread = threading.Thread(target=lambda: None)
    host = FakeHost(SimpleNamespace(review_thread=thread))
    seen = []
    previous = loop.threading.excepthook
    try:
        loop.threading.excepthook = seen.append          # the hook the host saves and still calls (the stderr traceback)
        host._install_handlers()
        args = SimpleNamespace(thread=thread, exc_value=OSError("the report folder is gone"), exc_type=OSError, exc_traceback=None)
        loop.threading.excepthook(args)
        assert host._thread_exc is None and host.lines[0][0] == "reviewer.error" and "report folder" in host.lines[0][1]["error"]
        other = SimpleNamespace(thread=threading.Thread(name="Thread-9"), exc_value=ValueError("boom"), exc_type=ValueError, exc_traceback=None)
        loop.threading.excepthook(other)
        assert isinstance(host._thread_exc, ValueError), "any other unnamed thread is still the run's crash"
        assert len(seen) == 2, "both are still reported to the original hook (stderr)"
    finally:
        loop.threading.excepthook = previous
        if host._saved_sigterm is not None:
            loop.signal.signal(loop.signal.SIGTERM, host._saved_sigterm)


# ---- end to end, with the vendored J2 -----------------------------------------------------------------------------------------------

def snapshot_of(run_dir):
    return {name: (os.stat(run_dir / name).st_mtime_ns, (run_dir / name).read_bytes()) for name in AFTER_END if (run_dir / name).exists()}


def report(run_dir):
    return json.loads((run_dir / "report.json").read_text(encoding="utf-8"))


def go(make_run_dir, data_dir, settings=None, engine=None):
    if engine is not None:
        (data_dir / "engine.json").write_text(json.dumps(engine))
    run_dir = make_run_dir(user_text=BREW_LAB, settings={**QUIET, **(settings or {})})
    running = Running(run_dir, "--mock")
    assert running.wait(60) == 0
    return run_dir, running


def test_the_reviewer_is_on_by_default_and_the_run_report_holds_its_notes_when_the_run_has_ended(j2, make_run_dir, data_dir):
    run_dir, running = go(make_run_dir, data_dir)
    assert events(run_dir)[-1]["t"] == "run.ended"
    assert report(run_dir)["review"]["verdict"] != PLACEHOLDER, "the host waited for the reviewer"
    assert not trace(run_dir, "reviewer.late")
    assert running.host.hooks.review_enabled() is True


def test_nothing_of_the_run_changes_after_run_ended_and_the_reviewer_is_not_a_late_writer(j2, make_run_dir, data_dir):
    run_dir, running = go(make_run_dir, data_dir)
    ended_at = len(events(run_dir))
    before = snapshot_of(run_dir)
    time.sleep(1.0)
    assert snapshot_of(run_dir) == before and len(events(run_dir)) == ended_at
    thread = getattr(running.host.run, "review_thread", None)
    assert thread is None or not thread.is_alive()


def test_a_reviewer_switched_off_in_the_settings_says_so_and_makes_no_call(j2, make_run_dir, data_dir):
    run_dir, running = go(make_run_dir, data_dir, engine={"reviewer": False})
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")
    assert report(run_dir)["review"]["verdict"] == "The reviewer is switched off in this team's settings."
    assert "switched off" in (run_dir / "report.md").read_text(encoding="utf-8")
    assert getattr(running.host.run, "review_thread", None) is None, "no reviewer thread was started"
    metrics = report(run_dir)["metrics"]
    assert metrics["ai_calls"] == running.host.run.calls, "the reviewer's call is not counted"


def test_a_slow_reviewer_past_reviewer_wait_leaves_the_placeholder_and_no_write_after_run_ended(j2, make_run_dir, data_dir, monkeypatch):
    release = threading.Event()

    def slow(self, metrics, mock=None):
        release.wait(20)
        return {"verdict": "far too late"}

    monkeypatch.setattr(j2.J2Run, "_review", slow)
    run_dir, running = go(make_run_dir, data_dir, engine={"reviewer_wait": 0.3})
    try:
        assert events(run_dir)[-1]["t"] == "run.ended"
        late = trace(run_dir, "reviewer.late")
        assert len(late) == 1 and late[0]["data"]["reviewer_wait"] == 0.3
        assert report(run_dir)["review"]["verdict"] == PLACEHOLDER
        before = snapshot_of(run_dir)
        n_events, n_trace = len(events(run_dir)), len(jsonl(run_dir / "trace.jsonl"))
    finally:
        release.set()
    running.host.run.review_thread.join(5)
    assert not running.host.run.review_thread.is_alive()
    time.sleep(0.3)
    assert snapshot_of(run_dir) == before, "the late reviewer saved nothing: report.json, report.md and artifacts.json are as they were at run.ended"
    assert len(events(run_dir)) == n_events and len(jsonl(run_dir / "trace.jsonl")) == n_trace


def test_a_reviewer_that_raises_still_ends_the_run_done_and_the_report_says_so(j2, make_run_dir, data_dir, monkeypatch):
    def broken(self, metrics, mock=None):
        raise RuntimeError("the reviewer's model fell over")

    monkeypatch.setattr(j2.J2Run, "_review", broken)
    run_dir, _ = go(make_run_dir, data_dir)
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")
    assert "Reviewer call failed" in report(run_dir)["review"]["verdict"]


def test_a_reviewer_thread_that_dies_outside_its_own_try_does_not_crash_the_finished_run(j2, make_run_dir, data_dir, monkeypatch, capsys):
    def explode(self, metrics, gen):
        raise OSError("the report folder vanished under the reviewer")

    monkeypatch.setattr(j2.J2Run, "_review_later", explode)
    run_dir, _ = go(make_run_dir, data_dir)
    last = events(run_dir)[-1]
    assert last["t"] == "run.ended" and last["status"] in ("done", "done_with_open_items"), "a reviewer's death is not the run's"
    assert trace(run_dir, "reviewer.error") and not trace(run_dir, "thread.died")
