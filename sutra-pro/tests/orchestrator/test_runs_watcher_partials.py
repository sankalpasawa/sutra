"""The watcher's live view of the agents (D133, WP9): `agent_live.json` -> `chat.partial` events, in the reset form.

The watcher reads the engine's file only when it changed and publishes one partial per working agent to that agent's chat session (a lookup the wiring
gives it, never an open), each replacing the last (`reset: true`, the text so far, the last tool line); an agent that is gone, or a run that ended, gets
`{reset: true, delta: "", done: true}`. With `publish` or `agent_session` unset the watcher is what it was. The partial is a control event of the bus:
shown, never stored, never replayed."""
from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

from sutra_app.orchestrator.events import CONTROL_TYPES, PARTIAL, EventBus
from sutra_app.orchestrator.runs import LIVE_FILE, LiveView, RunWatcher, live_partials, read_live

TASK = "tsk_aaaaaaaaaaaa"


def write_live(run_dir, agents, schema="agent-live/1"):
    body = {"schema": schema, "at": 1.0, "agents": {who: {"call": 1, "since": 1.0, "text": text, "tool": tool, "tools": 1 if tool else 0}
                                                    for who, (text, tool) in agents.items()}}
    tmp = run_dir / ".live.tmp"
    tmp.write_text(json.dumps(body), encoding="utf-8")
    os.replace(tmp, run_dir / LIVE_FILE)
    st = os.stat(run_dir / LIVE_FILE)
    os.utime(run_dir / LIVE_FILE, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))          # a changed stamp even on a coarse clock


class Rig:
    def __init__(self, tmp_path, *, sessions=None, status="running", with_run=True):
        self.run_dir = tmp_path / "run"
        self.run_dir.mkdir()
        self.row = SimpleNamespace(id=TASK, status=status, pid=11, run_id="j2-20261109-000000-ab12" if with_run else None, last_event_at=0, started_at=0,
                                   created_at=0)
        self.sessions = {"identity": "cs_id", "W-3": "cs_w3"} if sessions is None else sessions
        self.looked = []
        self.published = []
        self.ended = False
        rig = self

        class Projector:
            def drain(self, task_id):
                return SimpleNamespace(ended=rig.ended, more=False, freed_slot=False)

        class Tasks:
            def find_row(self, task_id):
                return rig.row

            def run_dir_of(self, row):
                return rig.run_dir

        class Launcher:
            def alive(self, pid):
                return True

        self.watcher = RunWatcher(Projector(), Tasks(), Launcher(), interval=0.01, clock=SimpleNamespace(now=lambda: 0.0), publish=lambda t, d: self.published.append((t, d)),
                                  agent_session=self.lookup, redact=lambda text: text.replace("SECRET", "[x]"))

    def lookup(self, row, who):
        self.looked.append(who)
        return self.sessions.get(who)

    def tick(self):
        return asyncio.run(self.watcher.tick(TASK))

    def ticks(self, n=1):
        async def main():
            return [await self.watcher.tick(TASK) for _ in range(n)]
        return asyncio.run(main())


def test_a_working_agent_becomes_a_reset_partial_for_its_session(tmp_path):
    rig = Rig(tmp_path)
    write_live(rig.run_dir, {"W-3": ("Findings: the app has", "Read src/app.py")})
    assert rig.tick() is False
    assert rig.published == [(PARTIAL, {"session_id": "cs_w3", "message_id": 0, "who": "W-3", "delta": "Findings: the app has", "reset": True,
                                         "tool": "Read src/app.py"})]


def test_nothing_is_published_until_the_file_changes_and_an_unchanged_agent_is_not_repeated(tmp_path):
    rig = Rig(tmp_path)
    write_live(rig.run_dir, {"W-3": ("a", "")})
    rig.ticks(3)
    assert len(rig.published) == 1                                                      # three looks, one change
    write_live(rig.run_dir, {"W-3": ("a", ""), "identity": ("b", "")})                  # a second agent: only it is new
    rig.tick()
    assert [d["who"] for _, d in rig.published] == ["W-3", "identity"]
    write_live(rig.run_dir, {"W-3": ("ab", ""), "identity": ("b", "")})
    rig.tick()
    assert [(d["who"], d["delta"]) for _, d in rig.published[2:]] == [("W-3", "ab")]


def test_an_agent_that_is_gone_gets_the_done_form(tmp_path):
    rig = Rig(tmp_path)
    write_live(rig.run_dir, {"W-3": ("x", "")})
    rig.tick()
    write_live(rig.run_dir, {})
    rig.tick()
    assert rig.published[-1] == (PARTIAL, {"session_id": "cs_w3", "message_id": 0, "who": "W-3", "delta": "", "reset": True, "done": True})
    rig.tick()
    assert len(rig.published) == 2                                                      # said once


def test_a_run_that_ends_closes_every_open_agent_row(tmp_path):
    rig = Rig(tmp_path)
    write_live(rig.run_dir, {"W-3": ("x", ""), "identity": ("y", "")})
    rig.tick()
    rig.ended = True
    assert rig.tick() is True
    done = [d for _, d in rig.published if d.get("done")]
    assert sorted(d["who"] for d in done) == ["W-3", "identity"] and all(d["delta"] == "" and d["reset"] for d in done)
    rig.tick()
    assert len([1 for _, d in rig.published if d.get("done")]) == 2


def test_the_session_is_looked_up_once_per_agent_and_a_missing_one_is_tried_again(tmp_path):
    rig = Rig(tmp_path, sessions={})
    write_live(rig.run_dir, {"W-3": ("x", "")})
    rig.ticks(2)
    assert rig.published == [] and rig.looked == ["W-3", "W-3"]                         # no chat yet: nothing shown, looked for at the next tick
    rig.sessions["W-3"] = "cs_w3"
    rig.tick()
    assert [d["session_id"] for _, d in rig.published] == ["cs_w3"]
    write_live(rig.run_dir, {"W-3": ("xy", "")})
    rig.tick()
    assert rig.looked == ["W-3", "W-3", "W-3"] and len(rig.published) == 2              # cached after it was found


def test_what_is_published_is_redacted(tmp_path):
    rig = Rig(tmp_path)
    write_live(rig.run_dir, {"W-3": ("the key is SECRET", "Read SECRET.txt")})
    rig.tick()
    data = rig.published[0][1]
    assert data["delta"] == "the key is [x]" and data["tool"] == "Read [x].txt"


def test_a_file_that_is_not_ours_or_does_not_read_shows_nothing(tmp_path):
    rig = Rig(tmp_path)
    write_live(rig.run_dir, {"W-3": ("x", "")}, schema="agent-live/9")
    rig.tick()
    (rig.run_dir / LIVE_FILE).write_text("{broken", encoding="utf-8")
    rig.tick()
    assert rig.published == []
    stamp, agents = read_live(rig.run_dir)
    assert stamp is not None and agents == {}
    assert read_live(rig.run_dir / "nowhere") == (None, {})


def test_with_no_run_yet_or_no_wiring_the_watcher_does_what_it_did(tmp_path):
    rig = Rig(tmp_path, with_run=False)
    write_live(rig.run_dir, {"W-3": ("x", "")})
    assert rig.tick() is False and rig.published == []
    (tmp_path / "b").mkdir()
    bare = Rig(tmp_path / "b")
    bare.watcher.publish = None
    write_live(bare.run_dir, {"W-3": ("x", "")})
    bare.tick()
    assert bare.published == [] and bare.looked == []
    bare.watcher.publish, bare.watcher.agent_session = lambda t, d: bare.published.append((t, d)), None
    bare.tick()
    assert bare.published == []


def test_a_failing_lookup_never_stops_the_watcher(tmp_path):
    rig = Rig(tmp_path)

    def boom(row, who):
        raise RuntimeError("database is locked")

    rig.watcher.agent_session = boom
    write_live(rig.run_dir, {"W-3": ("x", "")})
    assert rig.tick() is False and rig.published == []


def test_live_partials_is_pure_over_its_view():
    view = LiveView()
    out = live_partials(view, {"A": ("t", "")}, lambda who: "cs_a", lambda s: s)
    assert out == [(PARTIAL, {"session_id": "cs_a", "message_id": 0, "who": "A", "delta": "t", "reset": True, "tool": ""})]
    assert live_partials(view, {"A": ("t", "")}, lambda who: "never", lambda s: s) == []


def test_the_partial_is_a_control_event_of_the_bus_shown_never_stored(tmp_path):
    bus = EventBus()
    rig = Rig(tmp_path)
    rig.watcher.publish = bus.publish_one                                               # the bus takes the event the watcher builds (it drops an invalid one)
    write_live(rig.run_dir, {"W-3": ("x", "")})
    assert rig.tick() is False
    assert PARTIAL in CONTROL_TYPES and PARTIAL == "chat.partial"                       # broadcast to the open streams only: no seq, never in the ring
