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
  6. completion_text       the same account as plain text, and the goal
                           memory records THAT instead of the json blob --
                           with the excerpt still the fallback for every
                           attempt that finished before the field existed
  7. last_worker_message   WHAT was done, in the worker's own last words:
                           quoted never composed, Shadow's own turns
                           inadmissible, trimmed at a boundary, "" when
                           there is nothing to quote
  8. the outcome end to end  stamped by the same _complete on both
                           completion paths, absent for every caller that
                           injects no reader, and a reader that raises
                           costs the line and not the mission

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_completion_summary.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import goal_lifecycle
import mission_engine
import providers
import shadow_runner
from goal_store import GoalStore
from mission_engine import (artifact_context, completion_summary,
                            completion_text, MissionEngine, MissionScheduler,
                            MissionStore)


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


# ------------------------------------------------------------------------
# 6. completion_text -- the same account for a reader with no pane, and
#    the goal memory that was still recording the json blob
# ------------------------------------------------------------------------
class TestCompletionText(unittest.TestCase):
    """The plain-text twin of 16-shadow-home.js shadowCompletionText."""

    SUMMARY = {
        "objective": "ship the EMI check",
        "headline": "2 of 3 checks passed",
        "turns_used": 5, "max_turns": 20,
        "checks": [
            {"check": "EMI-OK", "tier": "contains_artifact", "met": True,
             "how": "found in the chat",
             "evidence": "the suite reports EMI-OK for every tenant"},
            {"check": "the copy reads right", "tier": "founder_confirm",
             "met": True, "how": "you confirmed it", "by": "founder"},
            {"check": "pytest passes", "tier": "verify", "met": False,
             "how": "still outstanding"},
        ],
    }

    def test_25_it_leads_with_the_headline_and_the_budget(self):
        out = completion_text(self.SUMMARY)
        self.assertTrue(out.startswith("Done — 2 of 3 checks passed"),
                        "a reader must not open mid-json: %r" % out[:60])
        self.assertIn("ship the EMI check", out)
        self.assertIn("5 of 20 turns used.", out)

    def test_26_every_check_carries_its_verdict_and_its_how(self):
        out = completion_text(self.SUMMARY)
        self.assertIn("✓ EMI-OK — found in the chat", out)
        self.assertIn("✓ the copy reads right — you confirmed it · founder",
                      out, "who confirmed rides the how line")
        self.assertIn("✗ pytest passes — still outstanding", out,
                      "an outstanding check is shown, not hidden")

    def test_27_evidence_is_quoted_under_the_check_it_proves(self):
        lines = completion_text(self.SUMMARY).split("\n")
        at = next(i for i, l in enumerate(lines) if l.startswith("✓ EMI-OK"))
        self.assertEqual(
            lines[at + 1],
            "    the suite reports EMI-OK for every tenant",
            "the quote is indented under its own check")

    def test_28_it_reaches_no_verdict_of_its_own(self):
        """PURE, and not a second evaluator: `how` and `met` are the
        server's words, copied. A row claiming nothing renders nothing."""
        out = completion_text({"headline": "1 of 1 checks passed",
                               "checks": [{"check": "x", "met": True}]})
        self.assertIn("✓ x", out)
        self.assertNotIn("—  ", out, "no how -> no empty dash")

    def test_29_an_absent_summary_is_empty_not_a_stub(self):
        """The "empty means absent" rule terminal_why already applies, so
        the caller can fall back rather than print a header with no facts."""
        for absent in (None, {}, "", [], 0):
            self.assertEqual(completion_text(absent), "",
                             "%r must read as absent" % (absent,))

    def test_30_it_survives_a_summary_with_no_checks(self):
        out = completion_text({"headline": "no check was set",
                               "turns_used": 2, "max_turns": 4})
        self.assertEqual(out, "Done — no check was set\n2 of 4 turns used.")


class TestTheGoalRemembersWhatWasDone(unittest.TestCase):
    """THE SURFACE THAT WAS LEFT BEHIND. goal_lifecycle._record_attempt_
    memory writes the attempt's `result` into durable goal memory, which
    18-goal-workspace.js renders verbatim under "What I learned". It was
    still recording result_excerpt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.goals = GoalStore()
        self.missions = MissionStore()
        self.says = []

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    #: the shape evidence_text really hands over -- a json dump with the
    #: chat's own sentence buried past the 150-character head cut
    TRANSCRIPT = ('{"role": "assistant", "text": "..."} ' + ("z" * 300)
                  + " I re-ran it and the suite reports EMI-OK for every "
                    "tenant, so the check is green.")

    def _done_attempt(self):
        g = self.goals.create(
            "get the EMI check green", "sess-1",
            done_when=[{"tier": "contains_artifact", "check": "EMI-OK"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))

        async def sayer(mm, text):
            self.says.append(text)
            return True

        async def waiter(mm):
            return True

        eng = MissionEngine(self.missions, sayer, waiter,
                            lambda mm: self.TRANSCRIPT)
        out = run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "done", "fixture sanity")
        return goal_lifecycle.on_attempt_end(out), out

    def _result_rows(self, goal):
        return [r for r in (goal.get("learned") or [])
                if r.get("kind") == "result"]

    def test_31_the_remembered_result_is_the_legible_account(self):
        goal, out = self._done_attempt()
        rows = self._result_rows(goal)
        self.assertEqual(len(rows), 1, "still exactly one result memory")
        text = rows[0]["text"]
        self.assertTrue(text.startswith("Done — 1 of 1 checks passed"),
                        "the goal's memory must not open mid-json: %r"
                        % text[:80])
        self.assertIn("✓ EMI-OK — found in the chat", text)
        self.assertIn("the suite reports EMI-OK", text,
                      "the chat's own sentence, quoted")
        self.assertNotIn('{"role"', text, "the json blob is gone")
        self.assertTrue(out["result_excerpt"].startswith('{"role"'),
                        "and the excerpt field itself is untouched")

    def test_32_a_record_from_before_the_field_falls_back(self):
        """Every attempt already on disk. No completion -> the excerpt, so
        nothing that finished before this shipped is remembered differently.
        """
        g = self.goals.create("outcome", "sess-1")
        goal = goal_lifecycle._record_attempt_memory(
            self.goals, g["id"],
            {"id": "m-old", "state": "done", "objective": "o",
             "turns_used": 1, "max_turns": 2,
             "result_excerpt": '{"role": "assistant"} tail'})
        rows = self._result_rows(goal)
        self.assertEqual([r["text"] for r in rows],
                         ['{"role": "assistant"} tail'])

    def test_33_an_empty_completion_falls_back_too(self):
        """Defensive: a stamped-but-empty field must not beat the excerpt
        and leave the goal remembering nothing at all."""
        g = self.goals.create("outcome", "sess-1")
        goal = goal_lifecycle._record_attempt_memory(
            self.goals, g["id"],
            {"id": "m-x", "state": "done", "completion": {},
             "result_excerpt": "the tail"})
        self.assertEqual([r["text"] for r in self._result_rows(goal)],
                         ["the tail"])

    def test_34_an_attempt_with_no_result_at_all_records_none(self):
        """A blocked attempt never reaches _complete, so it has neither
        field. It must not gain an empty memory row."""
        g = self.goals.create("outcome", "sess-1")
        goal = goal_lifecycle._record_attempt_memory(
            self.goals, g["id"], {"id": "m-b", "state": "blocked",
                                  "block_reason": "budget_exhausted"})
        self.assertEqual(self._result_rows(goal), [])

    def test_35_the_memory_is_bounded(self):
        """record_learned is durable goal state read back into every later
        briefing -- the 800-char cap the excerpt had still applies."""
        g = self.goals.create("outcome", "sess-1")
        goal = goal_lifecycle._record_attempt_memory(
            self.goals, g["id"],
            {"id": "m-l", "state": "done",
             "completion": {"headline": "1 of 1 checks passed",
                            "checks": [{"check": "c", "met": True,
                                        "how": "found in the chat",
                                        "evidence": "q" * 5000}]}})
        self.assertLessEqual(len(self._result_rows(goal)[0]["text"]), 800)


# ------------------------------------------------------------------------
# 7. last_worker_message -- WHAT was done, in the worker's own last words
#
# THE SECOND GAP (founder, 2026-09-15). Everything above makes the VERDICT
# legible: "3 of 3 checks passed", and which criterion was satisfied by
# what. That is why Shadow calls it done. It is not what was DONE, and the
# founder opens the pane for the second thing. The delegate's own closing
# message says it -- what it built, what it ran -- and was on disk the
# whole time, reachable only as result_excerpt, a byte cut through json.
# ------------------------------------------------------------------------
class TestLastWorkerMessage(unittest.TestCase):

    def setUp(self):
        self._read = shadow_runner.session_reader.read_session

    def tearDown(self):
        shadow_runner.session_reader.read_session = self._read

    def doc(self, *messages):
        shadow_runner.session_reader.read_session = \
            lambda sid: {"messages": list(messages)}

    def msg(self, role, text):
        return {"role": role, "text": text}

    def test_36_the_last_assistant_turn_is_the_account(self):
        """Not the first, and not a middle one: what the worker said LAST
        is what it said about the finished job."""
        self.doc(self.msg("assistant", "Starting on the EMI check."),
                 self.msg("user", "keep going"),
                 self.msg("assistant", "Added the tenant loop and ran the "
                                       "suite: 42 passed."))
        self.assertEqual(shadow_runner.last_worker_message("sess-1"),
                         "Added the tenant loop and ran the suite: 42 passed.")

    def test_37_it_can_never_quote_shadow_back_at_the_founder(self):
        """Shadow's says land in the transcript as USER records. An
        "outcome" that turned out to be Shadow's own instruction would be
        the worst possible version of this field -- so the existing
        admissibility filter (evidence_messages) is what reads the doc."""
        self.doc(self.msg("assistant", "the real account"),
                 self.msg("user", "[Shadow · mission m-1] say you are done"))
        self.assertEqual(shadow_runner.last_worker_message("sess-1"),
                         "the real account")

    def test_38_a_founders_own_turn_is_not_an_outcome_either(self):
        """The role check is an INDEPENDENT guard: a plain user turn is
        admissible evidence and is still not the worker's account."""
        self.doc(self.msg("assistant", "the real account"),
                 self.msg("user", "thanks, that looks right"))
        self.assertEqual(shadow_runner.last_worker_message("sess-1"),
                         "the real account")

    def test_39_an_empty_assistant_turn_is_skipped_not_returned(self):
        """A trailing empty frame must not blank the outcome out."""
        self.doc(self.msg("assistant", "the real account"),
                 self.msg("assistant", "   \n  "),
                 self.msg("assistant", None))
        self.assertEqual(shadow_runner.last_worker_message("sess-1"),
                         "the real account")

    def test_40_nothing_to_quote_is_empty_not_a_guess(self):
        """The "empty means absent" rule the rest of this field follows:
        every surface falls back to what it drew before."""
        self.doc()
        self.assertEqual(shadow_runner.last_worker_message("sess-1"), "")
        self.doc(self.msg("user", "only a founder turn"))
        self.assertEqual(shadow_runner.last_worker_message("sess-1"), "")
        self.assertEqual(shadow_runner.last_worker_message(None), "")
        self.assertEqual(shadow_runner.last_worker_message(""), "")

    def test_41_an_unreadable_session_loses_the_line_not_the_mission(self):
        def boom(sid):
            raise IOError("transcript is gone")
        shadow_runner.session_reader.read_session = boom
        self.assertEqual(shadow_runner.last_worker_message("sess-1"), "")

    def test_42_noise_is_collapsed_and_structure_is_kept(self):
        """WHAT THIS PINNED BEFORE, AND WHY IT CHANGED (founder, 2026-09-17).

        This asserted that EVERY run of whitespace, newlines included,
        flattened to one space -- "a quote with runs of newlines and tabs in
        it reads as machine noise". That was right for the only consumer it
        had: the one-line gist above the check list, which quotes this field.

        The DONE card now also renders the same field as MARKDOWN, in the
        Summary block under the verdicts, and markdown is made of line
        breaks: flattening them turns a heading into prose, a list into a
        run-on sentence and a table into rubble. The INTENT recorded here is
        unchanged -- no machine noise -- and it now applies to a field that
        is displayed rather than quoted, so noise and structure are
        separated instead of both being destroyed.

        The gist is unaffected: shadowCompletionHtml flattens this field
        itself before handing it to shadowResultGist, precisely so this
        change cannot move that line (16-shadow-home.js, shadowOutcomeFlat).
        """
        self.doc(self.msg("assistant", "I added\n\n  the loop\tand ran it."))
        out = shadow_runner.last_worker_message("sess-1")
        # noise out: the tab and the interior run are gone
        self.assertNotIn("\t", out)
        self.assertIn("the loop and ran it.", out)
        # structure in: the paragraph break survives
        self.assertIn("I added\n\n", out)

    def test_42b_markdown_structure_survives(self):
        """The case the Summary block exists for: a research answer whose
        headings, list and table must still be markdown when it lands."""
        self.doc(self.msg("assistant",
                          "## Latest\r\n\n\n\n- one   thing\n- two\n\n"
                          "| a | b |\n|---|---|\n| 1 | 2 |   \n"))
        out = shadow_runner.last_worker_message("sess-1")
        self.assertTrue(out.startswith("## Latest"), out[:20])
        self.assertIn("\n- one thing\n- two", out, "list rows kept")
        self.assertIn("|---|---|", out, "the table separator is intact")
        self.assertNotIn("\r", out, "carriage returns are noise")
        self.assertNotIn("\n\n\n", out, "at most one blank line")
        self.assertFalse(out.endswith(" "), "trailing space trimmed")

    def test_42c_leading_indentation_is_kept(self):
        """Indentation is what makes a nested list nested; only INTERIOR
        runs collapse."""
        self.doc(self.msg("assistant", "- top\n  - nested   item\n"))
        out = shadow_runner.last_worker_message("sess-1")
        self.assertIn("\n  - nested item", out)

    def test_43_a_long_message_is_cut_at_a_sentence(self):
        """_prose_tail's lesson at the other end of the string: a cut at
        whatever byte lands on the cap reads as something the worker wrote
        when it is not. A sentence boundary needs no ellipsis, because
        nothing was left mid-thought."""
        # sized off the cap, so raising OUTCOME_CHARS cannot quietly turn
        # this into a test that truncates nothing and asserts nothing
        one = "I rewired the tenant loop and it is green now. "
        body = one * ((shadow_runner.OUTCOME_CHARS // len(one)) + 5)
        self.doc(self.msg("assistant", body))
        out = shadow_runner.last_worker_message("sess-1")
        self.assertLessEqual(len(out), shadow_runner.OUTCOME_CHARS)
        self.assertTrue(out.endswith("green now."),
                        "cut on a sentence: %r" % out[-40:])
        self.assertNotIn("…", out, "nothing was left mid-thought")

    def test_44_with_no_sentence_near_the_cut_it_says_it_was_cut(self):
        # no full stop anywhere, and sized off the cap for the same reason
        body = "word " * ((shadow_runner.OUTCOME_CHARS // 5) + 50)
        self.doc(self.msg("assistant", body))
        out = shadow_runner.last_worker_message("sess-1")
        self.assertLessEqual(len(out), shadow_runner.OUTCOME_CHARS + 1)
        self.assertTrue(out.endswith("…"), "a cut mid-thought is marked")
        self.assertTrue(out.endswith("word…"), "and it cut on a word: %r"
                        % out[-12:])

    def test_45_a_short_message_is_returned_whole(self):
        self.doc(self.msg("assistant", "Done: two files, tests pass."))
        out = shadow_runner.last_worker_message("sess-1")
        self.assertEqual(out, "Done: two files, tests pass.")
        self.assertNotIn("…", out, "nothing was cut, so nothing is marked")


# ------------------------------------------------------------------------
# 8. the outcome reaches the record, the text and the panel
# ------------------------------------------------------------------------
class TestTheSummaryCarriesTheOutcome(Base):

    TRANSCRIPT = TestTheEngineStampsIt.TRANSCRIPT
    ACCOUNT = "Added the tenant loop in emi.py and ran the suite: 42 passed."

    def engine(self, transcript="", verifier=None, outcome_reader=None):
        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        return MissionEngine(self.store, sayer, waiter,
                             lambda m: transcript, verifier,
                             outcome_reader=outcome_reader)

    def test_46_completion_summary_quotes_it_verbatim(self):
        """QUOTED, never composed: the summary does not summarise it,
        shorten it or reword it."""
        m = {"objective": "o", "done_when": [], "turns_used": 1,
             "max_turns": 4}
        c = completion_summary(m, [], "", self.ACCOUNT)
        self.assertEqual(c["outcome"], self.ACCOUNT)
        json.dumps(c)

    def test_47_no_outcome_is_the_shape_that_shipped_before(self):
        """Every existing caller passes three arguments. The field is
        present and empty, which is what lets the panel test `c.outcome`
        and fall through to exactly the markup it drew before."""
        m = {"objective": "o", "done_when": []}
        self.assertEqual(completion_summary(m, [], "")["outcome"], "")
        self.assertEqual(
            completion_summary(m, [], "", None)["outcome"], "")

    def test_48_the_engine_asks_the_reader_and_stamps_the_answer(self):
        asked = []
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])

        def reader(mission):
            asked.append(mission["id"])
            return self.ACCOUNT

        m = run(self.engine(transcript=self.TRANSCRIPT,
                            outcome_reader=reader).run_mission(mid))
        self.assertEqual(m["state"], "done")
        self.assertEqual(asked, [mid],
                         "asked once, for the mission that completed")
        self.assertEqual(m["completion"]["outcome"], self.ACCOUNT)
        self.assertEqual(self.store.load(mid)["completion"]["outcome"],
                         self.ACCOUNT, "and it is on disk, not just returned")

    def test_49_the_verdict_is_untouched_by_the_outcome(self):
        """It DESCRIBES a settled completion. It cannot move a check."""
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        m = run(self.engine(transcript=self.TRANSCRIPT,
                            outcome_reader=lambda mm: "EMI-OK everywhere!"
                            ).run_mission(mid))
        c = m["completion"]
        self.assertEqual(c["headline"], "1 of 1 checks passed")
        self.assertEqual(c["checks"][0]["how"], "found in the chat")
        self.assertIn("the suite reports", c["checks"][0]["evidence"],
                      "the evidence still comes from the transcript")

    def test_50_no_reader_leaves_every_existing_path_unchanged(self):
        """The flag path, and every test that builds an engine without one."""
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        m = run(self.engine(transcript=self.TRANSCRIPT).run_mission(mid))
        self.assertEqual(m["state"], "done")
        self.assertEqual(m["completion"]["outcome"], "")
        self.assertEqual(m["completion"]["headline"], "1 of 1 checks passed")

    def test_51_a_reader_that_raises_cannot_lose_the_completion(self):
        """Guarded the same way on_evaluated is, for the same reason: a
        failure costs the outcome line and nothing else."""
        def boom(mission):
            raise RuntimeError("no transcript")
        mid = self.mission([{"tier": "contains_artifact", "check": "EMI-OK"}])
        m = run(self.engine(transcript=self.TRANSCRIPT,
                            outcome_reader=boom).run_mission(mid))
        self.assertEqual(m["state"], "done")
        self.assertEqual(m["completion"]["outcome"], "")
        self.assertEqual(m["completion"]["headline"], "1 of 1 checks passed")

    def test_52_the_settle_path_carries_it_too(self):
        """A mission the founder's own confirmation finishes is the one
        most likely to be read."""
        mid = self.mission([
            {"tier": "contains_artifact", "check": "EMI-OK"},
            {"tier": "founder_confirm", "check": "the copy reads right"},
        ])
        eng = self.engine(transcript=self.TRANSCRIPT,
                          outcome_reader=lambda mm: self.ACCOUNT)
        m = run(eng.run_mission(mid))
        self.assertEqual(m["state"], "paused", "fixture sanity")
        self.store.confirm_check(mid, 1, by="founder")
        m = eng.settle(mid)
        self.assertEqual(m["state"], "done")
        self.assertEqual(m["completion"]["outcome"], self.ACCOUNT)


class TestTheOutcomeInPlainText(unittest.TestCase):
    """completion_text is what the goal's memory records and what the
    panel's Copy button mirrors, so the account has to reach both."""

    SUMMARY = dict(TestCompletionText.SUMMARY,
                   outcome="Added the tenant loop and ran the suite.")

    def test_53_it_sits_between_the_budget_and_the_verdicts(self):
        lines = completion_text(self.SUMMARY).split("\n")
        at = lines.index("Added the tenant loop and ran the suite.")
        self.assertEqual(lines[at - 2], "5 of 20 turns used.")
        self.assertEqual(lines[at - 1], "",
                         "a paragraph of prose is not another header row")
        self.assertTrue(any(l.startswith("✓ EMI-OK") for l in lines[at:]),
                        "the verdicts still follow it")

    def test_54_without_one_the_text_is_what_it_was(self):
        """Every attempt already on disk, byte for byte."""
        no_outcome = dict(self.SUMMARY)
        no_outcome.pop("outcome")
        self.assertEqual(completion_text(no_outcome),
                         completion_text(TestCompletionText.SUMMARY))
        blank = dict(self.SUMMARY, outcome="")
        self.assertEqual(completion_text(blank),
                         completion_text(TestCompletionText.SUMMARY))

    def test_55_the_goal_remembers_the_account(self):
        """End to end on the durable surface: the outcome the engine
        stamped is what "What I learned" ends up holding."""
        text = completion_text(
            {"headline": "1 of 1 checks passed", "objective": "o",
             "turns_used": 1, "max_turns": 4,
             "outcome": "Added the tenant loop.",
             "checks": [{"check": "EMI-OK", "met": True,
                         "how": "found in the chat"}]})
        self.assertIn("Added the tenant loop.", text)
        self.assertTrue(text.startswith("Done — 1 of 1 checks passed"))


if __name__ == "__main__":
    unittest.main()
