"""Shadow's reasoning speaks through Sutra's runtime factory -- and only that.

THE QUESTION THIS ANSWERS (founder, 2026-09-15): "Shadow is an AI, right? If
Shadow uses a Claude process, shouldn't it be using Sutra Chat for that too?"

Sutra Chat is two layers, not one, and Shadow now takes exactly one of them:

  RUNTIME LAYER   provider_adapters.get(id).new_runtime() -- the one place
                  that decides which runtime class speaks to which provider.
                  ws_chat asks it (app.py:3470). Shadow's decider used to
                  construct SessionRuntime() by hand and is now ADOPTED into
                  the same factory.
  CHAT LAYER      chat_store. Its reverse index IS the definition of a Sutra
                  chat (_owned_transcripts), so a record here would publish
                  Shadow's private prompts and decision JSON into Chats as an
                  ordinary conversation. DELIBERATELY NOT ADOPTED, and these
                  tests hold that line.

Everything else about the reasoning turn is unchanged: one prompt, one turn,
process killed, no registry, no resume, no tools.

Run: .venv/bin/python -m unittest test_shadow_reasoning_runtime -v
"""
import asyncio
import json
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-reason-")

import app as app_module  # noqa: E402
import chat_store  # noqa: E402
import provider_adapters  # noqa: E402
import session_runtime  # noqa: E402
import shadow_runner  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()

DECISION = json.dumps({"action": "continue", "instruction": "do the next bit",
                       "reason": "it follows"})


class FakeRuntime:
    """Records everything the decider does to a runtime."""

    made = []

    def __init__(self, reply=DECISION):
        self.reply = reply
        self.spawned = None
        self.env = None
        self.sent = []
        self.killed = False
        self.cleared = False
        FakeRuntime.made.append(self)

    async def spawn(self, args, cwd, key, env=None):
        self.spawned = {"args": list(args), "cwd": cwd, "key": key, "env": env}
        self.env = env
        return object()

    async def send_user_frame(self, msg):
        self.sent.append(msg)

    async def demux_turn(self, emit, sid):
        await emit({"type": "token", "text": self.reply})
        return ("s-fake", None, True, None, None)

    def kill_group(self):
        self.killed = True

    def clear(self):
        self.cleared = True


def decider(reply=DECISION, **kw):
    FakeRuntime.made = []
    return shadow_runner.make_decider(
        lambda: ["/bin/claude", "-p"], "/tmp",
        new_runtime=lambda: FakeRuntime(reply), **kw)


CTX = {"outcome": "ship it", "checks": [], "turns_used": 1, "max_turns": 20,
       "last_instruction": "go", "last_response": "the chat replied"}


# ============================================  the runtime layer IS adopted ==
class ShadowUsesSutrasRuntimeFactory(unittest.TestCase):

    def test_shadow_asks_the_SAME_factory_ws_chat_asks(self):
        """provider_adapters.get(id).new_runtime() -- one factory, not two."""
        sentinel = object()

        class A:
            def new_runtime(self): return sentinel

        orig = provider_adapters.get
        provider_adapters.get = lambda pid: A()
        try:
            self.assertIs(app_module._shadow_new_runtime(), sentinel,
                          "Shadow's reasoning must come from the adapter")
        finally:
            provider_adapters.get = orig

    def test_ws_chat_and_shadow_now_share_one_factory_call(self):
        src = _read("app.py")
        self.assertIn("adapter.new_runtime()", src, "ws_chat's call")
        self.assertIn("adapter.new_runtime()", src.split(
            "_shadow_new_runtime")[1], "Shadow's call, same API")

    def test_a_missing_adapter_falls_back_rather_than_breaking_shadow(self):
        orig = provider_adapters.get
        provider_adapters.get = lambda pid: None
        try:
            rt = app_module._shadow_new_runtime()
            self.assertIsInstance(rt, session_runtime.SessionRuntime,
                                  "a build with no adapter still reasons")
        finally:
            provider_adapters.get = orig

    def test_the_decider_uses_the_injected_factory(self):
        d = decider()
        got = asyncio.get_event_loop().run_until_complete(d(CTX))
        self.assertEqual(len(FakeRuntime.made), 1, "one runtime per turn")
        self.assertIsNotNone(FakeRuntime.made[0].spawned, "and it spawned")
        self.assertEqual(got["action"], "continue")

    def test_without_an_injected_factory_it_is_byte_identical(self):
        """The flag path and every existing test keep the old construction."""
        d = shadow_runner.make_decider(lambda: ["/bin/false"], "/tmp")
        self.assertTrue(callable(d))
        src = _read("shadow_runner.py")
        self.assertIn("new_runtime() if new_runtime is not None "
                      "else srt.SessionRuntime()", src)

    def test_the_app_wires_it(self):
        src = _read("app.py")
        self.assertIn("new_runtime=_shadow_new_runtime", src,
                      "the default decider must be given the factory")


# ======================================  the CHAT layer is NOT adopted ======
class ShadowsReasoningIsNotAChat(unittest.TestCase):

    def setUp(self):
        self.chats = tempfile.mkdtemp(prefix="shadow-reason-chats-")
        os.environ["SUTRA_UI_CHATS"] = self.chats

    def _reason(self, n=1):
        d = decider()
        loop = asyncio.get_event_loop()
        for _ in range(n):
            loop.run_until_complete(d(CTX))

    def test_reasoning_creates_NO_chat_record(self):
        before = len(chat_store.index() or {})
        self._reason()
        self.assertEqual(len(chat_store.index() or {}), before,
                         "a reasoning turn must not become a Sutra chat")

    def test_reasoning_creates_no_sutra_id_and_no_index_row(self):
        self._reason()
        files = [f for f in os.listdir(self.chats)
                 if f.endswith(".json") and f != "_index.json"]
        self.assertEqual(files, [],
                         "no chat record on disk: %r" % files)

    def test_shadow_runner_never_imports_chat_store(self):
        """The boundary, asserted rather than assumed."""
        src = _read("shadow_runner.py")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                self.assertNotIn("chat_store", s,
                                 "reasoning must not reach the chat layer")

    def test_the_reasoning_process_is_not_registered_or_resumable(self):
        self._reason()
        rt = FakeRuntime.made[0]
        self.assertIsNone(session_runtime.lookup_runtime("s-fake"),
                          "no registry entry -- nothing can say into it")
        self.assertIsNone(rt.spawned["key"] and None,
                          "sanity")   # key is a marker, not a session id
        self.assertEqual(rt.spawned["key"], ("shadow-decide",),
                         "spawned under the internal marker, not a session id")

    def test_the_process_is_killed_after_every_turn(self):
        self._reason(n=3)
        self.assertEqual(len(FakeRuntime.made), 3, "one process per turn")
        self.assertTrue(all(r.killed for r in FakeRuntime.made),
                        "each reasoning process is one-shot")

    def test_no_MCP_tools_are_handed_to_the_reasoning_process(self):
        self._reason()
        env = FakeRuntime.made[0].env
        self.assertTrue(env is None or "SUTRA_MCP_SHADOW" not in env,
                        "the reasoning turn must stay tool-less: %r" % (env,))

    def test_the_prompt_never_leaves_as_a_chat_message(self):
        """What is sent is the decision prompt, and it goes to the process --
        not to chat_store, and not to any founder-visible surface."""
        self._reason()
        sent = FakeRuntime.made[0].sent
        self.assertEqual(len(sent), 1, "one prompt, one turn")
        self.assertIn("Decide.", sent[0])
        self.assertEqual(len(chat_store.index() or {}), 0)


# ==========================================  the contract is unchanged ======
class TheDecisionContractIsPreserved(unittest.TestCase):

    def test_continue_still_parses(self):
        got = asyncio.get_event_loop().run_until_complete(decider()(CTX))
        self.assertEqual(got["action"], "continue")
        self.assertEqual(got["instruction"], "do the next bit")

    def test_ask_founder_still_parses(self):
        reply = json.dumps({"action": "ask_founder", "reason": "need you"})
        got = asyncio.get_event_loop().run_until_complete(decider(reply)(CTX))
        self.assertEqual(got["action"], "ask_founder")

    def test_an_intervention_payload_still_survives(self):
        reply = json.dumps({"action": "ask_founder", "reason": "pick one",
            "intervention": {"question": "Which region?", "fields": [
                {"key": "region", "type": "choice", "label": "Region",
                 "options": [{"value": "a"}, {"value": "b"}]}]}})
        got = asyncio.get_event_loop().run_until_complete(decider(reply)(CTX))
        self.assertIn("intervention", got)
        self.assertEqual(got["intervention"]["fields"][0]["type"], "choice")

    def test_multiple_reasoning_turns(self):
        d = decider()
        loop = asyncio.get_event_loop()
        for i in range(4):
            got = loop.run_until_complete(d(CTX))
            self.assertEqual(got["action"], "continue", "turn %d" % i)
        self.assertEqual(len(FakeRuntime.made), 4)

    def test_a_junk_reply_is_still_refused(self):
        got = asyncio.get_event_loop().run_until_complete(
            decider("not json at all")(CTX))
        self.assertIsNone(got, "R10: never guess a decision")


# ===============================================  the worker is untouched ===
class TheWorkerPathIsUnchanged(unittest.TestCase):

    def test_the_worker_still_publishes_a_real_chat(self):
        src = _read("app.py")
        self.assertIn("def _publish_delegate_chat", src)
        self.assertIn("chat_store.begin_segment(rec", src,
                      "the delegate is still bound into Chats")

    def test_the_worker_spawn_is_not_routed_through_the_new_factory(self):
        src = _read("shadow_runner.py")
        seg = src.split("async def spawn_delegate_session")[1][:6000]
        self.assertIn("srt.SessionRuntime()", seg,
                      "the worker's construction is deliberately unchanged")


if __name__ == "__main__":
    unittest.main()
