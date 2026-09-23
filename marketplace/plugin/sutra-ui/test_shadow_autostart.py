"""test_shadow_autostart.py -- WORK SHADOW READ IS WORK THAT STARTS
(founder, 2026-09-23: "the worker MUST start automatically. There must be
NO user confirmation step").

THE BUG THIS PINS. A `mission` fence created the mission inside
/api/shadow/chat and left it at `brief_confirm`; a SECOND call from the
client -- POST .../act {start_now} -- was what actually ran it. The task's
existence and the task's start had two different owners, so any way of
losing that second call parked a task at READY behind a "Start the task"
button. Measured in the founder's live store: m-14047f1adc4e, "Draw a
diagram in a file about motorcycles", target_mode new, created and never
start-requested.

The start is now taken in the same turn that creates the mission. Nothing
here inspects the prompt: a fence starts, no fence creates nothing.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_autostart.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="shadow-autostart-"))

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore        # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


def _fence(objective, template="research", **extra):
    spec = {"objective": objective, "template": template,
            "target_mode": "new",
            "done_when": [{"tier": "judge", "check": "it is done"}]}
    spec.update(extra)
    return "```mission\n" + json.dumps(spec) + "\n```"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self._saved = app_module._SHADOW.get("session")
        self.client = TestClient(app_module.app, base_url="http://127.0.0.1")
        #: every start the runner is asked to take, without taking one
        self.started = []
        self._real_start = shadow_runner.start_mission_async
        shadow_runner.start_mission_async = (
            lambda mid, *a, **k: self.started.append(mid))

    def tearDown(self):
        shadow_runner.start_mission_async = self._real_start
        app_module._SHADOW["session"] = self._saved
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def _shadow_says(self, raw):
        class Rt:
            async def send_user_frame(self, _text):
                return None

            async def demux_turn(self, collect, sid):
                await collect({"type": "token", "text": raw})
                return (sid or "shadow-sess", 0.0, True, None, None)

        class Sess:
            alive = True
            session_id = "shadow-sess"
            rt = Rt()

        app_module._SHADOW["session"] = Sess()

    def _intake(self, message):
        return self.client.post("/api/shadow/chat",
                                json={"message": message, "intake": True},
                                headers=HDR).json()


class ActionableWorkStartsItself(Base):

    def test_a_fence_from_intake_is_started_in_the_same_turn(self):
        self._shadow_says("On it.\n" + _fence("Pull the latest news"))
        doc = self._intake("Pull the latest news")
        mid = doc["mission"]["id"]
        self.assertEqual(self.started, [mid],
                         "the runner was asked to start it, unprompted")

    def test_the_start_is_stamped_so_no_Start_button_is_drawn(self):
        """`brief_confirm` with no start stamp is exactly the shape that
        draws READY + "Start the task". The stamp is what removes it."""
        self._shadow_says("On it.\n" + _fence("Draw a diagram in a file"))
        doc = self._intake("Draw a diagram in a file about motorcycles")
        rec = self.store.load(doc["mission"]["id"])
        self.assertTrue(rec.get("start_requested_at"),
                        "the founder must have nothing left to press")

    def test_the_founder_reads_a_started_record_not_a_draft(self):
        self._shadow_says("On it.\n" + _fence("Make me a 10-day Africa plan"))
        doc = self._intake("Make me a 10-day Africa plan")
        self.assertTrue(doc["mission"].get("start_requested_at"),
                        "the record in the REPLY carries the stamp too")

    def test_every_fence_of_a_multi_task_reply_starts(self):
        self._shadow_says("Two things.\n" + _fence("first thing") + "\n"
                          + _fence("second thing"))
        doc = self._intake("do two things")
        ids = [m["id"] for m in doc["missions"]]
        self.assertEqual(len(ids), 2)
        self.assertEqual(sorted(self.started), sorted(ids),
                         "neither is left behind a button")

    def test_nothing_about_the_prompt_is_inspected(self):
        """The same short lowercase line starts or does not start purely on
        whether Shadow emitted a fence -- never on what it says."""
        self._shadow_says("On it.\n" + _fence("hi"))
        doc = self._intake("hi")
        self.assertEqual(self.started, [doc["mission"]["id"]],
                         "a fence on 'hi' starts, because Shadow said so")


class ConversationStartsNothing(Base):

    def test_no_fence_means_no_mission_and_no_start(self):
        self._shadow_says("Hi. What would you like done?")
        doc = self._intake("Hi")
        self.assertIsNone(doc.get("mission"))
        self.assertEqual(self.started, [], "nothing was started")
        self.assertEqual(self.store.list(), [], "and nothing was created")


class AProposalKeepsItsBrief(Base):
    """The boundary that did NOT move: a mission proposed inside an ordinary
    chat is a proposal, and the founder still opens it."""

    def test_a_fence_outside_intake_is_not_started(self):
        self._shadow_says("I could do that.\n" + _fence("Pull the news"))
        doc = self.client.post("/api/shadow/chat",
                               json={"message": "could you pull the news?"},
                               headers=HDR).json()
        mid = doc["mission"]["id"]
        self.assertEqual(self.started, [], "a proposal starts nothing")
        self.assertEqual(self.store.load(mid)["state"], "brief_confirm")
        self.assertFalse(self.store.load(mid).get("start_requested_at"))


if __name__ == "__main__":
    unittest.main()
