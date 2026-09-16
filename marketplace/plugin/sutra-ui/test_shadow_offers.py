"""\"Delegate offers\" -- the founder-set list of kinds, end to end.

The row in Shadow Settings > Tasks used to be a picture: chips with an x and
a "+ add", every one of them inert, because there was nowhere to keep a
delegate kind. This lane is the store that changed that, and the rules it
must keep.

  STORE      mission_engine.offered_kinds() prefers a persisted list over the
             built-ins, refuses a junk NAME rather than sanitising it,
             survives a restart, and NEVER raises -- a corrupt file must cost
             the founder their custom kinds, not their ability to delegate.

  CATALOGUE  templates() is the superset offered_kinds() is a view of.
             Removing a kind UN-OFFERS it and never UN-DEFINES it, so
             clone_for_retry can still rebuild a finished mission that used
             it. That asymmetry is the whole design and test_20 is the
             regression it exists to prevent.

  BEHAVIOUR  the fence parser, the delegate route and Shadow's own boot
             context read the founder's list at decision time -- not a
             fourth copy of four names typed into a fourth file.

  ROUTE      GET /api/shadow/settings reports the live list; POST
             /api/shadow/settings/offers writes it, refuses junk, refuses to
             empty itself, and leaves an audit row.

Run: ./run-tests.sh test_shadow_offers.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-offers-test-")

from fastapi.testclient import TestClient      # noqa: E402
import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_protocol                         # noqa: E402
from mission_engine import MissionStore         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
OFFERS = "/api/shadow/settings/offers"


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

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def on_disk(self):
        return json.loads(Path(mission_engine.offers_path()).read_text())


class TestTheStore(Base):

    def test_01_unset_is_the_built_ins(self):
        """An install nobody has configured offers what shipped -- and the
        file is not created merely by asking."""
        self.assertEqual(mission_engine.offered_kinds(),
                         list(mission_engine.BUILTIN_OFFERS))
        self.assertFalse(os.path.exists(mission_engine.offers_path()),
                         "a READ must not create the store")

    def test_02_the_built_in_fallback_is_exactly_the_built_in_templates(self):
        """BUILTIN_OFFERS is hand-ordered (fix first, because the Delegate
        form has always opened there). Its MEMBERSHIP is not a matter of
        taste: a fifth template must not be able to ship unoffered because
        someone forgot this tuple."""
        self.assertEqual(sorted(mission_engine.BUILTIN_OFFERS),
                         sorted(mission_engine.TEMPLATES))

    def test_03_the_default_offer_is_the_first_one(self):
        self.assertEqual(mission_engine.default_offer(), "fix")
        mission_engine.remove_offer("fix")
        self.assertEqual(mission_engine.default_offer(), "feature",
                         "the default must follow the founder's list, never "
                         "point at a kind they retired")

    def test_04_add_then_read_across_a_fresh_resolver(self):
        self.assertIn("review", mission_engine.add_offer("review"))
        self.assertIn("review", mission_engine.offered_kinds())
        self.assertEqual(self.on_disk()["offered"][-1], "review")
        self.assertEqual(self.on_disk()["custom"]["review"]["max_turns"],
                         mission_engine.DEFAULT_OFFER_TURNS)

    def test_05_a_minted_kind_gets_the_default_budget_and_no_invariants(self):
        mission_engine.add_offer("review")
        self.assertEqual(mission_engine.turn_budget("review"),
                         mission_engine.DEFAULT_OFFER_TURNS)
        self.assertEqual(mission_engine.templates()["review"]["invariants"],
                         mission_engine.DEFAULT_OFFER_INVARIANTS)

    def test_06_a_name_is_forgiven_its_typing_but_not_its_meaning(self):
        """Case and space are typing. Punctuation is a different name."""
        self.assertEqual(mission_engine.clean_offer_name("  Review "), "review")
        for junk in ("", None, "a", "x" * 25, "Code Review!", "2fast",
                     "-lead", "with space", {}, []):
            with self.assertRaises(ValueError, msg=repr(junk)):
                mission_engine.clean_offer_name(junk)

    def test_07_a_refused_name_leaves_no_file_behind(self):
        with self.assertRaises(ValueError):
            mission_engine.add_offer("Code Review!")
        self.assertFalse(os.path.exists(mission_engine.offers_path()),
                         "a refused write must leave no file behind")

    def test_08_adding_what_is_already_offered_is_a_no_op(self):
        """A double-click must not duplicate a chip."""
        first = mission_engine.add_offer("review")
        again = mission_engine.add_offer("review")
        self.assertEqual(first, again)
        self.assertEqual(again.count("review"), 1)

    def test_09_the_last_offer_cannot_be_removed(self):
        for k in ("watch", "research", "feature"):
            mission_engine.remove_offer(k)
        self.assertEqual(mission_engine.offered_kinds(), ["fix"])
        with self.assertRaises(ValueError):
            mission_engine.remove_offer("fix")
        self.assertEqual(mission_engine.offered_kinds(), ["fix"],
                         "the refusal must not have half-applied")

    def test_10_removing_what_is_not_offered_is_a_no_op(self):
        before = mission_engine.offered_kinds()
        self.assertEqual(mission_engine.remove_offer("nosuchkind"), before)

    def test_11_the_ceiling_is_enforced(self):
        n = len(mission_engine.offered_kinds())
        for i in range(mission_engine.MAX_OFFERS - n):
            mission_engine.add_offer("kind-%d" % i)
        self.assertEqual(len(mission_engine.offered_kinds()),
                         mission_engine.MAX_OFFERS)
        with self.assertRaises(ValueError):
            mission_engine.add_offer("one-too-many")

    def test_12_a_corrupt_store_costs_the_custom_kinds_not_an_exception(self):
        Path(mission_engine.offers_path()).write_text("{not json")
        self.assertEqual(mission_engine.offered_kinds(),
                         list(mission_engine.BUILTIN_OFFERS))
        self.assertEqual(sorted(mission_engine.templates()),
                         sorted(mission_engine.TEMPLATES))
        Path(mission_engine.offers_path()).write_text(
            json.dumps({"offered": "fix", "custom": 7}))
        self.assertEqual(mission_engine.offered_kinds(),
                         list(mission_engine.BUILTIN_OFFERS))

    def test_13_hand_edited_junk_entries_are_skipped_not_fatal(self):
        import json_store
        json_store.write_json(mission_engine.offers_path(), {
            "offered": ["fix", "Not A Kind", "review", "fix", 7],
            "custom": {"review": {"max_turns": "banana"},
                       "Bad Name": {"max_turns": 5},
                       "alsobad": "not a dict"}})
        self.assertEqual(mission_engine.offered_kinds(), ["fix", "review"],
                         "junk entries drop, good ones survive, no dupes")
        self.assertEqual(mission_engine.turn_budget("review"),
                         mission_engine.DEFAULT_OFFER_TURNS,
                         "a junk budget costs the default for that kind")

    def test_14_an_empty_offered_list_reads_as_unconfigured(self):
        """Not a legal state -- it can only arrive by hand-edit. Nothing
        offered would mean nothing can be delegated at all, so it degrades
        to the built-ins rather than to a mute Shadow."""
        import json_store
        json_store.write_json(mission_engine.offers_path(), {"offered": []})
        self.assertEqual(mission_engine.offered_kinds(),
                         list(mission_engine.BUILTIN_OFFERS))

    def test_15_a_built_in_wins_a_name_collision(self):
        """A hand-edited custom "watch" may change what Settings shows. It
        must never strip never_say off the real one."""
        import json_store
        json_store.write_json(mission_engine.offers_path(), {
            "offered": ["watch"],
            "custom": {"watch": {"max_turns": 99, "invariants": []}}})
        self.assertEqual(mission_engine.templates()["watch"],
                         mission_engine.TEMPLATES["watch"])
        self.assertIn("never_say",
                      mission_engine.templates()["watch"]["invariants"])

    def test_16_other_keys_in_the_store_survive_a_write(self):
        import json_store
        json_store.write_json(mission_engine.offers_path(),
                              {"something_else": 7})
        mission_engine.add_offer("review")
        self.assertEqual(self.on_disk()["something_else"], 7)
        self.assertIn("review", self.on_disk()["offered"])

    def test_17_the_store_lives_under_the_shadow_home(self):
        self.assertTrue(
            os.path.realpath(mission_engine.offers_path()).startswith(
                os.path.realpath(self.tmp.name) + os.sep))

    def test_18_it_is_not_the_limits_file(self):
        """A corrupt offer list must not cost the concurrency cap too."""
        self.assertNotEqual(mission_engine.offers_path(),
                            mission_engine.limits_path())
        mission_engine.set_max_running(3)
        Path(mission_engine.offers_path()).write_text("{not json")
        self.assertEqual(mission_engine.max_running(), 3)

    def test_19_a_separate_process_reads_back_what_was_written(self):
        """THE RESTART CLAIM, ASSERTED RATHER THAN CLICKED.

        Every in-process test here would still pass if the list were cached
        in a module global that happened to be warm. Only a cold interpreter
        reading the same home proves the founder's choice is on disk.
        """
        mission_engine.add_offer("review")
        mission_engine.remove_offer("watch")

        import subprocess
        import sys
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            [sys.executable, "-c",
             "import mission_engine; print(mission_engine.offered_kinds())"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)), timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(),
                         "['fix', 'feature', 'research', 'review']",
                         "a cold process must read the founder's list")


class TestTheCatalogue(Base):
    """Removal un-offers; it never un-defines."""

    def test_20_a_retired_kind_can_still_be_retried(self):
        """THE REGRESSION THIS DESIGN EXISTS TO PREVENT.

        clone_for_retry rebuilds a finished mission with its ORIGINAL
        template. If removing a kind deleted its definition, then retiring
        "review" would make every review task the founder had ever run
        un-retryable -- work already done, broken by a settings click.
        """
        mission_engine.add_offer("review")
        m = self.store.create("check the EMI rounding", "review",
                              target_mode="new")
        self.store.transition(m["id"], "brief_confirm", "proposed")
        self.store.transition(m["id"], "running", "started")
        self.store.transition(m["id"], "done", "finished")

        mission_engine.remove_offer("review")
        self.assertNotIn("review", mission_engine.offered_kinds(),
                         "the founder retired it")
        self.assertIn("review", mission_engine.templates(),
                      "but the definition must survive for retry")

        clone = mission_engine.clone_for_retry(self.store, m["id"])
        self.assertEqual(clone["template"], "review")
        self.assertEqual(clone["max_turns"],
                         mission_engine.DEFAULT_OFFER_TURNS)

    def test_21_re_adding_restores_the_budget_it_always_had(self):
        mission_engine.add_offer("review")
        mission_engine.set_turn_budget("review", 42)
        mission_engine.remove_offer("review")
        mission_engine.add_offer("review")
        self.assertEqual(mission_engine.turn_budget("review"), 42,
                         "a re-added kind must not be reset to the default")

    def test_22_create_gates_on_the_catalogue_not_the_offered_list(self):
        mission_engine.remove_offer("research")
        m = self.store.create("read the docs", "research", target_mode="new")
        self.assertEqual(m["template"], "research")
        with self.assertRaises(ValueError):
            self.store.create("x", "neverdefined", target_mode="new")

    def test_23_a_minted_kind_carries_its_invariants_onto_the_mission(self):
        mission_engine.add_offer("review")
        m = self.store.create("x", "review", target_mode="new")
        self.assertEqual(m["invariants"], [])
        w = self.store.create("y", "watch", target_mode="new")
        self.assertEqual(w["invariants"], ["never_say"])

    def test_24_a_minted_kind_has_a_settable_budget(self):
        mission_engine.add_offer("review")
        self.assertIn("review", mission_engine.settable_budget_kinds())
        self.assertNotIn("watch", mission_engine.settable_budget_kinds(),
                         "the never_say rule still decides, unchanged")
        self.assertEqual(mission_engine.set_turn_budget("review", 7), 7)


class TestTheBehaviour(Base):
    """The list is read at decision time, by the code that actually offers."""

    def fence(self, template):
        return ('```mission\n{"objective": "fix the EMI rounding", '
                '"template": "%s", "target_mode": "new"}\n```' % template)

    def test_30_the_fence_accepts_an_offered_kind(self):
        _display, blocks = shadow_protocol.parse_reply(self.fence("fix"))
        self.assertIn("mission", blocks)
        self.assertEqual(blocks["mission"]["template"], "fix")

    def test_31_the_fence_refuses_a_retired_kind_and_stays_visible(self):
        """An invalid block must never become an invisible side effect --
        the rule shadow_protocol already keeps for every other block."""
        mission_engine.remove_offer("watch")
        raw = self.fence("watch")
        display, blocks = shadow_protocol.parse_reply(raw)
        self.assertNotIn("mission", blocks, "a retired kind was acted on")
        self.assertIn("watch", display,
                      "a refused block must stay visible in the reply")

    def test_32_the_fence_accepts_a_kind_the_founder_minted(self):
        """The point of the whole feature: Shadow can offer what the founder
        added, without anyone editing a tuple in shadow_protocol.py."""
        mission_engine.add_offer("review")
        _display, blocks = shadow_protocol.parse_reply(self.fence("review"))
        self.assertIn("mission", blocks)
        self.assertEqual(blocks["mission"]["template"], "review")

    def test_33_an_explicit_kinds_argument_still_wins(self):
        _d, blocks = shadow_protocol.parse_reply(self.fence("review"),
                                                 kinds=["review"])
        self.assertIn("mission", blocks)
        _d, blocks = shadow_protocol.parse_reply(self.fence("fix"),
                                                 kinds=["review"])
        self.assertNotIn("mission", blocks)

    def test_34_a_broken_store_leaves_the_fence_working(self):
        """parse_reply sits on the reply path. It must degrade to the
        built-ins, never raise into a founder's conversation."""
        Path(mission_engine.offers_path()).write_text("{not json")
        _d, blocks = shadow_protocol.parse_reply(self.fence("fix"))
        self.assertIn("mission", blocks)

    def test_35_shadows_boot_context_names_the_live_offers(self):
        import shadow_session
        mission_engine.add_offer("review")
        mission_engine.remove_offer("watch")
        ctx = shadow_session.offers_context()
        self.assertIn("review", ctx)
        self.assertIn("fix", ctx)
        self.assertNotIn('"watch"', ctx,
                         "a retired kind must not be offered to Shadow")

    def test_36_the_boot_context_never_raises(self):
        Path(mission_engine.offers_path()).write_text("{not json")
        import shadow_session
        self.assertIn("fix", shadow_session.offers_context())

    def test_37_the_fence_gate_is_a_variable_not_a_typed_tuple(self):
        """A PROVABLE NEGATIVE, in the spirit of test_forbidden_calls.

        The gate at shadow_protocol.py:187 used to read

            val.get("template") in ("feature", "fix", "research", "watch")

        and that literal was the delegation-offer hardcode. It is now a
        membership test against a list resolved per reply. This asserts the
        SHAPE of the gate rather than the absence of four words -- the words
        legitimately survive as _BUILTIN_KINDS, the degraded answer when the
        store cannot be read, and a test that banned them outright would be
        banning the fallback rather than the hardcode.
        """
        import re as _re
        here = os.path.dirname(os.path.abspath(__file__))
        body = Path(os.path.join(here, "shadow_protocol.py")).read_text()
        self.assertIsNone(
            _re.search(r'template"\)\s*in\s*\(', body),
            "the mission fence gates on a typed-out tuple again -- it must "
            "gate on the founder's offered_kinds()")
        self.assertIn('val.get("template") in allowed', body,
                      "the fence gate must read the per-reply list")
        # and the four names appear ONCE, as the named fallback
        self.assertEqual(body.count('"fix", "feature", "research", "watch"'), 1)

    def test_38_the_four_names_are_gone_from_the_other_offer_doors(self):
        """app.py's delegate route and Shadow's own persona used to carry
        their own copies. Neither may again."""
        here = os.path.dirname(os.path.abspath(__file__))
        app_body = Path(os.path.join(here, "app.py")).read_text()
        self.assertNotIn('body.get("template") or "fix"', app_body,
                         "the delegate route defaults to a typed kind again")
        self.assertIn("_mission_engine.offered_kinds()", app_body)
        md = Path(os.path.join(here, "SHADOW.md")).read_text()
        self.assertNotIn("feature|fix|research|watch", md,
                         "the persona hardcodes the kind list again -- it "
                         "must point at DELEGATE OFFERS")
        self.assertIn("DELEGATE OFFERS", md)


class TestTheRoute(Base):

    def get_tasks(self):
        r = self.client.get("/api/shadow/settings", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["tasks"]

    def test_40_get_reports_the_live_list_and_its_band(self):
        mission_engine.add_offer("review")
        t = self.get_tasks()
        self.assertEqual(t["offers"], mission_engine.offered_kinds())
        self.assertIn("review", t["offers"])
        self.assertEqual(t["offers_min"], mission_engine.MIN_OFFERS)
        self.assertEqual(t["offers_max"], mission_engine.MAX_OFFERS)

    def test_41_get_quotes_a_budget_for_every_kind_it_offers(self):
        """The chip's tooltip states turns. A chip whose budget the payload
        omitted would render bare -- so the budget map covers the CATALOGUE,
        not just the built-ins."""
        mission_engine.add_offer("review")
        t = self.get_tasks()
        for k in t["offers"]:
            self.assertIn(k, t["turn_budget"], k)
        self.assertEqual(t["turn_budget"]["review"],
                         mission_engine.DEFAULT_OFFER_TURNS)

    def test_42_post_add_writes_what_the_engine_then_offers(self):
        r = self.client.post(OFFERS, json={"add": "review"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("review", r.json()["offers"])
        self.assertIn("review", mission_engine.offered_kinds(),
                      "the route and the offerer must read one store")

    def test_43_post_remove_writes_what_the_engine_then_offers(self):
        r = self.client.post(OFFERS, json={"remove": "watch"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("watch", r.json()["offers"])
        self.assertNotIn("watch", mission_engine.offered_kinds())

    def test_44_the_answer_carries_what_the_row_repaints_from(self):
        r = self.client.post(OFFERS, json={"add": "review"}, headers=HDR)
        body = r.json()
        for key in ("offers", "min", "max", "turn_budget"):
            self.assertIn(key, body, key)
        self.assertEqual(body["turn_budget"]["review"],
                         mission_engine.DEFAULT_OFFER_TURNS)

    def test_45_post_refuses_junk_and_a_missing_verb(self):
        for body in ({"add": "Code Review!"}, {"add": ""}, {"add": None},
                     {}, {"offers": ["fix"]}, {"add": "x"},
                     {"add": "review", "remove": "fix"}):
            r = self.client.post(OFFERS, json=body, headers=HDR)
            self.assertEqual(r.status_code, 400, "%r -> %s" % (body, r.text))
        self.assertEqual(mission_engine.offered_kinds(),
                         list(mission_engine.BUILTIN_OFFERS),
                         "nothing was stored")

    def test_46_post_refuses_to_empty_the_list(self):
        for k in ("watch", "research", "feature"):
            self.client.post(OFFERS, json={"remove": k}, headers=HDR)
        r = self.client.post(OFFERS, json={"remove": "fix"}, headers=HDR)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(mission_engine.offered_kinds(), ["fix"])

    def test_47_the_write_is_ledgered(self):
        """Every Shadow write leaves an audit row; an offer change is one."""
        import shadow_ledger
        self.client.post(OFFERS, json={"add": "review"}, headers=HDR)
        rows = shadow_ledger.read("actions", 50)
        self.assertTrue(
            any("review" in (r.get("summary") or "") for r in rows), rows)

    def test_48_the_route_is_flag_gated_like_every_other_shadow_write(self):
        providers.SETTINGS_PATH.write_text(json.dumps({"shadow.enabled": False}))
        r = self.client.post(OFFERS, json={"add": "review"}, headers=HDR)
        self.assertEqual(r.status_code, 403, r.text)

    def test_49_a_cross_origin_write_is_refused_without_the_panel_token(self):
        r = self.client.post(OFFERS, json={"add": "review"},
                             headers={"Origin": "http://127.0.0.1:8330"})
        self.assertEqual(r.status_code, 403, r.text)

    def test_50_the_delegate_route_refuses_a_retired_kind(self):
        """The founder's OWN door. Unlike retry, this is "start something
        new", so a kind they retired is not on offer here either."""
        self.client.post(OFFERS, json={"remove": "watch"}, headers=HDR)
        r = self.client.post("/api/shadow/missions",
                             json={"objective": "watch the build",
                                   "template": "watch", "target_mode": "new"},
                             headers=HDR)
        self.assertEqual(r.status_code, 400, r.text)

    def test_51_the_delegate_route_defaults_to_the_first_offer(self):
        self.client.post(OFFERS, json={"remove": "fix"}, headers=HDR)
        r = self.client.post("/api/shadow/missions",
                             json={"objective": "ship the thing",
                                   "target_mode": "new"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["template"], mission_engine.default_offer())
        self.assertNotEqual(r.json()["template"], "fix")


if __name__ == "__main__":
    unittest.main(verbosity=2)
