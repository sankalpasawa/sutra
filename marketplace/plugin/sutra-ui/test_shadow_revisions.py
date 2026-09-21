#!/usr/bin/env python3
"""THE REVISION LEDGER (founder, 2026-09-21).

WHAT IT IS FOR. `_invalidate_for_revision` already strips every verdict the
previous objective earned -- that part was right and is asserted elsewhere.
What it did not do was leave any trace, so a founder who redirected an Africa
trip to India watched their Africa question disappear between two renders
with nothing said. "Outdated" and "never happened" are different statements
and the founder is owed the first one.

THE LEDGER IS FOR THE SCREEN AND NOTHING ELSE. `revisions` is written here
and read by exactly one function, shadowRevisionsHtml. No loop, decision,
verdict, probe or completion consults it, which is what keeps it from
becoming a second source of truth a mission could complete against. The
tests below assert both halves: that it records what was superseded, and
that the live record is unaffected by its presence.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_revisions.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import providers
import mission_engine
from mission_engine import MissionStore


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def africa(self, state="running"):
        m = self.store.create(
            "Plan a personal trip to Africa for 10 days.", "research",
            target_mode="new", target_session="sess-1",
            done_when=[
                {"tier": "founder_confirm",
                 "check": "The Africa itinerary is feasible for 10 days."},
                {"tier": "judge", "check": "Every Africa day has lodging."}])
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        m = self.store.load(m["id"])
        m["turns_used"] = 4
        m["done_when"][0]["met"] = True
        m["done_when"][0]["confirmed_by"] = "founder"
        m["decision"] = {"question": "Is the Africa itinerary feasible?"}
        m["state"] = state
        if state == "paused":
            m["pause_reason"] = "founder_confirm"
        self.store.save(m)
        return m["id"]

    def india(self, mid):
        return self.store.amend(
            mid, objective="Plan a personal trip to India for 10 days.",
            done_when=[{"tier": "founder_confirm",
                        "check": "The India itinerary is feasible."}])


class TestWhatIsRecorded(Base):
    def test_the_superseded_objective_is_kept(self):
        """THE SNAPSHOT IS OF THE OLD REVISION. amend applies the new fields
        BEFORE it invalidates, so a ledger built from `m` at that moment
        would record the new objective as the abandoned one -- which is the
        bug this test exists to have caught."""
        m = self.india(self.africa())
        rows = m["revisions"]
        self.assertEqual(len(rows), 1)
        self.assertIn("Africa", rows[0]["objective"])
        self.assertNotIn("India", rows[0]["objective"])

    def test_the_superseded_checks_are_kept(self):
        rows = self.india(self.africa())["revisions"]
        checks = [c["check"] for c in rows[0]["checks"]]
        self.assertEqual(len(checks), 2)
        self.assertTrue(all("Africa" in c for c in checks), checks)

    def test_the_old_version_number_is_kept(self):
        rows = self.india(self.africa())["revisions"]
        self.assertEqual(rows[0]["version"], 1)

    def test_a_signature_is_recorded_as_having_been_given(self):
        """The row says the founder HAD signed it, which is true and is why
        the screen can say the signature no longer stands. It is a record of
        what happened, never a live flag -- see the live-record tests."""
        rows = self.india(self.africa())["revisions"]
        signed = [c for c in rows[0]["checks"] if c["met"]]
        self.assertEqual(len(signed), 1)
        self.assertIn("Africa", signed[0]["check"])


class TestTheLiveRecordIsUnaffected(Base):
    def test_the_live_checks_are_only_the_new_ones(self):
        m = self.india(self.africa())
        live = [c["check"] for c in m["done_when"]]
        self.assertEqual(live, ["The India itinerary is feasible."])

    def test_no_live_check_carries_a_verdict_from_the_old_revision(self):
        m = self.india(self.africa())
        for c in m["done_when"]:
            for key in ("met", "judged", "confirmed_by", "confirmed_at"):
                self.assertNotIn(key, c, "%s survived the revision" % key)

    def test_the_stale_decision_packet_is_gone(self):
        m = self.india(self.africa())
        self.assertIsNone(m.get("decision"))

    def test_a_running_task_keeps_running(self):
        """The founder's acceptance case: the conversation CONTINUES from
        the new objective rather than stopping for a fresh Start."""
        m = self.india(self.africa("running"))
        self.assertEqual(m["state"], "running")

    def test_a_task_parked_on_a_signature_is_released(self):
        """Changing the task IS the founder's answer to the question that
        parked it, so the pause it earned is not a pause the new revision
        is in."""
        m = self.india(self.africa("paused"))
        self.assertEqual(m["state"], "running")
        self.assertIsNone(m.get("pause_reason"))

    def test_the_budget_already_spent_stays_spent(self):
        m = self.india(self.africa())
        self.assertEqual(m["turns_used"], 4)

    def test_the_version_advances(self):
        m = self.india(self.africa())
        self.assertEqual(m["version"], 2)


class TestTheLedgerIsBounded(Base):
    def test_it_keeps_only_the_last_few_revisions(self):
        """A founder who changes direction repeatedly gets the recent ones.
        The record is not an archive of every abandoned objective."""
        mid = self.africa()
        for n in range(mission_engine.MAX_REVISIONS + 4):
            self.store.amend(mid, objective="Objective %d" % n,
                             done_when=[{"tier": "founder_confirm",
                                         "check": "check %d" % n}])
        rows = self.store.load(mid)["revisions"]
        self.assertEqual(len(rows), mission_engine.MAX_REVISIONS)
        # the ones kept are the LATEST, so the newest superseded objective
        # is the one immediately before the live one
        self.assertIn("Objective %d" % (mission_engine.MAX_REVISIONS + 2),
                      rows[-1]["objective"])

    def test_an_amend_that_changes_nothing_records_nothing(self):
        mid = self.africa()
        before = self.store.load(mid)
        self.store.amend(mid, objective=before["objective"],
                         done_when=before["done_when"])
        self.assertIsNone(self.store.load(mid).get("revisions"))


class TestItIsInertState(Base):
    def test_nothing_in_the_engine_reads_the_ledger(self):
        """The guard that stops `revisions` becoming a second source of
        truth a mission could complete against. One writer, one reader, and
        the reader is the front end."""
        src = Path(__file__).resolve().parent / "mission_engine.py"
        body = src.read_text(encoding="utf-8")
        touches = [ln.strip() for ln in body.splitlines()
                   if 'revisions' in ln and 'MAX_REVISIONS' not in ln
                   and not ln.strip().startswith("#")]
        # THE RULE IS ABOUT VERDICTS, NOT ABOUT MENTIONS. `revisions` may be
        # DESCRIBED -- completion_summary reads it to say "this replaced an
        # earlier plan", which is a sentence for the founder and cannot
        # settle anything. What it must never do is feed a check, a verdict,
        # a probe or the done decision. These are the only three sites, and
        # each is named so a fourth has to be argued for here.
        allowed = (
            'm["revisions"]',                       # the write, in _invalidate
            'm.get("revisions")',                   # the read-modify of it
            'mission.get("revisions")',             # completion_summary: history
        )
        for ln in touches:
            self.assertTrue(any(a in ln for a in allowed),
                            "unexpected reader of the revision ledger: %s" % ln)

    def test_the_ledger_cannot_satisfy_a_check(self):
        """The property the mention-guard above is a proxy for: a mission
        carrying a fat revision history still completes on its OWN checks."""
        mid = self.africa()
        self.india(mid)
        m = self.store.load(mid)
        self.assertTrue(m["revisions"], "no history to tempt the evaluator")
        results = [{"check": c["check"], "tier": c["tier"], "met": False}
                   for c in m["done_when"]]
        c = mission_engine.completion_summary(m, results)
        self.assertEqual(c["completed"], [],
                         "a superseded verdict satisfied a live check")
        self.assertEqual(len(c["remains"]), len(m["done_when"]))

    def test_completion_is_dropped_so_an_amended_task_is_not_finished(self):
        mid = self.africa()
        m = self.store.load(mid)
        m["completion"] = {"headline": "3 of 3 checks passed"}
        self.store.save(m)
        self.assertIsNone(self.india(mid).get("completion"))



class TestTheCompletionDescribesTheFinalRevision(Base):
    """The founder's rule: "if the user changed Africa -> India, the
    completion summary must describe INDIA. Do not summarize abandoned work
    as though it were the final result." """

    def _completed(self, mid):
        m = self.store.load(mid)
        results = [{"check": c["check"], "tier": c["tier"], "met": True}
                   for c in m["done_when"]]
        return mission_engine.completion_summary(m, results)

    def test_the_summary_names_the_final_objective(self):
        mid = self.africa()
        self.india(mid)
        c = self._completed(mid)
        self.assertIn("India", c["objective"])
        self.assertNotIn("Africa", c["objective"])

    def test_completed_lines_come_from_the_final_checks_only(self):
        mid = self.africa()
        self.india(mid)
        c = self._completed(mid)
        self.assertTrue(c["completed"], "nothing was reported as completed")
        for line in c["completed"]:
            self.assertNotIn("Africa", line, line)

    def test_the_abandoned_objective_is_reported_as_history(self):
        mid = self.africa()
        self.india(mid)
        c = self._completed(mid)
        self.assertEqual(c["revised"], 1)
        self.assertIn("Africa", c["was"])

    def test_an_unrevised_task_reports_no_history(self):
        mid = self.africa()
        c = self._completed(mid)
        self.assertEqual(c["revised"], 0)
        self.assertEqual(c["was"], "")

    def test_what_remains_is_the_unmet_checks(self):
        mid = self.africa()
        m = self.store.load(mid)
        results = [{"check": m["done_when"][0]["check"],
                    "tier": "founder_confirm", "met": True},
                   {"check": m["done_when"][1]["check"],
                    "tier": "judge", "met": False}]
        c = mission_engine.completion_summary(m, results)
        self.assertEqual(len(c["completed"]), 1)
        self.assertEqual(len(c["remains"]), 1)
        self.assertIn("lodging", c["remains"][0])

    def test_the_summary_reads_no_worker_transcript(self):
        """Built from the record, never concatenated out of worker messages
        -- the one construction the founder ruled out, because a worker that
        narrated a plan it then abandoned would dictate the result."""
        mid = self.africa()
        self.india(mid)
        m = self.store.load(mid)
        results = [{"check": c["check"], "tier": c["tier"], "met": True}
                   for c in m["done_when"]]
        loud = "I built a wonderful AFRICA itinerary with 12 stops."
        c = mission_engine.completion_summary(m, results, transcript=loud,
                                              outcome=loud)
        self.assertNotIn("Africa", " ".join(c["completed"]))
        self.assertNotIn("Africa", " ".join(c["remains"]))
        self.assertNotIn("Africa", c["objective"])


if __name__ == "__main__":
    unittest.main()
