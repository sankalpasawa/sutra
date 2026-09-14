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


if __name__ == "__main__":
    unittest.main()
