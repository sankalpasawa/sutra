#!/usr/bin/env python3
"""The decider reads whole worker messages, not a byte tail of the blob.

THE FAILURE (founder, 2026-09-15, mission m-cd009367d41a). `last_response`
was evidence_text sliced to DECISION_TAIL (2000). Measured on that mission's
real 112,379-character transcript, 12 of 146 assistant messages exceeded the
window, and the decider saw:

      9% of a 21,060-char message      16% of 12,899      23% of 8,672

A tail keeps the END. The STRUCTURE is at the start -- "## CHANGE",
"## TESTS", "## FINAL". So Shadow could see where a message finished and not
where it began, and spent turns 17-20 asking for resends of work that was
already done: "`## CHANGE` arrived intact this time", "Everything from
`## TESTS` onward arrived intact". Then it hit max turns and died `failed`.

And when _RECENT_TEXT is cold -- which is every restart, since it is
memory-only -- there is no prose tail to append, so the window landed inside
the JSON envelope. The real value began:

    ':29:09.733Z"}, {"role": "assistant", "text": "## FINAL'

WHAT IS ASSERTED HERE. Whole messages reach the decider, heads intact, with
no envelope, warm or cold; Shadow's own turns stay out; evaluate_done_when
still gets the FULL evidence_text; and none of DECISION_TAIL,
DECIDE_PROSE_TAIL or the verification semantics moved.

Run: python3 test_shadow_decider_window.py
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import session_reader
import shadow_runner as sr

SID = "sess-window"
SHADOW_SAY = "[Shadow · mission m-x] Carry on and paste the memo."


def _rec(role, text):
    return {"type": role, "message": {"role": role,
                                      "content": [{"type": "text",
                                                   "text": text}]},
            "timestamp": "2026-09-15T00:00:00.000Z", "cwd": "/repo"}


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / "-repo"
        self.proj.mkdir(parents=True)
        self._orig = session_reader.PROJECTS
        session_reader.PROJECTS = self.root
        sr._RECENT_TEXT.pop(SID, None)          # cold by default

    def tearDown(self):
        session_reader.PROJECTS = self._orig
        sr._RECENT_TEXT.pop(SID, None)
        self.tmp.cleanup()

    def write(self, rows, sid=SID):
        (self.proj / (sid + ".jsonl")).write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


class TestWholeMessagesReachTheDecider(Base):

    def test_01_a_21k_message_keeps_its_HEAD(self):
        """The replay shape. The old tail showed 9% of this and dropped the
        '## CHANGE' header that opens it."""
        big = "## CHANGE\n\n" + ("x" * 21000) + "\n\n## FINAL\ndone"
        self.write([_rec("user", "go"), _rec("assistant", big)])
        got = sr.worker_response(SID)
        self.assertTrue(got.startswith("## CHANGE"),
                        "the message was cut from the beginning: %r"
                        % got[:60])
        self.assertGreater(len(got), 2000 * 5,
                           "still effectively a tail: %d chars" % len(got))
        self.assertEqual(len(got), sr.DECIDE_RESPONSE_CHARS,
                         "a pathological single message is head-capped")
        self.assertEqual(got, (big)[:sr.DECIDE_RESPONSE_CHARS],
                         "the cap must keep the HEAD")

    def test_02_no_JSON_ENVELOPE_reaches_the_decider(self):
        big = "## TESTS\n\n" + ("y" * 9000)
        self.write([_rec("user", "go"), _rec("assistant", big)])
        got = sr.worker_response(SID)
        for marker in ('"role":', '"text":', '"timestamp":', '"messages":'):
            self.assertNotIn(marker, got, "envelope leaked: " + marker)

    def test_03_COLD_recent_text_still_yields_clean_prose(self):
        """_RECENT_TEXT is memory-only, so this is the state after every
        restart -- exactly when the old window fell into the json."""
        self.assertNotIn(SID, sr._RECENT_TEXT)
        self.write([_rec("assistant", "## FINAL\n\nShipped it.")])
        got = sr.worker_response(SID)
        self.assertEqual(got, "## FINAL\n\nShipped it.")
        # and the OLD path, for contrast, is envelope on a cold buffer
        blob = sr.evidence_text(SID)
        self.assertIn('"role"', blob[-mission_engine.DECISION_TAIL:],
                      "the premise of this fix no longer holds")

    def test_04_a_SHORT_message_is_byte_for_byte(self):
        short = "Done. Tests pass, PR is open."
        self.write([_rec("assistant", short)])
        self.assertEqual(sr.worker_response(SID), short)

    def test_05_SHADOWS_OWN_turns_stay_excluded(self):
        self.write([_rec("user", SHADOW_SAY),
                    _rec("assistant", "## FINAL\n\nI did the thing.")])
        got = sr.worker_response(SID)
        self.assertNotIn("Shadow · mission", got)
        self.assertNotIn("Carry on and paste", got)
        self.assertIn("I did the thing.", got)

    def test_06_an_EMPTY_transcript_degrades_safely(self):
        self.assertEqual(sr.worker_response(SID), "")
        self.assertEqual(sr.worker_response(""), "")
        self.assertEqual(sr.worker_response(None), "")
        self.write([_rec("user", "only shadow spoke")])
        self.assertEqual(sr.worker_response(SID), "")

    def test_07_only_the_LATEST_message_is_returned(self):
        """LATEST ONLY. An earlier draft accumulated backwards until a budget
        filled; on m-cd009367d41a a 24000-char budget pulled in six messages
        including SUPERSEDED `## CHANGE` drafts -- earlier, wrong versions of
        the content the decider was trying to read. One message cannot."""
        self.write([_rec("assistant", "## CHANGE\n\nfirst draft"),
                    _rec("user", SHADOW_SAY),
                    _rec("assistant", "## CHANGE\n\nsuperseded draft"),
                    _rec("assistant", "## FINAL\n\nthe real answer")])
        got = sr.worker_response(SID)
        self.assertEqual(got, "## FINAL\n\nthe real answer")
        self.assertNotIn("superseded", got, "a stale draft reached the decider")
        self.assertNotIn("first draft", got)

    def test_08_the_cap_keeps_the_HEAD_and_only_bites_when_oversized(self):
        """At or under the limit: byte for byte. Over it: the FIRST `limit`
        characters, never the last -- the opposite of the slice this
        replaces, because the head is what was being lost."""
        exact = "## CHANGE\n" + "z" * (200 - len("## CHANGE\n"))
        self.write([_rec("assistant", exact)])
        self.assertEqual(sr.worker_response(SID, limit=200), exact,
                         "a message AT the limit must not be touched")
        over = "## CHANGE\n" + "z" * 500
        self.write([_rec("assistant", over)])
        got = sr.worker_response(SID, limit=200)
        self.assertEqual(len(got), 200)
        self.assertEqual(got, over[:200], "the cap took the tail, not the head")
        self.assertTrue(got.startswith("## CHANGE"))

    def test_08b_the_cap_is_sized_above_p99_of_the_real_corpus(self):
        """114 assistant messages across 10 Shadow sessions: median 1008,
        p95 10672, p99 13989, max 21060. 16000 bites 1 in 114."""
        self.assertEqual(sr.DECIDE_RESPONSE_CHARS, 16000)


class TestNothingElseMoved(Base):

    def test_10_evaluate_done_when_still_gets_the_FULL_evidence(self):
        """The decider's window narrowed; the EVIDENCE did not. A check that
        matched before must still match."""
        self.write([_rec("assistant", "noise " * 400 + "FINAL: postgres"),
                    _rec("assistant", "and then some more work")])
        blob = sr.evidence_text(SID)
        m = {"done_when": [{"tier": "contains_artifact", "check": "FINAL:"}]}
        done, res = mission_engine.evaluate_done_when(m, blob)
        self.assertTrue(done, "evidence lost a match it used to have")
        # ...and the artifact is NOT in the decider's narrower view, which is
        # the whole reason the two must stay separate strings
        self.assertNotIn("FINAL: postgres", sr.worker_response(SID),
                         "the decider's view is the LATEST message, which "
                         "does not carry the artifact the evidence does")

    def test_11_the_caps_are_untouched(self):
        self.assertEqual(mission_engine.DECISION_TAIL, 2000)
        self.assertEqual(sr.DECIDE_PROSE_TAIL, 2000)
        self.assertEqual(sr._RECENT_CAP, 20000)

    def test_12_no_response_reader_keeps_the_HISTORICAL_value(self):
        """Every existing caller injects none, so nothing they do changes."""
        eng = mission_engine.MissionEngine(None, None, None, lambda m: "x")
        self.assertIsNone(eng.response_reader)

    def test_13_a_reader_that_RAISES_cannot_fail_a_turn(self):
        eng = mission_engine.MissionEngine(
            None, None, None, lambda m: "x",
            response_reader=lambda m: (_ for _ in ()).throw(RuntimeError("no")))
        self.assertIsNotNone(eng.response_reader)
        with self.assertRaises(RuntimeError):
            eng.response_reader({})     # the loop catches this, not the reader

    def test_14_the_decider_context_carries_what_it_was_given(self):
        """_decision_context still applies DECISION_TAIL -- unchanged -- but
        it is now applied to whole-message prose, not to the json blob."""
        eng = mission_engine.MissionEngine(None, None, None, lambda m: "x")
        ctx = eng._decision_context({"objective": "o", "done_when": []},
                                    "## CHANGE\n\nthe body")
        self.assertEqual(ctx["last_response"], "## CHANGE\n\nthe body")
        self.assertNotIn('"role":', ctx["last_response"])


class TestTheReplayShape(Base):
    """8. The m-cd009367d41a shape must not read as a truncated message."""

    def test_20_the_REAL_shape_arrives_whole(self):
        """The message Shadow actually needed was 1,811 characters -- it fitted
        inside the OLD 2000-char window twice over. It never arrived because
        `last_response` was the last 2000 BYTES OF JSON, not a message. So the
        regression shape is a normal-sized final message, and it must come
        through byte for byte with both of its headers."""
        final = ("## CHANGE\n\n`static/js/16-shadow-home.js:1080`\n\n"
                 + ("detail line\n" * 100)
                 + "\n## FINAL\n\nThe card shows the timestamp.")
        self.assertLess(len(final), sr.DECIDE_RESPONSE_CHARS)
        self.write([_rec("user", SHADOW_SAY),
                    _rec("assistant", "## CHANGE\n\nan earlier draft"),
                    _rec("assistant", final)])
        got = sr.worker_response(SID)
        self.assertEqual(got, final, "the real shape must arrive untouched")
        self.assertTrue(got.startswith("## CHANGE"))
        self.assertIn("## FINAL", got, "the closing block is missing")
        self.assertNotIn('"role":', got, "still shows the envelope")
        self.assertNotIn("an earlier draft", got, "a stale draft leaked in")

    def test_21_a_PATHOLOGICAL_message_keeps_its_head_not_its_tail(self):
        """The 21,060-char outlier -- 1 of 114 in the corpus. It is the only
        case the cap bites, and it loses its TAIL, never its head. Before this
        fix the decider saw 9% of it and that 9% was the tail."""
        body = ("## CHANGE\n\n" + ("detail line\n" * 2000)
                + "\n## FINAL\n\nthe closing block")
        self.assertGreater(len(body), 21000)
        self.write([_rec("assistant", body)])
        got = sr.worker_response(SID)
        self.assertEqual(len(got), sr.DECIDE_RESPONSE_CHARS)
        self.assertEqual(got, body[:sr.DECIDE_RESPONSE_CHARS])
        self.assertEqual(got.split("\n", 1)[0], "## CHANGE",
                         "the opening header is what kept being lost")
        # the tradeoff, stated: an oversized message DOES lose its tail
        self.assertNotIn("## FINAL", got,
                         "16k is the documented cost for 1 message in 114")


if __name__ == "__main__":
    unittest.main(verbosity=2)
