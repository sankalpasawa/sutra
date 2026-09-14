"""Observer lifecycle: a replacement runtime is always observable (2026-09-14).

WHY THIS FILE EXISTS. `_OBSERVED` was a set of `id(rt)`. CPython reuses the
address of a collected object, so a BRAND-NEW SessionRuntime could land on the
id of a runtime Shadow had already observed and reaped -- and attach_observer's
guard would return early for it. Nothing then subscribed: no `_turn_boundary`
reached the waiters, no token reached `_RECENT_TEXT`, no frame reached
`_LAST_FRAME_TS`. The mission waited on a queue nobody fed, saw total silence,
and died at STALL_SECS blaming the worker for Shadow's own bookkeeping.

The runtime-identity half is pinned by test_01 (a genuinely recycled id) and,
deterministically, by test_02. The SESSION-keyed half is the other failure the
same lifecycle has: `_LAST_FRAME_TS`, `_RECENT_TEXT` and `_BOUNDARIES` are
keyed by session id, outlive the runtime that filled them, and were inherited
by whatever attached to that id next -- a stale stamp reads as "silent since
then" (test_06) and stale prose reads as what the new worker just said
(test_05).

asyncio objects are built INSIDE the loop throughout: the lane runs on python
3.9, where asyncio.Queue() binds the running loop at construction. Same rule,
and same reason, as test_shadow_waiter.py.
"""
import asyncio
import gc
import os
import tempfile
import unittest

import session_runtime as srt
import shadow_runner


SID = "sess-observer-life"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        asyncio.set_event_loop(asyncio.new_event_loop())
        self._clear()

    def tearDown(self):
        self._clear()
        shadow_runner.DELEGATES.pop(SID, None)
        shadow_runner.ATTACHED.pop(SID, None)
        asyncio.get_event_loop().close()
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def _clear(self):
        shadow_runner._OBSERVED.clear()
        for m in (shadow_runner._BOUNDARIES, shadow_runner._RECENT_TEXT,
                  shadow_runner._LAST_FRAME_TS):
            m.pop(SID, None)

    @staticmethod
    def feed(rt, frame):
        """Deliver a frame the way session_runtime's demux does."""
        for cb in list(rt.subscribers):
            cb(frame)


# ============ the bug: identity that a new object can inherit ============
class TestRuntimeIdentity(Base):

    def test_01_a_genuinely_recycled_id_is_still_observed(self):
        """THE MEASURED MECHANISM, reproduced. Allocate until CPython hands
        back the address of a runtime that was already observed and freed;
        that runtime must still get an observer."""
        async def go():
            dead_ids = set()
            for _ in range(50):
                rt = srt.SessionRuntime()
                shadow_runner.attach_observer(SID, rt)
                self.assertTrue(rt.subscribers, "the first one is observed")
                dead_ids.add(id(rt))
                shadow_runner.DELEGATES[SID] = rt
                shadow_runner.release_delegate(SID)
                del rt
                gc.collect()

            for _ in range(3000):
                nxt = srt.SessionRuntime()
                if id(nxt) in dead_ids:
                    shadow_runner.attach_observer(SID, nxt)
                    return nxt
                del nxt
            return None

        recycled = run(go())
        if recycled is None:
            self.skipTest("no id reuse observed in 3000 allocations")
        self.assertTrue(
            recycled.subscribers,
            "a new runtime on a recycled address must still be subscribed")

    def test_02_a_replacement_is_never_suppressed_by_its_predecessor(self):
        """The same guarantee without depending on the allocator: whatever
        A's address was, B is a DIFFERENT OBJECT and must be a miss."""
        async def go():
            a = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, a)
            b = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, b)
            return a, b
        a, b = run(go())
        self.assertTrue(a.subscribers, "A observed")
        self.assertTrue(b.subscribers, "B observed despite A being alive")

    def test_03_attach_is_still_idempotent_for_ONE_live_runtime(self):
        """The property the guard exists for is unchanged: attaching the
        SAME runtime twice must not double-subscribe (two observers would
        double-count every frame into _RECENT_TEXT)."""
        async def go():
            rt = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, rt)
            shadow_runner.attach_observer(SID, rt)
            shadow_runner.attach_observer(SID, rt)
            return rt
        rt = run(go())
        self.assertEqual(len(rt.subscribers), 1, "exactly one observer")


# ================ the full cycle the mission actually lives =============
class TestReleaseThenReplace(Base):

    def test_04_A_reaped_then_B_observed_and_B_STAMPS(self):
        """1 A observed -> 2 A released -> 3 B created -> 4 B observed ->
        5 B's frames land -> 6 A's bookkeeping suppressed none of it."""
        async def go():
            a = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, a)
            self.feed(a, {"type": "token", "text": "A was here"})
            self.assertIn(SID, shadow_runner._LAST_FRAME_TS)

            shadow_runner.DELEGATES[SID] = a
            shadow_runner.release_delegate(SID)

            b = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, b)
            self.assertTrue(b.subscribers, "(4) B is observed")

            self.feed(b, {"type": "token", "text": "B speaking"})
            self.feed(b, {"type": "_turn_boundary", "got_result": True})
            return b

        b = run(go())
        # (5) every channel the waiter and the decider read is live for B
        self.assertIn(SID, shadow_runner._LAST_FRAME_TS,
                      "B stamps the liveness clock")
        self.assertIn("B speaking", shadow_runner._RECENT_TEXT[SID],
                      "B's prose reaches the decider")
        self.assertFalse(shadow_runner._BOUNDARIES[SID].empty(),
                         "B's boundary reaches the waiter")
        # (6) and none of it is A's
        self.assertNotIn("A was here", shadow_runner._RECENT_TEXT[SID],
                         "a dead runtime's prose is not B's evidence")
        self.assertEqual(len(b.subscribers), 1)

    def test_05_release_forgets_the_session_bookkeeping(self):
        """Stale prose is not merely untidy: evidence_text feeds it to the
        decider as what the target said."""
        async def go():
            rt = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, rt)
            self.feed(rt, {"type": "token", "text": "stale output"})
            self.feed(rt, {"type": "_turn_boundary", "got_result": True})
            shadow_runner.DELEGATES[SID] = rt
            shadow_runner.release_delegate(SID)
        run(go())
        for name, m in (("_RECENT_TEXT", shadow_runner._RECENT_TEXT),
                        ("_LAST_FRAME_TS", shadow_runner._LAST_FRAME_TS),
                        ("_BOUNDARIES", shadow_runner._BOUNDARIES)):
            self.assertNotIn(SID, m, "%s must not outlive the runtime" % name)

    def test_06_a_dead_runtimes_stamp_cannot_stall_its_replacement(self):
        """The stall the waiter would otherwise call on a worker that has
        not yet had the chance to speak."""
        async def go():
            a = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, a)
            shadow_runner._LAST_FRAME_TS[SID] = 1000.0   # long ago
            shadow_runner.DELEGATES[SID] = a
            shadow_runner.release_delegate(SID)
            b = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, b)
            return b
        run(go())
        self.assertNotIn(SID, shadow_runner._LAST_FRAME_TS,
                         "B starts with no stamp, so the waiter seeds it "
                         "fresh instead of measuring silence from A's death")

    def test_07_reap_attached_forgets_too(self):
        """The founder-owned path unwinds in the same shape as the delegate
        path -- one rule, both reapers."""
        async def go():
            rt = srt.SessionRuntime()
            shadow_runner.ATTACHED[SID] = rt
            shadow_runner.attach_observer(SID, rt)
            self.feed(rt, {"type": "token", "text": "founder chat"})
            shadow_runner.reap_attached(SID)
            nxt = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, nxt)
            return nxt
        nxt = run(go())
        self.assertTrue(nxt.subscribers, "the next runtime is observable")
        self.assertNotIn("founder chat",
                         shadow_runner._RECENT_TEXT.get(SID, ""))

    def test_08_forgetting_is_idempotent_and_unowned_is_a_no_op(self):
        shadow_runner._forget_session("never-seen-session")
        self.assertIsNone(shadow_runner.release_delegate("never-seen-session"))
        self.assertIsNone(shadow_runner.reap_attached("never-seen-session"))


if __name__ == "__main__":
    unittest.main()
