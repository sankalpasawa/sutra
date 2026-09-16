"""Shadow v4 step 9 (C2, ADR-043): the task's Shadow chat writes the brief.

At Start, a record with no manifest asks its OWN Shadow chat for the brief
(objective verbatim, repo, why now, rules in scope, floors, done when); the
text lands on the record and is what the worker boots with. Any failure --
no chat, no fence -- falls back to the template, audibly. And the founder
can open a task with one line (POST /api/shadow/tasks) and keep talking to
it (POST /api/shadow/tasks/{mid}/chat); a `mission` fence from that chat
amends that draft, never a second task.

Faked at the process boundary: the task chat's claude (FakeRuntime) and the
worker spawn (a recording fake of spawn_delegate_session). The store, the
engine hooks and the routes are real.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_brief.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

_ENV_TMP = tempfile.mkdtemp(prefix="shadow-brief-env-")
os.environ["SUTRA_UI_WORKDIR"] = os.path.join(_ENV_TMP, "workspace")
os.environ["SUTRA_UI_WORKDIR_ROOT"] = _ENV_TMP
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ["SUTRA_NATIVE_HOME"] = os.path.join(_ENV_TMP, "native")
os.environ["SUTRA_SHADOW_HOME"] = os.path.join(_ENV_TMP, "shadow")
os.environ["SUTRA_UI_CHATS"] = os.path.join(_ENV_TMP, "chats")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import providers                               # noqa: E402
import shadow_ledger                           # noqa: E402
import shadow_runner                           # noqa: E402
import shadow_task_chat as stc                 # noqa: E402
from mission_engine import MissionStore        # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
BRIEF = ('Objective: "Top 10 fruits in the market". Where: the workspace. '
         'Why now: the founder wants the list. Rules: [always answer in one '
         'line]. Floors: destructive git operations. Done when: a table by '
         'usage; state DONE-CHECK lines.')


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeRuntime:
    def __init__(self, replies, sid="tc-1", boots=True):
        self.replies = list(replies)
        self.sid = sid
        self.boots = boots
        self.sent = []
        self.alive = False

    async def spawn(self, args, cwd, key, env=None):
        self.alive = True

    async def send_user_frame(self, text):
        self.sent.append(text)

    async def demux_turn(self, collect, sid):
        if not self.boots:
            return (None, 0.0, False, "died at argv", True)
        await collect({"type": "session", "id": self.sid})
        await collect({"type": "token",
                       "text": self.replies.pop(0) if self.replies else ""})
        return (self.sid, 0.0, True, None, None)

    def kill_group(self):
        self.alive = False

    def clear(self):
        pass


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        os.environ["SUTRA_UI_CHATS"] = os.path.join(self.tmp.name, "chats")
        self._settings = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        stc.TASK_CHATS.clear()
        self.store = MissionStore()
        self.spawned = []
        self._orig = (app_module._shadow_new_runtime, app_module._shadow_args,
                      shadow_runner.spawn_delegate_session)
        self.runtimes = []
        self.next_reply = ["READY", "Here.\n```brief\n" + BRIEF + "\n```"]
        self.boots = True

        def new_runtime():
            rt = FakeRuntime(list(self.next_reply), boots=self.boots)
            self.runtimes.append(rt)
            return rt

        async def fake_spawn(build_args, cwd, manifest, register, env=None,
                             publish=None):
            self.spawned.append({"manifest": manifest, "cwd": cwd})
            return "worker-1"

        app_module._shadow_new_runtime = new_runtime
        app_module._shadow_args = (lambda session_id=None, **k:
                                   ["claude", "-p", "--input-format",
                                    "stream-json"]
                                   + (["--resume", session_id] if session_id
                                      else []))
        shadow_runner.spawn_delegate_session = fake_spawn

    def tearDown(self):
        (app_module._shadow_new_runtime, app_module._shadow_args,
         shadow_runner.spawn_delegate_session) = self._orig
        stc.TASK_CHATS.clear()
        providers.SETTINGS_PATH = self._settings
        self.tmp.cleanup()

    def mission(self, manifest=None):
        m = self.store.create("Top 10 fruits in the market", "research",
                              target_mode="new", manifest=manifest,
                              done_when=[{"tier": "founder_confirm",
                                          "check": "a table by usage"}])
        self.store.transition(m["id"], "brief_confirm", "proposed")
        return self.store.load(m["id"])


class TestBriefAtStart(Base):

    def test_01_the_task_chat_writes_the_brief_onto_the_record(self):
        shadow_ledger.append("instructions", {
            "text": "always answer in one line", "precedence": "d_ledger",
            "confirmed": True, "scope": "global"})
        m = self.mission()
        sid = run(app_module._delegate_spawn(m))
        self.assertEqual(sid, "worker-1")
        sent = self.spawned[0]["manifest"]
        self.assertIn(BRIEF, sent, "the worker boots with the composed brief")
        self.assertTrue(sent.startswith("[Shadow ·"), "tagged like a say")
        on_disk = self.store.load(m["id"])
        self.assertEqual(on_disk["manifest"], BRIEF)
        self.assertEqual(on_disk["brief_by"], "task_chat")
        self.assertEqual(on_disk["version"], m["version"],
                         "written onto the record, no re-confirm")
        ask = self.runtimes[0].sent[1]
        self.assertIn("always answer in one line", ask, "rules in scope")
        self.assertIn("destructive git operations", ask, "the floors")
        self.assertIn("Top 10 fruits in the market", self.runtimes[0].sent[0])

    def test_02_a_record_with_a_manifest_is_sent_as_it_is(self):
        m = self.mission(manifest="Founder wrote this brief.")
        run(app_module._delegate_spawn(m))
        self.assertIn("Founder wrote this brief.", self.spawned[0]["manifest"])
        self.assertEqual(self.runtimes, [], "no task chat was consulted")

    def test_03_no_fence_means_the_template_audibly(self):
        self.next_reply = ["READY", "I would rather talk first."]
        m = self.mission()
        run(app_module._delegate_spawn(m))
        sent = self.spawned[0]["manifest"]
        self.assertIn("You are a delegate session", sent)
        self.assertIn("Top 10 fruits in the market", sent)
        self.assertIsNone(self.store.load(m["id"]).get("manifest"))
        acts = shadow_ledger.read("actions", 10)
        self.assertTrue(any("no brief fence" in a["summary"] for a in acts))

    def test_04_a_chat_that_will_not_boot_means_the_template_audibly(self):
        self.boots = False
        m = self.mission()
        run(app_module._delegate_spawn(m))
        self.assertIn("You are a delegate session", self.spawned[0]["manifest"])
        acts = shadow_ledger.read("actions", 10)
        self.assertTrue(any("brief fallback" in a["summary"] for a in acts))
        self.assertIsNone(stc.get(m["id"]), "a failed boot leaves no chat")


class TestOpeningATask(Base):

    def fence(self, **spec):
        base = {"objective": "Top 10 fruits, ranked by usage",
                "template": "research", "target_mode": "new",
                "done_when": [{"tier": "founder_confirm",
                               "check": "a table by usage"}]}
        base.update(spec)
        return "```mission\n" + json.dumps(base) + "\n```"

    def test_10_one_line_opens_a_draft_and_the_chat_sharpens_it(self):
        self.next_reply = ["READY", "Got it, research.\n" + self.fence()]
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        self.assertEqual(doc["reply"], "Got it, research.")
        m = doc["mission"]
        self.assertEqual(m["state"], "brief_confirm", "a draft, not started")
        self.assertEqual(m["objective"], "Top 10 fruits, ranked by usage")
        self.assertEqual(m["template"], "research")
        self.assertEqual([c["check"] for c in m["done_when"]],
                         ["a table by usage"])
        self.assertEqual(m["task_chat_session"], "tc-1")
        self.assertTrue(m.get("task_chat"), "published as a chat")
        self.assertEqual(self.spawned, [], "nothing started")
        self.assertIn("top 10 fruits", self.runtimes[0].sent[0],
                      "the draft boots with the founder's line")

    def test_11_talking_to_the_task_amends_the_draft(self):
        self.next_reply = ["READY", "Got it.\n" + self.fence()]
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        mid = doc["mission"]["id"]
        self.runtimes[0].replies = [
            "Sharper.\n" + self.fence(objective="Top 10 fruits by usage, India",
                                      done_when=[{"tier": "founder_confirm",
                                                  "check": "India only"}])]
        doc = self.client.post("/api/shadow/tasks/%s/chat" % mid,
                               json={"message": "India only"},
                               headers=HDR).json()
        self.assertEqual(doc["reply"], "Sharper.")
        self.assertEqual(doc["mission"]["objective"],
                         "Top 10 fruits by usage, India")
        self.assertEqual(doc["mission"]["done_when"][0]["check"], "India only")
        self.assertEqual(self.runtimes[0].sent[-1], "India only")

    def test_12_a_chat_that_will_not_boot_leaves_the_verbatim_draft(self):
        self.boots = False
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        self.assertEqual(doc["mission"]["objective"], "top 10 fruits")
        self.assertEqual(doc["mission"]["state"], "brief_confirm")
        self.assertEqual(doc["reply"], "")

    def test_13_unknown_task_is_404_and_empty_message_is_400(self):
        r = self.client.post("/api/shadow/tasks/m-nobody/chat",
                             json={"message": "hi"}, headers=HDR)
        self.assertEqual(r.status_code, 404)
        r = self.client.post("/api/shadow/tasks", json={"message": " "},
                             headers=HDR)
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
