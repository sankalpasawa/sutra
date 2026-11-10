"""The steps at the end of a run (J2 sync 4, lane D2, D142 and D143): the guarded runner, the `agent_views` step, the `catalog` step and the
one call in `Host._conclude` that runs them.

The runner is proved with steps made here and a stand-in host. The two real steps are proved on this tree's own mock runs: a Brew Lab run
in the host (J2's mock mode, Chrome faked) writes the run folder, and the steps read it. A mock run is left out of the catalog by design, so
the catalog step is also called on the host of a finished mock run with its `mock` flag turned off, and one run with the template library on
is carried through the host with the flag turned off after J2 was configured (only the finish steps read it).
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
    BREW_LAB, QUIET, VAGUE, RaisingPort, Running, append_inbox, events, j2, jsonl, make_port_of, trace, wait_until,
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


def finish_lines(run_dir):
    return [row["data"] for row in trace(run_dir, "finish.step")]


def spy_order(monkeypatch, run_dir):
    """The order of the calls that end a run, and what the run folder and its trace held when `run.ended` was written."""
    from sutra_app.engine.host.heartbeat import Heartbeat
    from sutra_app.engine.host.publisher import StatePublisher
    order, seen = [], {}

    def around(cls, name, label):
        original = getattr(cls, name)

        def wrapper(self, *args, **kwargs):
            order.append(label)
            if label == "run.ended" and "files" not in seen:
                seen["files"] = sorted(str(p.relative_to(run_dir)).replace(os.sep, "/") for p in Path(run_dir).rglob("*") if p.is_file())
                seen["status"] = args[0]
                seen["trace"] = [row["data"] for row in jsonl(Path(run_dir) / "trace.jsonl") if row["type"] == "finish.step"]
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
    assert [line["step"] for line in finish_lines(run_dir)] == ["slow"]


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
    lines = {line["step"]: line for line in finish_lines(run_dir)}
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
    lines = {line["step"]: line for line in finish_lines(run_dir)}
    assert lines["slow"]["slow"] is True and lines["never"]["result"] == "skipped" and "slow took more than" in lines["never"]["why"]


def test_a_stopped_run_gets_no_step_and_no_file_from_one(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: [e for e in events(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"], what="the question")
    append_inbox(run_dir, 1, "stop")
    assert running.wait() == 0
    assert events(run_dir)[-1]["status"] == "stopped"
    assert finish_lines(run_dir) == [] and not (run_dir / "agent").exists()


def test_a_crashed_run_gets_no_step_and_no_file_from_one(j2, make_run_dir):
    run_dir = brew(make_run_dir)
    port = make_port_of(RaisingPort, NoModelAvailable("the model said no"))
    assert Running(run_dir, "--mock", make_port=port).wait() == 0
    assert events(run_dir)[-1]["status"] == "crashed"
    assert finish_lines(run_dir) == [] and not (run_dir / "agent").exists()


# ---- agent_views: the agent-readable JSON of a mock run ----------------------------------------------------------------------------

def test_a_finished_mock_run_has_its_agent_readable_json_before_run_ended_and_the_trace_says_how_many(j2, make_run_dir, monkeypatch):
    run_dir = brew(make_run_dir)
    order, seen = spy_order(monkeypatch, run_dir)
    assert Running(run_dir, "--mock").wait() == 0
    assert seen["status"] in ("done", "done_with_open_items")
    agent_files = {name for name in seen["files"] if name.startswith("agent/") and name.endswith(".json")}
    assert {"agent/goal.json", "agent/workflows.json", "agent/receipts.json", "agent/conditions.json", "agent/audits/A-1.json"} <= agent_files, \
        "the files were there when run.ended was written"
    assert any(name.startswith("site/sections/") for name in seen["files"]), "a website's sections get their JSON too"
    assert [line["step"] for line in seen["trace"]] == ["agent_views", "catalog"], "both lines were written before run.ended too"
    views, library = seen["trace"]
    assert views["result"] == "ok" and views["valid"] >= len(agent_files) and views["files"] == views["valid"] + len(views["invalid"])
    assert library["result"] == "skipped" and library["why"] == "the template library is off for this run", "the library is off by default (D18)"


def test_the_artifacts_pane_finds_the_validated_json_of_a_run_of_the_app(j2, make_run_dir):
    """`j2_artifacts.agent_view` is the one place that picks a row's Agent-readable file: after the step it names agent-views/1 and a model."""
    run_dir = brew(make_run_dir)
    assert Running(run_dir, "--mock").wait() == 0
    from sutra_app.engine import j2_artifacts
    charter = j2_artifacts.agent_view(str(run_dir), {"kind": "charter", "id": "goal", "file": "goal.json"})
    assert charter == {"format": "json", "file": "agent/goal.json", "schema": "agent-views/1", "model": "Charter", "valid": True}
    audit = json.loads((run_dir / "agent" / "audits" / "A-1.json").read_text(encoding="utf-8"))
    assert (audit["schema"], audit["model"], audit["valid"], audit["errors"]) == ("agent-views/1", "AuditResult", True, [])
    (run_dir / "agent" / "goal.json").unlink()                           # without the file the tab falls back to the run's own JSON, unvalidated
    assert j2_artifacts.agent_view(str(run_dir), {"kind": "charter", "id": "goal", "file": "goal.json"}) == {
        "format": "json", "file": "goal.json", "schema": None, "model": None, "valid": None}


def test_the_step_reads_what_the_run_kept_and_a_second_pass_changes_nothing(j2, make_run_dir):
    run_dir = brew(make_run_dir)
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    kept = {name: (run_dir / name).read_bytes() for name in ("goal.json", "workflows.json", "chat.jsonl", "audits.json", "summary.json")}
    written = lambda: {p.relative_to(run_dir): p.read_bytes() for p in (run_dir / "agent").rglob("*.json")}   # noqa: E731
    first = written()
    assert first
    row = finish.run_steps(running.host, "done", (("agent_views", finish.agent_views),))[0]
    assert row["result"] == "ok"
    assert written() == first, "the same run gives the same files, byte for byte"
    assert {name: (run_dir / name).read_bytes() for name in kept} == kept, "the files J2 keeps are read, never rewritten"


def test_the_step_prints_nothing_to_the_engine_log(j2, make_run_dir, capsys):
    """`build` prints a table unless it is asked to be quiet; the engine's standard output is the run's log file."""
    run_dir = brew(make_run_dir)
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    capsys.readouterr()
    assert finish.run_steps(running.host, "done", (("agent_views", finish.agent_views),))[0]["result"] == "ok"
    assert capsys.readouterr().out == ""


def test_agent_views_on_a_folder_that_is_gone_is_a_traced_failure_not_a_crash(tmp_path):
    host = SimpleNamespace(paths=SimpleNamespace(run_dir=tmp_path / "gone"), trace=lambda *args: None, stopping=threading.Event())
    row = finish.run_steps(host, "done", (("agent_views", finish.agent_views),))[0]
    assert row["result"] == "failed" and row["error"].startswith("SystemExit: no such run folder")


# ---- catalog ----------------------------------------------------------------------------------------------------------------------

def library_run(make_run_dir):
    """A mock run with the template library on: it stores templates in the library and keeps its decisions in `templates.json`."""
    return brew(make_run_dir, J2_TEMPLATE_LIBRARY="1", J2_ARTIFACT_SCHEMA="1")


def finished(run_dir, *, mock=True, template_library=None):
    """The host of a finished mock run, with the mock flag or the library setting changed the way another run would have them."""
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    host = running.host
    host.mock = mock
    if template_library is not None:
        host.settings = host.settings.model_copy(update={"template_library": template_library})
    return host


def catalog_row(host):
    return finish.run_steps(host, "done", (("catalog", finish.catalog),))[0]


def hold_the_library_lock(host):
    fd = os.open(host.paths.library_dir / ".lock", os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
    assert oslayer.try_lock(fd)
    return fd


def release(fd):
    oslayer.unlock(fd)
    os.close(fd)


def assert_the_library_lock_is_free(host):
    fd = os.open(host.paths.library_dir / ".lock", os.O_RDWR | oslayer.O_BINARY)
    try:
        assert oslayer.try_lock(fd), "the library lock is free"
        oslayer.unlock(fd)
    finally:
        os.close(fd)


def test_the_catalog_step_does_nothing_while_the_template_library_is_off(j2, make_run_dir):
    host = finished(brew(make_run_dir), mock=False)
    assert host.settings.template_library is False
    row = catalog_row(host)
    assert row["result"] == "skipped" and row["why"] == "the template library is off for this run"


def test_the_catalog_step_leaves_a_mock_run_out(j2, make_run_dir):
    host = finished(library_run(make_run_dir))
    assert host.mock is True and host.settings.template_library is True
    index_before = (host.paths.library_dir / "index.json").read_bytes()
    row = catalog_row(host)
    assert row["result"] == "skipped" and row["why"] == "a mock run teaches the library nothing"
    assert (host.paths.library_dir / "index.json").read_bytes() == index_before


def test_the_catalog_step_needs_a_run_that_stored_templates_and_then_neither_locks_nor_rewrites_the_library(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(brew(make_run_dir), mock=False, template_library=True)
    assert not (host.paths.run_dir / "templates.json").exists()
    monkeypatch.setattr(library, "_library_lock", lambda: pytest.fail("the lock is taken for a run with nothing to collect"))
    index_before = (host.paths.library_dir / "index.json").read_bytes()
    row = catalog_row(host)
    assert row["result"] == "skipped" and row["why"] == "the run stored no templates"
    assert (host.paths.library_dir / "index.json").read_bytes() == index_before


def test_the_catalog_step_collects_this_run_under_the_library_lock_and_the_catalog_gains_its_row_and_provenance(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)
    decisions = json.loads((host.paths.run_dir / "templates.json").read_text(encoding="utf-8"))["decisions"]
    specialised = [d for d in decisions if d.get("kind") == "specialised"]
    assert specialised, "the library run stored specialised templates"
    run_id = host.paths.run_id
    before = library.index()
    assert run_id not in before["runs"]
    version_meta = lambda d: json.loads((host.paths.library_dir / d["artifact"] / library.slug(d["section"]) / library.slug(d["template"]) /     # noqa: E731
                                         f"v{d['version']}" / "meta.json").read_text(encoding="utf-8"))
    assert "mock" not in version_meta(specialised[0]), "a version the run stored has no provenance yet"
    taken, calls = [], []
    real_lock, real_collect = library._library_lock, library.collect

    class Watched:
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
    monkeypatch.setattr(library, "_library_lock", Watched)
    monkeypatch.setattr(library, "collect", collect)
    row = catalog_row(host)
    assert calls == [(str(host.paths.runs_dir), [run_id], ["in"])], "collect ran inside the lock, for this run only"
    assert taken == ["in", "out"]
    assert row["result"] == "ok" and row["not_recorded"] == 0
    assert row["added"] + row["renumbered"] + row["same"] == len(specialised), "every specialised decision reached the catalog"
    after = library.index()
    assert after["runs"][run_id]["run"] == run_id and after["runs"][run_id]["mock"] is True and after["runs"][run_id]["business"] == "Brew Lab"
    assert len(after["runs"]) == len(before["runs"]) + 1, "the run is one more row of the catalog's By run"
    meta = version_meta(specialised[0])
    assert meta["mock"] is True and meta["business"]["name"] == "Brew Lab" and meta["made_by"]["date"] == "2026-11-04 10:00:04"
    assert any(use["run"] == run_id for use in meta["used_by"])
    assert_the_library_lock_is_free(host)


def test_a_second_pass_over_the_same_run_changes_nothing(j2, make_run_dir):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)
    first = catalog_row(host)
    index = library.index()
    again = catalog_row(host)
    assert first["result"] == again["result"] == "ok" and (again["added"], again["renumbered"]) == (0, 0)
    assert library.index() == index


def test_a_library_that_stays_locked_skips_the_step_with_the_busy_message_and_changes_nothing(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)
    index_before = (host.paths.library_dir / "index.json").read_bytes()
    monkeypatch.setattr(library, "LOCK_WAIT_S", 0.3)
    fd = hold_the_library_lock(host)                                     # another run holds the library lock
    try:
        row = catalog_row(host)
    finally:
        release(fd)
    assert row["result"] == "skipped" and "locked by another run" in row["why"] and "waited 0.3 s" in row["why"]
    assert (host.paths.library_dir / "index.json").read_bytes() == index_before, "a skipped step writes nothing"
    assert catalog_row(host)["result"] == "ok", "the next try, with the lock free, collects"


def test_a_lock_that_is_freed_in_time_lets_the_step_wait_and_finish(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)
    monkeypatch.setattr(library, "LOCK_WAIT_S", 10.0)
    fd = hold_the_library_lock(host)
    rows = []
    worker = threading.Thread(target=lambda: rows.append(catalog_row(host)), daemon=True)
    worker.start()
    time.sleep(0.4)
    assert worker.is_alive() and rows == [], "the step waits for the other writer"
    release(fd)
    worker.join(10)
    assert rows[0]["result"] == "ok" and rows[0]["seconds"] >= 0.3


def test_a_failure_inside_collect_is_a_traced_failure_and_the_lock_is_released(j2, make_run_dir, monkeypatch):
    from sutra_app.engine import j2_template_lib as library
    host = finished(library_run(make_run_dir), mock=False)

    def broken(runs_dir, runs=None):
        raise ValueError("the index is not JSON")
    monkeypatch.setattr(library, "collect", broken)
    row = catalog_row(host)
    assert row["result"] == "failed" and row["error"] == "ValueError: the index is not JSON"
    assert_the_library_lock_is_free(host)


def test_a_run_of_the_app_with_the_library_on_reaches_the_catalog_through_the_host_before_run_ended(j2, make_run_dir, monkeypatch):
    """Not a mock run (the flag is turned off once J2 and the port are configured in mock mode; only the finish steps read it): the run's
    row is in the catalog's index when `run.ended` is written, after the agent-readable files."""
    run_dir = library_run(make_run_dir)
    original = loop.Host._make_run

    def make_run(self):
        original(self)
        self.mock = False

    monkeypatch.setattr(loop.Host, "_make_run", make_run)
    seen = {}
    original_ended = loop.Host._emit_ended

    def ended(self, status, outcome, code):
        if "index" not in seen:
            seen["index"] = json.loads((self.paths.library_dir / "index.json").read_text(encoding="utf-8"))
            seen["trace"] = finish_lines(run_dir)
            seen["agent"] = (run_dir / "agent" / "goal.json").is_file()
        return original_ended(self, status, outcome, code)

    monkeypatch.setattr(loop.Host, "_emit_ended", ended)
    assert Running(run_dir, "--mock").wait() == 0
    assert [line["step"] for line in seen["trace"]] == ["agent_views", "catalog"]
    assert seen["trace"][1]["result"] == "ok" and seen["trace"][1]["not_recorded"] == 0
    assert run_dir.name in seen["index"]["runs"] and seen["agent"] is True
    assert events(run_dir)[-1]["t"] == "run.ended"
