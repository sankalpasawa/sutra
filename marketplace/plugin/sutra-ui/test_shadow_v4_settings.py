"""Shadow v4 step 7 (C7): "How Shadow behaves" -- the founder's own words.

One verbose text, in the SAME task-limits store 2.278.12 gave the numbers
(mission_engine.limits_path), read at every Shadow boot and appended to the
context under HOW SHADOW BEHAVES. Three levels, like test_shadow_run_limit:

  STORE   mission_engine.behaves() / set_behaves(): persisted, trimmed to
          BEHAVES_MAX_CHARS, never raises on a corrupt file.
  BOOT    shadow_session.standing_context() carries the text when set and
          nothing extra when empty; a failing limits read never erases the
          standing instructions block.
  ROUTE   GET /api/shadow/settings reports it; POST /api/shadow/settings/
          behaves writes it and refuses junk.

THE MEMORY HALF (founder, 2026-09-20) joins the same three levels, because
it is the same store answering a different question and it was reaching NO
reader at all: set_memory has persisted since 2026-09-17 and the settings
page has read it back, but memory() had no caller outside its own tests.
TestTheCarryBlock and TestTheCarryReaches below pin where each text lands:

  carry_block()   one renderer, both texts, each under its own heading, so
                  the precedence sentence cannot drift between readers.
  boot + chats    standing_context() carries both (task chats boot on it).
  decider         render_decide_prompt carries both -- the one-shot spawn
                  inherits no persona, so it reads them there or nowhere.
  worker brief    _facts_text carries MEMORY ONLY. `behaves` is policy
                  addressed to Shadow; a worker that neither checks in nor
                  asks must not be handed somebody else's rule.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_settings.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-behaves-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_ledger                           # noqa: E402
import shadow_session                          # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
ROUTE = "/api/shadow/settings/behaves"
TEXT = ("Check in every 3 turns. Never use the word mission with me. "
        "When two tasks conflict, ask before starting the second.")


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


class TestTheStore(Base):

    def test_01_unset_is_empty_and_creates_no_file(self):
        self.assertEqual(mission_engine.behaves(), "")
        self.assertFalse(os.path.exists(mission_engine.limits_path()))

    def test_02_set_then_read_survives_a_fresh_read(self):
        stored = mission_engine.set_behaves("  " + TEXT + "\n")
        self.assertEqual(stored, TEXT, "trimmed, otherwise verbatim")
        self.assertEqual(mission_engine.behaves(), TEXT)
        on_disk = json.loads(Path(mission_engine.limits_path()).read_text())
        self.assertEqual(on_disk["behaves"], TEXT)

    def test_03_lives_beside_the_numbers_not_in_a_second_store(self):
        mission_engine.set_max_running(3)
        mission_engine.set_behaves(TEXT)
        on_disk = json.loads(Path(mission_engine.limits_path()).read_text())
        self.assertEqual(on_disk["running_at_once"], 3)
        self.assertEqual(on_disk["behaves"], TEXT)
        self.assertEqual(mission_engine.max_running(), 3,
                         "writing the text must not disturb the cap")

    def test_04_long_text_is_cut_at_the_ceiling(self):
        long = "x" * (mission_engine.BEHAVES_MAX_CHARS + 500)
        self.assertEqual(len(mission_engine.set_behaves(long)),
                         mission_engine.BEHAVES_MAX_CHARS)

    def test_05_non_text_is_refused_not_coerced(self):
        for junk in (None, 12, ["a"], {"b": 1}):
            with self.assertRaises(ValueError):
                mission_engine.set_behaves(junk)

    def test_06_junk_on_disk_reads_as_empty_never_raises(self):
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"behaves": 42}))
        self.assertEqual(mission_engine.behaves(), "")
        Path(mission_engine.limits_path()).write_text("{not json")
        self.assertEqual(mission_engine.behaves(), "")

    def test_07_clearing_stores_empty(self):
        mission_engine.set_behaves(TEXT)
        self.assertEqual(mission_engine.set_behaves(""), "")
        self.assertEqual(mission_engine.behaves(), "")


class TestTheBoot(Base):

    def test_10_the_text_rides_the_boot_context_under_its_heading(self):
        mission_engine.set_behaves(TEXT)
        ctx = shadow_session.standing_context()
        self.assertIn("HOW SHADOW BEHAVES", ctx)
        self.assertIn(TEXT, ctx)
        self.assertIn("STANDING INSTRUCTIONS", ctx,
                      "the block the text joins is still there")

    def test_11_empty_text_adds_nothing(self):
        ctx = shadow_session.standing_context()
        self.assertNotIn("HOW SHADOW BEHAVES", ctx)

    def test_12_a_broken_limits_read_never_erases_standing_instructions(self):
        shadow_ledger.append("instructions", {
            "text": "always answer in one line", "precedence": "d_ledger",
            "confirmed": True, "scope": "global"})
        orig = mission_engine._read_limits

        def boom():
            raise OSError("limits unreadable")

        mission_engine._read_limits = boom
        try:
            ctx = shadow_session.standing_context()
        finally:
            mission_engine._read_limits = orig
        self.assertIn("STANDING INSTRUCTIONS", ctx)
        self.assertIn("always answer in one line", ctx)
        self.assertNotIn("HOW SHADOW BEHAVES", ctx)

    def test_13_precedence_line_names_what_outranks_it(self):
        mission_engine.set_behaves(TEXT)
        ctx = shadow_session.standing_context()
        head = ctx[ctx.index("HOW SHADOW BEHAVES"):]
        self.assertIn("floors", head[:400])
        self.assertIn("task", head[:400])


class TestTheRoute(Base):

    def test_20_get_reports_the_text_and_the_ceiling(self):
        mission_engine.set_behaves(TEXT)
        doc = self.client.get("/api/shadow/settings", headers=HDR).json()
        self.assertEqual(doc["behaves"], TEXT)
        self.assertEqual(doc["behaves_max"], mission_engine.BEHAVES_MAX_CHARS)

    def test_21_post_writes_and_echoes(self):
        r = self.client.post(ROUTE, json={"behaves": TEXT}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["behaves"], TEXT)
        self.assertEqual(mission_engine.behaves(), TEXT)

    def test_22_post_refuses_a_missing_key_and_a_non_string(self):
        r = self.client.post(ROUTE, json={}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(ROUTE, json={"behaves": 7}, headers=HDR)
        self.assertEqual(r.status_code, 400)

    def test_23_post_is_ledgered_as_a_setting(self):
        self.client.post(ROUTE, json={"behaves": TEXT}, headers=HDR)
        acts = shadow_ledger.read("actions", 10)
        self.assertTrue(any(a.get("kind") == "setting"
                            and "behaves" in (a.get("summary") or "")
                            for a in acts), acts)


MEMO = ("I am the CEO of Sutra. Meraki Labs is the holding company. "
        "Never call the product Sutra OS in anything a client reads.")


class TestTheCarryBlock(Base):
    """mission_engine.carry_block(): one renderer for both texts."""

    def test_30_both_unset_is_empty(self):
        self.assertEqual(mission_engine.carry_block(), "")

    def test_31_behaves_alone_renders_only_its_heading(self):
        mission_engine.set_behaves(TEXT)
        block = mission_engine.carry_block()
        self.assertIn("HOW SHADOW BEHAVES", block)
        self.assertIn(TEXT, block)
        self.assertNotIn("CARRIED INTO EVERY TASK", block)

    def test_32_memory_alone_renders_only_its_heading(self):
        mission_engine.set_memory(MEMO)
        block = mission_engine.carry_block()
        self.assertIn("CARRIED INTO EVERY TASK", block)
        self.assertIn(MEMO, block)
        self.assertNotIn("HOW SHADOW BEHAVES", block)

    def test_33_both_render_policy_first(self):
        mission_engine.set_behaves(TEXT)
        mission_engine.set_memory(MEMO)
        block = mission_engine.carry_block()
        self.assertLess(block.index("HOW SHADOW BEHAVES"),
                        block.index("CARRIED INTO EVERY TASK"),
                        "policy is ranked, so it is stated first")

    def test_34_memory_heading_says_it_is_not_permission(self):
        """The one line that keeps a FACT from reading as a GRANT. A wrong
        fact costs a wrong sentence; a wrong permission costs an action."""
        mission_engine.set_memory(MEMO)
        head = mission_engine.carry_block()
        head = head[:head.index(MEMO)]
        self.assertIn("NOT PERMISSION", head)
        self.assertIn("floor", head)

    def test_35_a_broken_limits_read_yields_empty_not_an_exception(self):
        mission_engine.set_memory(MEMO)
        orig = mission_engine._read_limits

        def boom():
            raise OSError("limits unreadable")

        mission_engine._read_limits = boom
        try:
            self.assertEqual(mission_engine.carry_block(), "")
        finally:
            mission_engine._read_limits = orig


class TestTheCarryReaches(Base):
    """Every reader of the two texts, and the one that deliberately is not."""

    def test_40_the_boot_context_carries_the_memory_text(self):
        """Which is also how every task chat gets it: shadow_task_chat boots
        on load_context() + offers_context() + standing_context()."""
        mission_engine.set_memory(MEMO)
        ctx = shadow_session.standing_context()
        self.assertIn("CARRIED INTO EVERY TASK", ctx)
        self.assertIn(MEMO, ctx)
        self.assertIn("STANDING INSTRUCTIONS", ctx)

    def test_41_an_empty_memory_adds_nothing_to_the_boot(self):
        ctx = shadow_session.standing_context()
        self.assertNotIn("CARRIED INTO EVERY TASK", ctx)

    def test_42_the_decider_context_carries_the_block(self):
        mission_engine.set_behaves(TEXT)
        mission_engine.set_memory(MEMO)
        eng = mission_engine.MissionEngine(None, None, None, lambda m: "x")
        ctx = eng._decision_context({"objective": "o", "done_when": []}, "")
        self.assertIn(TEXT, ctx["carry"])
        self.assertIn(MEMO, ctx["carry"])

    def test_43_an_unconfigured_install_omits_the_key_entirely(self):
        eng = mission_engine.MissionEngine(None, None, None, lambda m: "x")
        ctx = eng._decision_context({"objective": "o", "done_when": []}, "")
        self.assertNotIn("carry", ctx,
                         "the decider prompt must be what it was before")

    def test_44_the_decide_prompt_renders_it(self):
        import shadow_runner
        out = shadow_runner.render_decide_prompt({
            "outcome": "o", "checks": [], "turns_used": 1, "max_turns": 5,
            "carry": "HOW SHADOW BEHAVES:\n" + TEXT})
        self.assertIn("WHO YOU WORK FOR", out)
        self.assertIn(TEXT, out)

    def test_44b_the_prompt_tells_it_to_decide_on_them_not_ask_again(self):
        """Carrying the text is not the same as using it. Without this the
        decider SEES the founder's words and is still free to ask them the
        same question next task."""
        import shadow_runner
        out = shadow_runner.render_decide_prompt({
            "outcome": "o", "checks": [], "turns_used": 1, "max_turns": 5,
            "carry": "Never push to main without asking."})
        self.assertIn("standing answers", out)
        flat = " ".join(out.split())
        self.assertIn("read WHO YOU WORK FOR above", flat)
        self.assertIn("do not put the same question to them a second time",
                      flat)
        # and the three things they still cannot do
        self.assertIn("never reach the floors", out)
        self.assertIn("founder_confirm", out)

    def test_45_a_context_without_the_key_still_renders(self):
        """Several suites build a decision context by hand. A new key must
        not KeyError them, and must say plainly that there is nothing."""
        import shadow_runner
        out = shadow_runner.render_decide_prompt({
            "outcome": "o", "checks": [], "turns_used": 1, "max_turns": 5})
        self.assertIn("WHO YOU WORK FOR", out)
        self.assertIn("has not written any", out)

    def test_46_the_worker_brief_carries_memory_and_not_behaves(self):
        import shadow_task_chat
        facts = {"repo": "~/x", "rules": [], "floors": [], "about": MEMO}
        text = shadow_task_chat._facts_text(facts)
        self.assertIn(MEMO, text)
        self.assertIn("not permission", text)
        self.assertNotIn(TEXT, text,
                         "behaves is a rule addressed to Shadow, not the "
                         "worker, and must not travel in a brief")

    def test_47_no_memory_means_no_section_in_the_brief(self):
        import shadow_task_chat
        text = shadow_task_chat._facts_text(
            {"repo": "~/x", "rules": [], "floors": []})
        self.assertNotIn("about the founder", text)

    def test_48_brief_facts_reads_the_memory_box(self):
        mission_engine.set_memory(MEMO)
        self.assertEqual(app_module._brief_facts({}).get("about"), MEMO)

    def test_49_a_broken_limits_read_costs_the_line_not_the_brief(self):
        mission_engine.set_memory(MEMO)
        orig = mission_engine._read_limits

        def boom():
            raise OSError("limits unreadable")

        mission_engine._read_limits = boom
        try:
            facts = app_module._brief_facts({})
        finally:
            mission_engine._read_limits = orig
        self.assertEqual(facts.get("about"), "")
        self.assertIn("repo", facts)


class TestShadowFillsTheBoxes(Base):
    """mission_engine.remember()/forget(): the founder says it in a chat,
    Shadow writes it into the box they would otherwise have typed."""

    def test_50_a_bad_kind_and_an_empty_line_are_refused(self):
        with self.assertRaises(ValueError):
            mission_engine.remember("vibes", "something")
        with self.assertRaises(ValueError):
            mission_engine.remember("memory", "   ")
        with self.assertRaises(ValueError):
            mission_engine.forget("memory", "")

    def test_51_each_kind_writes_its_own_box(self):
        mission_engine.remember("personality", "Always run the suite first.")
        mission_engine.remember("memory", "I am the CEO.")
        self.assertEqual(mission_engine.behaves(), "Always run the suite first.")
        self.assertEqual(mission_engine.memory(), "I am the CEO.")

    def test_52_a_second_line_is_added_not_substituted(self):
        mission_engine.remember("memory", "I am the CEO.")
        mission_engine.remember("memory", "Meraki Labs is the holding co.")
        self.assertEqual(mission_engine.memory().split("\n"),
                         ["I am the CEO.", "Meraki Labs is the holding co."])

    def test_53_hearing_the_same_thing_twice_writes_once(self):
        """The founder repeats themselves. Reading their own words back in
        duplicate would leave them wondering which copy binds."""
        mission_engine.remember("memory", "I am the CEO.")
        mission_engine.remember("memory", "  i AM the ceo.  ")
        self.assertEqual(mission_engine.memory(), "I am the CEO.")

    def test_54_a_pasted_paragraph_becomes_one_line(self):
        mission_engine.remember("personality", "Ask first.\n\nThen act.")
        self.assertEqual(mission_engine.behaves(), "Ask first. Then act.")

    def test_55_what_the_founder_typed_by_hand_is_not_overwritten(self):
        mission_engine.set_memory("I am the CEO.")
        mission_engine.remember("memory", "We ship on Fridays.")
        self.assertIn("I am the CEO.", mission_engine.memory())
        self.assertIn("We ship on Fridays.", mission_engine.memory())

    def test_56_a_full_box_drops_the_oldest_and_keeps_the_newest(self):
        cap = mission_engine.MEMORY_MAX_CHARS
        mission_engine.set_memory("\n".join(["old line %d" % i
                                             for i in range(cap // 12)]))
        mission_engine.remember("memory", "the newest thing they said")
        out = mission_engine.memory()
        self.assertLessEqual(len(out), cap)
        self.assertTrue(out.endswith("the newest thing they said"))
        self.assertNotIn("old line 0", out)

    def test_57_forget_removes_the_line_and_leaves_the_rest(self):
        mission_engine.remember("personality", "Ask first.")
        mission_engine.remember("personality", "Never push to main.")
        mission_engine.forget("personality", "  ask FIRST.  ")
        self.assertEqual(mission_engine.behaves(), "Never push to main.")

    def test_58_forgetting_what_was_never_there_changes_nothing(self):
        mission_engine.remember("personality", "Ask first.")
        self.assertEqual(mission_engine.forget("personality", "nope"),
                         "Ask first.")

    def test_59_what_shadow_wrote_is_what_shadow_reads_next_boot(self):
        """The whole loop, end to end: told in a chat -> in the box -> in
        the context every Shadow and every task chat boots on."""
        mission_engine.remember("memory", "Never call it Sutra OS to a client.")
        ctx = shadow_session.standing_context()
        self.assertIn("Never call it Sutra OS to a client.", ctx)
        self.assertIn("CARRIED INTO EVERY TASK", ctx)

    def test_60_the_route_still_owns_the_box_so_the_founder_can_edit_it(self):
        mission_engine.remember("memory", "Shadow wrote this.")
        r = self.client.post("/api/shadow/settings/memory",
                             json={"memory": "the founder rewrote it"},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(mission_engine.memory(), "the founder rewrote it")


class TestTheShadowTool(unittest.TestCase):
    """shadow_remember is registered only for Shadow's own session, and
    writes through the same function the suite above pins."""

    def _run(self, body):
        import subprocess
        import sys
        home = tempfile.mkdtemp(prefix="shadow-tool-")
        settings = Path(home) / "providers-settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        env = dict(os.environ, SUTRA_SHADOW_HOME=home,
                   SUTRA_MCP_SHADOW="1", SUTRA_UI_SETTINGS=str(settings))
        out = subprocess.run(
            [sys.executable, "-c", body],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        return out.stdout.strip()

    def test_70_it_is_listed_with_both_kinds_in_its_schema(self):
        out = self._run(
            "import sutra_mcp, json;"
            "t = sutra_mcp.BY_NAME['shadow_remember'];"
            "print(json.dumps(t['schema']['properties']['kind']['enum']))")
        self.assertEqual(json.loads(out), ["personality", "memory"])

    def test_71_calling_it_writes_the_box_and_a_bad_kind_says_so(self):
        out = self._run(
            "import sutra_mcp, mission_engine;"
            "sutra_mcp.BY_NAME['shadow_remember']['fn']"
            "({'kind': 'memory', 'line': 'I am the CEO.'});"
            "print(mission_engine.memory());"
            "r = sutra_mcp.BY_NAME['shadow_remember']['fn']"
            "({'kind': 'vibes', 'line': 'x'});"
            "print(str(r)[-80:])")
        self.assertIn("I am the CEO.", out)
        self.assertIn("personality|memory", out)

    def test_72_it_is_absent_from_an_ordinary_session(self):
        """No SUTRA_MCP_SHADOW: a worker or a task chat cannot rewrite the
        founder's settings, which is the same fence every Shadow tool has."""
        import subprocess
        import sys
        env = dict(os.environ)
        env.pop("SUTRA_MCP_SHADOW", None)
        out = subprocess.run(
            [sys.executable, "-c",
             "import sutra_mcp; print('shadow_remember' in sutra_mcp.BY_NAME)"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "False", out.stderr[-2000:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
