"""Shadow v4.1 over HTTP (SHADOW-V3 section 13, founder 2026-09-21).

The three journeys the rulings add, each through the real routes with only
the two model-backed seams faked (the task's Shadow chat, and the loop
launcher):

  J7  SAY A LIMIT.  The founder says "no turn limit" in a task's chat; Shadow
      answers with a `limits` fence; the app applies it to THAT task at once,
      the reply carries a chip with Undo, and Undo puts it back.
  J8  REOPEN.  The founder gives a finished task more to do; the task goes
      back to work on the same record instead of answering 409.
  J9  TAKE OVER, THEN HAND BACK AFTER THE END.  A take-over pause waits
      (nothing times it out) and Resume brings Shadow back; on a finished
      task, Hand back reopens it.

Plus the protocol (what a `limits` fence may and may not carry) and the
default-scope writer the Now chat uses.

Run: ./run-tests.sh test_shadow_v41_routes.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-v41-routes-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_protocol                         # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
MIS = "/api/shadow/missions"


def fence(obj):
    return "```limits\n%s\n```" % json.dumps(obj)


class FakeChat:
    """The task's Shadow chat: answers with whatever the test queued, parsed
    by the REAL protocol so a malformed fence fails here as it would live."""

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
        self.chat_down = False
        self._real_ensure = app_module._ensure_task_chat

        async def _ensure(mission):
            if self.chat_down:
                raise RuntimeError("shadow chat will not boot")
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

    def task(self, state="running", target="s-worker", kind="fix",
             turns_used=0):
        m = self.store.create("make the login test pass", kind,
                              target_mode="existing", target_session=target,
                              done_when=[{"tier": "founder_confirm",
                                          "check": "the test passes"}])
        m = self.store.load(m["id"])
        m["state"], m["turns_used"] = state, turns_used
        self.store.save(m)
        return m["id"]

    def talk(self, mid, message, reply="Noted."):
        self.chat.replies = [reply]
        return self.client.post("/api/shadow/tasks/%s/chat" % mid,
                                json={"message": message}, headers=HDR)

    def act(self, mid, action, **body):
        return self.client.post("%s/%s/act" % (MIS, mid),
                                json={"action": action, **body}, headers=HDR)


# --------------------------------------------------------------- PROTOCOL --
class TestTheLimitsFence(unittest.TestCase):

    def parse(self, obj):
        return shadow_protocol.parse_reply("Done.\n" + fence(obj))

    def test_01_a_number_for_this_task(self):
        display, blocks = self.parse({"turns": 100})
        self.assertEqual(blocks["limits"], {"scope": "task", "turns": 100})
        self.assertEqual(display, "Done.", "the fence is off the display")

    def test_02_no_limit_in_the_founders_words(self):
        for said in (None, "none", "no limit", "unlimited", "Off"):
            _, blocks = self.parse({"turns": said})
            self.assertEqual(blocks["limits"]["turns"], "none", said)

    def test_03_the_default_scope_and_running_at_once(self):
        _, blocks = self.parse({"scope": "default", "turns": 40,
                                "running_at_once": 8})
        self.assertEqual(blocks["limits"], {"scope": "default", "turns": 40,
                                            "running_at_once": 8})

    def test_04_a_malformed_fence_stays_visible_and_sets_nothing(self):
        for bad in ({"turns": "twenty"}, {"turns": 0}, {"turns": True},
                    {"scope": "everyone", "turns": 5}, {"scope": "task"},
                    {"running_at_once": -1}, [5], "none"):
            display, blocks = self.parse(bad)
            self.assertNotIn("limits", blocks, bad)
            self.assertIn("```limits", display, bad)

    def test_05_a_fence_cannot_reach_anything_but_the_two_numbers(self):
        """The four floors, autonomy, another task's id: not settable by
        words. An extra key refuses the WHOLE fence rather than being
        dropped, so a model cannot smuggle one through beside a legal one."""
        for extra in ("floors", "autonomy", "mission_id", "budget_tokens"):
            _, blocks = self.parse({"turns": 50, extra: "x"})
            self.assertNotIn("limits", blocks, extra)

    def test_06_the_first_fence_wins(self):
        _, blocks = shadow_protocol.parse_reply(
            fence({"turns": 50}) + "\n" + fence({"turns": "none"}))
        self.assertEqual(blocks["limits"]["turns"], 50)


# --------------------------------------------------------------------- J7 --
class TestJ7SayALimit(Base):

    def test_10_no_limit_said_in_the_task_chat_binds_the_running_task(self):
        mid = self.task(turns_used=5)
        r = self.talk(mid, "no turn limit on this one",
                      "Done, no turn limit.\n" + fence({"turns": "none"}))
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        self.assertEqual(doc["reply"], "Done, no turn limit.")
        self.assertEqual(doc["limits"]["applied"][0]["label"],
                         "turns: no limit, this task")
        self.assertEqual(doc["limits"]["applied"][0]["undo"],
                         {"mid": mid, "action": "undo_limits"})
        self.assertTrue(doc["mission"]["no_turn_limit"],
                        "the reply carries the record as it NOW reads")
        m = self.store.load(mid)
        self.assertEqual(m["state"], "running", "and it never stopped running")
        m["turns_used"] = 900
        self.assertFalse(mission_engine.out_of_turns(m))

    def test_11_a_number_binds_too_and_undo_puts_it_back(self):
        mid = self.task()
        r = self.talk(mid, "give it 100 turns", "Ok.\n" + fence({"turns": 100}))
        self.assertEqual(self.store.load(mid)["max_turns"], 100)
        self.assertEqual(r.json()["limits"]["applied"][0]["label"],
                         "turns: 100, this task")
        u = self.act(mid, "undo_limits")
        self.assertEqual(u.status_code, 200, u.text)
        self.assertEqual(u.json()["max_turns"], 20)
        self.assertEqual(u.json()["limits_label"], "")
        self.assertEqual(self.act(mid, "undo_limits").status_code, 409,
                         "nothing left to undo is said, not swallowed")

    def test_12_a_refusal_is_an_answer_not_an_error(self):
        mid = self.task(turns_used=12)
        r = self.talk(mid, "cap it at 10 turns", "Ok.\n" + fence({"turns": 10}))
        self.assertEqual(r.status_code, 200)
        lim = r.json()["limits"]
        self.assertEqual(lim["applied"], [])
        self.assertIn("already used 12 turns", lim["refused"][0])
        self.assertEqual(self.store.load(mid)["max_turns"], 20)

    def test_13_a_reply_with_no_fence_carries_no_limits_key(self):
        mid = self.task()
        self.assertNotIn("limits", self.talk(mid, "how is it going?").json())

    def test_14_always_wording_changes_the_default_not_this_task(self):
        mid = self.task()
        r = self.talk(mid, "always give fixes 40 turns",
                      "Ok.\n" + fence({"scope": "default", "turns": 40}))
        self.assertEqual(r.json()["limits"]["applied"][0]["label"],
                         "turns: 40, every new fix task")
        self.assertEqual(mission_engine.turn_budget("fix"), 40)
        self.assertEqual(self.store.load(mid)["max_turns"], 20,
                         "a default binds the NEXT task, as it always has")

    def test_15_no_limit_is_per_task_and_the_default_says_so(self):
        got = app_module._apply_limits_fence(
            {"limits": {"scope": "default", "turns": "none"}})
        self.assertEqual(got["applied"], [])
        self.assertIn("per task", got["refused"][0])
        self.assertEqual(mission_engine.turn_budget("fix"), 20)

    def test_16_running_at_once_from_a_chat_writes_the_same_store(self):
        got = app_module._apply_limits_fence(
            {"limits": {"scope": "default", "running_at_once": 8}})
        self.assertEqual(got["applied"][0]["label"], "running at once: 8")
        self.assertEqual(mission_engine.max_running(), 8)

    def test_17_the_click_path_uses_the_same_writer(self):
        mid = self.task()
        r = self.act(mid, "set_limits", turns="none")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["limits_label"], "turns: no limit, this task")
        self.assertEqual(self.act(mid, "set_limits").status_code, 400)
        self.assertEqual(self.act(mid, "set_limits", turns="lots").status_code,
                         409)

    def test_18_a_limit_said_while_drafting_lands_on_the_draft(self):
        mid = self.task(state="brief_confirm")
        self.talk(mid, "no turn limit", "Ok.\n" + fence({"turns": "none"}))
        self.assertTrue(self.store.load(mid)["no_turn_limit"])


# --------------------------------------------------------------------- J8 --
class TestJ8AFinishedTaskReopens(Base):

    def test_20_more_work_for_a_done_task_is_200_not_409(self):
        for state in ("done", "stopped", "failed"):
            mid = self.task(state=state, target="s-" + state, turns_used=6)
            r = self.talk(mid, "also cover the logout path", "On it.")
            self.assertEqual(r.status_code, 200, "%s: %s" % (state, r.text))
            doc = r.json()
            self.assertTrue(doc["reopened"])
            self.assertEqual(doc["reply"], "On it.")
            self.assertEqual(doc["mission"]["id"], mid, "the SAME record")
            self.assertEqual(doc["mission"]["state"], "running")
            self.assertEqual(doc["mission"]["target_session"], "s-" + state,
                             "the SAME worker chat")
            self.assertIn(mid, self.launched, "and its loop is back")

    def test_21_the_words_are_recorded_once(self):
        """reopen writes them (via "reopen"); _record_founder_talk must not
        write them a second time or Shadow reads the same line twice."""
        mid = self.task(state="done")
        self.talk(mid, "also cover the logout path")
        says = self.store.load(mid)["founder_says"]
        self.assertEqual([s["via"] for s in says], ["reopen"])

    def test_22_the_reopen_stands_when_the_shadow_chat_will_not_boot(self):
        mid = self.task(state="done")
        self.chat_down = True
        r = self.talk(mid, "also cover the logout path")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["reply"], "")
        self.assertEqual(self.store.load(mid)["state"], "running")
        self.assertIn(mid, self.launched)

    def test_23_a_live_task_with_a_dead_shadow_chat_is_still_a_503(self):
        mid = self.task(state="running")
        self.chat_down = True
        self.assertEqual(self.talk(mid, "hello").status_code, 503)

    def test_24_over_the_cap_it_queues_and_launches_nothing(self):
        mission_engine.set_max_running(1)
        self.task(state="running", target="s-busy")
        mid = self.task(state="done", target="s-mine")
        r = self.talk(mid, "more please")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["mission"]["state"], "queued")
        self.assertNotIn(mid, self.launched)

    def test_25_refused_only_when_another_task_has_the_chat(self):
        mid = self.task(state="done", target="s-shared")
        other = self.task(state="running", target="s-shared")
        r = self.talk(mid, "more please")
        self.assertEqual(r.status_code, 409)
        self.assertIn(other, r.json()["detail"]["detail"])
        self.assertEqual(self.chat.heard, [],
                         "a refused reopen never reaches the Shadow chat")

    def test_26_give_instruction_reopens_too(self):
        mid = self.task(state="done")
        r = self.act(mid, "say", text="add a changelog line")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["state"], "running")
        self.assertIn(mid, self.launched)

    def test_27_a_limit_and_more_work_in_one_line(self):
        mid = self.task(state="failed", turns_used=20)
        r = self.talk(mid, "keep going, no turn limit",
                      "Going.\n" + fence({"turns": "none"}))
        doc = r.json()
        self.assertTrue(doc["reopened"])
        self.assertTrue(doc["mission"]["no_turn_limit"])


# --------------------------------------------------------------------- J9 --
class TestJ9TakeOverAndHandBack(Base):

    def test_30_a_take_over_waits_and_resume_brings_shadow_back(self):
        mid = self.task(state="running")
        r = self.act(mid, "take_over")
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "paused")
        self.assertEqual(m["pause_reason"], "founder_intervened")
        r = self.act(mid, "resume")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(mid)["state"], "running")
        self.assertIn(mid, self.launched)

    def test_31_nothing_in_the_engine_times_a_take_over_out(self):
        """V4-9: the pause never ends the task by itself. Held as a property
        of the state table: the only exits from paused are the founder's."""
        self.assertEqual(set(mission_engine.TRANSITIONS["paused"]),
                         {"running", "stopped", "failed"})
        # ...and the ONE sweep that walks paused tasks (the restart sweep)
        # acts on app_restart pauses only, so a founder's take-over is never
        # resumed or ended behind their back.
        src = Path(shadow_runner.__file__).read_text()
        self.assertIn('if m.get("pause_reason") != "app_restart":\n'
                      '            continue', src)
        self.assertEqual(src.count('store.list(states=("paused",))'), 1,
                         "a second sweep over paused tasks needs this test "
                         "to be re-read")

    def test_32_hand_back_after_the_end_reopens_with_no_words(self):
        mid = self.task(state="done", turns_used=9)
        r = self.act(mid, "reopen")
        self.assertEqual(r.status_code, 200, r.text)
        m = r.json()
        self.assertEqual(m["state"], "running")
        self.assertEqual(m["reopened"][-1]["via"], "hand_back")
        self.assertEqual(m["done_when"][0]["tier"], "founder_confirm",
                         "the founder says when hand-finished work is done")
        self.assertIn(mid, self.launched)

    def test_33_hand_back_with_words_carries_them(self):
        mid = self.task(state="stopped")
        r = self.act(mid, "reopen", text="now run the full suite")
        self.assertEqual(r.json()["founder_says"][-1]["text"],
                         "now run the full suite")

    def test_34_hand_back_on_a_live_task_is_refused(self):
        mid = self.task(state="running")
        self.assertEqual(self.act(mid, "reopen").status_code, 409)
        self.assertEqual(self.act("m-nope", "reopen").status_code, 404)


if __name__ == "__main__":
    unittest.main()
