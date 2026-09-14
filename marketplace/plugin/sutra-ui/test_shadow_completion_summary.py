"""A finished mission must SAY what was done and why it counts as done.

THE GAP (founder, 2026-09-15). Completion spoke to the founder twice and
neither line was legible:

    feed row      why_now = "mission done", which 14-needs-you.js renders
                  as "done - result inside"
    the inside    result_excerpt = transcript[:150] + " ... " + [-250:],
                  cut out of `live + json.dumps(doc)` (evidence_text), so
                  the head is mid-`{"role": "assistant", "text": ...}` far
                  more often than it is a sentence

And the fact the founder actually wanted -- WHICH criteria were satisfied,
and BY WHAT -- already existed: `results`, the evaluation the loop runs on
every turn, passed straight through _complete and was dropped.

WHAT IS PINNED HERE:

  1. artifact_context      quotes a match in its own words, never invents
                           one, and never trims into the match itself
  2. completion_summary    tier -> how, deterministic, evidence only where
                           there is evidence, no verdict it was not given
  3. _complete             stamps it, and result_excerpt still exists
  4. settle()              the founder-confirm path stamps the same thing
  5. terminal_why          the feed row carries the headline, and failed /
                           stopped / pre-field records are byte-identical

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_completion_summary.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
import shadow_runner
from mission_engine import (artifact_context, completion_summary,
                            MissionEngine, MissionStore)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ------------------------------------------------------------------------
# 1. artifact_context -- the quote, and what it refuses to do
# ------------------------------------------------------------------------
class TestArtifactContext(unittest.TestCase):

    def test_01_quotes_the_match_in_its_own_words(self):
        text = ("I ran the suite and it came back EMI-OK across all four "
                "tenants, so stage 3 is clear.")
        out = artifact_context(text, "EMI-OK")
        self.assertIn("EMI-OK", out)
        self.assertIn("came back", out, "the words around it came too")

    def test_02_collapses_the_json_blob_into_one_line(self):
        """evidence_text hands over `live + json.dumps(doc)`. A quote with
        raw newlines and runs of spaces in it reads as machine noise."""
        text = 'a\n\n  b   {"role": "assistant"}\tEMI-OK\n\n  done'
        out = artifact_context(text, "EMI-OK")
        self.assertNotIn("\n", out)
        self.assertNotIn("  ", out, "runs of whitespace collapsed")
        self.assertIn("EMI-OK", out)

    def test_03_no_match_is_empty_not_a_guess(self):
        """The honest answer to "where was it found" when it was not."""
        self.assertEqual(artifact_context("nothing here", "EMI-OK"), "")
        self.assertEqual(artifact_context("", "EMI-OK"), "")
        self.assertEqual(artifact_context("text", ""), "")
        self.assertEqual(artifact_context(None, None), "")

    def test_04_never_trims_into_the_match(self):
        """The window cut drops the partial token it lands in. It must not
        take the match with it -- a quote that no longer contains what it
        claims to quote is worse than no quote."""
        # one unbroken 200-char token right before the match: the leading
        # trim has no boundary to use that is left of the match
        text = ("x" * 200) + " EMI-OK tail words here"
        out = artifact_context(text, "EMI-OK", window=40)
        self.assertIn("EMI-OK", out)
        # and the same from the right
        text2 = "lead words EMI-OK " + ("y" * 200)
        self.assertIn("EMI-OK", artifact_context(text2, "EMI-OK", window=40))

    def test_05_marks_where_it_cut(self):
        long = ("alpha bravo charlie delta echo foxtrot " * 20)
        out = artifact_context(long + " EMI-OK " + long, "EMI-OK", window=40)
        self.assertTrue(out.startswith("…"), "cut at the head is marked")
        self.assertTrue(out.endswith("…"), "cut at the tail is marked")

    def test_06_a_short_transcript_is_returned_whole(self):
        out = artifact_context("just EMI-OK here", "EMI-OK")
        self.assertEqual(out, "just EMI-OK here")
        self.assertNotIn("…", out, "nothing was cut, so nothing is marked")


# ------------------------------------------------------------------------
# 2. completion_summary -- pure, and it never out-claims the evaluation
# ------------------------------------------------------------------------
class TestCompletionSummary(unittest.TestCase):

    def mission(self, checks, **over):
        m = {"objective": "ship the EMI check", "turns_used": 5,
             "max_turns": 20, "target_session": "sess-9", "done_when": checks}
        m.update(over)
        return m

    def test_07_every_tier_says_who_satisfied_it(self):
        checks = [
            {"tier": "contains_artifact", "check": "EMI-OK"},
            {"tier": "verify", "check": "pytest test_emi.py passes"},
            {"tier": "founder_confirm", "check": "the copy reads right",
             "met": True, "confirmed_by": "founder",
             "confirmed_at": "2026-09-15T01:00:00Z"},
        ]
        m = self.mission(checks)
        transcript = "the run came back EMI-OK on every tenant"
        done, results = mission_engine.evaluate_done_when(
            m, transcript, verifier=lambda c: True)
        self.assertTrue(done, "fixture sanity: this mission is complete")
        c = completion_summary(m, results, transcript)

        self.assertEqual(c["headline"], "3 of 3 checks passed")
        self.assertEqual((c["checks_met"], c["checks_total"]), (3, 3))
        hows = [r["how"] for r in c["checks"]]
        self.assertEqual(hows, ["found in the chat",
                                "Shadow ran this check and it passed",
                                "you confirmed it"])
        self.assertEqual(c["objective"], "ship the EMI check")
        self.assertEqual((c["turns_used"], c["max_turns"]), (5, 20))
        self.assertEqual(c["chat"], "sess-9")

    def test_08_only_the_artifact_tier_carries_a_quote(self):
        """`verify` ran a check, it did not find a string; `founder_confirm`
        is a person's word. Quoting the transcript at either would be
        evidence for a claim the tier never made."""
        checks = [
            {"tier": "contains_artifact", "check": "EMI-OK"},
            {"tier": "verify", "check": "EMI-OK"},
            {"tier": "founder_confirm", "check": "EMI-OK", "met": True},
        ]
        m = self.mission(checks)
        _done, results = mission_engine.evaluate_done_when(
            m, "the run said EMI-OK", verifier=lambda c: True)
        rows = completion_summary(m, results, "the run said EMI-OK")["checks"]
        self.assertIn("evidence", rows[0])
        self.assertNotIn("evidence", rows[1])
        self.assertNotIn("evidence", rows[2])

    def test_09_a_confirmation_carries_who_and_when(self):
        checks = [{"tier": "founder_confirm", "check": "looks right",
                   "met": True, "confirmed_by": "founder",
                   "confirmed_at": "2026-09-15T01:00:00Z"}]
        m = self.mission(checks)
        _d, results = mission_engine.evaluate_done_when(m, "")
        row = completion_summary(m, results, "")["checks"][0]
        self.assertEqual(row["by"], "founder")
        self.assertEqual(row["at"], "2026-09-15T01:00:00Z")

    def test_10_an_unmet_check_is_reported_unmet(self):
        """The summary DESCRIBES the evaluation, it does not re-run or
        improve it. An unmet row must never read as satisfied."""
        checks = [{"tier": "contains_artifact", "check": "EMI-OK"},
                  {"tier": "contains_artifact", "check": "NEVER-SAID"}]
        m = self.mission(checks)
        _d, results = mission_engine.evaluate_done_when(m, "EMI-OK")
        c = completion_summary(m, results, "EMI-OK")
        self.assertEqual(c["headline"], "1 of 2 checks passed")
        self.assertTrue(c["checks"][0]["met"])
        self.assertFalse(c["checks"][1]["met"])
        self.assertEqual(c["checks"][1]["how"], "still outstanding")
        self.assertNotIn("evidence", c["checks"][1])

    def test_11_an_artifact_it_cannot_locate_keeps_the_verdict(self):
        """Contrived but reachable: the verdict says met, the quote cannot
        be built. Report the check without evidence -- never drop the row,
        never invent the quote."""
        m = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        results = [{"tier": "contains_artifact", "check": "EMI-OK",
                    "met": True}]
        row = completion_summary(m, results, transcript="")["checks"][0]
        self.assertTrue(row["met"])
        self.assertNotIn("evidence", row)

    def test_12_no_checks_at_all_says_so(self):
        c = completion_summary(self.mission([]), [], "")
        self.assertEqual(c["headline"], "no check was set")
        self.assertEqual(c["checks"], [])

    def test_13_it_is_json_serialisable(self):
        """It is stamped on the mission file and served to the panel."""
        m = self.mission([{"tier": "verify", "check": "x"}])
        _d, results = mission_engine.evaluate_done_when(
            m, "", verifier=lambda c: True)
        json.dumps(completion_summary(m, results, ""))


# ------------------------------------------------------------------------
# 3 + 4. the engine stamps it, on both completion paths
# ------------------------------------------------------------------------
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self.says = []

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def mission(self, checks, max_turns=4):
        m = self.store.create("get the EMI check green", "fix",
                              target_session="sess-1", done_when=checks)
        self.store.transition(m["id"], "brief_confirm", "b")
        m = self.store.transition(m["id"], "running", "admitted")
        m["max_turns"] = max_turns
        self.store.save(m)
        return m["id"]

    def engine(self, transcript="", verifier=None):
        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        return MissionEngine(self.store, sayer, waiter,
                             lambda m: transcript, verifier)


class TestTheEngineStampsIt(Base):

    TRANSCRIPT = ('{"role": "assistant", "text": "..."} ' + ("z" * 300)
                  + " I re-ran it and the suite reports EMI-OK for every "
                    "tenant, so the check is green.")

    def test_14_a_completed_mission_carries_the_summary(self):
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        m = run(self.engine(transcript=self.TRANSCRIPT).run_mission(mid))
        self.assertEqual(m["state"], "done")
        c = m.get("completion")
        self.assertIsNotNone(c, "a done mission must say what it did")
        self.assertEqual(c["headline"], "1 of 1 checks passed")
        self.assertEqual(c["objective"], "get the EMI check green")
        self.assertEqual(c["checks"][0]["how"], "found in the chat")
        self.assertEqual(c["chat"], "sess-1")
        self.assertEqual(c["turns_used"], m["turns_used"],
                         "the budget it reports is the budget it spent")

    def test_15_the_quote_is_the_chats_words_not_the_json(self):
        """The whole point. result_excerpt on this same transcript opens
        mid-json; the summary's evidence is a sentence."""
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        m = run(self.engine(transcript=self.TRANSCRIPT).run_mission(mid))
        ev = m["completion"]["checks"][0]["evidence"]
        self.assertIn("EMI-OK", ev)
        self.assertIn("the suite reports", ev)
        self.assertNotIn('{"role"', ev, "the json blob is not the result")
        self.assertTrue(m["result_excerpt"].startswith('{"role"'),
                        "fixture sanity: the old excerpt really does")

    def test_16_result_excerpt_survives(self):
        """goal_lifecycle._record_attempt_memory and the overlay's mission
        card both read it. This change adds a field, it replaces none."""
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        m = run(self.engine(transcript=self.TRANSCRIPT).run_mission(mid))
        self.assertIn("result_excerpt", m)
        self.assertTrue(m["result_excerpt"])

    def test_17_it_is_on_disk_not_just_in_the_return(self):
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        run(self.engine(transcript=self.TRANSCRIPT).run_mission(mid))
        self.assertIn("completion", self.store.load(mid))

    def test_18_the_settle_path_stamps_the_same_thing(self):
        """A mission finished by the founder's own confirmation is the one
        most likely to be read, and it completes through settle(), not
        through the loop."""
        mid = self.mission([
            {"tier": "contains_artifact", "check": "EMI-OK"},
            {"tier": "founder_confirm", "check": "the copy reads right"},
        ])
        eng = self.engine(transcript=self.TRANSCRIPT)
        m = run(eng.run_mission(mid))
        self.assertEqual((m["state"], m.get("pause_reason")),
                         ("paused", "founder_confirm"),
                         "fixture sanity: it parked at the boundary")
        self.store.confirm_check(mid, 1, by="founder")
        m = eng.settle(mid)
        self.assertEqual(m["state"], "done")
        c = m["completion"]
        self.assertEqual(c["headline"], "2 of 2 checks passed")
        self.assertEqual(c["checks"][1]["how"], "you confirmed it")
        self.assertEqual(c["checks"][1]["by"], "founder")

    def test_19_an_unfinished_mission_has_no_summary(self):
        """The field is the record of a completion. Anything that did not
        complete must not carry one -- reading it is how the panel decides
        whether to draw the block at all."""
        mid = self.mission([{"tier": "contains_artifact", "check": "NEVER"}],
                           max_turns=2)
        m = run(self.engine(transcript="nothing matching here"
                            ).run_mission(mid))
        self.assertNotEqual(m["state"], "done")
        self.assertNotIn("completion", m)

    def test_20_the_ledger_row_leads_with_the_headline(self):
        import shadow_ledger
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        run(self.engine(transcript=self.TRANSCRIPT).run_mission(mid))
        rows = [json.loads(l) for l
                in open(shadow_ledger._path("actions"), encoding="utf-8")
                if mid in l]
        result = [r for r in rows if r.get("kind") == "result"]
        self.assertTrue(result, "the result row is still written")
        self.assertTrue(result[-1]["summary"].startswith("1 of 1 checks"),
                        "an audit row must not open mid-json")


# ------------------------------------------------------------------------
# 5. the feed row
# ------------------------------------------------------------------------
class TestTheFeedRowSaysWhatPassed(unittest.TestCase):

    def test_21_done_carries_the_headline(self):
        m = {"state": "done",
             "completion": {"headline": "3 of 3 checks passed"}}
        self.assertEqual(shadow_runner.terminal_why(m),
                         "3 of 3 checks passed")

    def test_22_failed_and_stopped_are_unchanged(self):
        self.assertEqual(shadow_runner.terminal_why({"state": "failed"}),
                         "mission failed")
        self.assertEqual(shadow_runner.terminal_why({"state": "stopped"}),
                         "mission stopped")

    def test_23_a_record_written_before_the_field_is_unchanged(self):
        """Every mission already on disk. The old line is the fallback, so
        nothing that completed before this change renders differently."""
        self.assertEqual(shadow_runner.terminal_why({"state": "done"}),
                         "mission done")
        self.assertEqual(
            shadow_runner.terminal_why({"state": "done", "completion": {}}),
            "mission done")

    def test_24_a_stopped_mission_never_borrows_a_headline(self):
        """Defensive: `state` decides, not the presence of the field."""
        m = {"state": "stopped", "completion": {"headline": "2 of 2 passed"}}
        self.assertEqual(shadow_runner.terminal_why(m), "mission stopped")


if __name__ == "__main__":
    unittest.main()
