"""The engine host process, in-process (work package E3, engine design 4.5 to 4.7, flows F1, F4, F5, F7).

`Host` runs in a thread of this process on a temp run folder in mock mode, with J2's Chrome checks faked (as J2's own `--fast`
flow does) and a scripted inbox. Because J2 reads its environment when it is imported, each test imports the vendored J2 anew
(`fresh_j2`) and puts the modules and the environment back afterwards. Helpers here are imported by the other host test files
(`from test_engine_host import ...`; this folder has no __init__.py, so pytest puts it on sys.path).
"""
import contextlib
import importlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from sutra_app.engine import llm
from sutra_app.engine.host import loop
from sutra_app.engine.host.heartbeat import Heartbeat, heartbeat_interval
from sutra_app.engine.host.inbox import Inbox, InboxTailer
from sutra_app.engine.port import PreflightResult
from sutra_app.library.types import overhead_atom_id
from sutra_app.orchestrator.models import parse_event

ENGINE = "sutra_app.engine"
J2_MODULES = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change",
              "j2_check", "j2_map", "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_studio", "j2_template_lib",
              "rehydrate")
BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the "
            "farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).")
VAGUE = ["a website for my cafe",
         "It's called Little Fig, in Koramangala, Bengaluru. Visitors should see our menu with prices, opening hours and "
         "where to find us. Cozy and simple, and it must work on phones.",
         "Option 2: skip the stories, keep the reserve for fixes."]
QUIET = {"J2_MEMORY": "0", "J2_REALIZATION": "0"}        # task settings: no lessons file, no realization plan: fast and plain


# ---- J2 and the environment ------------------------------------------------------------------------------------------
def fake_check(j2_check, html):
    """J2's --fast stub: the render check without a browser."""
    st = j2_check.static_checks(html)
    return {"available": True, **st, "phone": {"width": 360, "overflow_px": 0}, "desktop": {"width": 1280, "overflow_px": 0},
            "js_errors": [], "design": {}, "form_results": [{"index": i + 1, "has_submit": True, "submitted": True, "invalid": [],
                                                           "errors_during": [], "ok": True} for i in range(st["forms"])]}


def fake_chrome(j2_check) -> None:
    """Patch the render checks of an imported `j2_check` (the engine process of the process tests does it from a hook factory)."""
    j2_check.find_chrome = lambda: None
    j2_check.tap_targets = lambda html, selector, min_px=44: {"available": True, "roots": 1, "checked": 0, "small_count": 0,
                                                              "small": []}
    j2_check.check = lambda html: fake_check(j2_check, html)


@contextlib.contextmanager
def fresh_j2(base: Path):
    """Import the vendored J2 anew in mock mode with Chrome faked; put the modules and the environment back afterwards."""
    package = importlib.import_module(ENGINE)
    saved = {name: (sys.modules.pop(f"{ENGINE}.{name}", None), package.__dict__.pop(name, None)) for name in J2_MODULES}
    with pytest.MonkeyPatch.context() as mp:
        for name in list(os.environ):
            if name.startswith(("J2_", "STUDIO_")):
                mp.delenv(name)
        for key, value in {"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_MEMORY_FILE": str(base / "lessons.jsonl"),
                           "J2_PLAYBOOK_FILE": str(base / "playbooks.jsonl"), "J2_RUNS_DIR": str(base / "runs"),
                           "J2_LIBRARY_DIR": str(base / "library")}.items():
            mp.setenv(key, value)
        mp.setattr(llm, "MOCK", True)
        try:
            mod = importlib.import_module(f"{ENGINE}.j2")
            fake_chrome(mod.j2_check)
            yield mod
        finally:
            for name, (old, attr) in saved.items():
                sys.modules.pop(f"{ENGINE}.{name}", None)
                package.__dict__.pop(name, None)
                if old is not None:
                    sys.modules[f"{ENGINE}.{name}"] = old
                if attr is not None:
                    package.__dict__[name] = attr


@pytest.fixture
def j2(tmp_path, clean_env, llm_reset):
    saved = dict(os.environ)
    clean_env.setenv("SUTRA_HEARTBEAT_S", "0.2")
    clean_env.setenv("SUTRA_NODES", "off")                 # the function-node layer is not part of this package
    clean_env.setenv("SUTRA_ENV_FILE", str(tmp_path / "none.env"))
    with fresh_j2(tmp_path / "j2") as mod:
        yield mod
    os.environ.clear()
    os.environ.update(saved)


# ---- running a host ----------------------------------------------------------------------------------------------------
class Running:
    """A `Host` in a thread. `wait()` returns the exit code."""

    def __init__(self, run_dir: Path, *args: str, make_port=None):
        self.run_dir = Path(run_dir)
        self.host = loop.Host(loop._parse(["--run-dir", str(run_dir), *args]), make_port)
        self.code, self.error = None, None
        self.thread = threading.Thread(target=self._go, daemon=True)
        self.thread.start()

    def _go(self):
        try:
            self.code = self.host.execute()
        except BaseException as exc:  # noqa: BLE001
            self.error = exc

    def wait(self, timeout: float = 30.0) -> int:
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "the host did not finish"
        assert self.error is None, repr(self.error)
        return self.code


def jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def events(run_dir) -> list:
    return jsonl(Path(run_dir) / "events.jsonl")


def trace(run_dir, type=None) -> list:
    rows = jsonl(Path(run_dir) / "trace.jsonl")
    return [r for r in rows if type is None or r["type"] == type]


def chat(run_dir) -> list:
    return [m for m in jsonl(Path(run_dir) / "chat.jsonl") if not m.get("meta")]


def of(rows, t):
    return [e for e in rows if e["t"] == t]


def append_inbox(run_dir, n, kind, **fields) -> None:
    with open(Path(run_dir) / "inbox.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"n": n, "kind": kind, "at": "2026-11-04T10:00:00Z", **fields}) + "\n")


def wait_until(check, timeout: float = 20.0, what: str = "the condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = check()
        if got:
            return got
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


class Answerer(threading.Thread):
    """Plays the owner: every `say` that asks the Requester is answered at once, the next text of `answers` each time."""

    def __init__(self, run_dir, answers, skip=0, n0=0):
        super().__init__(daemon=True)
        self.run_dir, self.answers, self.sent, self.skip, self.n = Path(run_dir), list(answers), 0, skip, n0
        self._stop_flag = threading.Event()
        self.start()

    def run(self):
        asked = self.skip
        while not self._stop_flag.is_set():
            rows = events(self.run_dir)
            if any(e["t"] == "run.ended" for e in rows):          # the run is over: this thread must not outlive it
                return
            questions = [e for e in rows if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"]
            while asked < len(questions):
                text = self.answers[min(asked - self.skip, len(self.answers) - 1)]
                asked += 1
                self.sent += 1
                self.n += 1
                append_inbox(self.run_dir, self.n, "user", text=text)
            time.sleep(0.005)

    def stop(self):
        self._stop_flag.set()


def make_port_of(cls, *args, **kw):
    """A `make_port` for the host: `cls(*args, usage_sink=sink, **kw)`."""
    return lambda *, sink, mock, task, paths: cls(*args, usage_sink=sink, **kw)


class CountingPort(llm.ScriptedPort):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.requests = 0

    def complete(self, req, on_progress=None):
        self.requests += 1
        return super().complete(req, on_progress)


class GatePort(llm.ScriptedPort):
    """Blocks every request until `release()`; `close()` also wakes a blocked request, which then fails like a killed CLI."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.gate, self.waiting = threading.Event(), threading.Event()

    def release(self):
        self.gate.set()

    def close(self):
        super().close()
        self.gate.set()

    def complete(self, req, on_progress=None):
        self.waiting.set()
        self.gate.wait(30)
        return super().complete(req, on_progress)


class RaisingPort(llm.ScriptedPort):
    def __init__(self, exc, *args, after=0, **kw):
        super().__init__(*args, **kw)
        self.exc, self.after, self.seen = exc, after, 0

    def complete(self, req, on_progress=None):
        self.seen += 1
        if self.seen > self.after:
            raise self.exc
        return super().complete(req, on_progress)


@pytest.fixture
def brew_dir(make_run_dir):
    return make_run_dir(user_text=BREW_LAB, settings=QUIET)


# ---- the happy path -----------------------------------------------------------------------------------------------------
def test_a_vague_brief_asks_the_owner_gets_the_answers_through_the_inbox_and_ends_with_run_ended(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    answerer = Answerer(run_dir, VAGUE[1:])
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    answerer.stop()
    rows = events(run_dir)
    assert rows[0]["t"] == "run.started" and rows[0]["seed"] == "none" and rows[0]["mock"] is True and rows[0]["pid"] == os.getpid()
    ask = next(e for e in rows if e["t"] == "say" and e.get("act") == "ASK_REQUESTER")
    assert ask["who"] == "identity" and ask["to_user"] is True and ask["questions"] and ask["questions"][0]["question"]
    assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items") and rows[-1]["code"] is None
    assert [e["t"] for e in rows].count("run.ended") == 1
    users = [m["text"] for m in chat(run_dir) if m["who"] == "user"]
    assert users[0] == VAGUE[0] and users[1:] == VAGUE[1:1 + answerer.sent], "every answer delivered once, none twice"
    assert not [e for e in rows if e["t"] == "say" and e["who"] == "user"], "the owner's own lines are never say events"
    for row in rows:
        parse_event(row, strict=True)                       # every line is one of the eight events, with exactly their fields


def test_every_model_request_is_one_usage_event_helper_calls_included(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings={**QUIET, "J2_REALIZATION": "1"})     # realization adds planner and judge calls
    port = {}

    def make(*, sink, mock, task, paths):
        port["p"] = CountingPort(usage_sink=sink)
        return port["p"]
    assert Running(run_dir, "--mock", make_port=make).wait() == 0
    usage = of(events(run_dir), "usage")
    assert len(usage) == port["p"].requests > 10
    assert {u["purpose"] for u in usage} >= {"agent_turn", "plan", "judge"}, "planner and judge calls are usage events too"
    assert len({u["call_ref"] for u in usage}) == len(usage), "no request is counted twice"


def test_every_usage_event_carries_an_atom_and_a_call_before_the_first_turn_gets_the_overhead_key(j2, make_run_dir, monkeypatch):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    from sutra_app.engine.hooks import EventHooks

    class Early(EventHooks):
        def run_started(self, spec):
            llm.ask("system", "a call before any turn", lambda: "{}")

    monkeypatch.setitem(sys.modules, "early_hooks_module", type(sys)("early_hooks_module"))
    sys.modules["early_hooks_module"].factory = lambda **kw: Early(kw["writer"], kw["notify"], kw["validator"], kw["node_context_file"])
    monkeypatch.setenv("SUTRA_NODES", "on")
    monkeypatch.setenv("SUTRA_HOOKS", "early_hooks_module:factory")
    assert Running(run_dir, "--mock").wait() == 0
    usage = of(events(run_dir), "usage")
    overhead = overhead_atom_id("j2-20261104-100004-7f3a")
    assert usage[0]["purpose"] == "agent_turn" and usage[0]["atom"] == overhead and usage[0]["call_ref"].startswith("r:")
    assert all(u["atom"] for u in usage), "no usage line without an atom"
    assert llm.bound_atom() == overhead, "the host binds the run overhead key and nothing rebinds it without the layer"


def test_override_and_stop_lines(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: [e for e in events(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"], what="the question")
    append_inbox(run_dir, 1, "override", cmd="budget +5")
    wait_until(lambda: any("Owner override applied" in e["text"] for e in of(events(run_dir), "say")), what="the override")
    assert running.host.run.budget == 105
    append_inbox(run_dir, 2, "stop")
    assert running.wait() == 0
    ended = events(run_dir)[-1]
    assert ended["t"] == "run.ended" and ended["status"] == "stopped" and ended["outcome"] == "Stopped: stopped on request"
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["status"] == "stopped" and summary["outcome"] == "Stopped: stopped on request"
    assert running.host.stopping.is_set() and running.host.run.stopping is True
    assert chat(run_dir)[-1]["text"] == "Stopped: stopped on request."


def test_a_user_line_while_the_run_is_working_waits_one_deferred_trace_line_and_is_delivered_when_it_waits(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    port = {}

    def make(*, sink, mock, task, paths):
        port["p"] = GatePort(usage_sink=sink)
        return port["p"]
    running = Running(run_dir, "--mock", make_port=make)
    wait_until(lambda: "p" in port and port["p"].waiting.is_set(), what="a request in flight")
    append_inbox(run_dir, 1, "user", text=VAGUE[1])
    wait_until(lambda: trace(run_dir, "inbox.deferred"), what="the deferral")
    time.sleep(0.4)                                          # several ticks later it is still one line and still undelivered
    assert [t["data"]["n"] for t in trace(run_dir, "inbox.deferred")] == [1]
    assert [m["text"] for m in chat(run_dir) if m["who"] == "user"] == [VAGUE[0]]
    Answerer(run_dir, VAGUE[2:], skip=1, n0=1)               # the line n=1 answers the first question; the owner answers the rest
    port["p"].release()
    assert running.wait() == 0
    users = [m["text"] for m in chat(run_dir) if m["who"] == "user"]
    assert users[:2] == [VAGUE[0], VAGUE[1]] and users.count(VAGUE[1]) == 1, "delivered once the run waited for the owner"


def test_a_stop_line_behind_queued_user_lines_discards_them_and_stops_inside_six_seconds(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    port = {}

    def make(*, sink, mock, task, paths):
        port["p"] = GatePort(usage_sink=sink)
        return port["p"]
    running = Running(run_dir, "--mock", make_port=make)
    wait_until(lambda: "p" in port and port["p"].waiting.is_set(), what="a request in flight")
    started = time.time()
    with open(run_dir / "inbox.jsonl", "a", encoding="utf-8") as f:           # one append: the host reads all three together
        for n, kind, extra in ((1, "user", {"text": "first"}), (2, "user", {"text": "second"}), (3, "stop", {})):
            f.write(json.dumps({"n": n, "kind": kind, **extra}) + "\n")
    assert running.wait() == 0
    assert time.time() - started < 3, "closing the port wakes the blocked call at once; the stop does not wait for it"
    assert sorted(t["data"]["n"] for t in trace(run_dir, "inbox.discarded")) == [1, 2]
    assert not [m for m in chat(run_dir) if m["who"] == "user" and m["text"] in ("first", "second")]
    assert events(run_dir)[-1]["status"] == "stopped" and json.loads((run_dir / "summary.json").read_text())["status"] == "stopped"
    assert running.host.run.error is None and json.loads((run_dir / "snapshot.json").read_text())["error"] is None, \
        "the closed port that woke the call is not an error the page should show"


def test_termination_runs_the_stop_and_exits_143(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: any(e.get("act") == "ASK_REQUESTER" for e in of(events(run_dir), "say")), what="the question")
    running.host.request_termination()
    assert running.wait() == 143
    ended = events(run_dir)[-1]
    assert ended["t"] == "run.ended" and ended["status"] == "stopped" and "SIGTERM" in ended["outcome"]


def test_a_run_that_ends_drains_the_inbox_once_more_so_a_late_answer_is_not_lost(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: running.host.run is not None and running.host.run.status == "waiting" and not running.host.run.paused
               or running.thread.is_alive() is False, what="the end")
    assert running.wait() == 0
    assert events(run_dir)[-1]["t"] == "run.ended"
    with open(run_dir / "inbox.jsonl", "a") as f:
        f.write(json.dumps({"n": 1, "kind": "user", "text": "too late"}) + "\n")
    time.sleep(0.4)
    assert not [m for m in chat(run_dir) if m["text"] == "too late"], "a line after run.ended is never read"
    assert running.host.inbox.closed


# ---- the start: what can go wrong before there is a run ------------------------------------------------------------------
def test_a_missing_run_directory_is_one_stderr_line_and_exit_2(j2, data_dir, capsys):
    code = loop.main(["--run-dir", str(data_dir / "departments" / "web" / "runs" / "j2-20261104-100004-7f3a")])
    assert code == 2 and "run directory does not exist" in capsys.readouterr().err


@pytest.mark.parametrize("break_it, reason", [
    (lambda run: (run / "task.json").write_text("{not json"), "task.json is invalid"),
    (lambda run: (run / "task.json").write_text(json.dumps({"run_id": "j2-20261104-100004-7f3a"})), "task.json is invalid"),
    (lambda run: (run / "task.json").unlink(), "task.json cannot be read"),
])
def test_an_invalid_task_json_ends_the_run_as_crashed_start_failed_without_run_started(j2, run_dir, break_it, reason):
    break_it(run_dir)
    assert loop.main(["--run-dir", str(run_dir), "--mock"]) == 2
    rows = events(run_dir)
    assert [e["t"] for e in rows] == ["run.ended"]
    assert rows[0]["status"] == "crashed" and rows[0]["code"] == "start_failed" and rows[0]["outcome"].startswith("could not start: " + reason)
    parse_event(rows[0], strict=True)


def test_a_task_for_another_run_or_department_is_refused(j2, make_run_dir):
    other_run = make_run_dir(run_id="j2-20261104-100004-aaaa", dept_id="web")
    task = json.loads((other_run / "task.json").read_text())
    (other_run / "task.json").write_text(json.dumps({**task, "run_id": "j2-20261104-100004-bbbb"}))
    assert loop.main(["--run-dir", str(other_run), "--mock"]) == 2
    assert "not for the folder" in events(other_run)[0]["outcome"]
    other_dept = make_run_dir(run_id="j2-20261104-100004-cccc", dept_id="sales")
    (other_dept / "task.json").write_text(json.dumps({**json.loads((other_dept / "task.json").read_text()), "dept_id": "web"}))
    assert loop.main(["--run-dir", str(other_dept), "--mock"]) == 2
    assert "department web" in events(other_dept)[0]["outcome"]


def test_a_failed_preflight_leaves_a_system_line_and_run_ended_but_no_run_started(j2, run_dir, monkeypatch):
    monkeypatch.delenv("STUDIO_MOCK")
    class Missing(llm.ScriptedPort):
        def preflight(self):
            return PreflightResult(ok=False, message="Claude CLI not found on PATH (install it and run claude once)", providers=[])
    code = Running(run_dir, make_port=make_port_of(Missing)).wait()          # no --mock: the real-model path
    assert code == 3
    rows = events(run_dir)
    assert [e["t"] for e in rows] == ["run.ended"]
    assert rows[0]["status"] == "crashed" and rows[0]["code"] == "start_failed"
    assert rows[0]["outcome"] == "could not start: Claude CLI not found on PATH (install it and run claude once)"
    lines = jsonl(run_dir / "chat.jsonl")
    assert lines[0]["meta"] is True and lines[1]["who"] == "system" and "Claude CLI not found" in lines[1]["text"]


def test_a_mock_run_skips_the_preflight(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)

    class Missing(llm.ScriptedPort):
        def preflight(self):
            raise AssertionError("mock mode must not preflight")
    assert Running(run_dir, "--mock", make_port=make_port_of(Missing)).wait() == 0


def test_the_connector_layer_port_gets_the_port_spec_and_the_sink(j2, make_run_dir, monkeypatch):
    monkeypatch.delenv("STUDIO_MOCK")
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    seen = {}

    def make_port(spec, *, usage_sink=None):
        seen.update(spec=spec, sink=usage_sink)
        return llm.ScriptedPort(usage_sink=usage_sink)
    module = type(sys)("sutra_app.connectors.engine_port")
    module.make_port = make_port
    monkeypatch.setitem(sys.modules, "sutra_app.connectors.engine_port", module)
    assert Running(run_dir).wait() == 0                     # not mock, connector "auto": the connector layer's port, then preflight
    spec = seen["spec"]
    assert (spec.mock, spec.connector, spec.run_id, spec.dept_id, spec.task_id) == (False, "auto", "j2-20261104-100004-7f3a", "web",
                                                                                  "tsk_a1b2c3d4e5f6")
    assert spec.data_dir == str(run_dir.parents[3]) and isinstance(seen["sink"], loop.EventUsageSink)
    assert events(run_dir)[0]["mock"] is False


def test_without_the_connector_layer_the_run_cannot_start_and_says_so(j2, run_dir, monkeypatch):
    monkeypatch.delenv("STUDIO_MOCK")
    monkeypatch.setitem(sys.modules, "sutra_app.connectors.engine_port", None)          # an import of None raises ImportError
    assert Running(run_dir).wait() == 3
    assert events(run_dir)[0]["outcome"].startswith("could not start: the model connectors are not available")


@pytest.mark.parametrize("how, expect", [("--mock", True), ("SUTRA_MOCK", True), ("SUTRA_OFFLINE", True), ("STUDIO_MOCK", True),
                                         ("stub", True)])
def test_mock_mode_is_chosen_by_the_flag_the_environment_or_the_stub_connector(j2, make_run_dir, monkeypatch, how, expect):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET, connector="stub" if how == "stub" else "auto")
    monkeypatch.delenv("STUDIO_MOCK")
    if how in ("SUTRA_MOCK", "SUTRA_OFFLINE", "STUDIO_MOCK"):
        monkeypatch.setenv(how, "1")
    assert Running(run_dir, *(["--mock"] if how == "--mock" else [])).wait() == 0
    assert events(run_dir)[0]["mock"] is expect


# ---- hooks selection ---------------------------------------------------------------------------------------------------------
def test_the_default_hooks_target_is_the_function_node_layer():
    assert loop.DEFAULT_HOOKS == "sutra_app.engine.fnodes.layer:factory"


def test_nodes_off_selects_event_hooks(j2, brew_dir):
    from sutra_app.engine.hooks import EventHooks
    running = Running(brew_dir, "--mock")
    running.wait()
    assert type(running.host.hooks._inner) is EventHooks


def test_a_hooks_import_error_falls_back_to_event_hooks_with_one_publish_error_line(j2, brew_dir, monkeypatch):
    from sutra_app.engine.hooks import EventHooks
    monkeypatch.setenv("SUTRA_NODES", "on")
    monkeypatch.setenv("SUTRA_HOOKS", "no_such_module_anywhere:factory")
    running = Running(brew_dir, "--mock")
    assert running.wait() == 0
    assert type(running.host.hooks._inner) is EventHooks
    errors = [t for t in trace(brew_dir, "publish.error") if t["data"].get("where") == "hooks"]
    assert len(errors) == 1 and "no_such_module_anywhere" in errors[0]["data"]["error"]


def test_the_factory_gets_writer_notify_validator_node_context_file_and_the_task(j2, brew_dir, monkeypatch):
    from sutra_app.engine.hooks import EventHooks
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return EventHooks(kw["writer"], kw["notify"], kw["validator"], kw["node_context_file"])
    monkeypatch.setitem(sys.modules, "recording_factory_module", type(sys)("recording_factory_module"))
    sys.modules["recording_factory_module"].factory = factory
    monkeypatch.setenv("SUTRA_NODES", "on")
    monkeypatch.setenv("SUTRA_HOOKS", "recording_factory_module:factory")
    Running(brew_dir, "--mock").wait()
    assert set(seen) == {"writer", "notify", "validator", "node_context_file", "spec"}
    assert seen["spec"].task_id == "tsk_a1b2c3d4e5f6" and seen["node_context_file"] == brew_dir / "node_context.json"
    assert callable(seen["notify"])


def test_a_factory_value_error_is_could_not_start_exit_3(j2, run_dir, monkeypatch):
    def factory(**kw):
        raise ValueError("SUTRA_NODES=enforce is reserved")
    monkeypatch.setitem(sys.modules, "refusing_factory_module", type(sys)("refusing_factory_module"))
    sys.modules["refusing_factory_module"].factory = factory
    monkeypatch.setenv("SUTRA_NODES", "on")
    monkeypatch.setenv("SUTRA_HOOKS", "refusing_factory_module:factory")
    assert Running(run_dir, "--mock").wait() == 3
    rows = events(run_dir)
    assert [e["t"] for e in rows] == ["run.ended"] and rows[0]["code"] == "start_failed" and "enforce is reserved" in rows[0]["outcome"]


# ---- settings, environment, library ------------------------------------------------------------------------------------------
def test_settings_are_layered_written_and_exported_before_j2_is_imported(j2, make_run_dir, data_dir):
    (data_dir / "engine.json").write_text(json.dumps({"budget": 80, "max_cycles": 4}))
    run_dir = make_run_dir(user_text=BREW_LAB, settings={**QUIET, "J2_BUDGET": "90", "J2_FIXES": "1"})
    (data_dir / "departments" / "web" / "engine.json").write_text(json.dumps({"budget": 85}))
    Running(run_dir, "--mock").wait()
    written = json.loads((run_dir / "settings.json").read_text())
    assert (written["budget"], written["max_cycles"], written["fixes"], written["memory"]) == (90, 4, 1, False)
    assert os.stat(run_dir / "settings.json").st_mode & 0o777 == 0o600
    assert (os.environ["J2_BUDGET"], os.environ["J2_MAX_CYCLES"], os.environ["J2_FIXES"]) == ("90", "4", "1")
    assert os.environ["J2_RUNS_DIR"] == str(data_dir / "departments" / "web" / "runs")
    assert os.environ["J2_MEMORY_FILE"].endswith("departments/web/memory/lessons.jsonl")
    assert os.environ["J2_PLAYBOOK_FILE"].endswith("departments/web/memory/playbooks.jsonl")
    assert os.environ["J2_LIBRARY_DIR"] == str(data_dir / "library") and os.environ["STUDIO_MOCK"] == "1"
    assert "key" not in json.dumps(written).lower().replace("monkey", "")


def test_bad_settings_end_the_run_as_could_not_start(j2, make_run_dir, data_dir):
    run_dir = make_run_dir(settings={"J2_BUDGET": "lots"})
    assert Running(run_dir, "--mock").wait() == 3
    assert "settings:" in events(run_dir)[0]["outcome"] and "J2_BUDGET" in events(run_dir)[0]["outcome"]


def test_a_setting_key_that_is_not_a_j2_name_is_dropped_with_a_trace_line(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings={**QUIET, "evil": "1"})
    assert Running(run_dir, "--mock").wait() == 0
    assert trace(run_dir, "task.settings_dropped")[0]["data"] == {"keys": ["evil"]}


def test_the_template_library_is_seeded_once_and_never_overwritten(j2, make_run_dir, data_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    Running(run_dir, "--mock").wait()
    library = data_dir / "library"
    assert (library / "index.json").is_file() and (library / "prd").is_dir()
    (library / "mine.txt").write_text("owner's file")
    second = make_run_dir(run_id="j2-20261104-100005-7f3a", user_text=BREW_LAB, settings=QUIET)
    Running(second, "--mock").wait()
    assert (library / "mine.txt").read_text() == "owner's file"
    assert not [p for p in data_dir.iterdir() if p.name.startswith(".library")], "no half-copied folder is left"


# ---- the first lines of a run: framing, upstream, the seed ---------------------------------------------------------------------
def systems(run_dir) -> list:
    return [m["text"] for m in chat(run_dir) if m["who"] == "system"]


def test_framing_becomes_one_system_line_and_a_plain_run_has_none(j2, make_run_dir):
    plain = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    Running(plain, "--mock").wait()
    framed = make_run_dir(run_id="j2-20261104-100005-7f3a", user_text=BREW_LAB, settings=QUIET, framing="  Keep it short.  ")
    Running(framed, "--mock").wait()
    assert not [t for t in systems(plain) if t.startswith("Context from the team lead")]
    lines = [t for t in systems(framed) if t.startswith("Context from the team lead")]
    assert lines == ["Context from the team lead: Keep it short."]
    assert chat(framed)[0]["text"] == lines[0], "the host's lines come before the owner's message"
    assert [e["text"] for e in of(events(framed), "say")][0] == lines[0]


def test_upstream_files_are_copied_listed_and_the_unsafe_ones_refused(j2, make_run_dir, data_dir):
    up = data_dir / "departments" / "design" / "runs" / "j2-20261104-090000-1111"
    (up / "site").mkdir(parents=True)
    (up / "site" / "v1.html").write_text("<h1>old</h1>")
    (up / "brief.md").write_text("# brief")
    outside = data_dir / "secret.txt"
    outside.write_text("secret")
    (up / "link.txt").symlink_to(outside)
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET, upstream=[{
        "dept_id": "design", "run_id": "j2-20261104-090000-1111", "title": "Brand work",
        "files": ["site/v1.html", "brief.md", "/etc/passwd", "../../../secret.txt", "link.txt", "missing.md", "site"]}])
    assert Running(run_dir, "--mock").wait() == 0
    copied = run_dir / "upstream" / "j2-20261104-090000-1111"
    assert (copied / "site" / "v1.html").read_text() == "<h1>old</h1>" and (copied / "brief.md").read_text() == "# brief"
    assert not (copied / "link.txt").exists() and not (copied / "secret.txt").exists()
    line = next(t for t in systems(run_dir) if t.startswith("Earlier work from other teams"))
    assert "Brand work (run j2-20261104-090000-1111): site/v1.html, brief.md" in line and "passwd" not in line
    skipped = {t["data"]["file"]: t["data"]["reason"] for t in trace(run_dir, "upstream.skipped")}
    assert skipped["/etc/passwd"] == "absolute or '..' path" and skipped["../../../secret.txt"] == "absolute or '..' path"
    assert skipped["link.txt"] == "a symbolic link" and skipped["missing.md"] == "not a file" and skipped["site"] == "not a file"


def finished_run(make_run_dir, run_id, **task):
    run_dir = make_run_dir(run_id=run_id, user_text=BREW_LAB, settings=QUIET, **task)
    assert Running(run_dir, "--mock").wait() == 0
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")
    return run_dir


def test_seed_from_a_finished_run_of_the_department_is_rehydrated_and_the_message_is_a_change_request(j2, make_run_dir):
    old = finished_run(make_run_dir, "j2-20261104-100004-7f3a")
    new = make_run_dir(run_id="j2-20261104-110000-aaaa", user_text="Add a section for visiting hours", settings=QUIET,
                       seed_from=old.name)
    assert Running(new, "--mock").wait() == 0
    rows = events(new)
    assert rows[0]["t"] == "run.started" and rows[0]["seed"] == "rehydrated"
    line = f"Continuing from run {old.name}: the team keeps its charter, workflows, findings and site and treats your message as a change request."
    assert chat(new)[len(chat(old))]["text"] == line, "the old chat is copied first, then the host's line, then the owner's message"
    assert [m for m in chat(new) if m["who"] == "user" and m.get("change")], "J2 marked the message as a change request"
    assert (new / "site" / "v1.html").is_file() and len(chat(new)) > len(chat(old))
    assert rows[-1]["status"] in ("done", "done_with_open_items")
    assert not (old / "upstream").exists() and (old / "events.jsonl").read_text().count('"run.started"') == 1, "the old folder is never written again"


def test_a_refused_seed_starts_fresh_with_the_old_files_as_upstream(j2, make_run_dir, data_dir):
    old = data_dir / "departments" / "web" / "runs" / "j2-20261104-090000-2222"
    (old / "site").mkdir(parents=True)
    (old / "site" / "v1.html").write_text("<h1>old site</h1>")
    (old / "summary.json").write_text(json.dumps({"status": "stopped", "outcome": "Stopped: on request"}))
    (old / "events.jsonl").write_text("{}\n")
    (old / "prd.md").write_text("# PRD")
    new = make_run_dir(user_text=BREW_LAB, settings=QUIET, seed_from=old.name)
    assert Running(new, "--mock").wait() == 0
    assert events(new)[0]["seed"] == "fresh"
    assert systems(new)[0].startswith(f"Starting a new run. Your earlier files from run {old.name} are in upstream/{old.name}/ for reference. Reason:")
    copied = new / "upstream" / old.name
    assert (copied / "site" / "v1.html").read_text() == "<h1>old site</h1>" and (copied / "prd.md").is_file()
    assert not (copied / "events.jsonl").exists(), "the old run's event log is not history the team needs"
    assert trace(new, "seed.refused")


def test_a_seed_that_is_not_a_run_of_this_department_is_fresh_without_a_line(j2, make_run_dir):
    new = make_run_dir(user_text=BREW_LAB, settings=QUIET, seed_from="j2-20250101-000000-dead")
    assert Running(new, "--mock").wait() == 0
    assert events(new)[0]["seed"] == "fresh" and not [t for t in systems(new) if "earlier files" in t or "Continuing" in t]
    assert trace(new, "seed.skipped")


# ---- the heartbeat ----------------------------------------------------------------------------------------------------------
def test_heartbeat_interval_reads_the_environment():
    assert heartbeat_interval({}) == 5.0
    assert heartbeat_interval({"SUTRA_HEARTBEAT_S": "0.2"}) == 0.2
    assert [heartbeat_interval({"SUTRA_HEARTBEAT_S": v}) for v in ("0", "-1", "abc", "inf", "")] == [5.0] * 5


def test_the_first_heartbeat_follows_run_started_at_once_and_a_waiting_run_keeps_beating(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: len(of(events(run_dir), "heartbeat")) >= 4, what="four beats", timeout=10)
    rows = events(run_dir)
    assert rows[0]["t"] == "run.started" and rows[1]["t"] in ("heartbeat", "say")
    assert running.host.run.status == "waiting" and running.host.run.paused, "beating while the run waits for the owner"
    append_inbox(run_dir, 1, "stop")
    running.wait()
    assert events(run_dir)[-1]["t"] == "run.ended"
    assert running.host.heartbeat._thread is not None and not running.host.heartbeat._thread.is_alive()


def test_the_first_beat_is_not_delayed_by_the_interval(tmp_path):
    from sutra_app.engine.events import EventWriter
    (tmp_path / "events.jsonl").touch()
    writer = EventWriter(tmp_path)
    beat = Heartbeat(writer, 30)
    beat.start()
    wait_until(lambda: beat.beats == 1, timeout=1.0, what="the first beat")
    beat.stop()
    assert [e["t"] for e in events(tmp_path)] == ["heartbeat"]
    writer.close()


def test_the_end_status_follows_the_rule_of_the_summary():
    for outcome, status in (("Done: the site is workable.", "done"), ("Done with open items: two checks", "done_with_open_items"),
                            ("Crashed: boom", "crashed"), ("Stopped: stopped on request", "stopped"), ("Paused: waiting", "stopped"),
                            ("", "stopped"), (None, "stopped")):
        assert loop.outcome_status(outcome) == status


def test_a_heartbeat_stops_by_itself_once_run_ended_was_written(tmp_path):
    from sutra_app.engine.events import EventWriter, run_ended_event
    (tmp_path / "events.jsonl").touch()
    writer = EventWriter(tmp_path)
    beat = Heartbeat(writer, 0.02)
    beat.start()
    wait_until(lambda: beat.beats >= 2, what="two beats")
    writer.emit(run_ended_event(status="done", outcome="Done"))
    beat._thread.join(2)
    assert not beat._thread.is_alive()
    with pytest.raises(ValueError):
        Heartbeat(writer, 0)
    writer.close()


# ---- the inbox itself ---------------------------------------------------------------------------------------------------------
class FakeRun:
    def __init__(self, status="waiting", accept=True):
        self.status, self.accept, self.said, self.overrides = status, accept, [], []

    def user_says(self, text):
        self.said.append(text)
        return self.accept

    def apply_override(self, cmd):
        self.overrides.append(cmd)
        return self.accept


def test_the_tailer_reads_whole_lines_in_n_order_and_skips_what_it_cannot_use(tmp_path):
    path = tmp_path / "inbox.jsonl"
    seen = []
    tailer = InboxTailer(path, lambda type, data: seen.append((type, data)))
    assert tailer.read_new() == [], "a missing file is an empty inbox"
    path.write_text(json.dumps({"n": 2, "kind": "user", "text": "b"}) + "\n" + json.dumps({"n": 1, "kind": "user", "text": "a"}) + "\n"
                    + "not json\n" + json.dumps({"n": 3, "kind": "user"}) + "\n" + json.dumps({"n": 4, "kind": "dance"}) + "\n"
                    + json.dumps({"n": 1, "kind": "user", "text": "again"}) + "\n" + json.dumps({"n": 0, "kind": "stop"}) + "\n"
                    + json.dumps({"n": 5, "kind": "override"}) + "\n")
    assert [(line.n, line.text) for line in tailer.read_new()] == [(1, "a"), (2, "b")]
    reasons = [d["reason"] for t, d in seen if t == "inbox.skipped"]
    assert len(reasons) == 6 and "repeated n" in reasons and any("not JSON" in r for r in reasons)
    assert any("user line needs text" in r for r in reasons) and any("unknown kind" in r for r in reasons)
    assert any("n must be" in r for r in reasons) and any("override line needs cmd" in r for r in reasons)
    assert tailer.read_new() == [], "each line is read once"


def test_a_half_written_line_waits_for_its_newline(tmp_path):
    path = tmp_path / "inbox.jsonl"
    tailer = InboxTailer(path)
    whole = json.dumps({"n": 1, "kind": "user", "text": "hello"})
    path.write_text(whole[:20])
    assert tailer.read_new() == []
    with open(path, "a") as f:
        f.write(whole[20:] + "\n")
    assert [line.text for line in tailer.read_new()] == ["hello"]


def test_the_fifo_delivers_the_head_only_when_the_run_takes_it_and_defers_with_one_trace_line(tmp_path):
    path = tmp_path / "inbox.jsonl"
    seen = []
    inbox = Inbox(path, lambda type, data: seen.append((type, data)))
    path.write_text("".join(json.dumps(x) + "\n" for x in ({"n": 1, "kind": "user", "text": "a"}, {"n": 2, "kind": "override", "cmd": "ship"})))
    assert inbox.poll() is None and len(inbox) == 2
    running = FakeRun(status="running")
    assert [inbox.deliver(running) for _ in range(3)] == [False] * 3 and running.said == [], "a user line waits while the run works"
    assert [d["n"] for t, d in seen if t == "inbox.deferred"] == [1]
    waiting = FakeRun(accept=False)
    assert inbox.deliver(waiting) is False and waiting.said == ["a"], "user_says said no (lock held): the head stays"
    waiting.accept = True
    assert inbox.deliver(waiting) is True and inbox.deliver(waiting) is True and waiting.overrides == ["ship"]
    assert inbox.deliver(waiting) is False and len(inbox) == 0


def test_a_stop_line_clears_the_queue_and_nothing_is_read_after_close(tmp_path):
    path = tmp_path / "inbox.jsonl"
    seen = []
    inbox = Inbox(path, lambda type, data: seen.append((type, data)))
    path.write_text(json.dumps({"n": 1, "kind": "user", "text": "a"}) + "\n")
    inbox.poll()
    with open(path, "a") as f:
        f.write(json.dumps({"n": 2, "kind": "stop"}) + "\n" + json.dumps({"n": 3, "kind": "user", "text": "c"}) + "\n")
    stop = inbox.poll()
    assert stop.kind == "stop" and len(inbox) == 0
    assert sorted(d["n"] for t, d in seen if t == "inbox.discarded") == [1, 3]
    inbox.close()
    with open(path, "a") as f:
        f.write(json.dumps({"n": 4, "kind": "user", "text": "late"}) + "\n")
    assert inbox.poll() is None and len(inbox) == 0


# ---- strict records over the records of J2 sync 4 (D145 and Decide for me) --------------------------------------------------
def test_a_forced_audit_failure_run_with_the_late_judge_ends_in_strict_records_mode_and_holds_its_late_list(j2, make_run_dir, clean_env):
    """D145: the late judge's records (`late` in realization.json, the chat line's `judge`, the workflow row's judge) and the Plan workflow's
    version 0 are accepted when the records hook is strict: no RecordRejected stops the run, which ends done or done with open items."""
    clean_env.setenv("SUTRA_RECORDS", "strict")
    run_dir = make_run_dir(user_text=BREW_LAB, settings={"J2_MEMORY": "0", "J2_REALIZATION": "1", "J2_FORCE_AUDIT_FAIL": "1"})
    assert Running(run_dir, "--mock").wait(60) == 0
    rows = events(run_dir)
    assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items") and rows[-1]["code"] is None
    assert not [r for r in trace(run_dir, "record.warning")], "strict mode refused no record"
    real = json.loads((Path(run_dir) / "realization.json").read_text(encoding="utf-8"))
    assert real["late"] and real["late"][0]["revises"] and real["late"][0]["calls"] >= 1
    assert [m["judge"] for m in chat(run_dir) if "judge" in m] == [e["workflow"] for e in real["late"]]
    assert [w["version"] for w in json.loads((Path(run_dir) / "workflows.json").read_text(encoding="utf-8")) if w["name"] == "Plan"] == [0]


def test_a_decide_for_me_run_ends_in_strict_records_mode_with_its_settings_file_and_flagged_answers(j2, make_run_dir, clean_env):
    """Sync 4: Decide for me writes settings.json and answers in the Requester's name (`auto`, `auto_label`); strict mode accepts both."""
    clean_env.setenv("SUTRA_RECORDS", "strict")
    clean_env.setenv("J2_DECIDE_FOR_ME", "1")           # the host exports only the engine settings it knows: J2 reads this one from the environment
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    assert Running(run_dir, "--mock").wait(60) == 0
    rows = events(run_dir)
    assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items") and rows[-1]["code"] is None
    assert not [r for r in trace(run_dir, "record.warning")], "strict mode refused no record"
    assert json.loads((Path(run_dir) / "settings.json").read_text(encoding="utf-8")).get("decide_for_me") is True
    answers = [m for m in chat(run_dir) if m["who"] == "user" and m.get("auto")]
    assert answers and all(m.get("auto_label") for m in answers), "the vague brief raised questions and Decide for me answered them"
