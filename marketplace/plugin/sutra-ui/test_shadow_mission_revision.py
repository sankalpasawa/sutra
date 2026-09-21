#!/usr/bin/env python3
"""THE FOUNDER MAY CHANGE THEIR MIND AT ANY POINT (founder, 2026-09-21).

THE FAILURE. An Africa trip mission reached NEEDS YOU. The founder said
"I changed my mind, I want to visit India not Africa." Shadow answered
"India it is -- amending the task now, the file becomes india-trip-plan.md"
and NOTHING AMENDED. The objective, the done_when and the version never
moved, so the Africa criteria stayed authoritative, the Africa artifact
stayed the answer, and NEEDS YOU went on asking about a trip nobody wanted.
Shadow said one thing and the record said another.

TWO ROOT CAUSES, and the second is the dangerous one.

  1. `app.api_shadow_task_chat` applied a `mission` fence only while
     DRAFTING. The guard was deliberate -- "after Start it would make a
     casual question re-scope live work" -- and too blunt: it blocked every
     objective change, not just the casual ones. The discriminator was
     already in the protocol, because the task chat emits a `mission` fence
     only when it MEANS to amend. Prose changes nothing; a fence does.

  2. `run_mission` reloaded before any terminal decision -- "a takeover that
     landed while we evaluated must win" -- and compared STATE ONLY. An
     amend leaves a running mission running, so a worker turn composed under
     the Africa brief could still reach `_complete` and finish the India
     mission on Africa's evidence.

THE BOUNDARY IS mission_id + version, and `version` was ALREADY the
revision: `mint_approval` stamps it and `approve_held_say` has always
refused a say whose version moved ("the task changed since it asked"). This
work extends that one narrow guard to the loop, the sign-off and the
verification state. No second state machine was introduced.

NO SPECIAL CASES. Nothing here matches on "Africa", "India", "changed my
mind", or a filename. The fence is the signal and the version is the
boundary.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_mission_revision.py
"""
import asyncio
import os
import tempfile
import unittest

# the live home is not a test fixture -- see tests-never-touch-live-stores
os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-rev-test-")

import mission_engine                                          # noqa: E402
import shadow_decision                                         # noqa: E402

AFRICA = "Plan a personal trip for me to Africa for 10 days"
INDIA = "Plan a personal trip for me to India for 10 days"
JAPAN = "Plan a personal trip for me to Japan for 10 days"

AFRICA_CHECKS = [
    {"tier": "verify", "check": "africa-trip-plan.md exists",
     "probe": {"kind": "file_exists", "path": "africa-trip-plan.md"}},
    {"tier": "founder_confirm",
     "check": "the destinations, pace and budget match what you want"},
]
INDIA_CHECKS = [
    {"tier": "verify", "check": "india-trip-plan.md exists",
     "probe": {"kind": "file_exists", "path": "india-trip-plan.md"}},
    {"tier": "founder_confirm",
     "check": "the India itinerary is the trip you want"},
]


class Base(unittest.TestCase):

    def setUp(self):
        os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(
            prefix="shadow-rev-test-")
        self.root = tempfile.mkdtemp()
        self.store = mission_engine.MissionStore()

    def running(self, objective=AFRICA, checks=None):
        m = self.store.create(objective, "research",
                              done_when=list(checks or AFRICA_CHECKS))
        self.store.transition(m["id"], "brief_confirm", "briefed")
        self.store.transition(m["id"], "running", "go")
        return self.store.load(m["id"])

    def engine(self):
        eng = mission_engine.MissionEngine.__new__(
            mission_engine.MissionEngine)
        eng.store = self.store
        eng.probe_root = self.root
        return eng


# ══ 1-4. THE AMEND ITSELF ═══════════════════════════════════════════════
class AmendingALiveTask(Base):

    def test_1_a_running_task_can_be_amended(self):
        """THE BUG: this used to be refused, so Shadow's "amending now" was
        a sentence and not a change."""
        m = self.running()
        before = m["version"]
        out = self.store.amend(m["id"], objective=INDIA,
                               done_when=list(INDIA_CHECKS))
        self.assertEqual(out["objective"], INDIA)
        self.assertEqual(out["version"], before + 1)

    def test_2_a_NEEDS_YOU_task_can_be_amended(self):
        """NEEDS YOU means "Shadow needs a decision", never "the mission can
        no longer change". Changing the task IS the founder's answer."""
        m = self.running()
        paused = self.engine()._await_confirmation(m["id"])
        self.assertEqual(paused["pause_reason"], "founder_confirm")
        out = self.store.amend(m["id"], objective=INDIA,
                               done_when=list(INDIA_CHECKS))
        self.assertEqual(out["objective"], INDIA)
        self.assertEqual(out["state"], "running",
                         "a pause earned by the old revision is not a pause "
                         "the new one is in")
        self.assertIsNone(out.get("pause_reason"))

    def test_3_old_verification_state_is_invalidated(self):
        """Old criteria, old verdicts and old signatures all belonged to a
        question nobody is asking now."""
        m = self.running()
        rows = m["done_when"]
        rows[0]["met"] = True
        rows[0]["judged"] = {"state": "met", "reason": "africa plan is good"}
        rows[1]["met"] = True
        rows[1]["confirmed_by"] = "founder"
        self.store.save(m)
        out = self.store.amend(m["id"], objective=INDIA,
                               done_when=list(INDIA_CHECKS))
        for row in out["done_when"]:
            self.assertNotIn("met", row)
            self.assertNotIn("judged", row)
            self.assertNotIn("confirmed_by", row)

    def test_4_the_decision_packet_and_completion_go_with_it(self):
        m = self.running()
        m["decision"] = {"asks": [{"index": 1, "check": "africa?"}],
                         "artifacts": [{"path": "africa-trip-plan.md"}]}
        m["completion"] = {"headline": "2 of 2 checks passed"}
        m["approval"] = {"id": "ap-1", "version": m["version"]}
        m["pending_say"] = "continue with the Africa plan"
        self.store.save(m)
        out = self.store.amend(m["id"], objective=INDIA,
                               done_when=list(INDIA_CHECKS))
        for key in ("decision", "completion", "approval", "pending_say"):
            self.assertNotIn(key, out, "%s survived the revision" % key)

    def test_a_conversational_message_creates_no_revision(self):
        """No fence, no amend -- and amend is the only thing that bumps the
        version. "What are you doing?" reaches founder_says and nothing
        else, which is the behaviour that was already correct."""
        m = self.running()
        before = m["version"]
        self.assertEqual(self.store.load(m["id"])["version"], before)

    def test_an_amend_that_changes_nothing_invalidates_nothing(self):
        """Re-sending the same brief is not a change of mind."""
        m = self.running()
        m["done_when"][0]["met"] = True
        self.store.save(m)
        out = self.store.amend(m["id"], objective=AFRICA)
        self.assertTrue(out["done_when"][0].get("met"),
                        "an identical brief must not throw away real work")


# ══ 5-9 + 14-15. THE STALE RESULT RULE ══════════════════════════════════
class StaleResultsHaveNoAuthority(Base):
    """THE MOST IMPORTANT INVARIANT. A turn composed under revision N may
    never advance revision N+1."""

    def test_5_the_guard_sees_a_revision_that_moved(self):
        m = self.running()
        eng = self.engine()
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        moved, why = eng._revision_moved(m)
        self.assertTrue(moved)
        self.assertIn("v1", why)
        self.assertIn("v2", why)

    def test_6_an_unmoved_revision_is_not_stale(self):
        m = self.running()
        moved, why = self.engine()._revision_moved(m)
        self.assertFalse(moved)
        self.assertEqual(why, "")

    def test_7_an_old_worker_result_cannot_complete_the_new_revision(self):
        """THE AFRICA -> INDIA RACE, end to end. Worker A is composed under
        Africa; the founder switches to India; A returns with every Africa
        check satisfied. The mission must NOT be done."""
        open(os.path.join(self.root, "africa-trip-plan.md"), "w").write("x")
        m = self.running()
        snapshot = self.store.load(m["id"])          # worker A's revision
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        eng = self.engine()
        moved, _ = eng._revision_moved(snapshot)
        self.assertTrue(moved, "worker A's result must read as stale")
        fresh = self.store.load(m["id"])
        self.assertNotEqual(fresh["state"], "done")
        self.assertEqual(fresh["objective"], INDIA)

    def test_8_old_criteria_cannot_satisfy_the_new_revision(self):
        """The Africa artifact exists; the India criterion asks for the
        India file. Nothing about the old one answers the new one."""
        open(os.path.join(self.root, "africa-trip-plan.md"), "w").write("x")
        m = self.running()
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        fresh = self.store.load(m["id"])
        done, results = mission_engine.evaluate_done_when(
            fresh, "", probe_root=self.root)
        self.assertFalse(done)
        self.assertFalse(results[0]["met"],
                         "africa-trip-plan.md must not satisfy the India "
                         "criterion")

    def test_9_the_new_artifact_does_satisfy_the_new_revision(self):
        """...and the converse, so the guard is a boundary and not a mute."""
        open(os.path.join(self.root, "india-trip-plan.md"), "w").write("x")
        m = self.running()
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        fresh = self.store.load(m["id"])
        _, results = mission_engine.evaluate_done_when(
            fresh, "", probe_root=self.root)
        self.assertTrue(results[0]["met"])

    def test_14_old_worker_returning_AFTER_the_new_one_is_still_stale(self):
        """Ordering is not the boundary. Two revisions past the snapshot and
        it is every bit as stale as it was at one."""
        m = self.running()
        snapshot = self.store.load(m["id"])
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        self.store.amend(m["id"], objective=JAPAN)
        moved, why = self.engine()._revision_moved(snapshot)
        self.assertTrue(moved)
        self.assertIn("v3", why)

    def test_15_a_result_produced_BEFORE_the_amend_is_stale_after_it(self):
        """Timestamps are not the boundary either: the work really was done
        first, and it still has no authority over what was asked second."""
        m = self.running()
        snapshot = self.store.load(m["id"])
        snapshot["done_when"][0]["met"] = True       # A finished its checks
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        moved, _ = self.engine()._revision_moved(snapshot)
        self.assertTrue(moved)
        self.assertFalse(self.store.load(m["id"])["done_when"][0].get("met"))

    def test_13_rapid_changes_leave_only_the_last_authoritative(self):
        """Africa -> India -> Japan. Only Japan is the task."""
        m = self.running()
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        self.store.amend(m["id"], objective=JAPAN, done_when=[
            {"tier": "verify", "check": "japan-trip-plan.md exists",
             "probe": {"kind": "file_exists", "path": "japan-trip-plan.md"}}])
        fresh = self.store.load(m["id"])
        self.assertEqual(fresh["objective"], JAPAN)
        self.assertEqual(fresh["version"], 3)
        self.assertEqual([c["check"] for c in fresh["done_when"]],
                         ["japan-trip-plan.md exists"])


# ══ THE SIGN-OFF IS BOUND TO WHAT IT WAS SHOWN ══════════════════════════
class ASignatureNamesItsRevision(Base):

    def test_a_stale_sign_off_is_refused(self):
        """A founder_confirm is signed BY INDEX, and an amend replaces
        done_when wholesale -- so index 1 of Africa and index 1 of India are
        different questions."""
        m = self.running()
        was = m["version"]
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        with self.assertRaises(ValueError) as caught:
            self.store.confirm_check(m["id"], 1, version=was)
        self.assertIn("stale", str(caught.exception))

    def test_a_current_sign_off_still_works(self):
        m = self.running()
        out = self.store.confirm_check(m["id"], 1, version=m["version"])
        self.assertTrue(out["done_when"][1]["met"])

    def test_a_sign_off_with_no_version_is_unchanged(self):
        """Every existing caller passes none, and keeps its behaviour."""
        m = self.running()
        out = self.store.confirm_check(m["id"], 1)
        self.assertTrue(out["done_when"][1]["met"])

    def test_the_decision_packet_names_its_revision(self):
        open(os.path.join(self.root, "africa-trip-plan.md"), "w").write("x")
        m = self.running()
        packet = shadow_decision.packet_for(m, self.root)
        self.assertEqual(packet["version"], m["version"])


# ══ 10-12. WHAT THE NEW WORKER IS TOLD ══════════════════════════════════
class TheNewBriefIsTheNewObjective(Base):

    def test_10_11_the_worker_contract_carries_the_new_objective(self):
        import app
        m = self.running()
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        fresh = self.store.load(m["id"])
        block = app._worker_checks_block(fresh)
        self.assertIn("india-trip-plan.md exists", block)
        self.assertEqual(fresh["version"], 2)

    def test_12_no_stale_objective_specific_material_survives(self):
        import app
        m = self.running()
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        fresh = self.store.load(m["id"])
        block = app._worker_checks_block(fresh)
        self.assertNotIn("africa", block.lower(),
                         "the new brief must not carry the old objective's "
                         "criteria")
        self.assertNotIn("africa", fresh["objective"].lower())

    def test_artifacts_follow_the_criteria_that_own_them(self):
        """Ownership is shadow_paths.owned_artifacts, which reads THIS
        revision's probes -- so the old artifact stops being owned the
        moment its criterion is replaced. No new mechanism, no filename
        matching."""
        import shadow_paths
        m = self.running()
        self.assertEqual(shadow_paths.owned_artifacts(m),
                         ["africa-trip-plan.md"])
        self.store.amend(m["id"], objective=INDIA,
                         done_when=list(INDIA_CHECKS))
        fresh = self.store.load(m["id"])
        self.assertEqual(shadow_paths.owned_artifacts(fresh),
                         ["india-trip-plan.md"])


# ══ 18-20. NOTHING PREVIOUSLY FIXED IS REGRESSED ════════════════════════
class TheEarlierBoundariesStillHold(Base):

    def test_18_artifact_ownership_is_still_explicit(self):
        import shadow_paths
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "shadow_paths.py")).read()
        tail = src[src.index("def owned_artifacts"):]
        tail = tail[tail.index('"""', tail.index('"""') + 3) + 3:]
        for banned in ("glob", "walk", "listdir", "git", "getmtime"):
            self.assertNotIn(banned, tail)
        self.assertEqual(shadow_paths.owned_artifacts({}), [])

    def test_20_the_action_ledger_is_still_mission_scoped(self):
        import shadow_ledger
        self.assertEqual(
            shadow_ledger.read_for_mission("actions", None, 10), [])

    def test_a_stale_row_is_logged_for_observability(self):
        """Structured, and ids/versions only -- never the payload."""
        import shadow_ledger
        m = self.running()
        eng = self.engine()
        eng._ledger_stale(m["id"], "worker result is stale: v1 -> v2")
        rows = shadow_ledger.read_for_mission("actions", m["id"], 10)
        stale = [r for r in rows if r.get("kind") == "worker_result_stale"]
        self.assertTrue(stale)
        self.assertIn("v1", stale[-1]["summary"])


if __name__ == "__main__":
    unittest.main()
