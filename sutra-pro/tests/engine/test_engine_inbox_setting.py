"""The Simple view's Decide for me switch in the engine process (J2 sync 4): the inbox line `{"kind": "setting", "decide_for_me": bool}`
that the host applies with `J2Run.set_auto`, and the task key `J2_DECIDE_FOR_ME` that starts a run with the switch on. The
server side (the route, the page's choice, the line written to a live run) is tested in test_engine_api_commands.py and
tests/orchestrator."""
import json

import pytest

from sutra_app.engine.host.inbox import KINDS, Inbox, InboxTailer
from sutra_app.engine.spec import ENV_NAMES, TASK_SETTING_KEYS, EngineSettings

from test_engine_host import QUIET, VAGUE, GatePort, Running, append_inbox, chat, events, j2, trace, wait_until  # noqa: F401  (j2 is a fixture)


class FakeRun:
    """What `Inbox.deliver` needs of a run."""

    def __init__(self, status="waiting", accept=True):
        self.status, self.accept, self.said, self.auto = status, accept, [], []

    def user_says(self, text):
        self.said.append(text)
        return self.accept

    def apply_override(self, cmd):
        return self.accept

    def set_auto(self, on):
        self.auto.append(on)
        return True


def line(n, kind, **fields):
    return json.dumps({"n": n, "kind": kind, **fields}) + "\n"


# ---- reading the line --------------------------------------------------------------------------------------------------------
def test_a_setting_is_a_kind_of_inbox_line_with_a_yes_or_a_no(tmp_path):
    assert KINDS == ("user", "override", "stop", "setting")
    path = tmp_path / "inbox.jsonl"
    seen = []
    tailer = InboxTailer(path, lambda type, data: seen.append((type, data)))
    path.write_text(line(1, "setting", decide_for_me=True) + line(2, "setting", decide_for_me=False, at="2026-11-10T10:00:00Z")
                    + line(3, "setting") + line(4, "setting", decide_for_me=1) + line(5, "setting", decide_for_me="true")
                    + line(6, "setting", decide_for_me=None))
    got = tailer.read_new()
    assert [(x.n, x.kind, x.decide_for_me, x.text, x.cmd) for x in got] == [(1, "setting", True, None, None), (2, "setting", False, None, None)]
    reasons = [d["reason"] for t, d in seen if t == "inbox.skipped"]
    assert len(reasons) == 4 and all("setting line needs decide_for_me" in r for r in reasons), "only a real true or false is a setting"


def test_the_other_kinds_carry_no_setting(tmp_path):
    path = tmp_path / "inbox.jsonl"
    path.write_text(line(1, "user", text="a", decide_for_me=True) + line(2, "stop", decide_for_me=True))
    assert [x.decide_for_me for x in InboxTailer(path).read_new()] == [None, None]


# ---- delivering it -----------------------------------------------------------------------------------------------------------
def test_a_setting_is_applied_whatever_the_run_is_doing_and_leaves_the_rest_of_the_queue_alone(tmp_path):
    path = tmp_path / "inbox.jsonl"
    inbox = Inbox(path)
    path.write_text(line(1, "setting", decide_for_me=True) + line(2, "user", text="a") + line(3, "setting", decide_for_me=False))
    assert inbox.poll() is None and len(inbox) == 3
    running = FakeRun(status="running")
    assert inbox.deliver(running) is True and inbox.deliver(running) is True and running.auto == [True, False]
    assert len(inbox) == 1 and running.said == [], "the answer still waits for the run to stop"
    assert inbox.deliver(running) is False and running.said == []
    waiting = FakeRun()
    assert inbox.deliver(waiting) is True and waiting.said == ["a"] and len(inbox) == 0


def test_a_setting_does_not_wait_behind_an_answer_the_run_cannot_take_yet(tmp_path):
    path = tmp_path / "inbox.jsonl"
    inbox = Inbox(path)
    path.write_text(line(1, "user", text="first") + line(2, "setting", decide_for_me=True))
    inbox.poll()
    running = FakeRun(status="running")
    assert inbox.deliver(running) is True and running.auto == [True], "the setting jumps the queue"
    assert inbox.deliver(running) is False and running.said == [] and len(inbox) == 1


def test_a_stop_line_discards_the_settings_queued_with_everything_else(tmp_path):
    path = tmp_path / "inbox.jsonl"
    seen = []
    inbox = Inbox(path, lambda type, data: seen.append((type, data)))
    path.write_text(line(1, "setting", decide_for_me=True) + line(2, "stop") + line(3, "setting", decide_for_me=False))
    assert inbox.poll().kind == "stop" and len(inbox) == 0
    assert sorted(d["n"] for t, d in seen if t == "inbox.discarded") == [1, 3]


# ---- the host ----------------------------------------------------------------------------------------------------------------
def test_a_setting_line_switches_decide_for_me_on_in_a_run_that_waits_for_an_answer_and_the_run_goes_on(j2, make_run_dir):
    """The mock asks the owner what the website is for; nobody answers. The setting line is the only thing the owner sends, and J2 answers
    the question itself (`set_auto` answers an open question at once) and the run ends."""
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: [e for e in events(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"], what="the question")
    assert running.host.run.auto is False
    append_inbox(run_dir, 1, "setting", decide_for_me=True)
    assert running.wait(60) == 0
    assert running.host.run.auto is True
    rows = events(run_dir)
    assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items")
    auto = [m for m in chat(run_dir) if m["who"] == "user" and m.get("auto")]
    assert auto and all(m.get("auto_label") for m in auto), "every answer the switch gave is flagged and says in plain words what it chose"
    assert not [t for t in trace(run_dir, "inbox.skipped")], "the line was a good one"


def test_the_switch_can_be_turned_off_again_with_a_second_line(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: [e for e in events(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"], what="the question")
    append_inbox(run_dir, 1, "setting", decide_for_me=True)
    wait_until(lambda: running.host.run.auto is True or running.code is not None, what="the switch on")
    if running.code is None:
        append_inbox(run_dir, 2, "setting", decide_for_me=False)
        wait_until(lambda: running.host.run.auto is False or running.code is not None, what="the switch off")
        assert running.host.run.auto is False
        if running.code is None:
            append_inbox(run_dir, 3, "stop")     # off again, the run may wait at its next question: the owner stops it
    assert running.wait(60) == 0


def test_a_run_started_with_the_task_key_answers_its_own_questions_from_the_first_one(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings={**QUIET, "J2_DECIDE_FOR_ME": "1"})
    running = Running(run_dir, "--mock")
    assert running.wait(60) == 0                                   # no Answerer, no setting line: the key alone did it
    assert running.host.settings.decide_for_me is True and running.host.run.auto is True
    assert [m for m in chat(run_dir) if m["who"] == "user" and m.get("auto")]
    rows = events(run_dir)
    assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items")


def test_a_setting_line_is_applied_while_the_run_is_working_and_the_question_it_then_asks_is_answered(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    port = {}

    def make(*, sink, mock, task, paths):
        port["p"] = GatePort(usage_sink=sink)
        return port["p"]
    running = Running(run_dir, "--mock", make_port=make)
    wait_until(lambda: "p" in port and port["p"].waiting.is_set(), what="a request in flight")
    assert running.host.run.status == "running"
    append_inbox(run_dir, 1, "setting", decide_for_me=True)
    wait_until(lambda: running.host.run.auto is True, what="the switch on while the run works")
    assert not trace(run_dir, "inbox.deferred"), "a setting never waits for the run to stop"
    port["p"].release()
    assert running.wait(60) == 0
    assert [m for m in chat(run_dir) if m["who"] == "user" and m.get("auto")], "the question the run asked afterwards was answered by the switch"


def test_without_the_key_or_a_line_the_run_waits_for_the_owner_as_before(j2, make_run_dir):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    running = Running(run_dir, "--mock")
    wait_until(lambda: [e for e in events(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"], what="the question")
    assert running.host.settings.decide_for_me is False and running.host.run.auto is False
    assert running.host.run.paused and not [m for m in chat(run_dir) if m.get("auto")], "nobody answered it"
    append_inbox(run_dir, 1, "stop")
    assert running.wait() == 0 and events(run_dir)[-1]["status"] == "stopped"


# ---- the setting itself ------------------------------------------------------------------------------------------------------
def test_decide_for_me_is_an_engine_setting_and_the_eighth_task_key():          # J2 sync 6 appended two task-only keys after it
    assert EngineSettings().decide_for_me is False and ENV_NAMES["decide_for_me"] == "J2_DECIDE_FOR_ME"
    assert TASK_SETTING_KEYS[7] == "J2_DECIDE_FOR_ME" and len(TASK_SETTING_KEYS) == 10
    assert EngineSettings(decide_for_me=True).to_env()["J2_DECIDE_FOR_ME"] == "1" and EngineSettings().to_env()["J2_DECIDE_FOR_ME"] == "0"
    layered = EngineSettings.layered({}, None, {"decide_for_me": False}, {"J2_DECIDE_FOR_ME": "1"})
    assert layered.decide_for_me is True, "the task's key beats the team's file"
    assert EngineSettings.layered({"J2_DECIDE_FOR_ME": "on"}, None, None, {}).decide_for_me is True
    with pytest.raises(Exception):
        EngineSettings.layered({}, None, None, {"J2_DECIDE_FOR_ME": "maybe"})
