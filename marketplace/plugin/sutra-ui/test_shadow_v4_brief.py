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
                             publish=None, on_first_turn=None):
            # the REAL spawner fires this from its adoption hook, on the first
            # frame that carries a session id; a fake that swallowed it would
            # hide the one wire this test class can see
            self.spawned.append({"manifest": manifest, "cwd": cwd,
                                 "on_first_turn": on_first_turn})
            if on_first_turn is not None:
                on_first_turn()
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

    def test_05_the_spawn_names_turn_1_at_first_contact(self):
        """THE CARD MUST NOT READ "turn 0 of 25" WHILE TURN 1 IS PAINTING.

        mission_engine.open_first_turn existed, shadow_runner accepted the
        hook, and the engine tests drove it through a fake spawner -- but
        `_delegate_spawn`, the ONE production spawn, never passed it. So in
        the running app the field was written only by run_mission's
        say-and-wait block, which the `briefed` branch skips for turn 1:
        turns 2..n read right and turn 1 read zero for its whole length.

        Both halves are asserted: the argument reaches the spawner, and the
        record it writes is the one a card renders.
        """
        m = self.mission(manifest="Founder wrote this brief.")
        self.assertIsNone(self.store.load(m["id"]).get("turn_open"),
                          "nothing is painting before the spawn")
        run(app_module._delegate_spawn(m))
        self.assertIsNotNone(self.spawned[0]["on_first_turn"],
                             "the hook is PASSED -- not left at its default")
        on_disk = self.store.load(m["id"])
        self.assertEqual(on_disk.get("turn_open"), 1,
                         "turn 1 is named the moment the worker paints")
        self.assertEqual(on_disk.get("turns_used") or 0, 0,
                         "...and naming it never counts it as finished")


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

    def test_14_a_RUNNING_task_still_answers_and_spends_no_turn(self):
        """Step 1 of the Shadow conversation UX (founder, 2026-09-16): the
        founder talks to a task that has already started. The route is the
        one that existed; what this pins is that a conversation is not work.
        """
        self.next_reply = ["READY", "Got it.\n" + self.fence()]
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        mid = doc["mission"]["id"]
        m = self.store.load(mid)
        m["state"], m["turns_used"], m["max_turns"] = "running", 3, 12
        self.store.save(m)
        before = self.store.load(mid)

        self.runtimes[0].replies = ["I am validating the data pipeline."]
        r = self.client.post("/api/shadow/tasks/%s/chat" % mid,
                             json={"message": "what are you working on?"},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, "a running task must answer")
        self.assertEqual(r.json()["reply"], "I am validating the data pipeline.",
                         "Shadow's own words come straight back")
        self.assertEqual(self.runtimes[0].sent[-1], "what are you working on?",
                         "the founder's line reaches the task's Shadow chat")

        after = self.store.load(mid)
        for field in ("turns_used", "max_turns", "state", "version",
                      "objective", "done_when"):
            self.assertEqual(after.get(field), before.get(field),
                             "%s must not move for a conversation" % field)
        # STEP 2 (2026-09-16) changed exactly one thing here: the line is now
        # RECORDED as decision input, tagged `via: talk`. It is still not an
        # instruction -- every counter above is unmoved, nothing was sent, and
        # only mission_engine._instruction composes what the worker receives.
        says = after.get("founder_says") or []
        self.assertEqual([s["text"] for s in says],
                         ["what are you working on?"])
        self.assertEqual(says[0]["via"], "talk")
        self.assertIsNone(after.get("last_instruction"),
                          "recording input must not compose an instruction")
        self.assertEqual(self.spawned, [], "and no worker was spawned")

    def test_15_after_Start_a_mission_fence_can_no_longer_re_scope(self):
        """THE FENCE AMENDS A DRAFT, AND ONLY A DRAFT. _apply_task_fence
        reaches MissionStore.amend, which refuses a TERMINAL mission but not
        a running one -- it would bump the version and rewrite the objective
        and the done_when of work the worker is already executing. Before
        Start that is the feature (test_11); after Start it would let a
        casual question re-scope live work."""
        self.next_reply = ["READY", "Got it.\n" + self.fence()]
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        mid = doc["mission"]["id"]
        m = self.store.load(mid)
        m["state"] = "running"
        self.store.save(m)
        before = self.store.load(mid)

        self.runtimes[0].replies = [
            "Sure.\n" + self.fence(objective="Something else entirely",
                                   done_when=[{"tier": "founder_confirm",
                                               "check": "nothing"}])]
        doc = self.client.post("/api/shadow/tasks/%s/chat" % mid,
                               json={"message": "what are you working on?"},
                               headers=HDR).json()
        self.assertEqual(doc["reply"], "Sure.", "the reply still comes back")
        after = self.store.load(mid)
        self.assertEqual(after["objective"], before["objective"],
                         "a running task must not be re-scoped by a chat")
        self.assertEqual(after["done_when"], before["done_when"],
                         "nor its checks rewritten")
        self.assertEqual(after["version"], before["version"],
                         "and no new version was cut")
        self.assertEqual(doc["mission"]["objective"], before["objective"],
                         "the payload shows the record as it stands")

    def test_16_a_terminal_task_never_talks_as_though_finished_work_is_live(self):
        """PIN MOVED for Shadow v4.1 (V4-9, founder 2026-09-21: "it should
        resume the work and not say that the work is done"). This used to
        assert a 409 on done / failed / stopped. The guard it stood for is
        kept and made stronger: a terminal task is never talked to AS
        terminal. One that cannot go back to work (this one never got a
        worker chat) still refuses with a 409 and sends nothing into the
        Shadow chat; one that can is reopened FIRST -- covered end to end in
        test_shadow_v41_routes.py."""
        self.next_reply = ["READY", "Got it.\n" + self.fence()]
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        mid = doc["mission"]["id"]
        sent_before = len(self.runtimes[0].sent)
        for state in ("done", "failed", "stopped"):
            m = self.store.load(mid)
            m["state"] = state
            self.store.save(m)
            r = self.client.post("/api/shadow/tasks/%s/chat" % mid,
                                 json={"message": "still there?"},
                                 headers=HDR)
            self.assertEqual(r.status_code, 409, "%s must refuse" % state)
            self.assertIn("Retry", r.json()["detail"]["detail"],
                          "and the refusal says what to do instead")
            self.assertEqual(self.store.load(mid)["state"], state,
                             "%s must not be resurrected" % state)
        self.assertEqual(len(self.runtimes[0].sent), sent_before,
                         "and nothing was ever sent into the Shadow chat")

    # ---------------------------------------------------------- step 2 ---
    # ONE MEMORY OF THE FOUNDER. A post-Start conversational line is appended
    # to the SAME `founder_says` the instruction composer writes, tagged
    # `via` so Shadow can tell a deliberate instruction from a passing
    # remark. Nothing here reaches the worker: founder_says is input to a
    # decision, and mission_engine._instruction is still the only thing that
    # composes an instruction.

    def running(self):
        """A started task with its Shadow chat already booted."""
        self.next_reply = ["READY", "Got it.\n" + self.fence()]
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        mid = doc["mission"]["id"]
        m = self.store.load(mid)
        m["state"], m["turns_used"], m["max_turns"] = "running", 3, 12
        self.store.save(m)
        return mid

    def talk(self, mid, message, reply="Noted."):
        self.runtimes[0].replies = [reply]
        return self.client.post("/api/shadow/tasks/%s/chat" % mid,
                                json={"message": message}, headers=HDR)

    def test_20_a_talked_line_lands_in_founder_says_tagged_talk(self):
        mid = self.running()
        r = self.talk(mid, "I think JSON is better than CSV.",
                      "CSV was chosen because the export is flat.")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["reply"],
                         "CSV was chosen because the export is flat.",
                         "the founder still gets a direct answer")
        says = self.store.load(mid)["founder_says"]
        self.assertEqual(len(says), 1)
        self.assertEqual(says[0]["text"], "I think JSON is better than CSV.")
        self.assertEqual(says[0]["via"], "talk", "the channel is recorded")
        self.assertFalse(says[0]["seen"], "and it is news until a turn reads it")
        self.assertEqual(says[0]["at_turn"], 3, "stamped at the turn it landed")

    def test_21_shadows_own_reply_is_never_recorded_as_founder_input(self):
        mid = self.running()
        self.talk(mid, "what are you doing?", "I am validating the pipeline.")
        texts = [s["text"] for s in self.store.load(mid)["founder_says"]]
        self.assertEqual(texts, ["what are you doing?"])
        self.assertNotIn("I am validating the pipeline.", texts,
                         "Shadow must never read its own answer back as an "
                         "instruction it was given")

    def test_22_drafting_conversation_is_not_recorded(self):
        """Before Start the conversation IS the drafting, and it lands on the
        objective through the `mission` fence. Recording it as well would
        replay the whole drafting exchange into the first decision."""
        self.next_reply = ["READY", "Got it.\n" + self.fence()]
        doc = self.client.post("/api/shadow/tasks",
                               json={"message": "top 10 fruits"},
                               headers=HDR).json()
        mid = doc["mission"]["id"]
        self.talk(mid, "India only", "Sharper.")
        self.assertIsNone(self.store.load(mid).get("founder_says"),
                          "a draft's chat is drafting, not steering")

    def test_23_a_terminal_task_records_nothing(self):
        mid = self.running()
        for state in ("done", "failed", "stopped"):
            m = self.store.load(mid)
            m["state"] = state
            self.store.save(m)
            self.assertEqual(self.talk(mid, "still there?").status_code, 409)
            self.assertIsNone(self.store.load(mid).get("founder_says"),
                              "%s must record nothing" % state)

    def test_24_both_channels_land_in_one_list_in_order(self):
        mid = self.running()
        self.talk(mid, "how close are we?")
        self.client.post("/api/shadow/missions/%s/act" % mid,
                         json={"action": "say", "text": "Do not modify the API."},
                         headers=HDR)
        self.talk(mid, "also, JSON would be better")
        says = self.store.load(mid)["founder_says"]
        self.assertEqual([(s["text"], s.get("via")) for s in says],
                         [("how close are we?", "talk"),
                          ("Do not modify the API.", None),
                          ("also, JSON would be better", "talk")],
                         "one list, chronological, channel preserved")

    def test_25_the_decider_sees_both_and_consumes_each_once(self):
        """The existing `seen` cursor is the whole anti-duplication story:
        no new marker, and it is already durable because it lives on the
        mission record."""
        import mission_engine
        mid = self.running()
        self.talk(mid, "JSON would be better")
        self.client.post("/api/shadow/missions/%s/act" % mid,
                         json={"action": "say", "text": "Do not modify the API."},
                         headers=HDR)
        m = self.store.load(mid)
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        ctx = eng._decision_context(m, "the worker said something")
        self.assertEqual([s["text"] for s in ctx["founder_says"]],
                         ["JSON would be better", "Do not modify the API."])
        prompt = shadow_runner.render_decide_prompt(ctx)
        self.assertIn("- [conversation] JSON would be better", prompt)
        self.assertIn("- [instruction] Do not modify the API.", prompt)
        # ...and once a turn has read them they are standing context, so they
        # cannot steer every later turn for the rest of the mission
        for said in m["founder_says"]:
            said["seen"] = True
        self.store.save(m)
        self.assertNotIn(
            "founder_says",
            eng._decision_context(self.store.load(mid), ""),
            "a consumed line must not go again")

    def test_26_consumption_survives_a_restart(self):
        """A fresh store object -- the restart case -- must see the same
        cursor: it is a field on the mission file, not process memory."""
        import mission_engine
        mid = self.running()
        self.talk(mid, "JSON would be better")
        m = self.store.load(mid)
        m["founder_says"][0]["seen"] = True
        self.store.save(m)
        fresh = MissionStore()
        eng = mission_engine.MissionEngine(fresh, None, None, None)
        self.assertNotIn("founder_says",
                         eng._decision_context(fresh.load(mid), ""))
        self.assertEqual(fresh.load(mid)["founder_says"][0]["text"],
                         "JSON would be better",
                         "and the line itself is still on the record")

    def test_27_talking_spawns_no_worker_turn(self):
        """The conversation does not trigger orchestration. The worker is
        driven by run_mission and by nothing else."""
        mid = self.running()
        before = self.store.load(mid)
        self.talk(mid, "how close are we?")
        after = self.store.load(mid)
        for field in ("turns_used", "max_turns", "state", "version",
                      "last_instruction", "turn_open"):
            self.assertEqual(after.get(field), before.get(field),
                             "%s must not move for a conversation" % field)
        self.assertEqual(self.spawned, [], "and no worker was spawned")

    def test_28_a_store_failure_costs_the_row_and_nothing_else(self):
        """A Shadow-side fault must never become a worker fault: the founder
        still gets their answer, and the mission is untouched."""
        mid = self.running()
        broken = MissionStore
        try:
            class Boom(broken):
                def save(self, mission):
                    raise OSError("disk went away")
            app_module._mission_engine.MissionStore = Boom
            r = self.talk(mid, "JSON would be better")
        finally:
            app_module._mission_engine.MissionStore = broken
        self.assertEqual(r.status_code, 200, "the answer still comes back")
        self.assertIsNone(self.store.load(mid).get("founder_says"))
        self.assertEqual(self.store.load(mid)["state"], "running",
                         "and the mission is untouched")

    def test_13_unknown_task_is_404_and_empty_message_is_400(self):
        r = self.client.post("/api/shadow/tasks/m-nobody/chat",
                             json={"message": "hi"}, headers=HDR)
        self.assertEqual(r.status_code, 404)
        r = self.client.post("/api/shadow/tasks", json={"message": " "},
                             headers=HDR)
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
