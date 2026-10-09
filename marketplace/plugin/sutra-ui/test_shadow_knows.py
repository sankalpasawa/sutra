"""What Shadow knows -- learned memory and personality (founder, 2026-10-07).

The system fills these in from working with the founder, Shadow re-uses them
in every later chat, and the founder can edit them if they want to. Five
levels:

  STORE     shadow_knows: said/typed bind, inferred waits for Keep, asked
            binds only when the founder stated it as standing; dedupe; a
            dropped suggestion stays dropped; credentials refused; FULL
            REFUSES instead of evicting; dated lines stop binding.
  REUSE     carry_block() puts the learned lines beneath the founder's own
            text in every boot, task chat and decision; byte-identical when
            nothing is learned. The worker brief carries learned MEMORY only.
  ASKS      the decider may carry `remember` on either decision shape; the
            engine hands it to the store with the question Shadow asked as
            evidence; the prompt asks for it only when the founder has just
            said something.
  ROUTES    GET/POST /api/shadow/knows, and the listing on /api/shadow/settings.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_knows.py
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-knows-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_knows                            # noqa: E402
import shadow_ledger                           # noqa: E402
import shadow_runner                           # noqa: E402
import shadow_session                          # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


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

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def texts(self, section, status="active"):
        rows = (shadow_knows.active(section) if status == "active"
                else shadow_knows.pending(section))
        return [r["text"] for r in rows]


class TestTheStore(Base):

    def test_01_what_the_founder_said_binds_at_once(self):
        row = shadow_knows.add("memory", "  I am the   CEO. ", "said",
                               category="identity")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["text"], "I am the CEO.")
        self.assertEqual(self.texts("memory"), ["I am the CEO."])

    def test_02_a_guess_waits_for_keep_even_when_it_claims_to_bind(self):
        row = shadow_knows.add("personality", "Do not ask on routine fixes",
                               "inferred", binding=True)
        self.assertEqual(row["status"], "pending")
        self.assertEqual(self.texts("personality"), [])

    def test_03_an_answer_binds_only_when_stated_as_standing(self):
        a = shadow_knows.add("personality", "Always run tests first",
                             "asked", binding=True)
        b = shadow_knows.add("memory", "Prefers EU regions", "asked")
        self.assertEqual(a["status"], "active")
        self.assertEqual(b["status"], "pending")

    def test_04_the_same_line_twice_is_one_row(self):
        shadow_knows.add("memory", "I am the CEO.", "said")
        shadow_knows.add("memory", "i am THE ceo.", "said")
        self.assertEqual(len(shadow_knows.rows()), 1)

    def test_05_saying_a_pending_suggestion_outright_activates_it(self):
        shadow_knows.add("memory", "Ships on Fridays", "inferred")
        shadow_knows.add("memory", "Ships on Fridays", "said")
        self.assertEqual(self.texts("memory"), ["Ships on Fridays"])
        self.assertEqual(self.texts("memory", "pending"), [])

    def test_06_a_dropped_suggestion_is_never_suggested_again(self):
        """The decider sees the same answer on every later turn of a task;
        without this, Drop would last exactly one turn."""
        row = shadow_knows.add("memory", "Likes MotoGP", "inferred")
        shadow_knows.forget(row["id"])
        with self.assertRaises(shadow_knows.Refused):
            shadow_knows.add("memory", "Likes MotoGP", "asked")
        self.assertEqual(shadow_knows.pending(), [])
        # ...but the founder saying it again brings it back
        again = shadow_knows.add("memory", "Likes MotoGP", "said")
        self.assertEqual(again["status"], "active")

    def test_07_credentials_are_never_remembered(self):
        for line in ("my api key is sk-abcdefghijklmnopqrstuv",
                     "password: hunter2",
                     "token = ghp_abcdefghijklmnopqrstuvwxyz"):
            with self.assertRaises(shadow_knows.Refused, msg=line):
                shadow_knows.add("memory", line, "said")
        self.assertEqual(shadow_knows.rows(), [])

    def test_08_full_refuses_and_never_evicts_the_oldest(self):
        orig = shadow_knows.MAX_ACTIVE
        shadow_knows.MAX_ACTIVE = 2
        try:
            shadow_knows.add("memory", "one", "said")
            shadow_knows.add("memory", "two", "said")
            with self.assertRaises(shadow_knows.Refused) as cm:
                shadow_knows.add("memory", "three", "said")
            self.assertIn("full", str(cm.exception))
            self.assertEqual(self.texts("memory"), ["one", "two"])
            # the other section has its own room
            shadow_knows.add("personality", "terse", "said")
        finally:
            shadow_knows.MAX_ACTIVE = orig

    def test_09_a_past_date_stops_binding_and_is_flagged_not_dropped(self):
        shadow_knows.add("memory", "Launch on Oct 20", "said",
                         category="focus", expires="2000-01-01")
        shadow_knows.add("memory", "Launch on Oct 21", "said",
                         expires="2999-01-01")
        self.assertEqual(self.texts("memory"), ["Launch on Oct 21"])
        listed = {r["text"]: r["expired"]
                  for r in shadow_knows.listing()["memory"]}
        self.assertEqual(listed, {"Launch on Oct 20": True,
                                  "Launch on Oct 21": False})

    def test_10_keep_edit_forget(self):
        row = shadow_knows.add("personality", "Be terse", "inferred")
        shadow_knows.keep(row["id"])
        self.assertEqual(self.texts("personality"), ["Be terse"])
        edited = shadow_knows.edit(row["id"], "Be terse, outcome first")
        self.assertEqual(edited["source"], "typed")
        self.assertEqual(self.texts("personality"),
                         ["Be terse, outcome first"])
        shadow_knows.forget(row["id"])
        self.assertEqual(self.texts("personality"), [])
        with self.assertRaises(shadow_knows.Refused):
            shadow_knows.keep(row["id"])

    def test_11_history_is_append_only(self):
        row = shadow_knows.add("memory", "x one", "said")
        shadow_knows.edit(row["id"], "x two")
        raw = shadow_ledger.read("knows", 50)
        self.assertEqual([r["text"] for r in raw], ["x one", "x two"])

    def test_12_an_unknown_category_is_filed_not_refused(self):
        row = shadow_knows.add("memory", "Uses HubSpot", "said",
                               category="nonsense")
        self.assertEqual(row["category"], "you",
                         "unknown names file under the first memory group")

    def test_13_forget_by_the_words(self):
        shadow_knows.add("memory", "I am the CEO.", "said")
        self.assertIsNotNone(shadow_knows.forget_text("memory", "i am the ceo."))
        self.assertIsNone(shadow_knows.forget_text("memory", "not there"))
        self.assertEqual(self.texts("memory"), [])

    def test_14_a_broken_ledger_costs_the_lines_never_the_boot(self):
        home = Path(self.tmp.name) / "ledger"
        home.mkdir(exist_ok=True)
        (home / "knows.jsonl").write_text("{not json\n")
        self.assertEqual(shadow_knows.rows(), [])
        self.assertEqual(shadow_knows.lines("memory"), [])


class TestGroupsAndSwitches(Base):
    """Three memory groups, one personality list, four switches (founder,
    2026-10-07: "fixed category of things ... not loads of stuff")."""

    def test_15_old_category_names_land_in_the_new_groups(self):
        for old, group in (("identity", "you"), ("people", "you"),
                           ("projects", "work"), ("focus", "work"),
                           ("tools", "work"), ("vocabulary", "preferences"),
                           ("preferences", "preferences")):
            self.assertEqual(shadow_knows.group_of("memory", old), group, old)
        self.assertEqual(shadow_knows.group_of("personality", "autonomy"),
                         "rules")

    def test_16_rows_on_disk_are_regrouped_on_read_not_rewritten(self):
        shadow_ledger.append("knows", {
            "id": "know-old1", "section": "memory", "category": "projects",
            "text": "Main repo is sutra", "source": "said",
            "status": "active"})
        self.assertEqual(shadow_knows.active("memory", "work")[0]["text"],
                         "Main repo is sutra")
        self.assertEqual(shadow_ledger.read("knows", 5)[0]["category"],
                         "projects", "the record itself is untouched")

    def test_17_ten_per_group_and_each_group_has_its_own_room(self):
        for i in range(shadow_knows.MAX_ACTIVE):
            shadow_knows.add("memory", "fact %d" % i, "said", category="you")
        with self.assertRaises(shadow_knows.Refused) as cm:
            shadow_knows.add("memory", "one more", "said", category="you")
        self.assertIn("About you is full", str(cm.exception))
        shadow_knows.add("memory", "Main repo is sutra", "said",
                         category="work")

    def test_18_the_defaults_are_maximum_power_and_reach_shadow(self):
        """founder, 2026-10-08: "default of maximum power to shadow"."""
        self.assertEqual(shadow_knows.switches(), {}, "nothing was set")
        listed = {s["name"]: s for s in shadow_knows.switch_listing()}
        self.assertEqual(set(listed), {"acting", "checkins", "done",
                                       "replies"})
        self.assertEqual({k: v["value"] for k, v in listed.items()},
                         {"acting": "just_do_it", "checkins": "milestones",
                          "done": "prove", "replies": "short"})
        self.assertFalse(any(v["set"] for v in listed.values()))
        block = mission_engine.carry_block()
        self.assertIn("Should Shadow check with you before it starts? Just do it.", block)
        self.assertIn('How carefully should Shadow check the work? Check everything.', block)
        self.assertFalse(mission_engine.confirm_top_tier(),
                         "maximum power asks nothing before it starts")

    def test_18b_the_wired_switches_show_what_the_engine_enforces(self):
        """Set through their own routes, the page still tells the truth."""
        import shadow_presence
        mission_engine.set_confirm_top_tier(True)
        shadow_presence.set_nudges_per_hour(0)
        now = shadow_knows.effective()
        self.assertEqual((now["acting"], now["checkins"]),
                         ("ask_first", "only_stuck"))
        mission_engine.set_confirm_top_tier(False)
        shadow_presence.set_nudges_per_hour(8)
        now = shadow_knows.effective()
        self.assertEqual((now["acting"], now["checkins"]),
                         ("just_do_it", "often"))

    def test_19_a_switch_reaches_shadow_and_two_move_engine_settings(self):
        import shadow_presence
        shadow_knows.set_switch("acting", "ask_first")
        self.assertTrue(mission_engine.confirm_top_tier())
        shadow_knows.set_switch("acting", "just_do_it")
        self.assertFalse(mission_engine.confirm_top_tier())
        shadow_knows.set_switch("checkins", "often")
        self.assertEqual(shadow_presence.nudges_per_hour(), 6)
        shadow_knows.set_switch("replies", "detailed")
        block = mission_engine.carry_block()
        self.assertIn("HOW THE FOUNDER WANTS YOU TO WORK", block)
        self.assertIn("How long should Shadow's messages be? Detailed.", block)
        self.assertIn("How often should Shadow update you? Often.", block)
        with self.assertRaises(shadow_knows.Refused):
            shadow_knows.set_switch("replies", "loud")
        with self.assertRaises(shadow_knows.Refused):
            shadow_knows.set_switch("mood", "x")


class TestReuse(Base):

    def test_20_nothing_learned_adds_no_learned_heading(self):
        mission_engine.set_behaves("Check in rarely.")
        block = mission_engine.carry_block()
        self.assertTrue(block.startswith(mission_engine._BEHAVES_HEAD
                                         + "Check in rarely."))
        self.assertNotIn("LEARNED", block)

    def test_21_learned_lines_sit_beneath_the_founders_own(self):
        mission_engine.set_behaves("Check in rarely.")
        mission_engine.set_memory("I am the CEO.")
        shadow_knows.add("personality", "Run tests first", "said",
                         category="verification")
        shadow_knows.add("memory", "Sankalp has final say", "said",
                         category="people")
        shadow_knows.add("memory", "Only a guess", "inferred")
        block = mission_engine.carry_block()
        order = [block.index(s) for s in (
            "Check in rarely.", "[Other rules] Run tests first",
            "I am the CEO.", "[About you] Sankalp has final say")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("Only a guess", block)

    def test_22_every_boot_and_task_chat_carries_them(self):
        shadow_knows.add("memory", "Main repo is sutra", "said")
        ctx = shadow_session.standing_context()
        self.assertIn("Main repo is sutra", ctx)
        self.assertIn("WHAT SHADOW HAS LEARNED ABOUT THE FOUNDER", ctx)

    def test_23_shadow_chooses_what_the_worker_hears(self):
        """Personality and memory are Shadow's. Nothing hands them to the
        worker wholesale: the brief writer sees both in its own context and
        picks the lines the task needs; the decider is told the same."""
        import shadow_task_chat
        shadow_knows.add("memory", "Main repo is sutra", "said")
        shadow_knows.add("personality", "Never ping before 10am", "said")
        facts = app_module._brief_facts({})
        self.assertNotIn("Main repo is sutra",
                         shadow_task_chat._facts_text(facts))
        ctx = shadow_session.standing_context("m-x")
        self.assertIn("Main repo is sutra", ctx)
        self.assertIn("Never ping before 10am", ctx)
        prompt = " ".join(shadow_runner.render_decide_prompt(
            {"carry": mission_engine.carry_block()}).split())
        self.assertIn("They are YOURS, not the worker's", prompt)
        self.assertIn("only when it changes what the worker should do next",
                      prompt)

    def test_24_the_decider_reads_them(self):
        shadow_knows.add("personality", "Run tests first", "said")
        prompt = shadow_runner.render_decide_prompt(
            {"carry": mission_engine.carry_block()})
        self.assertIn("Run tests first", prompt)


class TestLearningFromAsks(Base):

    def decision(self, remember, action="continue"):
        raw = {"action": action, "reason": "r", "remember": remember}
        if action == "continue":
            raw["instruction"] = "Write the migration now."
        return mission_engine.validate_decision(raw)

    def test_30_remember_rides_both_decision_shapes(self):
        rows = [{"section": "memory", "text": "Prefers EU", "standing": True}]
        for action in ("continue", "ask_founder"):
            d = self.decision(rows, action)
            self.assertEqual(d["remember"][0]["text"], "Prefers EU", action)
            self.assertIs(d["remember"][0]["standing"], True)

    def test_31_absent_or_junk_leaves_the_decision_unchanged(self):
        base = mission_engine.validate_decision(
            {"action": "continue", "reason": "r",
             "instruction": "Write the migration now."})
        for junk in (None, "x", [], [{"section": "vibes", "text": "x"}],
                     [{"section": "memory", "text": "  "}]):
            self.assertEqual(self.decision(junk), base, junk)

    def test_32_at_most_two_and_standing_must_be_true(self):
        d = self.decision([{"section": "memory", "text": "a",
                            "standing": "yes"}] +
                          [{"section": "memory", "text": t}
                           for t in ("b", "c")])
        self.assertEqual([r["text"] for r in d["remember"]], ["a", "b"])
        self.assertIs(d["remember"][0]["standing"], False)

    def test_33_the_engine_files_them_with_the_question_as_evidence(self):
        m = {"id": "m-test", "founder_response": {
            "question": "Which region should this deploy to?"}}
        d = self.decision([
            {"section": "memory", "text": "Deploys go to EU West",
             "category": "tools", "standing": True, "why": "said always"},
            {"section": "personality", "text": "Pick regions yourself",
             "category": "autonomy"}])
        wrote = mission_engine.MissionEngine._adopt_remember(None, m, d)
        self.assertEqual([r["status"] for r in wrote], ["active", "pending"])
        self.assertIn("Which region", wrote[0]["evidence"])
        self.assertEqual(wrote[0]["mission_id"], "m-test")
        acts = [a["summary"] for a in shadow_ledger.read("actions", 10)]
        self.assertTrue(any(s.startswith("learned memory") for s in acts))
        self.assertTrue(any(s.startswith("suggested personality")
                            for s in acts))

    def test_34_a_refusal_is_a_ledger_row_not_a_failed_turn(self):
        d = self.decision([{"section": "memory",
                            "text": "password: hunter2", "standing": True}])
        wrote = mission_engine.MissionEngine._adopt_remember(
            None, {"id": "m-x"}, d)
        self.assertEqual(wrote, [])
        acts = [a["summary"] for a in shadow_ledger.read("actions", 5)]
        self.assertTrue(any("could not remember" in s for s in acts))

    def test_35_the_prompt_asks_only_when_the_founder_just_spoke(self):
        quiet = shadow_runner.render_decide_prompt({})
        self.assertNotIn("WHAT THIS TEACHES YOU", quiet)
        for ctx in ({"founder_response": {"question": "q", "summary": [
                        {"label": "Region", "value": "EU"}]}},
                    {"founder_says": [{"text": "always run tests",
                                       "via": "say"}]}):
            self.assertIn("WHAT THIS TEACHES YOU",
                          shadow_runner.render_decide_prompt(ctx), ctx)


class TestTheFirstMessage(Base):
    """Shadow decides what a line needs before anything starts (founder,
    2026-10-07): only work starts a worker, and the long-lived Now chat
    re-reads what it knows when that changes."""

    def test_50_intake_starts_a_worker_only_for_work(self):
        p = " ".join(app_module.SHADOW_INTAKE_PREFIX.split())
        self.assertTrue(p.startswith("[Intake]"))
        self.assertNotIn("not as a question to answer", p,
                         "the old rule that made every line a task")
        self.assertIn("Only a mission block starts a worker", p)
        for kind in ("WORK", "A QUESTION", "SOMETHING TO REMEMBER",
                     "A SETTING", "A GREETING"):
            self.assertIn(kind, p)
        self.assertIn("shadow_remember", p)

    def test_51_the_now_chat_hears_what_changed_once(self):
        class Sess:
            pass
        sess = Sess()
        sess.carry_stamp = app_module._carry_stamp()      # as at boot
        self.assertEqual(app_module._carry_refresh(sess), "",
                         "nothing changed: nothing is resent")
        shadow_knows.add("memory", "Sankalp has final say", "said")
        pre = app_module._carry_refresh(sess)
        self.assertIn("has changed since you started", pre)
        self.assertIn("Sankalp has final say", pre)
        self.assertEqual(app_module._carry_refresh(sess), "",
                         "sent once per change, not every turn")

    def test_52_forgetting_everything_is_said_too(self):
        class Sess:
            pass
        sess = Sess()
        row = shadow_knows.add("memory", "Temporary", "said")
        sess.carry_stamp = app_module._carry_stamp()
        shadow_knows.forget(row["id"])
        pre = app_module._carry_refresh(sess)
        self.assertIn("has changed since you started", pre)
        self.assertNotIn("Temporary", pre, "the forgotten line is gone")


class TestTaskChatsHearChangesToo(Base):
    """founder, 2026-10-08: a personality change reaches the task chats
    already open, not only the next task."""

    def chat(self, stamp):
        import asyncio
        import shadow_task_chat
        c = shadow_task_chat.TaskChat("m-x")
        c.carry_stamp = stamp
        sent = []

        async def turn(text, timeout, images=None):
            sent.append(text)
            return "ok"
        c._turn = turn
        return c, sent, (lambda line: asyncio.run(c.talk(line)))

    def test_55_a_switch_changed_mid_task_reaches_its_chat_once(self):
        import shadow_task_chat
        c, sent, talk = self.chat(shadow_task_chat._carry_stamp())
        talk("how is it going")
        self.assertEqual(sent[-1], "how is it going", "nothing changed yet")
        shadow_knows.set_switch("replies", "detailed")
        talk("and now")
        self.assertTrue(sent[-1].startswith(mission_engine.CARRY_CHANGED_HEAD))
        self.assertIn("How long should Shadow's messages be? Detailed.", sent[-1])
        self.assertTrue(sent[-1].endswith("and now"))
        talk("again")
        self.assertEqual(sent[-1], "again", "said once per change")

    def test_56_a_resumed_chat_is_told_the_current_settings(self):
        c, sent, talk = self.chat(mission_engine.CARRY_UNKNOWN)
        talk("back again")
        self.assertIn("Should Shadow check with you before it starts?", sent[-1])
        talk("next")
        self.assertEqual(sent[-1], "next")


class TestRoutes(Base):

    def post(self, body):
        return self.client.post("/api/shadow/knows", json=body, headers=HDR)

    def test_40_add_keep_edit_forget_through_the_route(self):
        r = self.post({"action": "add", "section": "memory",
                       "text": "Uses Vercel", "category": "tools"})
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["row"]["id"]
        self.assertEqual(r.json()["row"]["source"], "typed")
        r = self.post({"action": "edit", "id": rid, "text": "Deploys on Vercel"})
        self.assertEqual(r.json()["knows"]["memory"][0]["text"],
                         "Deploys on Vercel")
        r = self.post({"action": "forget", "id": rid})
        self.assertEqual(r.json()["knows"]["memory"], [])

    def test_41_keep_a_suggestion(self):
        row = shadow_knows.add("personality", "Be terse", "inferred")
        listing = self.client.get("/api/shadow/knows").json()
        self.assertEqual(listing["pending"], 1)
        r = self.post({"action": "keep", "id": row["id"]})
        self.assertEqual(r.json()["row"]["status"], "active")
        self.assertEqual(r.json()["knows"]["pending"], 0)

    def test_42_refusals_and_bad_actions(self):
        self.assertEqual(self.post({"action": "nope"}).status_code, 400)
        self.assertEqual(self.post({"action": "keep", "id": "know-x"})
                         .status_code, 409)
        r = self.post({"action": "add", "section": "memory",
                       "text": "api key: sk-abcdefghijklmnopqrstuv"})
        self.assertEqual(r.status_code, 409)

    def test_43_settings_carries_the_listing(self):
        shadow_knows.add("memory", "I am the CEO.", "said")
        s = self.client.get("/api/shadow/settings").json()
        self.assertEqual([r["text"] for r in s["knows"]["memory"]],
                         ["I am the CEO."])

    def test_45_a_chat_that_opened_no_task_can_be_deleted(self):
        """The x on a conversation row (founder, 2026-10-07: "not able to
        delete"). Unbound: gone. Bound to a task: refused, delete the task.
        Unknown: 404. A bad id: 400, never a path."""
        import shadow_conversations
        shadow_conversations.create("shc-aaaa1111", "Who has final say?")
        shadow_conversations.create("shc-bbbb2222", "Write a file")
        shadow_conversations.bind_mission("shc-bbbb2222", "m-1")
        go = lambda cid: self.client.post(
            "/api/shadow/conversations/%s/delete" % cid, json={}, headers=HDR)
        r = go("shc-aaaa1111")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(shadow_conversations.load("shc-aaaa1111"))
        self.assertFalse(os.path.exists(
            shadow_conversations._path("shc-aaaa1111") + ".lock"))
        self.assertEqual(go("shc-bbbb2222").status_code, 409)
        self.assertIsNotNone(shadow_conversations.load("shc-bbbb2222"))
        self.assertEqual(go("shc-cccc3333").status_code, 404)
        self.assertEqual(go("..%2F..%2Fx").status_code in (400, 404), True)

    def test_46_a_switch_is_set_through_the_route(self):
        r = self.post({"action": "switch", "name": "replies",
                       "value": "normal"})
        self.assertEqual(r.status_code, 200, r.text)
        sw = {s["name"]: s for s in r.json()["knows"]["switches"]}
        self.assertEqual((sw["replies"]["value"], sw["replies"]["set"]),
                         ("normal", True))
        self.assertEqual(self.post({"action": "switch", "name": "replies",
                                    "value": "loud"}).status_code, 409)

    def test_44_the_flag_off_is_dark(self):
        providers.SETTINGS_PATH.write_text(json.dumps({"shadow.enabled": False}))
        self.assertEqual(self.client.get("/api/shadow/knows").status_code, 403)
        self.assertEqual(self.post({"action": "add"}).status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
