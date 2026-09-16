"""\"Budget per task\" -- the founder-set turn budget, end to end.

The budget was a real number the founder could only READ. The settings page
printed mission_engine.TEMPLATES[kind]["max_turns"] beside an AUTO pill, and
that pill was honest: there was no control, no route and no store behind it.
This lane covers the feature that replaced it, at the three levels it has to
be true at or it is not a setting at all:

  STORE       mission_engine.turn_budget(kind) prefers a persisted value over
              the template default, clamps into [MIN_TURNS, TURNS_CEILING]
              IN THE STORE (not in the stepper -- a hand-written POST must
              not reach 0 or 500), survives a restart, and NEVER raises: this
              sits on the mission-creation path, so a corrupt file must cost
              the default, not the task the founder just asked for.
  CREATION    MissionStore.create stamps the configured number onto the new
              mission's max_turns, which is the only thing run_mission ever
              compares. Because it is a SNAPSHOT, a budget change binds the
              next task and never re-budgets one already running -- the
              "new tasks only" claim, asserted rather than assumed.
  ROUTE       GET /api/shadow/settings reports the effective budgets, the
              band, and which kinds carry an override; POST
              /api/shadow/settings/budget writes one kind, clamps, refuses
              junk / an unknown kind / watch, and resets to auto on null.

WHY A SIBLING ROUTE rather than a second field on /api/shadow/settings/tasks:
that route is one route, one field, and test_shadow_run_limit's test_34 and
test_35 hold it to that. Both still pass unmodified, which is the point.

WATCH IS EXCLUDED and has its own tests here. Its budget is never consumed --
run_mission returns on the never_say invariant before it ever compares
max_turns -- so a number stored for it could never bind, and a control that
looks kept but is never read is worse than one that says it cannot be set.

Run: ./run-tests.sh test_shadow_turn_budget.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-budget-test-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import goal_lifecycle                          # noqa: E402
import goal_store                              # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
from mission_engine import MissionStore         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
BUDGET = "/api/shadow/settings/budget"
TASKS = "/api/shadow/settings/tasks"
SETTINGS = "/api/shadow/settings"


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

    def tasks(self):
        r = self.client.get(SETTINGS, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["tasks"]


# ------------------------------------------------------------------ STORE --
class TestTheStore(Base):

    def test_01_unset_is_the_template_default(self):
        for kind, expected in (("feature", 30), ("fix", 20),
                               ("research", 15), ("watch", 0)):
            self.assertEqual(mission_engine.turn_budget(kind), expected)
        self.assertEqual(mission_engine.turn_budget_overrides(), [])

    def test_02_a_read_does_not_create_the_file(self):
        """An install nobody has configured must be byte-identical to one
        from before this setting existed."""
        mission_engine.turn_budgets()
        self.assertFalse(os.path.exists(mission_engine.limits_path()))

    def test_03_set_then_read_survives_a_fresh_resolver(self):
        mission_engine.set_turn_budget("feature", 45)
        self.assertEqual(mission_engine.turn_budget("feature"), 45)
        # the value is on disk, not in a module global
        self.assertEqual(
            json.loads(Path(mission_engine.limits_path()).read_text()),
            {"turn_budget": {"feature": 45}})

    def test_04_out_of_band_numbers_clamp_in_the_store(self):
        """THE CLAMP IS THE SERVER'S, and this is the assertion that says so.
        The stepper stopping at the ends is a courtesy; this is the part a
        hand-written POST cannot get around."""
        self.assertEqual(mission_engine.set_turn_budget("fix", 0),
                         mission_engine.MIN_TURNS)
        self.assertEqual(mission_engine.set_turn_budget("fix", -20),
                         mission_engine.MIN_TURNS)
        self.assertEqual(mission_engine.set_turn_budget("fix", 500),
                         mission_engine.TURNS_CEILING)
        self.assertEqual(mission_engine.MIN_TURNS, 1)
        self.assertEqual(mission_engine.TURNS_CEILING, 100)

    def test_05_junk_raises_and_stores_nothing(self):
        # None is absent deliberately: it is the reset-to-auto sentinel
        # (test_06), not junk. Everything that cannot be a whole number is.
        for junk in ("twenty", {}, [], object()):
            with self.assertRaises(ValueError):
                mission_engine.set_turn_budget("fix", junk)
        self.assertEqual(mission_engine.turn_budget("fix"), 20)
        self.assertEqual(mission_engine.turn_budget_overrides(), [])

    def test_06_reset_to_auto_deletes_the_key(self):
        """Auto is the ABSENCE of a setting, not a sentinel number -- so a
        future change to a template default still reaches it."""
        mission_engine.set_turn_budget("fix", 40)
        self.assertEqual(mission_engine.turn_budget_overrides(), ["fix"])
        self.assertEqual(mission_engine.set_turn_budget("fix", None), 20)
        self.assertEqual(mission_engine.turn_budget_overrides(), [])
        self.assertNotIn(
            "turn_budget",
            json.loads(Path(mission_engine.limits_path()).read_text()))

    def test_07_a_budget_set_to_its_own_default_still_counts_as_set(self):
        """Overrides are read off the store, never inferred by comparing the
        value to the default -- otherwise a founder who deliberately chose 20
        for `fix` would be redrawn as `auto` and lose the reset control."""
        mission_engine.set_turn_budget("fix", 20)
        self.assertEqual(mission_engine.turn_budget("fix"), 20)
        self.assertEqual(mission_engine.turn_budget_overrides(), ["fix"])

    def test_08_a_corrupt_store_costs_the_default_not_an_exception(self):
        Path(mission_engine.limits_path()).write_text("{not json at all")
        self.assertEqual(mission_engine.turn_budget("fix"), 20)
        self.assertEqual(mission_engine.turn_budgets()["feature"], 30)
        self.assertEqual(mission_engine.turn_budget_overrides(), [])

    def test_09_a_hand_edited_junk_value_degrades_to_the_default(self):
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"turn_budget": {"fix": "loads"}}))
        self.assertEqual(mission_engine.turn_budget("fix"), 20)

    def test_10_a_hand_edited_out_of_band_value_is_clamped_on_read(self):
        """Writing through the store clamps; a file edited by hand has not
        been through it, so the READ has to clamp too."""
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"turn_budget": {"fix": 9999}}))
        self.assertEqual(mission_engine.turn_budget("fix"),
                         mission_engine.TURNS_CEILING)

    def test_11_the_two_settings_share_the_file_without_clobbering(self):
        """Both directions: the budget write must not lose the cap, and the
        cap write must not lose the budget."""
        mission_engine.set_max_running(3)
        mission_engine.set_turn_budget("feature", 45)
        self.assertEqual(mission_engine.max_running(), 3)
        self.assertEqual(mission_engine.turn_budget("feature"), 45)
        mission_engine.set_max_running(7)
        self.assertEqual(mission_engine.turn_budget("feature"), 45)
        mission_engine.set_turn_budget("fix", 11)
        self.assertEqual(mission_engine.max_running(), 7)

    def test_12_watch_is_not_settable_and_a_hand_edit_is_ignored(self):
        with self.assertRaises(ValueError):
            mission_engine.set_turn_budget("watch", 40)
        # defence in depth: even a file edited by hand cannot give watch one
        Path(mission_engine.limits_path()).write_text(
            json.dumps({"turn_budget": {"watch": 40}}))
        self.assertEqual(mission_engine.turn_budget("watch"), 0)
        self.assertEqual(mission_engine.turn_budget_overrides(), [])

    def test_13_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            mission_engine.set_turn_budget("nonsense", 10)

    def test_14_settable_kinds_are_derived_from_the_invariant(self):
        """"A kind that never speaks never spends a turn" is the rule; the
        tuple must follow from never_say rather than name watch."""
        self.assertEqual(set(mission_engine.SETTABLE_BUDGET_KINDS),
                         {"feature", "fix", "research"})
        for k in mission_engine.SETTABLE_BUDGET_KINDS:
            self.assertNotIn("never_say",
                             mission_engine.TEMPLATES[k]["invariants"])

    def test_15_a_separate_process_reads_back_what_was_written(self):
        """THE RESTART CLAIM, ASSERTED RATHER THAN CLICKED.

        test_03 proves the value survives a fresh RESOLVER; this proves it
        survives a fresh INTERPRETER, which is what "restart the app" means.
        A module-level global or a cached dict would pass test_03 and fail
        here, which is exactly the difference the objective turns on.
        """
        mission_engine.set_turn_budget("feature", 65)
        env = dict(os.environ)
        env["SUTRA_SHADOW_HOME"] = self.tmp.name
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            [sys.executable, "-c",
             "import mission_engine; print(mission_engine.turn_budget"
             "('feature'))"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(out.stdout.strip(), "65",
                         "a new process must read the founder's budget off "
                         "disk, not fall back to the template (stderr: %s)"
                         % out.stderr[-300:])


# --------------------------------------------------------------- CREATION --
class TestCreation(Base):

    def test_20_create_stamps_the_configured_budget(self):
        mission_engine.set_turn_budget("feature", 45)
        m = self.store.create("ship it", "feature", target_mode="new")
        self.assertEqual(m["max_turns"], 45)

    def test_21_unset_still_stamps_the_template_default(self):
        m = self.store.create("ship it", "feature", target_mode="new")
        self.assertEqual(m["max_turns"], 30)

    def test_22_the_budget_is_a_snapshot_new_tasks_only(self):
        """THE THIRD CLAUSE OF THE OBJECTIVE. A mission created before the
        change keeps the number it was born with; only the next one moves."""
        before = self.store.create("old task", "fix", target_mode="new")
        mission_engine.set_turn_budget("fix", 55)
        after = self.store.create("new task", "fix", target_mode="new")
        self.assertEqual(self.store.load(before["id"])["max_turns"], 20,
                         "a change re-budgeted a task already created")
        self.assertEqual(after["max_turns"], 55)

    def test_23_watch_is_still_zero_with_a_budget_set_elsewhere(self):
        mission_engine.set_turn_budget("feature", 90)
        m = self.store.create("just watch", "watch", target_mode="new")
        self.assertEqual(m["max_turns"], 0)

    def test_24_a_retry_takes_the_CURRENT_setting(self):
        """clone_for_retry routes through create(), so a retry is stamped
        with the budget in force NOW rather than its parent's. That is the
        right reading of a retry -- a new task with an old brief -- and it is
        how a founder who raises the budget after watching a task run out of
        road gets the bigger number without editing anything."""
        m = self.store.create("fix the thing", "fix", target_mode="new")
        self.assertEqual(m["max_turns"], 20)
        self.store.transition(m["id"], "brief_confirm", "proposed")
        self.store.transition(m["id"], "running", "go")
        self.store.transition(m["id"], "failed", "out of road")
        mission_engine.set_turn_budget("fix", 60)
        clone = mission_engine.clone_for_retry(self.store, m["id"])
        self.assertEqual(self.store.load(clone["id"])["max_turns"], 60)

    def test_25_a_goal_continuation_does_NOT_take_the_setting(self):
        """THE ONE PLACE THE SETTING DOES NOT REACH, pinned so a future
        refactor cannot change it silently. A goal's budget is cumulative
        across attempts ("extend adds, never resets"), so a continuation
        carries the prior ceiling forward; re-reading the setting here would
        reset a goal that had already spent three attempts' worth of road.
        `extra_turns` is the control that moves a goal's ceiling.
        """
        gs = goal_store.GoalStore()
        g = gs.create("get it shipped", target_session="sess-1",
                      done_when=[])
        first = goal_lifecycle.start_first_attempt(g["id"], template="fix")
        self.assertEqual(first["max_turns"], 20, "first attempt takes create()")
        self.store.transition(first["id"], "running", "go")
        blocked = self.store.transition(first["id"], "blocked", "out of road")
        # end attempt 1 through the real hook: a blocked mission is
        # deliberately NOT terminal, so the goal keeps holding it until this
        # runs, and resume_goal refuses a goal with a live attempt
        goal_lifecycle.on_attempt_end(blocked)
        mission_engine.set_turn_budget("fix", 90)
        second = goal_lifecycle.resume_goal(g["id"], extra_turns=5,
                                            template="fix")
        self.assertEqual(second["max_turns"], 25,
                         "a continuation must carry prev + extra_turns, not "
                         "re-read the setting")


# ------------------------------------------------------------------ ROUTE --
class TestTheRoute(Base):

    def test_30_get_reports_the_effective_budgets_and_the_band(self):
        mission_engine.set_turn_budget("feature", 45)
        t = self.tasks()
        self.assertEqual(t["turn_budget"],
                         {"feature": 45, "fix": 20, "research": 15,
                          "watch": 0})
        self.assertEqual(t["turn_budget_min"], 1)
        self.assertEqual(t["turn_budget_max"], 100)
        self.assertEqual(t["turn_budget_set"], ["feature"])
        self.assertEqual(t["turn_budget_kinds"],
                         ["feature", "fix", "research"])

    def test_31_post_writes_what_create_then_stamps(self):
        """The whole feature in one assertion: the route writes, and the
        engine's own create path reads back what was written."""
        r = self.client.post(BUDGET, json={"kind": "fix", "turns": 40},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["turns"], 40)
        self.assertFalse(r.json()["auto"])
        m = self.store.create("do the thing", "fix", target_mode="new")
        self.assertEqual(m["max_turns"], 40)

    def test_32_post_clamps_and_says_what_it_stored(self):
        for sent, kept in ((0, 1), (-5, 1), (999, 100)):
            r = self.client.post(BUDGET, json={"kind": "fix", "turns": sent},
                                 headers=HDR)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["turns"], kept,
                             "a hand-written POST reached %r" % (sent,))

    def test_33_post_refuses_junk_a_missing_field_and_watch(self):
        for body in ({"kind": "fix", "turns": "forty"},
                     {"kind": "fix"},
                     {"turns": 40},
                     {},
                     {"kind": "nonsense", "turns": 40},
                     {"kind": "watch", "turns": 40}):
            r = self.client.post(BUDGET, json=body, headers=HDR)
            self.assertEqual(r.status_code, 400, "%r -> %s" % (body, r.text))
        self.assertEqual(mission_engine.turn_budget_overrides(), [],
                         "nothing was stored")

    def test_34_null_resets_to_auto(self):
        self.client.post(BUDGET, json={"kind": "fix", "turns": 40},
                         headers=HDR)
        r = self.client.post(BUDGET, json={"kind": "fix", "turns": None},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["auto"])
        self.assertEqual(body["turns"], 20, "a reset lands on the default")
        self.assertEqual(body["turn_budget_set"], [])
        self.assertEqual(self.store.create("x", "fix",
                                           target_mode="new")["max_turns"], 20)

    def test_35_the_response_carries_the_whole_map(self):
        """The row and all four Delegate-offer chips repaint off this, so a
        response that named only the written kind would leave chips stale."""
        r = self.client.post(BUDGET, json={"kind": "research", "turns": 35},
                             headers=HDR)
        self.assertEqual(r.json()["turn_budget"],
                         {"feature": 30, "fix": 20, "research": 35,
                          "watch": 0})
        self.assertEqual(r.json()["default"], 15,
                         "the response must name what auto would be")

    def test_36_the_cap_route_still_refuses_a_budget(self):
        """The sibling-route decision, asserted from this side too:
        /settings/tasks is still one route, one field."""
        r = self.client.post(TASKS, json={"turn_budget": {"fix": 99}},
                             headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(TASKS, json={"running_at_once": 3,
                                          "turn_budget": {"fix": 99}},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(mission_engine.turn_budget("fix"), 20,
                         "the cap route moved a budget")

    def test_37_the_write_is_ledgered(self):
        import shadow_ledger
        self.client.post(BUDGET, json={"kind": "fix", "turns": 40},
                         headers=HDR)
        rows = shadow_ledger.read_latest("actions")
        self.assertTrue(
            any(r.get("kind") == "setting" and "turn budget for fix"
                in (r.get("summary") or "") for r in rows),
            "no ledger row for the budget write: %r" % (rows[-3:],))

    def test_38_the_flag_gates_it(self):
        providers.SETTINGS_PATH.write_text(json.dumps(
            {"shadow.enabled": False}))
        r = self.client.post(BUDGET, json={"kind": "fix", "turns": 40},
                             headers=HDR)
        self.assertEqual(r.status_code, 403)

    def test_39_the_panel_token_gates_it(self):
        r = self.client.post(BUDGET, json={"kind": "fix", "turns": 40},
                             headers={"Origin": "http://127.0.0.1:8330"})
        self.assertIn(r.status_code, (401, 403),
                      "an untokened write reached the store: %s" % r.text)
        self.assertEqual(mission_engine.turn_budget("fix"), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
