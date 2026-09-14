"""The decider must see what the WORKER SAID, not the tail of a json.dumps.

MEASURED, not theorised (delegate 0423e185, mission m-1e37cbe31708,
2026-09-14). evidence_text built `live + " " + json.dumps(doc)` and took the
last 40k. _decision_context then takes the last DECISION_TAIL (2000) of that.
On that live session json.dumps(doc) alone was 90,676 characters, so the
decider's entire window fell inside the serialization -- escaped unicode,
`\\n` literals, `{"role": "assistant", "text": ...}` -- and `live`, the clean
streamed prose, sat at the FRONT where the tail could never reach it.

It cost a real turn. At 05:16:47 the decider said "Your Stage 3 reply didn't
land -- the last thing on the wire is still the Stage 2 tail" and spent turn
6 of 20 re-issuing work the chat had already done.

The fix appends the clean prose AFTER the blob. The blob is unchanged and is
still what the verifier reads; only the tail is no longer json.
"""
import json
import os
import tempfile
import unittest

import mission_engine
import session_reader
import shadow_runner


SID = "sess-prose"
TAIL = mission_engine.DECISION_TAIL          # 2000, the decider's window


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        shadow_runner._RECENT_TEXT.pop(SID, None)
        self._orig_read = session_reader.read_session

    def tearDown(self):
        session_reader.read_session = self._orig_read
        shadow_runner._RECENT_TEXT.pop(SID, None)
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def transcript(self, doc):
        session_reader.read_session = lambda sid: doc

    def big_doc(self, n=200):
        """A transcript whose SERIALIZATION alone dwarfs the decision tail --
        the live shape, where json.dumps was 90k."""
        return {"messages": [
            {"role": "assistant",
             "text": "tool output line %d with — escapes and \n newlines "
                     "and a table | col | col |" % i,
             "tools": ["Bash"], "ts": "2026-09-14T05:%02d:00Z" % (i % 60)}
            for i in range(n)],
            "meta": {"cwd": "/Users/x/repo", "model": "claude"}}


class TestTheDeciderWindow(Base):

    def test_T1_clean_prose_survives_in_the_decision_window(self):
        """T1. Serialized tool output far exceeds 2000 chars; the worker's
        actual words must still be in the last 2000."""
        prose = ("STAGE 4 COMPLETE. The leasing mechanism uses a 200ms "
                 "renewal window and fails closed. ")
        shadow_runner._RECENT_TEXT[SID] = prose
        doc = self.big_doc()
        self.transcript(doc)
        self.assertGreater(len(json.dumps(doc)), TAIL,
                           "the fixture must actually exceed the window")

        window = shadow_runner.evidence_text(SID)[-TAIL:]
        self.assertIn("STAGE 4 COMPLETE", window,
                      "the worker's own words must reach the decider")
        self.assertIn("fails closed", window)

    def test_T2_a_huge_payload_cannot_evict_the_latest_prose(self):
        """T2. Grow the tool payload by 10x -- the prose must still be there.
        This is the property the old code did not have: its window moved with
        the serialization, so a bigger transcript pushed prose out entirely."""
        prose = "FINAL ANSWER: use the token bucket. "
        shadow_runner._RECENT_TEXT[SID] = prose
        for n in (50, 500, 2000):
            with self.subTest(messages=n):
                self.transcript(self.big_doc(n))
                window = shadow_runner.evidence_text(SID)[-TAIL:]
                self.assertIn("FINAL ANSWER", window,
                              "prose evicted at %d messages" % n)

    def test_T3_historical_and_tool_evidence_stays_in_the_blob(self):
        """T3. The verifier reads the whole return value, not the tail. The
        40k blob is still there and still carries the transcript."""
        shadow_runner._RECENT_TEXT[SID] = "recent prose. "
        doc = self.big_doc(20)
        doc["messages"][0]["text"] = "MARKER-FROM-HISTORY at the very start"
        self.transcript(doc)

        out = shadow_runner.evidence_text(SID)
        self.assertIn("MARKER-FROM-HISTORY", out,
                      "older transcript evidence must remain verifiable")
        self.assertIn('"role"', out, "the serialized doc is still present")
        self.assertIn("recent prose", out)

    def test_T4_no_live_text_is_byte_identical_to_before(self):
        """T4. With nothing streamed, the return value must be exactly the
        old expression -- no trailing separator, no appended empty tail."""
        doc = self.big_doc(10)
        self.transcript(doc)
        shadow_runner._RECENT_TEXT.pop(SID, None)

        expected_doc = dict(doc)
        expected_doc["messages"] = shadow_runner.evidence_messages(doc)
        expected = ("" + " " + json.dumps(expected_doc))[-40000:]
        self.assertEqual(shadow_runner.evidence_text(SID), expected)

    def test_T5_the_blob_prefix_is_unchanged(self):
        """The fix must APPEND only. The first 40k of the return value is
        byte-for-byte the old expression, so nothing the verifier relied on
        moved or was truncated differently."""
        live = "some streamed prose. "
        shadow_runner._RECENT_TEXT[SID] = live
        doc = self.big_doc(30)
        self.transcript(doc)

        expected_doc = dict(doc)
        expected_doc["messages"] = shadow_runner.evidence_messages(doc)
        old_blob = (live + " " + json.dumps(expected_doc))[-40000:]
        out = shadow_runner.evidence_text(SID)
        self.assertTrue(out.startswith(old_blob),
                        "the historical blob must be an exact prefix")
        self.assertEqual(out, old_blob + " "
                         + live[-shadow_runner.DECIDE_PROSE_TAIL:])

    def test_T6_shadow_authored_turns_are_still_excluded(self):
        """The authorship boundary is untouched: an injected Shadow say must
        not become admissible just because the tail changed. _RECENT_TEXT is
        assistant-only by construction, so the appended half cannot leak it
        either."""
        import shadow_egress
        tagged = shadow_egress.say_tag("m-1") + " do the thing"
        self.transcript({"messages": [
            {"role": "user", "text": tagged},
            {"role": "assistant", "text": "the chat's own answer"}]})
        shadow_runner._RECENT_TEXT[SID] = "the chat's own answer"
        out = shadow_runner.evidence_text(SID)
        self.assertNotIn("do the thing", out,
                         "Shadow's own injected turn stays out of evidence")
        self.assertIn("the chat's own answer", out)

    def test_T7_the_constant_matches_the_window_it_exists_to_fill(self):
        """A smaller DECIDE_PROSE_TAIL would leave json in the decider's
        window; they are deliberately the same size."""
        self.assertEqual(shadow_runner.DECIDE_PROSE_TAIL,
                         mission_engine.DECISION_TAIL)


class TestTheTailStartsAtAWord(Base):
    """THE PHANTOM FRAGMENT (founder dogfood, 2026-09-14, m-f83478e90923).

    `live[-limit:]` cut wherever the byte landed, and Shadow read the result
    as literally what the worker said. A cut through "defensi|ble answer in
    enterprise security" made it believe the message BEGAN mid-word, and it
    spent four turns telling the delegate to stop emitting a leading fragment
    that never existed.
    """

    TAILC = shadow_runner.DECIDE_PROSE_TAIL

    def test_P1_a_cut_inside_a_word_moves_to_the_next_word(self):
        """The dogfood case, reproduced exactly: the cut falls through
        "defensi|ble", so the OLD slice began with the fragment 'ble '."""
        head = "ble answer in enterprise security "
        after_cut = head + "more words " * 200
        after_cut = after_cut[:self.TAILC]          # exactly one tail's worth
        live = ("earlier words " * 50) + "defensi" + after_cut
        # the pre-fix slice is precisely the phantom Shadow complained about
        self.assertTrue(live[-self.TAILC:].startswith("ble answer"),
                        "the fixture must actually cut mid-word")
        got = shadow_runner._prose_tail(live)
        self.assertFalse(got.startswith("ble "),
                         "the mid-word fragment must not survive: %r"
                         % got[:20])
        self.assertTrue(got.startswith("answer in enterprise"),
                        "the tail must start at the next whole word: %r"
                        % got[:30])

    def test_P2_the_cap_is_never_exceeded(self):
        live = "word " * 5000
        self.assertLessEqual(len(shadow_runner._prose_tail(live)), self.TAILC)

    def test_P3_a_tail_that_was_never_truncated_is_byte_identical(self):
        live = "a short message that fits well inside the window"
        self.assertEqual(shadow_runner._prose_tail(live), live,
                         "a short message must not lose its first word")

    def test_P4_a_cut_already_on_a_boundary_is_left_alone(self):
        """The cut must land EXACTLY after a space, so the tail already
        begins at a whole word and there is nothing to move."""
        body = ("word " * 500)[:self.TAILC]
        live = ("a" * 100) + " " + body
        self.assertEqual(len(live) - self.TAILC, 101)      # the space is at 100
        got = shadow_runner._prose_tail(live)
        self.assertEqual(got, body,
                         "nothing to fix means nothing is changed")

    def test_P5_one_unbroken_token_is_returned_rather_than_emptied(self):
        live = "z" * (self.TAILC * 2)
        got = shadow_runner._prose_tail(live)
        self.assertEqual(len(got), self.TAILC,
                         "no whitespace to find: keep the slice, lose nothing")

    def test_P6_evidence_text_uses_it_and_the_blob_is_untouched(self):
        word = "defensible answer"
        live = ("q" * (self.TAILC - len(word) + 7)) + word
        shadow_runner._RECENT_TEXT[SID] = live
        session_reader.read_session = lambda sid: {}
        out = shadow_runner.evidence_text(SID)
        self.assertTrue(out.startswith(live[-40000:][:50]),
                        "the blob prefix is unchanged")
        self.assertTrue(out.rstrip().endswith("answer"),
                        "the appended tail still ends where it did")
        self.assertNotIn(" ble ", out[-self.TAILC:],
                         "no mid-word fragment in the appended tail")

    def test_P7_the_appended_tail_loses_no_reachable_match(self):
        """`live` is capped at _RECENT_CAP and sits WHOLE inside the 40k
        blob, so trimming a partial token off the APPENDED copy cannot make
        a contains_artifact check unreachable."""
        self.assertLessEqual(shadow_runner._RECENT_CAP, 40000)
        word = "defensible answer"
        live = ("q" * (self.TAILC - len(word) + 7)) + word
        shadow_runner._RECENT_TEXT[SID] = live
        session_reader.read_session = lambda sid: {}
        out = shadow_runner.evidence_text(SID)
        self.assertIn("defensible answer", out,
                      "the whole word is still reachable via the blob")


if __name__ == "__main__":
    unittest.main()
