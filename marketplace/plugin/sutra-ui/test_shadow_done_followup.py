#!/usr/bin/env python3
"""ANSWERING A FINISHED TASK IS NOT REOPENING IT (founder, 2026-09-21, p13).

THE BUG, REPRODUCED:

    founder  "Make a file of 10 lines about Pedro Acosta"
    worker   writes and verifies pedro-acosta.txt
    mission  DONE
    founder  "Can you print those 10 lines here please?"
    -> Shadow answers with the ten lines, AND the rail goes back to RUNNING

THE TRANSITION THAT CAUSED IT, and it was an ORDERING bug rather than a
missing rule. api_shadow_task_chat opened with:

    reopened = mission["state"] in TERMINAL
    if reopened:
        mission = _reopen_and_launch(store, mid, message, "talk")

-- unconditional, and BEFORE Shadow had read the message. V4-9 introduced it
for a good reason (a terminal task used to refuse the founder's words with a
409) and simply had nothing to consult: the `forward` verdict is produced by
the talk turn, which had not happened yet.

THE FIX IS THE ORDER. Answering mutates nothing, so the talk moves ahead of
the reopen and the reopen is gated on shadow_forward.classify -- the same
authority resume_after_reply already uses for a paused task, and Shadow's own
verdict rather than a second classifier. No keyword list, no second state
machine.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_done_followup.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

# THE HOME IS BOUND BEFORE THE FIRST IMPORT, not in setUp. conftest.py
# does this for pytest, and the DMG gate runs these lanes through
# run-tests.sh (plain unittest), where nothing does -- so anything that
# ledgers during import or outside a test method reached the LIVE shadow
# home. shadow_ledger refuses that outright, which is how this was
# caught; a per-test temp home still binds in setUp on top of it.
os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="shadow-done-followup-"))

import app as app_module
from fastapi.testclient import TestClient

import mission_engine
import providers
import shadow_protocol
import shadow_runner
from mission_engine import MissionStore

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


def forward(worker):
    """Shadow's own verdict on this turn, the way it really arrives."""
    return "Here you go.\n```forward\n%s\n```" % json.dumps({"worker": worker})


class FakeChat:
    def __init__(self):
        self.replies = []
        self.heard = []
        self.alive = True

    async def talk(self, message):
        self.heard.append(message)
        raw = self.replies.pop(0) if self.replies else "Noted."
        return shadow_protocol.parse_reply(raw)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self.chat = FakeChat()
        self._real_ensure = app_module._ensure_task_chat

        async def _ensure(mission):
            return self.chat
        app_module._ensure_task_chat = _ensure
        self.launched = []
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        app_module._ensure_task_chat = self._real_ensure
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    _n = 0

    def finished(self):
        """A task that produced its file and completed, like the report.

        A UNIQUE worker session per task: the mission fence refuses a second
        mission driving one chat ("that chat is already driven by task ..."),
        which is correct and is not what these lanes are about."""
        Base._n += 1
        m = self.store.create(
            "Make a file of 10 lines about Pedro Acosta", "research",
            target_mode="existing", target_session="s-worker-%d" % Base._n,
            done_when=[{"tier": "contains_artifact",
                        "check": "pedro-acosta.txt"}])
        mid = m["id"]
        m = self.store.load(mid)
        m["state"], m["turns_used"] = "done", 3
        m["completion"] = {"headline": "1 of 1 checks passed",
                           "artifacts": ["pedro-acosta.txt"],
                           "said": "pedro-acosta.txt has 10 lines on his "
                                   "2026 season."}
        self.store.save(m)
        return mid

    def talk(self, mid, message, worker):
        self.chat.replies = [forward(worker)]
        return self.client.post("/api/shadow/tasks/%s/chat" % mid,
                                json={"message": message}, headers=HDR)

    def state(self, mid):
        return self.store.load(mid)["state"]


class AFollowUpLeavesItFinished(Base):
    """LANE 1 + 2: artifact follow-up and status follow-up. Shadow says the
    founder was asking IT something, so nothing moves."""

    ASKS = [
        "Can you print those 10 lines here please?",
        "Show me the file contents",
        "What did you put in the file?",
        "Summarize what you created",
        "Where are we at?",
        "What did you do?",
        "Is it finished?",
    ]

    def test_every_follow_up_leaves_the_mission_done(self):
        for ask in self.ASKS:
            with self.subTest(ask=ask):
                mid = self.finished()
                r = self.talk(mid, ask, worker=False)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(self.state(mid), "done", ask)

    def test_the_worker_is_not_relaunched(self):
        mid = self.finished()
        self.talk(mid, "Can you print those 10 lines here please?",
                  worker=False)
        self.assertEqual(self.launched, [], "the worker must not come back")

    def test_the_route_does_not_report_a_reopen(self):
        """The client draws "Back on it -- this task is running again." and
        re-reads the rail on `reopened`. No reopen, no flip."""
        mid = self.finished()
        r = self.talk(mid, "Show me the file contents", worker=False)
        self.assertNotIn("reopened", r.json())

    def test_shadow_still_answers(self):
        mid = self.finished()
        r = self.talk(mid, "What did you put in the file?", worker=False)
        self.assertEqual(r.json()["reply"], "Here you go.")
        self.assertTrue(self.chat.heard, "Shadow must still be asked")

    def test_no_second_mission_is_created(self):
        mid = self.finished()
        self.talk(mid, "Summarize what you created", worker=False)
        self.assertEqual(len(self.store.list()), 1)

    def test_the_completion_is_untouched(self):
        """The result the founder is asking about must survive being asked
        about -- including completion.said from pass 12."""
        mid = self.finished()
        before = dict(self.store.load(mid)["completion"])
        self.talk(mid, "Can you print those 10 lines here please?",
                  worker=False)
        self.assertEqual(self.store.load(mid)["completion"], before)

    def test_the_record_is_not_written_either(self):
        """AND NOT FORGOTTEN, which is a different thing. `founder_says` is
        INPUT TO A DECISION and a done mission has no decision to take, so
        _record_founder_talk has always refused a terminal record -- that
        guard is untouched here. The exchange is not lost: it is in the
        task's own Shadow chat, which is a real session the founder can
        open, and which is where Shadow reads it from next time."""
        mid = self.finished()
        self.talk(mid, "What did you put in the file?", worker=False)
        self.assertEqual(self.store.load(mid).get("founder_says") or [], [],
                         "a done mission takes no decision input")
        self.assertIn("What did you put in the file?", self.chat.heard[-1],
                      "but Shadow was asked, in its own chat")


class NewWorkStillReopensIt(Base):
    """LANE 3: a revision or new work is what V4-9 exists for, and is
    unchanged."""

    CHANGES = [
        "Change it to 15 lines.",
        "Update the file with today's information.",
        "update it with today's latest information",
        "Make the same thing for Marc Marquez.",
    ]

    def test_every_change_reopens_and_relaunches(self):
        for change in self.CHANGES:
            with self.subTest(change=change):
                mid = self.finished()
                self.launched = []
                r = self.talk(mid, change, worker=True)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(self.state(mid), "running", change)
                self.assertEqual(self.launched, [mid], change)
                self.assertTrue(r.json().get("reopened"), change)

    def test_it_is_the_same_mission(self):
        mid = self.finished()
        self.talk(mid, "Change it to 15 lines.", worker=True)
        self.assertEqual(len(self.store.list()), 1,
                         "a revision must not fork a second mission")

    def test_a_missing_verdict_still_reopens(self):
        """THE FLOOR, unchanged: a dropped fence must never silently swallow
        "change it to 15 lines". classify falls to _is_meta_only, which
        defaults to forwarding."""
        mid = self.finished()
        self.chat.replies = ["Sure."]        # no forward fence at all
        self.client.post("/api/shadow/tasks/%s/chat" % mid,
                         json={"message": "Change it to 15 lines."},
                         headers=HDR)
        self.assertEqual(self.state(mid), "running")


class NothingElseMoved(Base):
    """The states this pass must not touch."""

    def test_a_running_task_is_unaffected(self):
        m = self.store.create("x", "fix", target_mode="existing",
                              target_session="s", done_when=[])
        mid = m["id"]
        m = self.store.load(mid)
        m["state"] = "running"
        self.store.save(m)
        r = self.talk(mid, "where are we at?", worker=False)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.state(mid), "running")
        self.assertNotIn("reopened", r.json())

    def test_a_needs_you_task_is_not_reopened_by_this_path(self):
        """A paused task is not terminal, so this gate never sees it --
        resume_after_reply owns that case and is unchanged."""
        m = self.store.create("x", "fix", target_mode="existing",
                              target_session="s",
                              done_when=[{"tier": "founder_confirm",
                                          "check": "it is what you want"}])
        mid = m["id"]
        m = self.store.load(mid)
        m["state"], m["pause_reason"] = "paused", "founder_confirm"
        self.store.save(m)
        r = self.talk(mid, "Is it finished?", worker=False)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.state(mid), "paused",
                         "a status question must not move a NEEDS YOU task")
        self.assertEqual(self.launched, [])

    def test_a_stopped_task_follows_the_same_two_lanes(self):
        """`stopped` is terminal too, and gets the same treatment."""
        mid = self.finished()
        m = self.store.load(mid)
        m["state"] = "stopped"
        self.store.save(m)
        self.talk(mid, "What did you do?", worker=False)
        self.assertEqual(self.state(mid), "stopped")


if __name__ == "__main__":
    unittest.main()
