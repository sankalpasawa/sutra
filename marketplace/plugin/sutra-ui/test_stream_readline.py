"""The stream-json read loop must survive an oversized line.

WHY THIS EXISTS
---------------
`asyncio.create_subprocess_exec` defaults its StreamReader to a 64 KiB limit,
and stream-json is one JSON object per line. A `user` frame carrying a
tool_result -- any Read of a sizeable file, any verbose Bash capture --
routinely exceeds that. `StreamReader.readline()` then raises

    ValueError: Separator is not found, and chunk exceed the limit

which used to propagate out of the read loop (the `try` began one line too
late), past an outer handler catching only WebSocketDisconnect, and take the
websocket and the child process down mid-answer. To the operator that was "the
chat randomly dies when the agent reads a big file", with no error shown.

Two independent protections, and this asserts both, because either alone is
insufficient: the raised limit makes it rare, the guard makes it survivable.

stdlib only: unittest + asyncio, matching the rest of this suite.

Run: python3 test_stream_readline.py
"""
import asyncio
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BIG = 200_000            # comfortably over the 64 KiB default, realistic for a tool_result


def _emit(nbytes):
    return ('import sys;'
            'sys.stdout.write("{\\"type\\":\\"user\\",\\"x\\":\\"" + "A"*%d + "\\"}\\n");'
            'sys.stdout.write("{\\"type\\":\\"done\\"}\\n");'
            'sys.stdout.flush()' % nbytes)


class TestReadLimit(unittest.TestCase):

    def _read_first(self, **kw):
        async def go():
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", _emit(BIG),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **kw)
            try:
                return await proc.stdout.readline(), None
            except ValueError as exc:
                return None, exc
            finally:
                try: proc.kill()
                except Exception: pass
                await proc.wait()
        return asyncio.run(go())

    def test_the_default_limit_really_does_raise(self):
        """Guards the premise. If asyncio ever changes this, the fix below is
        no longer load-bearing and the reason for it should be re-read."""
        line, exc = self._read_first()
        self.assertIsNone(line)
        self.assertIsInstance(exc, ValueError)

    def test_the_configured_limit_reads_the_line(self):
        line, exc = self._read_first(limit=8 * 1024 * 1024)
        self.assertIsNone(exc)
        self.assertGreater(len(line), BIG)

    def test_a_guarded_loop_survives_even_at_the_default(self):
        """The belt to the limit's braces: with the guard, an oversized line
        costs one dropped frame instead of the whole connection."""
        async def go():
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", _emit(BIG),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            seen, skipped = [], 0
            try:
                while True:
                    try:
                        line = await proc.stdout.readline()
                    except (ValueError, asyncio.LimitOverrunError):
                        skipped += 1
                        # The drain must CONSUME the buffered bytes. readuntil
                        # alone re-raises on the same data and consumes nothing.
                        while True:
                            try:
                                await proc.stdout.readuntil(b"\n"); break
                            except asyncio.LimitOverrunError as over:
                                try: await proc.stdout.readexactly(over.consumed)
                                except asyncio.IncompleteReadError: break
                            except Exception:
                                break
                        continue
                    if not line:
                        break
                    seen.append(line)
            finally:
                try: proc.kill()
                except Exception: pass
                await proc.wait()
            return seen, skipped
        seen, skipped = asyncio.run(go())
        self.assertGreaterEqual(skipped, 1, "the oversized line should have been skipped")
        self.assertTrue(any(b'"done"' in l for l in seen),
                        "the loop must resynchronise and still deliver later frames")


class TestSourceKeepsBothProtections(unittest.TestCase):
    """Source-level, because the behavioural tests above exercise the PATTERN
    and cannot see whether the shipped code still uses it. The spawn and the
    read loop both moved to SessionRuntime (PLAN-100 S17/S18); the guards
    follow the code they protect."""

    def setUp(self):
        with open(os.path.join(HERE, "session_runtime.py")) as handle:
            self.src = handle.read()

    def test_subprocess_raises_the_stream_limit(self):
        # Generous window: the rationale comment on this call is long, and an
        # earlier version of this test sliced it off and failed on its own
        # documentation. Bound it at the closing paren instead of a guess.
        start = self.src.index("await asyncio.create_subprocess_exec")
        spawn = self.src[start:self.src.index("start_new_session=True", start)]
        self.assertRegex(spawn, r"limit\s*=\s*\d",
                         "the chat subprocess is back on asyncio's 64 KiB default")

    def test_readline_is_inside_a_guard(self):
        loop = self.src[self.src.index("eof = False"):][:2600]
        guard = loop.index("try:")
        read = loop.index("self.proc.stdout.readline()")
        self.assertLess(guard, read,
                        "readline() sits outside the try again -- an oversized line "
                        "will kill the websocket instead of dropping one frame")

    def test_the_guard_catches_the_right_thing(self):
        loop = self.src[self.src.index("eof = False"):][:2600]
        self.assertIn("ValueError", loop)
        self.assertIn("LimitOverrunError", loop)


if __name__ == "__main__":
    unittest.main(verbosity=2)
