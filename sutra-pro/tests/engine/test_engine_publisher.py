"""`StatePublisher` and `HostHooks` (work package E3, engine design 4.5 and 4.6): the published files, the node, step and atom/1
events, the wait_on and tokens of the map's function nodes, the turn boundaries, the final publish."""
import json
import os
import re
import time
from pathlib import Path

import pytest
from test_engine_host import (  # noqa: F401  (j2 is a fixture)
    BREW_LAB, QUIET, VAGUE, Running, append_inbox, events, j2, of, trace, wait_until,
)

from sutra_app.engine import llm
from sutra_app.engine.events import EventWriter
from sutra_app.engine.hooks import EventHooks, TurnInfo, TurnOutcome
from sutra_app.engine.host.publisher import HostHooks, StatePublisher, builder_status, wait_on_key
from sutra_app.engine.port import CallTag
from sutra_app.orchestrator.models import parse_event

RUN_ID = "j2-20261104-100004-7f3a"
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")


def say(run, text, timeout=60.0):
    assert run.user_says(text) is True
    deadline = time.time() + timeout
    while run.status != "waiting":
        assert time.time() < deadline, "the run did not stop"
        time.sleep(0.003)


@pytest.fixture
def make(j2, tmp_path):
    """make(boundaries=True, **publisher_kwargs) -> (run, publisher, run_dir): a J2Run in mock mode whose hooks are wired like the host's."""
    counter = iter(range(1, 100))

    def build(boundaries=True, **kw):
        run_dir = tmp_path / "runs" / f"j2-20261104-1000{next(counter):02d}-7f3a"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir)
        pub = StatePublisher(writer, run_dir, **kw)
        inner = EventHooks(writer, pub.notify)
        llm.configure(llm.ScriptedPort(), mock=True, base_tag=CallTag(run_id=RUN_ID, dept_id="web", task_id="tsk_1"))
        run = j2.J2Run(run_dir=str(run_dir), run_id=run_dir.name[3:], hooks=HostHooks(inner, pub) if boundaries else inner)
        pub.attach(run)
        return run, pub, run_dir
    return build


def brew(run, pub):
    say(run, BREW_LAB)
    return events(Path(run.dir))


def snap_of(run_dir) -> dict:
    try:
        return json.loads((Path(run_dir) / "snapshot.json").read_text())
    except (OSError, ValueError):
        return {}


def last_by(rows, key):
    out = {}
    for e in rows:
        out[e[key]] = e
    return out


# ---- the files ------------------------------------------------------------------------------------------------------------------
def test_snapshot_and_live_are_replaced_atomically_and_only_when_they_changed(make):
    run, pub, run_dir = make(boundaries=False)
    assert pub.publish() is True
    snap_path, live_path = run_dir / "snapshot.json", run_dir / "live.json"
    snap, live = json.loads(snap_path.read_text()), json.loads(live_path.read_text())
    assert snap["status"] == "idle" and snap["saved"] is None and live["schema"] == "engine-live/1" and live["pid"] == os.getpid()
    assert {"output", "doc", "docset", "stages", "stage_i", "docs", "board", "site_tag", "sites", "at"} <= set(live)
    assert oct(snap_path.stat().st_mode & 0o777) == "0o600"
    inode, count = snap_path.stat().st_ino, pub.publishes
    time.sleep(1.1)                                       # `at` moves on by a second, which alone is no change
    assert pub.publish() is False and snap_path.stat().st_ino == inode and pub.publishes == count
    run.post("system", "a new line")
    assert pub.publish() is True
    assert snap_path.stat().st_ino != inode and json.loads(snap_path.read_text())["total"] == 1
    assert not [p for p in run_dir.iterdir() if ".tmp-" in p.name], "no temp file is left"


def test_a_post_reaches_the_files_within_the_250_ms_window_and_bursts_are_batched(make):
    run, pub, run_dir = make(boundaries=False)
    pub.publish()
    pub.start()
    try:
        time.sleep(0.3)                                    # the window since the last publish has passed
        start, base = time.time(), pub.publishes
        for i in range(30):
            run.post("system", f"burst {i}")
            pub.notify()
        wait_until(lambda: snap_of(run_dir).get("total") == 30, timeout=3, what="the burst")
        assert time.time() - start < 1.0
        time.sleep(0.6)
        assert pub.publishes - base <= 4, "at most one publish per 250 ms window"
        run.post("system", "later")
        pub.notify()
        wait_until(lambda: snap_of(run_dir).get("total") == 31, timeout=1.0, what="the later post")
    finally:
        pub.stop()


def test_the_publisher_wakes_every_second_while_the_run_is_running(make, monkeypatch):
    run, pub, run_dir = make(boundaries=False, wake_interval=0.05)
    run.status = "running"
    pub.start()
    try:
        run.thinking = "identity"                          # a change no hook announces
        wait_until(lambda: snap_of(run_dir).get("thinking") == "identity", timeout=2,
                   what="the periodic wake")
    finally:
        pub.stop()
        run.status = "waiting"


def test_a_publish_error_is_traced_and_never_raised(make, monkeypatch):
    run, pub, run_dir = make()
    from sutra_app.engine import views

    def boom(r):
        raise RuntimeError("no state today")
    monkeypatch.setattr(views, "live_state", boom)
    assert pub.publish() is False
    pub.boundary()                                         # the J2 hooks call this: it must not raise
    errors = trace(run_dir, "publish.error")
    assert errors and errors[0]["data"]["where"] == "live_state" and "no state today" in errors[0]["data"]["error"]


def test_nothing_is_published_after_stop_except_the_final_publish(make):
    run, pub, run_dir = make(boundaries=False)
    pub.publish()
    pub.stop()
    run.post("system", "after the stop")
    assert pub.publish() is False
    pub.final()
    assert json.loads((run_dir / "snapshot.json").read_text())["total"] == 1


# ---- the events ----------------------------------------------------------------------------------------------------------------
def test_one_publish_emits_node_then_step_then_atom_and_a_second_one_emits_nothing(make):
    run, pub, run_dir = make(boundaries=False)
    say(run, BREW_LAB)
    assert not [e for e in events(run_dir) if e["t"] in ("node", "step", "atom")], "only the publisher writes those, and it has not run"
    pub.publish(force=True)
    rows = [e for e in events(run_dir) if e["t"] in ("node", "step", "atom")]
    rank = {"node": 0, "step": 1, "atom": 2}
    assert [rank[e["t"]] for e in rows] == sorted(rank[e["t"]] for e in rows) and {e["t"] for e in rows} == set(rank)
    assert {e["fn"] for e in of(rows, "node") if "fn" in e} == set(FUNCTIONS)
    assert {e["step"] for e in of(rows, "node") if "step" in e} >= {"W-1", "W-2"}
    before = len(events(run_dir))
    pub.publish(force=True)
    assert len(events(run_dir)) == before, "on change only"
    for e in rows:
        parse_event(e, strict=True)


def test_a_changed_node_is_the_only_event_of_the_next_publish_and_wait_on_and_tokens_come_from_the_map(make):
    run, pub, run_dir = make(boundaries=False)
    say(run, VAGUE[0])
    assert run.paused
    pub.publish(force=True)
    identity = last_by(of(events(run_dir), "node"), "fn")["identity"]
    assert identity["status"] == "waiting_on_you" and identity["wait_on"] == "you" and identity["tokens"] == {"input": 0, "output": 0}
    run.call_log[0]["tokens"] = {"input": 30, "output": 7}
    run.call_log[0]["seconds"] = 1.5
    before = len(events(run_dir))
    pub.publish(force=True)
    new = events(run_dir)[before:]
    assert len(new) == 1 and new[0]["t"] == "node" and new[0]["fn"] == "identity"
    assert new[0]["tokens"] == {"input": 30, "output": 7} and new[0]["seconds"] == 1.5 and new[0]["calls"] == 1
    assert new[0]["wait_on"] == "you" and "goal" not in new[0]


def test_a_brew_lab_run_emits_valid_events_with_waits_builders_teams_and_forward_only_atoms(make):
    run, pub, run_dir = make()
    rows = brew(run, pub)
    for e in rows:
        parse_event(e, strict=True)
    waits = {(e["fn"], e["wait_on"]) for e in of(rows, "node") if "fn" in e and e.get("wait_on")}
    assert ("identity", "adaptation") in waits and all(w in FUNCTIONS + ("you",) or re.fullmatch(r"W-\d+", w) for _, w in waits)
    assert all(e["status"] in ("idle", "running", "waiting", "waiting_on_you", "fault") for e in of(rows, "node") if "fn" in e)
    builders = last_by([e for e in of(rows, "node") if "step" in e], "step")
    assert set(builders) >= {"W-1", "W-2", "W-3"} and all(re.fullmatch(r"W-\d+", b) for b in builders)
    assert builders["W-2"]["calls"] >= 1 and builders["W-2"]["status"] in ("filed", "idle", "done_unchecked")
    steps = last_by(of(rows, "step"), "step")
    workflows = {k: v for k, v in steps.items() if k.startswith("W-")}
    assert workflows["W-2"]["parent"] == "work:website" and workflows["W-2"]["name"]
    for wid, step in workflows.items():                    # handoff is the exact inverse of reads
        assert all(wid in workflows[r]["handoff"] for r in step["reads"] if r in workflows)
        assert all(wid in workflows[h]["reads"] for h in step["handoff"])
    teams = [v for k, v in steps.items() if k.startswith("team:")]
    assert teams and all(t["parent"] is None and t["reads"] == [] for t in teams)
    atoms = of(rows, "atom")
    assert atoms and all(a["atom"]["schema"] == "atom/1" and re.fullmatch(r"W-\d+\.a\d+", a["atom"]["id"]) for a in atoms)
    assert all(a["node"] == a["atom"]["id"].split(".")[0] and not {"outcome", "card", "ledger"} & set(a) for a in atoms)
    seen = {}
    for a in atoms:
        before = seen.get(a["atom"]["id"])
        assert before in (None, "open") and a["atom"]["status"] != before, "forward only: open, then one terminal word"
        seen[a["atom"]["id"]] = a["atom"]["status"]


def test_every_turn_boundary_publishes_so_every_function_turn_is_seen_running_and_done(make):
    run, pub, run_dir = make()                             # the publisher thread is not started: only the boundaries publish
    rows = brew(run, pub)
    turns = {t["data"]["turn_no"] for t in trace(run_dir, "turn.started") if t["data"]["function"] in FUNCTIONS}
    seen = {}
    for e in of(rows, "node"):
        if "task" in e:
            seen.setdefault(e["task"]["id"], []).append(e["task"]["state"])
    assert {f"t-{n}" for n in turns} <= set(seen) and len(turns) > 8
    assert all(states[0] == "running" and states[-1] == "done" for states in seen.values())
    running_event = next(e for e in of(rows, "node") if "task" in e and e["task"]["state"] == "running")
    assert running_event["task"]["summary"].startswith("J2.") and running_event["task"]["set_by"] and running_event["context"]


def test_final_publishes_the_last_state_before_run_ended_would_be_written(make):
    run, pub, run_dir = make(boundaries=False)
    say(run, BREW_LAB)
    pub.final()
    snap = json.loads((run_dir / "snapshot.json").read_text())
    assert snap["status"] == "waiting" and snap["done"] is True and snap["outcome"].startswith("Done")
    last_nodes = last_by([e for e in events(run_dir) if e["t"] == "node" and "fn" in e], "fn")
    assert all(n["status"] != "running" for n in last_nodes.values())


def test_an_atom_whose_status_changes_is_emitted_again_with_the_new_status(make):
    run, pub, run_dir = make(boundaries=False)
    say(run, BREW_LAB)
    pub.publish(force=True)
    first = of(events(run_dir), "atom")
    aid = first[0]["atom"]["id"]
    pub._atoms[aid] = ("open", 0)                          # as if it had been published open
    pub.publish(force=True)
    again = [a for a in of(events(run_dir), "atom") if a["atom"]["id"] == aid]
    assert len(again) == 2 and again[1]["atom"]["status"] == first[0]["atom"]["status"]
    assert again[1]["atom"]["ts_open"] == again[0]["atom"]["ts_open"], "ts_open is when the atom was first seen"


# ---- wait_on, builder status, HostHooks -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("display, expect", [
    (None, None), ("", None), ("Requester", "you"), ("Requester (you)", "you"), ("you", "you"), ("Adaptation", "adaptation"),
    ("identity", "identity"), ("W-3 Builder", "W-3"), ("W-12", "W-12"), ("Validator", None), ("System", None), ("Somebody", None),
    (42, None)])
def test_wait_on_maps_display_names_back_to_keys(display, expect):
    names = {"validator": "Validator", "identity": "Identity", "adaptation": "Adaptation", "priority": "Priority",
             "coordination": "Coordination", "audit": "Audit", "user": "Requester (you)", "system": "System", "W-12": "W-12 Builder"}
    assert wait_on_key(display, names) == expect
    assert wait_on_key("W-12 Builder", names) == "W-12"


@pytest.mark.parametrize("lane, workflow, atoms, expect", [
    ("working", "registered", None, "running"), ("idle", "running", "open", "running"), ("idle", "unfunded", None, "not_made"),
    ("blocked", "held", None, "fault"), ("idle", "failed", "verify_failed", "fault"), ("waiting", "registered", None, "waiting"),
    ("idle", "done", "closed", "filed"), ("idle", "done", None, "filed"), ("idle", "done", "verify_failed", "done_unchecked"),
    ("idle", "done", "abandoned", "not_made"), ("idle", "registered", None, "idle"), (None, None, None, "idle")])
def test_builder_status_uses_the_nine_map_words(lane, workflow, atoms, expect):
    assert builder_status(lane, workflow, atoms) == expect


def test_host_hooks_forward_every_hook_remember_the_error_code_and_read_through(make):
    calls = []

    class Inner(EventHooks):
        def __init__(self):
            self.last_error = None
            self.marker = "read through"

        def run_started(self, spec): calls.append(("run_started", spec))
        def run_status(self, snap): calls.append(("run_status", snap))
        def turn_started(self, t): calls.append(("turn_started", t))
        def turn_finished(self, t, o): calls.append(("turn_finished", t, o))
        def call_finished(self, c): calls.append(("call_finished", c)); return None
        def message_posted(self, m, questions=None): calls.append(("message_posted", m, questions))
        def record_saved(self, name, data): calls.append(("record_saved", name)); return ["w"]
        def run_error(self, code, message): calls.append(("run_error", code, message))
        def system_addendum(self, fn): return "extra for " + fn

    class FakePub:
        def __init__(self): self.log = []
        def notify(self): self.log.append("notify")
        def turn_started(self, t): self.log.append("turn_started")
        def turn_finished(self, t): self.log.append("turn_finished")
        def boundary(self): self.log.append("boundary")

    pub, hooks = FakePub(), None
    hooks = HostHooks(Inner(), pub)
    info = TurnInfo(run_id=RUN_ID, dept_id="web", turn_no=1, function="identity", step=1, step_label="J2.a", cycle=1, task="t", context=[])
    outcome = TurnOutcome(result="ok")
    hooks.run_started({"a": 1})
    hooks.run_status({"s": 1})
    hooks.turn_started(info)
    hooks.turn_finished(info, outcome)
    hooks.call_finished("call")
    hooks.message_posted({"id": 1}, questions=["q"])
    assert hooks.record_saved("x.json", {}) == ["w"]
    hooks.run_error("quota", "out of quota")
    assert [c[0] for c in calls] == ["run_started", "run_status", "turn_started", "turn_finished", "call_finished", "message_posted",
                                     "record_saved", "run_error"]
    assert calls[5][2] == ["q"] and (hooks.error_code, hooks.error_message) == ("quota", "out of quota")
    assert hooks.system_addendum("audit") == "extra for audit" and hooks.marker == "read through"
    assert pub.log == ["notify", "turn_started", "boundary", "turn_finished", "boundary", "notify", "notify", "notify"]


def test_a_failing_inner_turn_started_reaches_j2_and_a_failing_turn_finished_still_closes_the_task(make):
    class Fatal(RuntimeError):
        fatal = True

    class Inner(EventHooks):
        def __init__(self, fail_start):
            self.fail_start = fail_start

        def turn_started(self, t):
            if self.fail_start:
                raise Fatal("strict")

        def turn_finished(self, t, o):
            raise Fatal("strict end")

    class FakePub:
        def __init__(self): self.log = []
        def notify(self): pass
        def turn_started(self, t): self.log.append("turn_started")
        def turn_finished(self, t): self.log.append("turn_finished")
        def boundary(self): self.log.append("boundary")

    info = TurnInfo(run_id=RUN_ID, dept_id="web", turn_no=1, function="identity", step=1, step_label="J2.a", cycle=1, task="t", context=[])
    pub = FakePub()
    with pytest.raises(Fatal):
        HostHooks(Inner(True), pub).turn_started(info)
    assert pub.log == [], "a refused turn start is not published as a turn"
    with pytest.raises(Fatal):
        HostHooks(Inner(False), pub).turn_finished(info, TurnOutcome(result="ok"))
    assert pub.log == ["turn_finished", "boundary"]


def test_the_host_publishes_files_and_events_in_a_real_host_run(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    assert Running(run_dir, "--mock").wait() == 0
    rows = events(run_dir)
    assert rows[-1]["t"] == "run.ended"
    snap = json.loads((run_dir / "snapshot.json").read_text())
    assert snap["status"] == "waiting" and snap["done"] is True, "the final publish came before run.ended"
    assert json.loads((run_dir / "live.json").read_text())["output"] == "website"
    assert [e["t"] for e in rows if e["t"] in ("node", "step", "atom")][:1] == ["node"]
    assert all(rows.index(e) < len(rows) - 1 for e in rows if e["t"] != "run.ended"), "run.ended is last"
    last = last_by([e for e in rows if e["t"] == "node" and "fn" in e], "fn")
    assert all(n["status"] != "running" for n in last.values())
    append_inbox(run_dir, 1, "stop")                       # unread: the run is over
