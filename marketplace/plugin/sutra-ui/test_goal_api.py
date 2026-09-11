"""V5 slice 6: the Goal routes, through the real FastAPI app.

The domain is already covered by test_goal_store / _lifecycle / _progress /
_memory. These tests are about the SHELL: gating, request/response shapes,
error mapping, and that the routes delegate to goal_lifecycle rather than
re-implementing it.

`start`/`resume` stub shadow_runner.start_mission_async, so the tests assert
the route hands the right attempt to the EXISTING mission start path without
spawning real work.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="goal-api-test-")

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import goal_lifecycle  # noqa: E402
import goal_store  # noqa: E402
import providers  # noqa: E402
import session_runtime  # noqa: E402
from goal_store import GoalStore  # noqa: E402
from mission_engine import MissionStore  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
BASE = "/api/shadow/goals"
C_ART = "contains_artifact"


class _LiveRt:
    """The fixture chat's runtime: alive, and never touched by these tests."""
    alive = True


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        # a Path, not a str: providers reads it with .read_text()
        self.settings = Path(self.tmp.name) / "settings.json"
        self.settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = self.settings
        self.goals = GoalStore()
        self.missions = MissionStore()
        # Start/Resume now require a chat Shadow can actually speak into
        # (2026-09-11): a live runtime for the fixture session is what a real
        # target has. `ensure_runtime` returns it untouched -- the founder
        # always wins -- so nothing is spawned and no transcript is read.
        self._rt = _LiveRt()
        session_runtime.register_runtime("01a081", self._rt)

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        session_runtime.unregister_runtime("01a081", self._rt)
        self.tmp.cleanup()

    def flag_off(self):
        self.settings.write_text(json.dumps({"shadow.enabled": False}))

    def post(self, path, body):
        return self.client.post(path, json=body, headers=HDR)

    def get(self, path):
        return self.client.get(path, headers=HDR)

    def make_goal(self, outcome="ship the connector retry fix",
                  session="01a081",
                  checks=(("BUILD OK",), ("RETRY OK",))):
        r = self.post(BASE, {
            "outcome": outcome, "target_session": session,
            "done_when": [{"tier": C_ART, "check": c[0]} for c in checks]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def stub_start(self):
        """Replace the async start with a recorder."""
        calls = []
        orig = app_module.shadow_runner.start_mission_async

        def fake(mid, say, provisioner=None, verifier=None):
            calls.append(mid)
            return {"accepted": True, "mission_id": mid}

        app_module.shadow_runner.start_mission_async = fake
        self.addCleanup(
            lambda: setattr(app_module.shadow_runner,
                            "start_mission_async", orig))
        return calls


class TestGate(Base):
    def test_01_every_goal_route_respects_the_shadow_gate(self):
        g = self.make_goal()
        self.flag_off()
        self.assertEqual(self.get(BASE).status_code, 403)
        self.assertEqual(self.get(BASE + "/" + g["id"]).status_code, 403)
        self.assertEqual(self.post(BASE, {"outcome": "x",
                                          "target_session": "s"}
                                   ).status_code, 403)
        self.assertEqual(self.post(BASE + "/%s/act" % g["id"],
                                   {"action": "start"}).status_code, 403)

    def test_02_the_gate_message_matches_every_other_shadow_route(self):
        self.flag_off()
        r = self.get(BASE)
        self.assertEqual(r.json()["detail"], "the shadow flag is off")


class TestCreate(Base):
    def test_03_create_lands_in_draft_and_does_not_start_work(self):
        g = self.make_goal()
        self.assertTrue(g["id"].startswith("g-"))
        self.assertEqual(g["state"], "draft")
        self.assertEqual(g["target_session"], "01a081")
        self.assertEqual(g["outcome"], "ship the connector retry fix")
        self.assertIsNone(g["current_mission_id"],
                          "creation never starts an attempt")
        self.assertEqual(self.missions.list(), [],
                         "and never creates a mission")
        self.assertEqual(g["checks_label"], "0 of 2 checks")

    def test_04_outcome_and_target_session_are_required(self):
        self.assertEqual(self.post(BASE, {"target_session": "s"}
                                   ).status_code, 400)
        self.assertEqual(self.post(BASE, {"outcome": "x"}).status_code, 400)
        self.assertEqual(self.post(BASE, {"outcome": "  ",
                                          "target_session": "s"}
                                   ).status_code, 400)

    def test_05_one_active_goal_per_chat_is_a_409(self):
        self.make_goal()
        r = self.post(BASE, {"outcome": "something else",
                             "target_session": "01a081"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("one active goal per chat", r.json()["detail"])
        # a different chat is fine
        self.assertEqual(self.post(BASE, {"outcome": "other",
                                          "target_session": "01a082"}
                                   ).status_code, 200)

    def test_06_a_terminal_goal_releases_the_chat(self):
        g = self.make_goal()
        self.assertEqual(self.post(BASE + "/%s/act" % g["id"],
                                   {"action": "stop"}).status_code, 200)
        self.assertEqual(self.post(BASE, {"outcome": "next one",
                                          "target_session": "01a081"}
                                   ).status_code, 200)


class TestListAndDetail(Base):
    def test_07_list_carries_what_a_home_row_needs(self):
        self.make_goal()
        self.make_goal(outcome="other", session="01a082")
        rows = self.get(BASE).json()["goals"]
        self.assertEqual(len(rows), 2)
        for field in ("id", "outcome", "state", "target_session",
                      "checks_met", "checks_total", "checks_label",
                      "turns_used", "max_turns", "turn_label",
                      "block_reason", "attempt", "current_mission_id",
                      "created_at", "updated_at"):
            self.assertIn(field, rows[0], field)
        self.assertNotIn("learned", rows[0], "the list stays a list")

    def test_08_list_filters_by_state_and_session(self):
        a = self.make_goal()
        self.make_goal(outcome="other", session="01a082")
        self.assertEqual(
            [r["id"] for r in
             self.get(BASE + "?target_session=01a081").json()["goals"]],
            [a["id"]])
        self.assertEqual(
            len(self.get(BASE + "?state=draft").json()["goals"]), 2)
        self.assertEqual(
            len(self.get(BASE + "?state=done").json()["goals"]), 0)

    def test_09_detail_exposes_the_full_ui_contract(self):
        g = self.make_goal()
        d = self.get(BASE + "/" + g["id"]).json()
        for field in ("id", "target_session", "outcome", "state",
                      "current_mission_id", "checks", "checks_met",
                      "checks_total", "checks_label", "unmet",
                      "turns_used", "max_turns", "turn_label",
                      "block_reason", "attempts", "learned",
                      "founder_guidance", "blockers", "history",
                      "done_when", "created_at", "updated_at",
                      "last_evaluated_at"):
            self.assertIn(field, d, field)
        self.assertEqual([c["check"] for c in d["checks"]],
                         ["BUILD OK", "RETRY OK"])
        self.assertEqual(d["unmet"], ["BUILD OK", "RETRY OK"])

    def test_10_detail_hides_storage_mechanics(self):
        g = self.make_goal()
        goal_lifecycle.record_founder_guidance(g["id"], "mock server first")
        d = self.get(BASE + "/" + g["id"]).json()
        for internal in ("seq", "created_ns", "check_results"):
            self.assertNotIn(internal, d, internal)
        for item in d["learned"]:
            self.assertNotIn("dedupe_key", item)

    def test_11_an_unknown_goal_is_a_404(self):
        self.assertEqual(self.get(BASE + "/g-nope").status_code, 404)
        self.assertEqual(self.post(BASE + "/g-nope/act",
                                   {"action": "stop"}).status_code, 404)


class TestStartAndResume(Base):
    def test_12_start_creates_one_attempt_via_the_lifecycle(self):
        calls = self.stub_start()
        g = self.make_goal()
        r = self.post(BASE + "/%s/act" % g["id"], {"action": "start"})
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        self.assertTrue(doc["started"]["accepted"])
        mid = doc["mission_id"]
        self.assertEqual(calls, [mid],
                         "handed to the existing mission start path")
        m = self.missions.load(mid)
        self.assertEqual(m["goal_id"], g["id"])
        self.assertEqual(m["target_session"], "01a081")
        self.assertEqual(m["target_mode"], "existing")
        self.assertEqual(m["state"], "brief_confirm")
        self.assertEqual(doc["goal"]["current_mission_id"], mid)
        self.assertEqual(len(doc["goal"]["attempts"]), 1)

    def test_13_start_twice_is_a_409(self):
        self.stub_start()
        g = self.make_goal()
        self.post(BASE + "/%s/act" % g["id"], {"action": "start"})
        r = self.post(BASE + "/%s/act" % g["id"], {"action": "start"})
        self.assertEqual(r.status_code, 409, r.text)

    def test_14_resume_needs_a_blocked_goal(self):
        self.stub_start()
        g = self.make_goal()
        r = self.post(BASE + "/%s/act" % g["id"], {"action": "resume"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("blocked", r.json()["detail"])

    def test_15_resume_runs_a_new_attempt_in_the_same_chat(self):
        calls = self.stub_start()
        g = self.make_goal()
        first = goal_lifecycle.start_first_attempt(g["id"])
        # take the attempt to blocked the way the engine would
        self.missions.transition(first["id"], "running")
        self.missions.block(first["id"], "budget_exhausted", "max turns (2)")
        goal_lifecycle.on_attempt_end(self.missions.load(first["id"]))
        blocked = self.get(BASE + "/" + g["id"]).json()
        self.assertEqual(blocked["state"], "blocked")

        r = self.post(BASE + "/%s/act" % g["id"],
                      {"action": "resume", "extra_turns": 3})
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        second = self.missions.load(doc["mission_id"])
        self.assertNotEqual(second["id"], first["id"], "a NEW attempt")
        self.assertEqual(second["target_session"], "01a081",
                         "the SAME chat -- no retargeting, no fresh chat")
        self.assertEqual(calls, [second["id"]])
        self.assertEqual(len(doc["goal"]["attempts"]), 2)
        self.assertEqual(doc["goal"]["attempts"][0]["ended_state"],
                         "blocked")
        self.assertEqual(len(self.goals.list()), 1, "no second goal")
        self.assertTrue(second["manifest"], "briefed with goal context")

    def test_16_a_blocked_goal_response_carries_its_blocker(self):
        g = self.make_goal()
        first = goal_lifecycle.start_first_attempt(g["id"])
        self.missions.transition(first["id"], "running")
        self.missions.block(first["id"], "ping_pong", "ping-pong detected")
        goal_lifecycle.on_attempt_end(self.missions.load(first["id"]))
        d = self.get(BASE + "/" + g["id"]).json()
        self.assertEqual(d["state"], "blocked")
        self.assertEqual(d["block_reason"], "ping_pong")
        self.assertTrue(d["blockers"])
        self.assertIn("ping_pong", d["blockers"][0]["text"])
        self.assertIsNone(d["current_mission_id"])
        row = [r for r in self.get(BASE).json()["goals"]
               if r["id"] == g["id"]][0]
        self.assertEqual(row["block_reason"], "ping_pong")


class TestStopAndGuidance(Base):
    def test_17_stop_abandons_the_goal_and_its_attempt(self):
        self.stub_start()
        g = self.make_goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.missions.transition(m["id"], "running")
        r = self.post(BASE + "/%s/act" % g["id"],
                      {"action": "stop", "note": "not worth it"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["state"], "stopped")
        self.assertIsNone(d["current_mission_id"])
        self.assertEqual(self.missions.load(m["id"])["state"], "stopped")
        self.assertEqual(self.missions.load(m["id"])["ended_by"], "founder")

    def test_18_guidance_is_recorded_and_returned(self):
        g = self.make_goal()
        r = self.post(BASE + "/%s/act" % g["id"],
                      {"action": "guidance",
                       "text": "bring the mock server up first"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(len(d["founder_guidance"]), 1)
        self.assertEqual(d["founder_guidance"][0]["source"], "founder")
        self.assertIn("mock server", d["founder_guidance"][0]["text"])
        self.assertEqual(self.post(BASE + "/%s/act" % g["id"],
                                   {"action": "guidance", "text": " "}
                                   ).status_code, 400)

    def test_19_an_unknown_action_is_a_400(self):
        g = self.make_goal()
        r = self.post(BASE + "/%s/act" % g["id"], {"action": "teleport"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("unknown action", r.json()["detail"])


class TestFounderConfirmation(Base):
    def _verifying_goal(self):
        g = self.goals.create(
            "ship it", "01a084",
            done_when=[{"tier": C_ART, "check": "BUILD OK"},
                        {"tier": "founder_confirm", "check": "sign off"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.missions.transition(m["id"], "running")
        # one evaluation: the artifact check passed, the founder one has not
        goal_lifecycle.record_evaluation(
            self.missions.load(m["id"]),
            [{"tier": C_ART, "check": "BUILD OK", "met": True},
             {"tier": "founder_confirm", "check": "sign off", "met": False}],
            False)
        return g, m

    def test_20_confirming_updates_goal_progress_immediately(self):
        g, m = self._verifying_goal()
        before = self.get(BASE + "/" + g["id"]).json()
        self.assertEqual(before["checks_label"], "1 of 2 checks")
        self.assertEqual(before["unmet"], ["sign off"])
        r = self.post(BASE + "/%s/act" % g["id"],
                      {"action": "confirm", "index": 1})
        self.assertEqual(r.status_code, 200, r.text)
        after = r.json()
        self.assertEqual(after["checks_label"], "2 of 2 checks",
                         "no waiting for the next mission evaluation")
        self.assertEqual(after["unmet"], [])
        # the existing mission writer is still the one that stamped it
        mm = self.missions.load(m["id"])
        self.assertTrue(mm["done_when"][1]["met"])
        self.assertEqual(mm["done_when"][1]["confirmed_by"], "founder")

    def test_21_confirming_does_not_lose_previously_proven_checks(self):
        g, _m = self._verifying_goal()
        self.post(BASE + "/%s/act" % g["id"],
                  {"action": "confirm", "index": 1})
        d = self.get(BASE + "/" + g["id"]).json()
        self.assertEqual([c["met"] for c in d["checks"]], [True, True])

    def test_22_confirm_needs_a_live_attempt_and_a_real_index(self):
        g = self.make_goal()
        r = self.post(BASE + "/%s/act" % g["id"],
                      {"action": "confirm", "index": 0})
        self.assertEqual(r.status_code, 409)
        self.assertIn("no live attempt", r.json()["detail"])
        g2, _m = self._verifying_goal()
        # index 0 is contains_artifact, not founder_confirm
        r2 = self.post(BASE + "/%s/act" % g2["id"],
                       {"action": "confirm", "index": 0})
        self.assertEqual(r2.status_code, 409)

    def test_23_the_mission_confirm_action_also_syncs_the_goal(self):
        """The pre-existing mission route must not leave the goal stale."""
        g, m = self._verifying_goal()
        r = self.post("/api/shadow/missions/%s/act" % m["id"],
                      {"action": "confirm_check", "index": 1})
        self.assertEqual(r.status_code, 200, r.text)
        d = self.get(BASE + "/" + g["id"]).json()
        self.assertEqual(d["checks_label"], "2 of 2 checks")


class TestQueuedCancellation(Base):
    def test_24_dropping_a_queued_attempt_clears_current_mission_id(self):
        """Slice 3 finding: a dropped queued attempt never reaches the
        runner's funnel, so the goal would keep a stale live attempt."""
        g = self.make_goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.missions.transition(m["id"], "queued", "cap reached")
        self.assertEqual(self.goals.load(g["id"])["current_mission_id"],
                         m["id"])
        r = self.post("/api/shadow/missions/%s/act" % m["id"],
                      {"action": "drop"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.missions.load(m["id"])["state"], "stopped")
        held = self.goals.load(g["id"])
        self.assertIsNone(held["current_mission_id"],
                          "no stale live attempt")
        self.assertEqual(held["state"], "stopped",
                         "an explicit founder drop abandons the goal")
        self.assertEqual(held["attempts"][0]["ended_state"], "stopped")

    def test_25_the_mission_stop_action_synchronises_the_goal(self):
        """Slice 3 finding: the API Stop bypassed founder_stop, so a goal
        read a founder decision as machine trouble and blocked."""
        g = self.make_goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.missions.transition(m["id"], "running")
        r = self.post("/api/shadow/missions/%s/act" % m["id"],
                      {"action": "stop"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["ended_by"], "founder")
        held = self.goals.load(g["id"])
        self.assertEqual(held["state"], "stopped",
                         "stopped, not blocked")
        self.assertIsNone(held["current_mission_id"])

    def test_26_a_standalone_mission_stop_still_behaves(self):
        solo = self.missions.create("standalone", "fix")
        self.missions.transition(solo["id"], "brief_confirm")
        self.missions.transition(solo["id"], "running")
        r = self.post("/api/shadow/missions/%s/act" % solo["id"],
                      {"action": "stop"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["state"], "stopped")
        self.assertEqual(self.goals.list(), [])


class TestProgressAndMemoryThroughTheApi(Base):
    def test_27_progress_comes_through_unchanged(self):
        g = self.make_goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.missions.transition(m["id"], "running")
        goal_lifecycle.record_evaluation(
            self.missions.load(m["id"]),
            [{"tier": C_ART, "check": "BUILD OK", "met": True},
             {"tier": C_ART, "check": "RETRY OK", "met": False}], False)
        d = self.get(BASE + "/" + g["id"]).json()
        self.assertEqual(d["checks_label"], "1 of 2 checks")
        self.assertEqual(d["checks_met"], 1)
        self.assertEqual(d["checks_total"], 2)
        self.assertEqual(d["unmet"], ["RETRY OK"])
        self.assertEqual(d["turn_label"], "turn 0/20")
        blob = json.dumps(d)
        self.assertNotIn("percent", blob.lower())

    def test_28_memory_comes_through_unchanged(self):
        g = self.make_goal()
        goal_lifecycle.record_founder_guidance(g["id"], "mock server first")
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.missions.transition(m["id"], "running")
        self.missions.block(m["id"], "ping_pong", "ping-pong detected")
        goal_lifecycle.on_attempt_end(self.missions.load(m["id"]))
        d = self.get(BASE + "/" + g["id"]).json()
        kinds = sorted({item["kind"] for item in d["learned"]})
        self.assertIn("attempt_outcome", kinds)
        self.assertIn("blocker", kinds)
        self.assertIn("founder_guidance", kinds)
        self.assertTrue(d["history"])
        self.assertEqual(len(d["attempts"]), 1)

    def test_29_goal_memory_never_reaches_the_instruction_ledger(self):
        import shadow_ledger
        g = self.make_goal()
        self.post(BASE + "/%s/act" % g["id"],
                  {"action": "guidance", "text": "goal-scoped only"})
        self.assertEqual(shadow_ledger.read("instructions", 100), [],
                         "global Shadow memory is untouched")


if __name__ == "__main__":
    unittest.main()
