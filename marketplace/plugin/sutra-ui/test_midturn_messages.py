"""A message typed while a reply runs (Claude only).

It is written to claude's stdin at once and claude takes it in at its next
step (`joined`), or runs it right after. Stop is Esc: it interrupts the
running turn WITHOUT ending the process (control_request/interrupt), so a
handed message runs at once. Wire shapes measured against claude 2.1.283.
"""
import asyncio
import json
import pathlib
import unittest

from session_runtime import SessionRuntime
from test_runtime_states import run_turn, BASE

HERE = pathlib.Path(__file__).parent


class _Stdin:
    def __init__(self):
        self.lines = []

    def write(self, b):
        self.lines.append(json.loads(b.decode("utf-8")))

    async def drain(self):
        return None


def _echo(text):
    return {"type": "user", "isReplay": True, "session_id": "s-1",
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


class TestJoin(unittest.TestCase):
    def test_echo_of_a_handed_message_emits_joined(self):
        rt = SessionRuntime()
        rt.turn_own = "first"
        rt.sent_ahead = [{"message": "second"}]
        frames = []
        async def prim(f):
            frames.append(f["type"])
        run_turn(rt, prim, events=[BASE[0], _echo("first"), _echo("second"), BASE[2]])
        self.assertEqual(frames.count("joined"), 1)
        self.assertEqual(rt.sent_ahead, [])
        self.assertEqual([p["message"] for p in rt.absorbed], ["second"])

    def test_own_echo_is_not_a_join(self):
        rt = SessionRuntime()
        rt.turn_own = "first"
        frames = []
        async def prim(f):
            frames.append(f["type"])
        run_turn(rt, prim, events=[BASE[0], _echo("first"), BASE[2]])
        self.assertNotIn("joined", frames)

    def test_echo_that_differs_from_what_was_sent_still_joins(self):
        # the stuck reply: claude folded the message in but its echo was not
        # the sent text (expanded slash command), so it stayed in sent_ahead
        # and the socket waited for a turn of its own that never came
        rt = SessionRuntime()
        rt.turn_own = "first"
        rt.sent_ahead = [{"message": "/review"}]
        frames = []
        async def prim(f):
            frames.append(f["type"])
        run_turn(rt, prim, events=[BASE[0], _echo("first"),
                                   _echo("Review the current diff..."), BASE[2]])
        self.assertEqual(frames.count("joined"), 1)
        self.assertEqual(rt.sent_ahead, [])

    def test_own_echo_that_differs_is_still_its_own(self):
        rt = SessionRuntime()
        rt.turn_own = "/review"
        rt.sent_ahead = [{"message": "second"}]
        frames = []
        async def prim(f):
            frames.append(f["type"])
        run_turn(rt, prim, events=[BASE[0], _echo("Review the diff..."), BASE[2]])
        self.assertNotIn("joined", frames)
        self.assertEqual(len(rt.sent_ahead), 1, "not taken in yet: runs as its own turn")

    def test_echo_with_an_image_joins(self):
        rt = SessionRuntime()
        rt.turn_own = "first"
        rt.sent_ahead = [{"message": "look at this"}]
        img = _echo("look at this")
        img["message"]["content"].append(
            {"type": "image", "source": {"type": "base64", "data": "AA=="}})
        run_turn(rt, events=[BASE[0], _echo("first"), img, BASE[2]])
        self.assertEqual(rt.sent_ahead, [])

    def test_turn_not_opened_by_the_chat_never_takes_a_handed_message(self):
        # Shadow and the helpers call demux_turn without turn_own
        rt = SessionRuntime()
        rt.sent_ahead = [{"message": "second"}]
        run_turn(rt, events=[BASE[0], _echo("second"), BASE[2]])
        self.assertEqual(len(rt.sent_ahead), 1)

    def test_joining_state_does_not_outlive_the_turn(self):
        rt = SessionRuntime()
        rt.turn_own = "never echoed"
        run_turn(rt, events=[BASE[0], BASE[2]])
        self.assertIsNone(rt.turn_own)
        self.assertFalse(rt._joining)


class TestSoftInterrupt(unittest.TestCase):
    def test_interrupt_is_a_control_request_not_a_kill(self):
        rt = SessionRuntime()
        class P:
            returncode = None
            stdin = _Stdin()
        rt.proc = P()
        asyncio.run(rt.send_interrupt())
        asyncio.run(rt.send_interrupt())
        a, b = P.stdin.lines
        self.assertEqual(a["type"], "control_request")
        self.assertEqual(a["request"], {"subtype": "interrupt"})
        self.assertNotEqual(a["request_id"], b["request_id"])
        self.assertFalse(rt.stopped, "a soft interrupt is not the operator's Stop")

    def test_interrupted_result_is_an_error_the_socket_must_not_treat_as_failure(self):
        # the cut turn closes with error_during_execution; ws_chat checks
        # rt.soft_stop BEFORE its failure branch (which would kill the process)
        src = (HERE / "app.py").read_text(encoding="utf-8")
        soft = src.index("if rt.soft_stop:")
        self.assertLess(soft, src.index("if rt.stopped:\n", soft))
        self.assertLess(soft, src.index("failed = (result_error is not None)"))
        rt = SessionRuntime()
        cut = {"type": "result", "subtype": "error_during_execution",
               "is_error": True, "session_id": "s-1"}
        out = run_turn(rt, events=[BASE[0], cut])
        self.assertIsNotNone(out[3], "result_error set, so soft_stop must intercept it")

    def _boundary(self, rt, events):
        seen = []
        rt.subscribe(lambda f: seen.append(f) if f.get("type") == "_turn_boundary" else None)
        out = run_turn(rt, events=events)
        return out, seen[-1]

    def test_stop_reaches_observers_as_stopped_not_as_an_error(self):
        # Shadow's watcher raises a "hit an error" rescue on an errored boundary
        rt = SessionRuntime()
        rt.soft_stop = True
        cut = {"type": "result", "subtype": "error_during_execution",
               "is_error": True, "session_id": "s-1"}
        out, b = self._boundary(rt, [BASE[0], cut])
        self.assertIsNotNone(out[3], "ws_chat still gets the error back")
        self.assertIsNone(b["error"])
        self.assertTrue(b["stopped"])

    def test_a_real_error_still_reaches_observers(self):
        rt = SessionRuntime()
        bad = {"type": "result", "subtype": "error_during_execution",
               "is_error": True, "session_id": "s-1"}
        _, b = self._boundary(rt, [BASE[0], bad])
        self.assertIsNotNone(b["error"], "no Stop pressed: a real failure")
        self.assertFalse(b["stopped"])


class TestStopIsEsc(unittest.TestCase):
    """Stop ends the reply and keeps the process, like Esc in Claude Code; an
    interrupt that goes unheard falls back to the kill."""
    def test_stop_interrupts_first_and_kills_only_as_backstop(self):
        src = (HERE / "app.py").read_text(encoding="utf-8")
        stop = src.index('if payload.get("type") == "stop":')
        body = src[stop:src.index("why = _why_not_join(payload)", stop)]
        self.assertLess(body.index("await rt.send_interrupt()"), body.index("rt.stop()"))
        self.assertIn("_kill_if_unheard(live_turn)", body)
        self.assertNotIn('"interrupt"', src[stop:stop + 4000],
                         "no separate Send-now frame: Stop is the one control")

    def test_esc_key_sends_stop(self):
        boot = (HERE / "static/js/08-boot.js").read_text(encoding="utf-8")
        esc = boot.index('if (e.key === "Escape"){')
        self.assertIn('JSON.stringify({type:"stop"})', boot[esc:esc + 2500])


class TestPaneFrames(unittest.TestCase):
    """The pane says where a mid-reply message went instead of 'Queued'."""
    def test_client_handles_handed_and_queued_and_send_now_is_a_stop(self):
        js = (HERE / "static/js/01-state.js").read_text(encoding="utf-8")
        self.assertIn('f.type === "handed" || f.type === "queued"', js)
        chat = (HERE / "static/js/05-chat.js").read_text(encoding="utf-8")
        self.assertIn("Sent to Claude", chat)
        self.assertIn("data-sendnow", chat)
        # Send now is the SAME soft stop as Esc, not a second server path
        click = js[js.index('closest("[data-sendnow]")'):][:600]
        self.assertIn('type: "stop"', click)

    def test_server_says_why_a_message_waits(self):
        src = (HERE / "app.py").read_text(encoding="utf-8")
        self.assertIn('{"type": "handed"}', src)
        self.assertIn('{"type": "queued", "reason": why}', src)


if __name__ == "__main__":
    unittest.main()
