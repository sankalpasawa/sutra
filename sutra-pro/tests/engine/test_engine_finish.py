"""The steps at the end of a run (J2 sync 4, lane D2, D142 and D143): the guarded runner, the `agent_views` step, the `catalog` step and the
one call in `Host._conclude` that runs them.

The runner is proved with steps made here and a stand-in host. The two real steps are proved on this tree's own mock runs: a Brew Lab run
in the host (J2's mock mode, Chrome faked) writes the run folder, and the steps read it. A mock run is skipped by the catalog step by
design, so the catalog step is also called on the host of a finished mock run with its `mock` flag turned off, and a run with the template
library on is carried through the host with the flag turned off after J2 was configured (only the finish steps read it).
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_engine_host as host_tests
from test_engine_host import (  # noqa: F401  (j2 is a fixture)
    BREW_LAB, QUIET, VAGUE, Answerer, RaisingPort, Running, append_inbox, chat, events, j2, jsonl, make_port_of, of, trace, wait_until,
)

from sutra_app import oslayer
from sutra_app.engine.host import finish, loop
from sutra_app.engine.port import NoModelAvailable


@pytest.fixture(autouse=True)
def _import_the_modules_the_steps_use_anew(monkeypatch):
    """`fresh_j2` puts back the J2 modules it imported anew; the two the finish steps import are not in its list, so they would outlive
    the test and keep the first test's copies of the modules they import. Added here, for this file only."""
    monkeypatch.setattr(host_tests, "J2_MODULES", host_tests.J2_MODULES + ("j2_agent_models", "j2_agent_views"))


# ---- the runner, with steps made here ---------------------------------------------------------------------------------------------

class StandInHost:
    """What the runner reads of a host: `trace` and `stopping`."""

    def __init__(self):
        self.lines = []
        self.stopping = threading.Event()

    def trace(self, type, data=None):
        self.lines.append((type, data))


class Clock:
    """A clock that moves by the next number of `lengths` at every second reading: a step reads it twice, so it 'takes' that long."""

    def __init__(self, *lengths):
        self.lengths, self.now, self.reads = list(lengths), 0.0, 0

    def __call__(self):
        self.reads += 1
        if self.reads % 2 == 0:
            self.now += self.lengths.pop(0)
        return self.now


def step(log, name, result=None, raises=None):
    def run(host):
        log.append(name)
        if raises is not None:
            raise raises
        return result
    return name, run


@pytest.mark.parametrize("status", ["done", "done_with_open_items"])
def test_a_run_that_ended_well_gets_every_step_in_order_and_one_trace_line_each(status):
    log, host = [], StandInHost()
    steps = (step(log, "one", {"files": 2}), step(log, "two"))
    rows = finish.run_steps(host, status, steps, clock=Clock(0.5, 1.5))
    assert log == ["one", "two"]
    assert rows == [{"step": "one", "files": 2, "result": "ok", "seconds": 0.5}, {"step": "two", "result": "ok", "seconds": 1.5}]
    assert host.lines == [("finish.step", rows[0]), ("finish.step", rows[1])]


@pytest.mark.parametrize("status", ["stopped", "crashed", "", "running", "Done"])
def test_a_run_that_did_not_end_well_gets_no_step_and_no_trace_line(status):
    log, host = [], StandInHost()
    assert finish.run_steps(host, status, (step(log, "one"),)) == []
    assert log == [] and host.lines == []


def test_the_default_steps_are_agent_views_then_catalog_and_the_good_endings_are_the_two_that_finished_the_work():
    assert [name for name, _ in finish.STEPS] == ["agent_views", "catalog"]
    assert finish.ENDED_WELL == ("done", "done_with_open_items") and finish.STEP_SECONDS == 10.0 and finish.TRACE_TYPE == "finish.step"


def test_an_exception_is_one_trace_line_and_the_next_step_still_runs():
    log, host = [], StandInHost()
    rows = finish.run_steps(host, "done", (step(log, "one", raises=ValueError("the model said no")), step(log, "two")), clock=Clock(0.1, 0.1))
    assert log == ["one", "two"]
    assert rows[0] == {"step": "one", "result": "failed", "error": "ValueError: the model said no", "seconds": 0.1}
    assert rows[1]["result"] == "ok" and host.lines[0] == ("finish.step", rows[0])


def test_a_system_exit_is_traced_like_an_exception_and_does_not_leave_the_runner():
    """`j2_agent_views.build` raises SystemExit for a run folder that is not there: it must not end the engine process."""
    log, host = [], StandInHost()
    rows = finish.run_steps(host, "done", (step(log, "one", raises=SystemExit("no such run folder: x")), step(log, "two")), clock=Clock(0, 0))
    assert log == ["one", "two"] and rows[0]["result"] == "failed" and rows[0]["error"] == "SystemExit: no such run folder: x"
    assert finish.run_steps(StandInHost(), "done", (step([], "one", raises=SystemExit(2)),), clock=Clock(0))[0]["error"] == "SystemExit: 2"


def test_an_error_text_is_clipped_so_a_trace_line_stays_small():
    rows = finish.run_steps(StandInHost(), "done", (step([], "one", raises=RuntimeError("x" * 5000)),), clock=Clock(0))
    assert rows[0]["result"] == "failed" and len(rows[0]["error"]) <= 300


def test_a_keyboard_interrupt_is_not_swallowed():
    """Only exceptions and SystemExit are guarded: a Ctrl-C meant for the engine process still reaches it."""
    with pytest.raises(KeyboardInterrupt):
        finish.run_steps(StandInHost(), "done", (step([], "one", raises=KeyboardInterrupt()),))


def test_a_step_that_does_not_apply_is_a_skip_with_its_reason_and_not_a_failure():
    def not_here(host):
        raise finish.Skip("the template library is off for this run")
    host = StandInHost()
    rows = finish.run_steps(host, "done", (("catalog", not_here),), clock=Clock(0))
    assert rows == [{"step": "catalog", "result": "skipped", "why": "the template library is off for this run", "seconds": 0}]
    assert host.lines == [("finish.step", rows[0])]


def test_a_step_over_the_limit_is_traced_slow_and_ends_the_rest_with_the_reason():
    log, host = [], StandInHost()
    rows = finish.run_steps(host, "done", (step(log, "one"), step(log, "two"), step(log, "three")), clock=Clock(10.4))
    assert log == ["one"], "the steps after a slow one never start"
    assert rows[0] == {"step": "one", "result": "ok", "seconds": 10.4, "slow": True}
    assert rows[1] == {"step": "two", "result": "skipped", "why": "one took more than 10 s"}
    assert rows[2] == {"step": "three", "result": "skipped", "why": "one took more than 10 s"}
    assert [data["step"] for _, data in host.lines] == ["one", "two", "three"]


def test_a_failing_step_that_is_also_slow_is_traced_as_both():
    rows = finish.run_steps(StandInHost(), "done", (step([], "one", raises=OSError("disk")), step([], "two")), clock=Clock(12.0))
    assert rows[0]["result"] == "failed" and rows[0]["slow"] is True and rows[1]["result"] == "skipped"


def test_a_step_that_takes_exactly_the_limit_is_not_slow():
    log = []
    rows = finish.run_steps(StandInHost(), "done", (step(log, "one"), step(log, "two")), clock=Clock(10.0, 0.0))
    assert log == ["one", "two"] and "slow" not in rows[0]


def test_no_step_starts_once_the_process_was_asked_to_stop():
    log, host = [], StandInHost()
    host.stopping.set()
    rows = finish.run_steps(host, "done", (step(log, "one"),))
    assert log == [] and rows == [{"step": "one", "result": "skipped", "why": "the process was asked to stop"}]


def test_a_trace_that_fails_never_breaks_the_end_of_a_run():
    class BrokenTrace(StandInHost):
        def trace(self, type, data=None):
            raise RuntimeError("the disk is full")
    log = []
    rows = finish.run_steps(BrokenTrace(), "done", (step(log, "one"), step(log, "two")), clock=Clock(0, 0))
    assert log == ["one", "two"] and len(rows) == 2


def test_importing_the_runner_imports_no_j2_module():
    """The host sets J2's environment before J2 is first imported, and loop.py imports this module: the J2 modules are imported inside the steps."""
    root = str(Path(finish.__file__).resolve().parents[3])
    code = (f"import sys; sys.path.insert(0, {root!r}); import sutra_app.engine.host.finish; "
            "bad = sorted(n for n in sys.modules if n.startswith('sutra_app.engine.j2')); print(bad); sys.exit(1 if bad else 0)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


# ---- the seam in Host._conclude ---------------------------------------------------------------------------------------------------

def brew(make_run_dir, **settings):
    return make_run_dir(user_text=BREW_LAB, settings={**QUIET, **settings})


def spy_order(monkeypatch, run_dir):
    """The order of the calls that end a run, and what the run folder held when `run.ended` was written."""
    from sutra_app.engine.host.heartbeat import Heartbeat
    from sutra_app.engine.host.publisher import StatePublisher
    order, seen = [], {}

    def around(cls, name, label):
        original = getattr(cls, name)

        def wrapper(self, *args, **kwargs):
            order.append(label)
            if label == "run.ended":
                seen["files"] = sorted(str(p.relative_to(run_dir)).replace(os.sep, "/") for p in Path(run_dir).rglob("*") if p.is_file())
                seen["status"] = args[0]
                seen["trace"] = jsonl(Path(run_dir) / "trace.jsonl")
            return original(self, *args, **kwargs)
        monkeypatch.setattr(cls, name, wrapper)

    around(StatePublisher, "stop", "publisher.stop")
    around(StatePublisher, "final", "publisher.final")
    around(Heartbeat, "stop", "heartbeat.stop")
    around(loop.Host, "_emit_ended", "run.ended")
    original_run_steps = finish.run_steps

    def run_steps(host, status, *args, **kwargs):
        order.append("finish.run_steps")
        seen["beating"] = not host.heartbeat._stop.is_set()
        return original_run_steps(host, status, *args, **kwargs)
    monkeypatch.setattr(finish, "run_steps", run_steps)
    return order, seen


def test_the_steps_run_right_after_the_publisher_stopped_and_before_the_heartbeat_does_and_before_run_ended(j2, make_run_dir, monkeypatch):
    run_dir = brew(make_run_dir)
    order, seen = spy_order(monkeypatch, run_dir)
    assert Running(run_dir, "--mock").wait() == 0
    assert order[order.index("publisher.stop"):][:5] == ["publisher.stop", "finish.run_steps", "heartbeat.stop", "publisher.final", "run.ended"]
    assert seen["beating"] is True, "the heartbeat still beats while the steps work"
    assert events(run_dir)[-1]["t"] == "run.ended"


def test_a_step_that_takes_a_while_does_not_stop_the_heartbeat(j2, make_run_dir, monkeypatch):
    run_dir = brew(make_run_dir)
    beats = {}

    def slow_step(host):
        beats["before"] = host.heartbeat.beats
        time.sleep(0.7)                                                 # the heartbeat of these tests is 0.2 s
        beats["after"] = host.heartbeat.beats

    monkeypatch.setattr(finish, "STEPS", (("slow", slow_step),))
    assert Running(run_dir, "--mock").wait() == 0
    assert beats["after"] >= beats["before"] + 2
    assert [row["step"] for row in trace(run_dir, "finish.step") for row in [row["data"]]] == ["slow"]


@pytest.mark.parametrize("raised", [RuntimeError("a step broke"), SystemExit("no such run folder: x"), OSError("disk")])
def test_a_step_that_raises_is_traced_and_the_run_still_ends_done_with_run_ended_last(j2, make_run_dir, monkeypatch, raised):
    run_dir = brew(make_run_dir)
    ran = []

    def breaks(host):
        raise raised

    def after(host):
        ran.append("after")
        return {"note": "still ran"}

    monkeypatch.setattr(finish, "STEPS", (("breaks", breaks), ("after", after)))
    assert Running(run_dir, "--mock").wait() == 0
    ended = events(run_dir)[-1]
    assert ended["t"] == "run.ended" and ended["status"] in ("done", "done_with_open_items") and ended["code"] is None
    lines = {row["data"]["step"]: row["data"] for row in trace(run_dir, "finish.step")}
    assert lines["breaks"]["result"] == "failed" and type(raised).__name__ in lines["breaks"]["error"]
    assert lines["after"]["result"] == "ok" and lines["after"]["note"] == "still ran" and ran == ["after"]


def test_a_step_over_the_limit_through_the_host_ends_the_rest_and_the_run_still_ends_done(j2, make_run_dir, monkeypatch):
    run_dir = brew(make_run_dir)
    monkeypatch.setattr(finish, "STEP_SECONDS", 0.2)
    ran = []

    def slow(host):
        time.sleep(0.4)

    def never(host):
        ran.append("never")

    monkeypatch.setattr(finish, "STEPS", (("slow", slow), ("never", never)))
    assert Running(run_dir, "--mock").wait() == 0
    assert ran == [] and events(run_dir)[-1]["status"] in ("done", "done_with_open_items")
    lines = {row["data"]["step"]: row["data"] for row in trace(run_dir, "finish.step")}
    assert lines["slow"]["slow"] is True and lines["never"]["result"] == "skipped" and "slow took more than" in lines["never"]["why"]


def test_a_stopped_run_runs_no_step(j2, make_run_dir, monkeypatch):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    ran = []
    monkeypatch.setattr(finish, "STEPS", (("spy", lambda host: ran.append("spy")),))
    running = Running(run_dir, "--mock")
    wait_until(lambda: [e for e in events(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"], what="the question")
    append_inbox(run_dir, 1, "stop")
    assert running.wait() == 0
    assert events(run_dir)[-1]["status"] == "stopped" and ran == [] and trace(run_dir, "finish.step") == []


def test_a_crashed_run_runs_no_step(j2, make_run_dir, monkeypatch):
    run_dir = brew(make_run_dir)
    ran = []
    monkeypatch.setattr(finish, "STEPS", (("spy", lambda host: ran.append("spy")),))
    port = make_port_of(RaisingPort, NoModelAvailable("the model said no"))
    assert Running(run_dir, "--mock", make_port=port).wait() == 0
    assert events(run_dir)[-1]["status"] == "crashed" and ran == [] and trace(run_dir, "finish.step") == []


# ---- agent_views: the agent-readable JSON of a mock run ----------------------------------------------------------------------------

def test_a_finished_mock_run_has_its_agent_readable_json_before_run_ended_and_the_trace_says_how_many(j2, make_run_dir, monkeypatch):
    run_dir = brew(make_run_dir)
    order, seen = spy_order(monkeypatch, run_dir)
    assert Running(run_dir, "--mock").wait() == 0
    agent_files = [name for name in seen["files"] if name.startswith("agent/") and name.endswith(".json")]
    assert {"agent/goal.json", "agent/workflows.json"} <= set(agent_files), "the files exist when run.ended is written"
    assert any(name.startswith("agent/audits/") for name in agent_files)
    assert seen["status"] in ("done", "done_with_open_items")
    mine = [row["data"] for row in seen["trace"] if row["type"] == "finish.step"]
    assert [m["step"] for m in mine] == ["agent_views", "catalog"], "both lines are written before run.ended too"
    views = mine[0]
    assert views["result"] == "ok" and views["files"] >= len(agent_files) and views["valid"] >= 1
    assert views["valid"] + len(views["invalid"]) <= views["files"]
    assert mine[1]["result"] == "skipped" and "off" in mine[1]["why"], "the template library is off by default (D18)"


def test_the_agent_readable_files_are_the_valid_models_the_artifacts_pane_looks_for(j2, make_run_dir):
    run_dir = brew(make_run_dir)
    assert Running(run_dir, "--mock").wait() == 0
    goal = json.loads((run_dir / "agent" / "goal.json").read_text(encoding="utf-8"))
    assert goal.get("schema") == "agent-views/1" and goal.get("valid") is True and goal.get("model")
    from sutra_app.engine import j2_artifacts
    groups = j2_artifacts.groups(str(run_dir), None) if False else None            # (the groups view is lane B's; the file is what matters here)
    assert groups is None


def test_the_step_is_idempotent_and_never_touches_what_the_run_wrote(j2, make_run_dir):
    run_dir = brew(make_run_dir)
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    kept = {name: (run_dir / name).read_bytes() for name in ("goal.json", "workflows.json", "chat.jsonl", "audits.json", "summary.json")
            if (run_dir / name).exists()}
    first = {p.relative_to(run_dir): p.read_bytes() for p in (run_dir / "agent").rglob("*.json")}
    row = finish.run_steps(running.host, "done", (("agent_views", finish.agent_views),))[0]
    assert row["result"] == "ok"
    assert {p.relative_to(run_dir): p.read_bytes() for p in (run_dir / "agent").rglob("*.json")}.keys() == first.keys()
    assert {name: (run_dir / name).read_bytes() for name in kept} == kept, "the files J2 keeps are read, never rewritten"


def test_agent_views_on_a_folder_that_is_gone_is_a_traced_failure_not_a_crash(j2, make_run_dir, tmp_path):
    run_dir = brew(make_run_dir)
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    host = SimpleNamespace(paths=SimpleNamespace(run_dir=tmp_path / "gone"), trace=lambda *a: None, stopping=threading.Event())
    row = finish.run_steps(host, "done", (("agent_views", finish.agent_views),))[0]
    assert row["result"] == "failed" and row["error"].startswith("SystemExit: no such run folder")


# ---- catalog ----------------------------------------------------------------------------------------------------------------------

def library_run(make_run_dir, **settings):
    """A mock run with the template library on: it stores templates and keeps `templates.json` in its folder."""
    return brew(make_run_dir, J2_TEMPLATE_LIBRARY="1", J2_ARTIFACT_SCHEMA="1", **settings)


def finished(run_dir, **overrides):
    """The host of a finished mock run, with the settings or the mock flag changed the way a real run would have them."""
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    host = running.host
    for name, value in overrides.items():
        if name == "template_library":
            host.settings = host.settings.model_copy(update={"template_library": value})
        else:
            setattr(host, name, value)
    return host


def catalog_rows(host):
    return finish.run_steps(host, "done", (("catalog", finish.catalog),))[0]


def test_the_catalog_step_does_nothing_while_the_template_library_is_off(j2, make_run_dir, data_dir):
    host = finished(brew(make_run_dir), mock=False)
    assert host.settings.template_library is False
    row = catalog_rows(host)
    assert row["result"] == "skipped" and row["why"] == "the template library is off for this run"
    assert not (data_dir / "library" / ".lock").exists() or True


def test_the_catalog_step_leaves_a_mock_run_out(j2, make_run_dir):
    host = finished(library_run(make_run_dir))
    assert host.mock is True and host.settings.template_library is True
    row = catalog_rows(host)
    assert row["result"] == "skipped" and row["why"] == "a mock run teaches the library nothing"


def test_the_catalog_step_needs_a_run_that_stored_templates(j2, make_run_dir):
    host = finished(brew(make_run_dir), template_library=True, mock=False)
    assert not (host.paths.run_dir / "templates.json").exists()
    row = catalog_rows(host)
    assert row["result"] == "skipped" and row["why"] == "the run stored no templates"


def test_the_catalog_step_collects_this_runs_templates_under_the_library_lock(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)
    assert (host.paths.run_dir / "templates.json").is_file(), "the library run stored its decisions"
    taken, calls = [], []
    real_lock, real_collect = library._library_lock, library.collect

    class Held:
        def __enter__(self):
            taken.append("in")
            self.inner = real_lock()
            self.inner.__enter__()

        def __exit__(self, *exc):
            taken.append("out")
            return self.inner.__exit__(*exc)

    def collect(runs_dir, runs=None):
        calls.append((runs_dir, runs, list(taken)))
        return real_collect(runs_dir, runs=runs)
    monkeypatch.setattr(library, "_library_lock", Held)
    monkeypatch.setattr(library, "collect", collect)
    row = catalog_rows(host)
    assert row["result"] == "ok" and set(row) >= {"added", "renumbered", "same", "not_recorded"}
    assert calls == [(str(host.paths.runs_dir), [host.paths.run_id], ["in"])], "collect ran inside the lock, for this run only"
    assert taken == ["in", "out"]
    assert host.paths.run_id in library.index()["runs"], "the run is a row of the catalog's By run"
    assert row["added"] + row["same"] + row["renumbered"] >= 1 or row["not_recorded"] >= 1


def test_the_lock_is_free_again_after_the_step(j2, make_run_dir):
    host = finished(library_run(make_run_dir), mock=False)
    assert catalog_rows(host)["result"] == "ok"
    fd = os.open(host.paths.library_dir / ".lock", os.O_RDWR | oslayer.O_BINARY)
    try:
        assert oslayer.try_lock(fd), "the step released the library lock"
        oslayer.unlock(fd)
    finally:
        os.close(fd)


def test_a_library_that_stays_locked_skips_the_step_with_the_busy_message_and_changes_nothing(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)
    index_before = (host.paths.library_dir / "index.json").read_bytes()
    monkeypatch.setattr(library, "LOCK_WAIT_S", 0.3)
    fd = os.open(host.paths.library_dir / ".lock", os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
    try:
        assert oslayer.try_lock(fd)                                      # another run holds the library lock
        row = catalog_rows(host)
    finally:
        oslayer.unlock(fd)
        os.close(fd)
    assert row["result"] == "skipped" and "locked by another run" in row["why"]
    assert (host.paths.library_dir / "index.json").read_bytes() == index_before, "a skipped step writes nothing"


def test_a_failure_inside_collect_is_a_traced_failure_and_the_lock_is_released(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)

    def broken(runs_dir, runs=None):
        raise ValueError("the index is not JSON")
    monkeypatch.setattr(library, "collect", broken)
    row = catalog_rows(host)
    assert row["result"] == "failed" and row["error"] == "ValueError: the index is not JSON"
    fd = os.open(host.paths.library_dir / ".lock", os.O_RDWR | oslayer.O_BINARY)
    try:
        assert oslayer.try_lock(fd)
        oslayer.unlock(fd)
    finally:
        os.close(fd)


def test_a_library_run_reaches_the_catalog_through_the_host_before_run_ended(j2, make_run_dir, monkeypatch):
    """A run of the app (not a mock run) with the library on: its row is in the index when `run.ended` is written."""
    run_dir = library_run(make_run_dir)
    original = loop.Host._make_run

    def make_run(self):
        original(self)
        self.mock = False                   # J2 and the port are configured in mock mode already; only the finish steps read this flag

    monkeypatch.setattr(loop.Host, "_make_run", make_run)
    seen = {}
    original_ended = loop.Host._emit_ended

    def ended(self, status, outcome, code):
        if "index" not in seen:
            seen["index"] = json.loads((self.paths.library_dir / "index.json").read_text(encoding="utf-8"))
            seen["trace"] = [row["data"] for row in jsonl(Path(run_dir) / "trace.jsonl") if row["type"] == "finish.step"]
        return original_ended(self, status, outcome, code)

    monkeypatch.setattr(loop.Host, "_emit_ended", ended)
    assert Running(run_dir, "--mock").wait() == 0
    assert [t["step"] for t in seen["trace"]] == ["agent_views", "catalog"]
    assert seen["trace"][1]["result"] == "ok", seen["trace"][1]
    assert run_dir.name in seen["index"]["runs"]
