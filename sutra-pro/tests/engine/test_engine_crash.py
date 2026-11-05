"""Failures end in a defined state (work package E3, engine design flow F7 and ENG-09): a model error of every code, a dead run
thread, a disk error, a fatal hook, an internal error of the host, a port that cannot be built, a torn or bad inbox line."""
import json
import sys
import time

import pytest
from test_engine_host import (  # noqa: F401  (j2 is a fixture)
    BREW_LAB, QUIET, VAGUE, Answerer, RaisingPort, Running, chat, events, j2, jsonl, make_port_of, of, trace, wait_until,
)

from sutra_app.engine.host import loop
from sutra_app.engine.hooks import EventHooks
from sutra_app.engine.port import (
    CliMissing, ModelTimeout, NoModelAvailable, NotSignedIn, QuotaExhausted, StructuredOutputFailed,
)
from sutra_app.orchestrator.models import parse_event

ERRORS = [(NoModelAvailable, "no_model"), (CliMissing, "cli_missing"), (NotSignedIn, "not_signed_in"), (QuotaExhausted, "quota"),
          (ModelTimeout, "timeout"), (StructuredOutputFailed, "structured")]


@pytest.fixture
def brew(make_run_dir):
    return make_run_dir(user_text=BREW_LAB, settings=QUIET)


def crashed_end(run_dir):
    rows = events(run_dir)
    assert rows[-1]["t"] == "run.ended", "run.ended is the last line"
    assert [e["t"] for e in rows].count("run.ended") == 1
    return rows[-1]


@pytest.mark.parametrize("cls, code", ERRORS)
def test_a_model_error_ends_the_run_as_crashed_with_its_code_and_a_stopped_message(j2, brew, cls, code):
    assert cls.code == code
    port = make_port_of(RaisingPort, cls("the model said no"))
    assert Running(brew, "--mock", make_port=port).wait() == 0, "a crash that was handled is still a normal end of the process"
    ended = crashed_end(brew)
    assert ended["status"] == "crashed" and ended["code"] == code
    assert ended["outcome"] == f"Crashed: {cls.__name__}: the model said no"
    stopped = [m for m in chat(brew) if m["who"] == "system" and m["text"].startswith("Stopped:")]
    assert stopped and stopped[0]["text"] == f"Stopped: {cls.__name__}: the model said no"
    assert any(e["text"] == stopped[0]["text"] for e in of(events(brew), "say")), "the page and the watcher can show it"
    summary = json.loads((brew / "summary.json").read_text())
    assert summary["status"] == "crashed" and summary["outcome"] == ended["outcome"]
    snapshot = json.loads((brew / "snapshot.json").read_text())
    assert snapshot["status"] == "waiting" and snapshot["error"] == f"{cls.__name__}: the model said no"
    parse_event(ended, strict=True)


def test_a_model_that_fails_later_in_the_run_crashes_it_where_it_stands(j2, brew):
    port = make_port_of(RaisingPort, CliMissing("Claude CLI not found on PATH"), after=4)
    assert Running(brew, "--mock", make_port=port).wait() == 0
    ended = crashed_end(brew)
    assert ended["status"] == "crashed" and ended["code"] == "cli_missing"
    assert len(of(events(brew), "usage")) >= 4 and len(chat(brew)) > 5
    assert json.loads((brew / "summary.json").read_text())["status"] == "crashed"
    assert (brew / "report.json").exists(), "the crash path still writes J2's report"


def test_a_port_that_cannot_be_built_is_could_not_start(j2, brew, monkeypatch):
    monkeypatch.delenv("STUDIO_MOCK")

    def make(*, sink, mock, task, paths):
        raise CliMissing("Claude CLI not found on PATH (install it and run claude once)")
    assert Running(brew, make_port=make).wait() == 3
    rows = events(brew)
    assert [e["t"] for e in rows] == ["run.ended"] and rows[0]["code"] == "start_failed"
    assert "CliMissing: Claude CLI not found" in rows[0]["outcome"]
    assert "Claude CLI not found" in jsonl(brew / "chat.jsonl")[-1]["text"]


# ---- the run thread dies -----------------------------------------------------------------------------------------------------------
class Died(BaseException):
    """What `_run_safe` (which catches only Exception) cannot catch."""


@pytest.mark.parametrize("exc, text", [(Died("boom"), "Died: boom"), (SystemExit(3), "SystemExit: 3")])
def test_a_run_thread_killed_by_an_uncatchable_exception_is_ended_as_crashed_by_the_excepthook(j2, brew, monkeypatch, exc, text):
    def dies(self):
        self.post("system", "about to die")
        raise exc
    monkeypatch.setattr(j2.J2Run, "_run", dies)
    running = Running(brew, "--mock")
    assert running.wait() == 0
    ended = crashed_end(brew)
    assert ended["status"] == "crashed" and ended["code"] == "internal" and ended["outcome"] == "Crashed: " + text
    assert chat(brew)[-1]["text"] == "Stopped: " + text
    assert json.loads((brew / "summary.json").read_text())["status"] == "crashed"
    assert trace(brew, "thread.died")[0]["data"]["error"] == text
    assert json.loads((brew / "snapshot.json").read_text())["status"] == "waiting"


def test_a_run_thread_that_exits_silently_is_found_by_its_free_lock(j2, brew, monkeypatch):
    def exits(self):
        return None                                      # the thread ends, nothing sets the status to waiting, no exception to hear
    monkeypatch.setattr(j2.J2Run, "_run", exits)
    monkeypatch.setattr(loop, "DEAD_THREAD_GRACE_S", 0.3)
    started = time.time()
    assert Running(brew, "--mock").wait() == 0
    ended = crashed_end(brew)
    assert ended["status"] == "crashed" and ended["code"] == "internal" and "ended without finishing" in ended["outcome"]
    assert 0.3 <= time.time() - started < 5


def test_a_disk_error_while_the_crash_is_being_recorded_still_ends_the_run_as_crashed(j2, brew, monkeypatch):
    original = j2.J2Run.post

    def post(self, who, text, **meta):
        if str(text).startswith("Stopped:"):
            raise OSError(28, "No space left on device")      # path f: the crash path itself fails
        return original(self, who, text, **meta)
    monkeypatch.setattr(j2.J2Run, "post", post)
    assert Running(brew, "--mock", make_port=make_port_of(RaisingPort, QuotaExhausted("out of quota"))).wait() == 0
    ended = crashed_end(brew)
    assert ended["status"] == "crashed" and ended["code"] == "internal" and "No space left" in ended["outcome"]


def test_a_fatal_hook_error_in_strict_mode_crashes_the_run(j2, brew, monkeypatch):
    class RecordRejected(RuntimeError):
        pass

    class Strict(EventHooks):
        def record_saved(self, name, data):
            if name == "workflows.json":
                raise RecordRejected("workflows.json is not a valid record")
            return super().record_saved(name, data)

    module = type(sys)("strict_hooks_module")
    module.factory = lambda **kw: Strict(kw["writer"], kw["notify"], kw["validator"], kw["node_context_file"])
    monkeypatch.setitem(sys.modules, "strict_hooks_module", module)
    monkeypatch.setenv("SUTRA_NODES", "on")
    monkeypatch.setenv("SUTRA_HOOKS", "strict_hooks_module:factory")
    assert Running(brew, "--mock").wait() == 0
    ended = crashed_end(brew)
    assert ended["status"] == "crashed" and ended["code"] == "internal" and "RecordRejected" in ended["outcome"]


# ---- the host itself ---------------------------------------------------------------------------------------------------------------
def test_an_internal_error_of_the_host_is_run_ended_crashed_internal_and_exit_70(j2, brew, monkeypatch, capsys):
    def broken(self):
        raise RuntimeError("a bug in the host")
    monkeypatch.setattr(loop.Host, "_serve", broken)
    assert Running(brew, "--mock").wait() == 70
    rows = events(brew)
    assert rows[-1]["status"] == "crashed" and rows[-1]["code"] == "internal" and rows[-1]["outcome"] == "Crashed: RuntimeError: a bug in the host"
    assert "a bug in the host" in capsys.readouterr().err


def test_an_internal_error_before_the_run_exists_is_the_same(j2, brew, monkeypatch):
    def broken(self):
        raise RuntimeError("no run for you")
    monkeypatch.setattr(loop.Host, "_make_run", broken)
    assert Running(brew, "--mock").wait() == 70
    assert [e["t"] for e in events(brew)] == ["run.ended"] and events(brew)[0]["code"] == "internal"


# ---- a torn or bad inbox -------------------------------------------------------------------------------------------------------------
def test_a_torn_line_waits_a_bad_line_is_skipped_and_the_answer_behind_them_is_delivered(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: any(e.get("act") == "ASK_REQUESTER" for e in of(events(run_dir), "say")), what="the question")
    answer = json.dumps({"n": 2, "kind": "user", "text": VAGUE[1]})
    with open(run_dir / "inbox.jsonl", "a", encoding="utf-8") as f:
        f.write("{this is not json}\n")
        f.write(answer[:25])                              # the server is still writing this line
        f.flush()
        time.sleep(0.5)
        assert [m["text"] for m in chat(run_dir) if m["who"] == "user"] == [VAGUE[0]], "a torn line is not delivered"
        f.write(answer[25:] + "\n")
    Answerer(run_dir, VAGUE[2:], skip=1, n0=2)
    assert running.wait() == 0
    assert [m["text"] for m in chat(run_dir) if m["who"] == "user"][:2] == [VAGUE[0], VAGUE[1]]
    skipped = trace(run_dir, "inbox.skipped")
    assert len(skipped) == 1 and "not JSON" in skipped[0]["data"]["reason"] and skipped[0]["data"]["line"] == "{this is not json}"
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")


def test_an_inbox_that_is_replaced_by_a_shorter_file_is_read_again_from_the_start(tmp_path):
    from sutra_app.engine.host.inbox import InboxTailer
    path = tmp_path / "inbox.jsonl"
    tailer = InboxTailer(path)
    path.write_text(json.dumps({"n": 1, "kind": "user", "text": "a long first line that is never repeated"}) + "\n")
    assert [line.n for line in tailer.read_new()] == [1]
    path.write_text(json.dumps({"n": 2, "kind": "stop"}) + "\n")
    assert [line.n for line in tailer.read_new()] == [2]
