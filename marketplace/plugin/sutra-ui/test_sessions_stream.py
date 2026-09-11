"""Regression: /api/sessions/stream must survive its own poll loop.

2.254.0 (3e8e2e04) deleted the `live sync` constant block while leaving both
names in use inside api_sessions_stream's generator. The failure mode is
nasty precisely because the FIRST frame works: gen() computes the index,
yields the opening `sync` event, and only then reaches

    await asyncio.sleep(SESSION_POLL_S)

and dies with NameError. So the panel listed sessions at boot and silently
never updated again, while the backend logged a crash per connection.

Two guards, because either alone would have missed it:

  1. a STRUCTURAL check that every module-level constant the streaming
     generator references is actually bound in app.py -- this is the check
     that would have caught the deletion at the moment it happened, without
     needing to run the stream at all;
  2. a BEHAVIOURAL check that drives the generator past one full poll, which
     is the only way to reach the line that crashed.
"""
import ast
import asyncio
import unittest


class TestStreamConstants(unittest.TestCase):
    """Structural: no orphaned constants on the streaming path."""

    def test_01_the_poll_constants_are_defined_and_sane(self):
        import app
        self.assertTrue(hasattr(app, "SESSION_POLL_S"),
                        "SESSION_POLL_S is referenced by the stream generator")
        self.assertTrue(hasattr(app, "SESSION_HEARTBEAT_S"),
                        "SESSION_HEARTBEAT_S is referenced by the stream "
                        "generator")
        self.assertIsInstance(app.SESSION_POLL_S, (int, float))
        self.assertIsInstance(app.SESSION_HEARTBEAT_S, (int, float))
        self.assertGreater(app.SESSION_POLL_S, 0,
                           "a zero poll would spin the event loop")
        self.assertLessEqual(app.SESSION_POLL_S, 5,
                            "the panel must feel live")
        self.assertGreater(app.SESSION_HEARTBEAT_S, app.SESSION_POLL_S,
                           "the heartbeat is a keep-alive, not a poll")

    def test_02_every_constant_the_generator_uses_is_bound(self):
        """The check that would have caught the deletion.

        Collects the UPPER_SNAKE names loaded inside api_sessions_stream and
        asserts each one resolves on the app module. A future edit that
        removes a constant but leaves a reference fails here instead of in
        production on the second poll.
        """
        import app
        src = open(app.__file__.replace(".pyc", ".py")).read()
        tree = ast.parse(src)
        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name == "api_sessions_stream":
                target = node
        self.assertIsNotNone(target, "the streaming route still exists")
        used = {n.id for n in ast.walk(target)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                and n.id.isupper() and len(n.id) > 2}
        self.assertIn("SESSION_POLL_S", used,
                      "this test is only meaningful while the poll is used")
        missing = sorted(n for n in used if not hasattr(app, n))
        self.assertEqual(missing, [],
                         "constants referenced by the stream but not defined "
                         "in app.py: %s" % missing)


class TestStreamRuns(unittest.TestCase):
    """Behavioural: the loop completes an iteration THROUGH the sleep."""

    def _drive(self, want_events, timeout=5.0):
        """Pull events off the real generator until `want_events` are seen.

        Drives the generator object directly rather than over HTTP: the route
        returns an endless StreamingResponse, and a test that opened it would
        have to decide when to stop reading anyway. The generator IS the code
        that crashed.
        """
        import app

        async def run():
            gen = None
            seen = []
            # a fast poll and an immediate heartbeat, so one iteration of the
            # real loop is observable inside a test; the shipped values stay
            # untouched on the module (restored in tearDown)
            gen = app.api_sessions_stream
            resp = await gen()
            body = resp.body_iterator
            deadline = asyncio.get_event_loop().time() + timeout
            while len(seen) < want_events:
                if asyncio.get_event_loop().time() > deadline:
                    raise AssertionError(
                        "stream produced %d/%d events before timing out: %r"
                        % (len(seen), want_events, seen))
                chunk = await asyncio.wait_for(body.__anext__(), timeout)
                text = chunk.decode() if isinstance(chunk, bytes) else chunk
                for line in text.splitlines():
                    if line.startswith("event:"):
                        seen.append(line.split(":", 1)[1].strip())
            await body.aclose()
            return seen

        return asyncio.run(run())

    def setUp(self):
        import app
        self.app = app
        self._poll = app.SESSION_POLL_S
        self._beat = app.SESSION_HEARTBEAT_S
        app.SESSION_POLL_S = 0.01     # one real iteration, fast
        app.SESSION_HEARTBEAT_S = 0   # tick every loop, so it is observable

    def tearDown(self):
        self.app.SESSION_POLL_S = self._poll
        self.app.SESSION_HEARTBEAT_S = self._beat

    def test_03_the_stream_survives_its_first_poll(self):
        """The opening `sync` always worked; a SECOND event proves the
        generator got past `await asyncio.sleep(SESSION_POLL_S)`."""
        seen = self._drive(2)
        self.assertEqual(seen[0], "sync", "the opening frame is the index")
        self.assertGreaterEqual(len(seen), 2,
                                "a second event means the poll loop ran")
        self.assertIn("tick", seen[1:],
                      "the heartbeat fires after the sleep: %r" % (seen,))

    def test_04_a_read_error_does_not_kill_the_stream(self):
        """The other reference to the constant is the except-path sleep."""
        import session_reader as sr
        real = self.app.sr.index
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("transcript directory vanished")
            return real()

        self.app.sr.index = flaky
        try:
            seen = self._drive(1)
        finally:
            self.app.sr.index = real
        self.assertGreaterEqual(calls["n"], 2,
                                "the generator retried after the error")
        self.assertEqual(seen[0], "sync",
                         "and still served the index once it could")


if __name__ == "__main__":
    unittest.main()
