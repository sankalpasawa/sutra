"""test_fanout_worker.py -- worker.run_one against REAL subprocesses.

test_fanout.py proves the orchestration is right by injecting a fake runner. A
fake runner proves nothing about whether `codex exec` was actually spawned with
a legal flag order, whether the ACP handshake completes, or whether a child
process group dies when the job is cancelled. That is what this file is for,
and it asserts against the ARGV THE STUB RECORDED FROM INSIDE ITSELF rather
than against what the code intended -- the discipline qa/fake_codex_agent.py's
header spells out, and the reason build_acp_args' dropped-model bug survived
until someone read the wire.

No claude, codex or deepseek binary is required, no key, no network, nothing
billed: the three qa stubs stand in, and each one refuses what the real CLI was
measured to refuse.

DEEPSEEK IS COVERED BY TWO STUBS, AND THE SECOND ONE IS THE POINT.

qa/fake_acp_agent.py answers session/prompt with a bare
{"stopReason": "end_turn"} and no content -- "the turn is not what is under
test", by its own comment. Against it, the DeepSeek case proves the handshake
runs and that a textless turn is reported honestly as a failure rather than as
an empty success. It cannot show that an ANSWER reaches the caller.

That left the one path real DeepSeek prose actually takes -- session/update ->
agent_message_chunk -> `token` (acp_runtime.py:465) -- with no coverage
anywhere in this repository: a grep for agent_message_chunk finds a single hit,
the translator itself. A worker that dropped every DeepSeek reply would have
passed the entire suite. SPEAKING_ACP_STUB below closes that: same protocol,
same refusals, plus the notification, and the assertions cover a multi-chunk
answer being joined in order.

WHAT IS STILL UNVERIFIED, stated rather than implied: no test here runs the
real @sluisr/deepseek-cli. The stub's wire shape is modelled on the probes
recorded in acp_runtime.py and qa/fake_acp_agent.py, so it proves Sutra's side
of the contract, not the vendor's.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_STUB = os.path.join(HERE, "qa", "fake_claude_agent.py")
CODEX_STUB = os.path.join(HERE, "qa", "fake_codex_agent.py")
ACP_STUB = os.path.join(HERE, "qa", "fake_acp_agent.py")

#: A SECOND ACP stub, written to this test's tmpdir, that actually SPEAKS.
#:
#: qa/fake_acp_agent.py answers session/prompt with a bare
#: {"stopReason": "end_turn"} and no content -- "the turn is not what is under
#: test", by its own comment -- so it cannot show that a DeepSeek answer
#: reaches the caller. That left agent_message_chunk, the ONLY way real
#: DeepSeek prose becomes a Sutra `token` frame (acp_runtime.py:465), with no
#: coverage anywhere in this repo: a grep for the string finds exactly one hit,
#: the runtime's own translator.
#:
#: This stub is the shipped one's protocol plus that one notification. It is
#: NOT a permissive stub: it keeps every refusal the real agent was measured to
#: make -- session/new fails unauthenticated with the real Gemini sentence, and
#: an unknown method answers -32601 rather than {} -- because dropping those is
#: precisely the mistake qa/fake_acp_agent.py's header was written about. It
#: lives here rather than in qa/ so no shipped suite can inherit it.
SPEAKING_ACP_STUB = r'''#!/usr/bin/env python3
import json, os, sys

REPLY = os.environ.get("SUTRA_TEST_ACP_REPLY", "hello from deepseek")
CHUNKS = int(os.environ.get("SUTRA_TEST_ACP_CHUNKS", "2"))
AUTH_METHOD = "deepseek-api-key"
MODES = [{"id": "default", "name": "Default", "description": "d"},
         {"id": "autoEdit", "name": "Auto Edit", "description": "d"},
         {"id": "yolo", "name": "YOLO", "description": "d"},
         {"id": "plan", "name": "Plan", "description": "d"}]
MODELS = [{"modelId": "deepseek-v4-flash", "name": "deepseek-v4-flash"}]
STATE = {"authed": False, "mode": "default"}


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def reply(i, result):
    send({"jsonrpc": "2.0", "id": i, "result": result})


def error(i, code, message):
    send({"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": message}})


def note(path, row):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def session_state():
    return {"modes": {"availableModes": MODES, "currentModeId": STATE["mode"]},
            "models": {"availableModels": MODELS,
                       "currentModelId": "deepseek-v4-flash"}}


def main():
    note(os.environ.get("SUTRA_TEST_ACP_ARGV"), sys.argv)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, i, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if i is None:
            continue
        if method == "initialize":
            reply(i, {"protocolVersion": 1,
                      "agentCapabilities": {"loadSession": True}})
        elif method == "authenticate":
            if params.get("methodId") != AUTH_METHOD:
                error(i, -32602, "Invalid auth method")
            else:
                STATE["authed"] = True
                note(os.environ.get("SUTRA_TEST_ACP_AUTH"),
                     {"methodId": params.get("methodId")})
                reply(i, {})
        elif method == "session/new":
            if not STATE["authed"]:
                error(i, -32000, "Gemini API key is missing or not configured.")
            else:
                st = session_state()
                st["sessionId"] = "speaking-session"
                reply(i, st)
        elif method == "session/set_mode":
            mid = params.get("modeId")
            if any(m["id"] == mid for m in MODES):
                STATE["mode"] = mid
                reply(i, {})
            else:
                error(i, -32603, "Invalid or unavailable mode: %s" % mid)
        elif method == "session/prompt":
            note(os.environ.get("SUTRA_TEST_ACP_PROMPT"), params)
            # THE POINT OF THIS STUB: prose arrives as session/update
            # notifications BEFORE the response, exactly as the real agent
            # streams it, and split across chunks so the caller has to join
            # them rather than take the last one.
            words = REPLY.split(" ")
            per = max(1, len(words) // max(1, CHUNKS))
            at = 0
            while at < len(words):
                piece = " ".join(words[at:at + per])
                if at + per < len(words):
                    piece += " "
                send({"jsonrpc": "2.0", "method": "session/update",
                      "params": {"sessionId": "speaking-session",
                                 "update": {"sessionUpdate": "agent_message_chunk",
                                            "content": {"type": "text",
                                                        "text": piece}}}})
                at += per
            reply(i, {"stopReason": "end_turn"})
        else:
            error(i, -32601, '"Method not found": %s' % method)


main()
'''


def _run(coro):
    """One loop per call, drained and closed.

    AcpRuntime.spawn starts a background _reader_loop for the process's whole
    life; leaving it pending on a discarded loop produced "Event loop is
    closed" noise at interpreter shutdown and could strand a task across
    tests. Cancel what is left, then close.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for t in pending:
            t.cancel()
        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True))
        loop.close()


class WorkerTest(unittest.TestCase):
    """One tmp HOME, all three providers stubbed, env restored afterwards."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sutra-test-fanout-worker-")
        cls.home = os.path.join(cls.tmp, "home")
        cls.work = os.path.join(cls.tmp, "workspace")
        for d in (os.path.join(cls.home, ".claude"),
                  os.path.join(cls.home, ".codex"),
                  os.path.join(cls.home, ".deepseek"), cls.work):
            os.makedirs(d, exist_ok=True)
        # existence-only readiness probe; providers never opens it
        with open(os.path.join(cls.home, ".codex", "auth.json"), "w") as fh:
            fh.write("")
        for stub in (CLAUDE_STUB, CODEX_STUB, ACP_STUB):
            os.chmod(stub, 0o755)

        cls.cl_argv = os.path.join(cls.tmp, "claude-argv.jsonl")
        cls.cx_argv = os.path.join(cls.tmp, "codex-argv.jsonl")
        cls.cx_stdin = os.path.join(cls.tmp, "codex-stdin.txt")
        cls.acp_argv = os.path.join(cls.tmp, "acp-argv.jsonl")
        cls.acp_auth = os.path.join(cls.tmp, "acp-auth.jsonl")
        # the speaking ACP stub and its own recordings
        cls.speaking_stub = os.path.join(cls.tmp, "speaking_acp.py")
        with open(cls.speaking_stub, "w") as fh:
            fh.write(SPEAKING_ACP_STUB)
        os.chmod(cls.speaking_stub, 0o755)
        cls.sp_argv = os.path.join(cls.tmp, "sp-argv.jsonl")
        cls.sp_auth = os.path.join(cls.tmp, "sp-auth.jsonl")
        cls.sp_prompt = os.path.join(cls.tmp, "sp-prompt.jsonl")

        cls._saved = dict(os.environ)
        os.environ.update({
            "HOME": cls.home,
            "SUTRA_UI_WORKDIR_ROOT": cls.tmp,
            "SUTRA_UI_WORKDIR": cls.work,
            "SUTRA_UI_SETTINGS": os.path.join(cls.tmp, "settings.json"),
            "SUTRA_UI_CLAUDE_BIN": CLAUDE_STUB,
            "SUTRA_FAKE_CLAUDE_ARGV": cls.cl_argv,
            "SUTRA_FAKE_CLAUDE_SESSION": "aaaaaaaa-1111-2222-3333-444444444444",
            "SUTRA_UI_CODEX_BIN": CODEX_STUB,
            "SUTRA_FAKE_CODEX_SCRIPT": "ok",
            "SUTRA_FAKE_CODEX_ARGV": cls.cx_argv,
            "SUTRA_FAKE_CODEX_STDIN": cls.cx_stdin,
            "SUTRA_UI_DEEPSEEK_BIN": ACP_STUB,
            "SUTRA_UI_DEEPSEEK_API_KEY": "sk-fake-not-a-real-key",
            "SUTRA_FAKE_ACP_ARGV": cls.acp_argv,
            "SUTRA_FAKE_ACP_AUTH": cls.acp_auth,
        })
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("SUTRA_UI_PROVIDER", None)
        # The settings file this test owns, so nothing reads the operator's.
        with open(os.environ["SUTRA_UI_SETTINGS"], "w") as fh:
            json.dump({"provider": "claude", "permission_mode": "plan",
                       "workdir": cls.work}, fh)

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._saved)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- readiness -------------------------------------------------------

    def test_00_all_three_stubs_are_runnable(self):
        """If this fails nothing below means anything."""
        import providers
        ready = {p["id"] for p in providers.runnable_providers()}
        for pid in ("claude", "codex", "deepseek"):
            self.assertIn(pid, ready, "%s not runnable: %s"
                          % (pid, providers.provider_by_id(pid)["reason"]))

    def test_01_gemini_is_not_eligible(self):
        import fanout
        self.assertNotIn("gemini", fanout.eligible_providers())

    # ---- the three providers --------------------------------------------

    def test_claude_worker_returns_text(self):
        import worker
        got = _run(worker.run_one("claude", "say something", self.work, "plan"))
        self.assertTrue(got["ok"], got.get("error"))
        self.assertEqual(got["text"], "ack")
        self.assertEqual(got["provider"], "claude")

    def test_codex_worker_returns_text(self):
        import worker
        got = _run(worker.run_one("codex", "say something", self.work, "plan"))
        self.assertTrue(got["ok"], got.get("error"))
        self.assertEqual(got["text"], "hello from codex")
        self.assertEqual(got["provider"], "codex")

    def test_codex_receives_the_prompt_on_stdin_not_argv(self):
        """E2BIG protection. A long sub-task instruction in argv would work in
        testing and die in production."""
        import worker
        marker = "PROMPT-MARKER-%d" % int(time.time())
        _run(worker.run_one("codex", marker, self.work, "plan"))
        with open(self.cx_stdin) as fh:
            self.assertIn(marker, fh.read())
        rows = [json.loads(l) for l in open(self.cx_argv) if l.strip()]
        self.assertTrue(rows)
        self.assertNotIn(marker, " ".join(rows[-1]))
        self.assertEqual(rows[-1][-1], "-", "argv must end with the stdin marker")

    def test_deepseek_completes_the_full_acp_handshake(self):
        """Against the SHIPPED stub, which answers with no content -- so the
        honest result is a failure naming exactly that, never an empty
        success. Result collection is proved separately, below."""
        import worker
        got = _run(worker.run_one("deepseek", "say something", self.work, "plan"))
        self.assertEqual(got["provider"], "deepseek")
        # authenticate() ran BEFORE session/new -- without it the fork defaults
        # the session to Gemini auth and refuses a valid DeepSeek key.
        self.assertTrue(os.path.exists(self.acp_auth),
                        "authenticate() was never called")
        rows = [json.loads(l) for l in open(self.acp_argv) if l.strip()]
        self.assertTrue(rows, "the ACP process was never spawned")
        self.assertIn("--acp", rows[-1])
        self.assertIn("--skip-trust", rows[-1])
        self.assertFalse(got["ok"])
        self.assertIn("no text", got["error"])

    # ---- DeepSeek result collection, against a stub that speaks ----------

    def _speaking_deepseek(self, reply="hello from deepseek", chunks=2):
        """Run one DeepSeek worker against the speaking ACP stub."""
        import worker
        saved = {k: os.environ.get(k) for k in
                 ("SUTRA_UI_DEEPSEEK_BIN", "SUTRA_TEST_ACP_REPLY",
                  "SUTRA_TEST_ACP_CHUNKS", "SUTRA_TEST_ACP_ARGV",
                  "SUTRA_TEST_ACP_AUTH", "SUTRA_TEST_ACP_PROMPT")}
        os.environ.update({
            "SUTRA_UI_DEEPSEEK_BIN": self.speaking_stub,
            "SUTRA_TEST_ACP_REPLY": reply,
            "SUTRA_TEST_ACP_CHUNKS": str(chunks),
            "SUTRA_TEST_ACP_ARGV": self.sp_argv,
            "SUTRA_TEST_ACP_AUTH": self.sp_auth,
            "SUTRA_TEST_ACP_PROMPT": self.sp_prompt,
        })
        try:
            return _run(worker.run_one("deepseek", "say something",
                                       self.work, "plan"))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_deepseek_result_is_actually_collected(self):
        """THE GAP THIS CLOSES. Real DeepSeek prose reaches Sutra only as
        session/update -> agent_message_chunk -> `token`
        (acp_runtime.py:465), and nothing in this repo drove that path before
        this test: a grep for agent_message_chunk finds one hit, the
        translator itself. So a worker that silently dropped every DeepSeek
        answer would have passed the whole suite."""
        for f in (self.sp_argv, self.sp_auth, self.sp_prompt):
            if os.path.exists(f):
                os.remove(f)
        got = self._speaking_deepseek()
        self.assertTrue(got["ok"], got.get("error"))
        self.assertEqual(got["text"], "hello from deepseek")
        self.assertEqual(got["provider"], "deepseek")

    def test_deepseek_chunks_are_joined_in_order(self):
        """The answer arrives in pieces; taking the last one would pass a
        single-chunk test and lose most of a real reply."""
        got = self._speaking_deepseek(
            reply="alpha beta gamma delta epsilon zeta", chunks=3)
        self.assertTrue(got["ok"], got.get("error"))
        self.assertEqual(got["text"], "alpha beta gamma delta epsilon zeta")

    def test_the_full_handshake_ran_in_order_before_the_prompt(self):
        """spawn -> initialize -> authenticate -> session/new -> session/prompt.
        initialize is implicit (AcpRuntime.spawn awaits it, and session/new
        would not have been answered without it); the rest are recorded from
        inside the stub."""
        for f in (self.sp_argv, self.sp_auth, self.sp_prompt):
            if os.path.exists(f):
                os.remove(f)
        got = self._speaking_deepseek()
        self.assertTrue(got["ok"], got.get("error"))
        argv = [json.loads(l) for l in open(self.sp_argv) if l.strip()][-1]
        self.assertIn("--acp", argv)
        self.assertIn("--skip-trust", argv)
        auth = [json.loads(l) for l in open(self.sp_auth) if l.strip()]
        self.assertEqual([a["methodId"] for a in auth], ["deepseek-api-key"])
        prompts = [json.loads(l) for l in open(self.sp_prompt) if l.strip()]
        self.assertEqual(len(prompts), 1, "exactly one turn")
        self.assertEqual(prompts[0]["prompt"],
                         [{"type": "text", "text": "say something"}])
        # session/new must have succeeded, which the stub refuses before auth
        self.assertEqual(prompts[0]["sessionId"], "speaking-session")

    def test_a_speaking_deepseek_worker_leaves_no_process_behind(self):
        before = self._child_count()
        self._speaking_deepseek()
        time.sleep(0.5)
        self.assertLessEqual(self._child_count(), before)

    # ---- what a worker must NOT do ---------------------------------------

    def test_no_worker_ever_resumes_a_session(self):
        """session_id is always None. A resumed worker would attach to a
        thread it does not own -- and codex would echo the id back as its own
        (switch.py records that measured behaviour)."""
        import worker
        _run(worker.run_one("claude", "x", self.work, "plan"))
        _run(worker.run_one("codex", "x", self.work, "plan"))
        for row in [json.loads(l) for l in open(self.cl_argv) if l.strip()]:
            self.assertNotIn("--resume", row)
        for row in [json.loads(l) for l in open(self.cx_argv) if l.strip()]:
            self.assertNotIn("resume", row)

    def test_the_claude_worker_carries_no_sutra_mcp_server(self):
        import worker
        _run(worker.run_one("claude", "x", self.work, "plan"))
        row = [json.loads(l) for l in open(self.cl_argv) if l.strip()][-1]
        self.assertNotIn("--mcp-config", row)
        self.assertNotIn("mcp__sutra__*", row)

    def test_a_worker_writes_no_chat_record(self):
        import worker
        chats = os.path.join(self.tmp, "chats")
        os.environ["SUTRA_UI_CHATS"] = chats
        try:
            before = sorted(os.listdir(chats)) if os.path.isdir(chats) else []
            _run(worker.run_one("claude", "x", self.work, "plan"))
            _run(worker.run_one("codex", "x", self.work, "plan"))
            after = sorted(os.listdir(chats)) if os.path.isdir(chats) else []
            self.assertEqual(before, after, "a worker wrote to the chat store")
        finally:
            os.environ.pop("SUTRA_UI_CHATS", None)

    def test_a_worker_does_not_move_the_global_provider(self):
        """settings.json read as BYTES, the same discipline
        test_chat_local_provider applies -- this is the claim the feature
        cannot be trusted to make about itself."""
        import worker
        path = os.environ["SUTRA_UI_SETTINGS"]
        before = open(path, "rb").read()
        _run(worker.run_one("codex", "x", self.work, "plan"))
        _run(worker.run_one("deepseek", "x", self.work, "plan"))
        self.assertEqual(open(path, "rb").read(), before)

    def test_a_worker_is_not_reachable_through_the_runtime_registry(self):
        """Registering one would make a throwaway process a legal target for
        a Shadow say."""
        import session_runtime
        import worker
        before = dict(session_runtime.RUNTIMES)
        _run(worker.run_one("claude", "x", self.work, "plan"))
        self.assertEqual(dict(session_runtime.RUNTIMES), before)

    # ---- refusals --------------------------------------------------------

    def test_an_unknown_provider_is_refused_not_spawned(self):
        import worker
        got = _run(worker.run_one("nope", "x", self.work, "plan"))
        self.assertFalse(got["ok"])
        self.assertIn("unknown provider", got["error"])

    def test_a_provider_without_an_adapter_is_refused(self):
        import worker
        got = _run(worker.run_one("gemini", "x", self.work, "plan"))
        self.assertFalse(got["ok"])

    def test_a_workdir_outside_the_root_is_refused(self):
        """Same confinement every other spawn path applies."""
        import worker
        got = _run(worker.run_one("claude", "x", "/etc", "plan"))
        self.assertFalse(got["ok"])
        self.assertIn("not allowed", got["error"])

    # ---- lifecycle -------------------------------------------------------

    def _child_count(self):
        out = subprocess.run(
            ["pgrep", "-f", "fake_(claude|codex|acp)_agent.py|speaking_acp.py"],
            capture_output=True, text=True)
        return len([l for l in out.stdout.split("\n") if l.strip()])

    def test_no_child_process_survives_a_completed_worker(self):
        import worker
        before = self._child_count()
        for pid in ("claude", "codex", "deepseek"):
            _run(worker.run_one(pid, "x", self.work, "plan"))
        time.sleep(0.5)
        self.assertLessEqual(self._child_count(), before,
                             "a worker left a process behind")

    def test_on_spawn_and_on_done_bracket_the_live_process(self):
        import worker
        seen = {"spawn": [], "done": []}
        _run(worker.run_one("claude", "x", self.work, "plan",
                            on_spawn=lambda rt: seen["spawn"].append(rt),
                            on_done=lambda rt: seen["done"].append(rt)))
        self.assertEqual(len(seen["spawn"]), 1)
        self.assertEqual(len(seen["done"]), 1)
        self.assertIs(seen["spawn"][0], seen["done"][0])

    def test_cancelling_a_worker_kills_its_process_group(self):
        """THE mandatory one. A stop mid-fan-out must not orphan a CLI."""
        import worker
        live = []

        async def go():
            task = asyncio.ensure_future(worker.run_one(
                "claude", "x", self.work, "plan",
                on_spawn=live.append))
            for _ in range(200):
                await asyncio.sleep(0.01)
                if live:
                    break
            self.assertTrue(live, "the worker never spawned")
            proc = live[0].proc
            self.assertIsNotNone(proc)
            pid = proc.pid
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return pid

        pid = _run(go())
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return          # gone, which is the pass condition
            time.sleep(0.05)
        self.fail("the worker's process %d survived cancellation" % pid)

    def test_orchestration_cancel_kills_a_live_worker(self):
        """The path ws_chat's Stop actually takes: orch.cancel(), not
        task.cancel()."""
        import fanout
        import worker
        orch = fanout.Orchestration()

        async def go():
            task = asyncio.ensure_future(worker.run_one(
                "claude", "x", self.work, "plan",
                on_spawn=orch.add, on_done=orch.done))
            for _ in range(200):
                await asyncio.sleep(0.01)
                if orch.live:
                    break
            self.assertTrue(orch.live, "the worker never registered")
            pid = list(orch.live)[0].proc.pid
            orch.cancel()
            try:
                await asyncio.wait_for(task, 10)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            return pid

        pid = _run(go())
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.05)
        self.fail("orch.cancel() left process %d running" % pid)

    # ---- end to end, through the engine ----------------------------------

    @staticmethod
    def _billing(models):
        """Pin fanout.cost_map for one block."""
        import contextlib
        import fanout

        @contextlib.contextmanager
        def cm():
            orig = fanout.cost_map
            fanout.cost_map = lambda pids: {p: models.get(p, "unknown")
                                            for p in pids}
            try:
                yield
            finally:
                fanout.cost_map = orig
        return cm()

    def test_an_unreadable_codex_credential_is_treated_as_expensive(self):
        """Live, unpinned: the qa codex stub answers no `login status`, so
        providers.codex_auth reports "unknown" -- and routing must not PREFER
        a provider whose billing it could not determine."""
        import fanout
        self.assertEqual(fanout.billing_model("codex"), "unknown")
        self.assertEqual(fanout.provider_cost("codex"), "high")
        self.assertEqual(fanout.billing_model("claude"), "subscription")
        self.assertEqual(
            fanout.choose_provider("light", ["claude", "codex"],
                                   fanout.cost_map(["claude", "codex"]))[0],
            "claude")

    def test_e2e_real_providers_through_the_orchestrator(self):
        """Planner + workers + merge, every call a real subprocess.

        The planner is stubbed at the PLAN TEXT only -- a canned reply, because
        qa/fake_claude_agent.py always answers "ack" and cannot emit a task
        list. Everything after the plan is real: real routing, real spawns,
        real collection, real ordering.
        """
        import fanout
        plan = json.dumps([
            {"instruction": "competitor one", "capability": "standard"},
            {"instruction": "competitor two", "capability": "deep"},
            {"instruction": "competitor three", "capability": "standard"},
        ])
        calls = []

        async def runner(pid, prompt, workdir, perm_mode, orch):
            import worker
            if prompt.startswith("You are planning how to execute one job"):
                return {"ok": True, "text": plan, "error": None, "provider": pid}
            calls.append((pid, prompt))
            return await worker.run_one(pid, prompt, workdir, perm_mode,
                                        on_spawn=orch.add, on_done=orch.done)

        # THE BILLING SCENARIO IS PINNED, not inherited from this machine.
        # cost_map() resolves codex by running `codex login status`, and the
        # qa stub does not implement it -- so unpinned, codex reads "unknown",
        # is treated as expensive (correctly), and every sub-task lands on
        # claude. That is the right ROUTING answer and the wrong TEST: this
        # one exists to drive two providers' real spawn paths at once.
        with self._billing({"claude": "subscription", "codex": "subscription",
                            "deepseek": "metered"}):
            out = _run(fanout.run("compare three competitors", "claude",
                                  self.work, "plan", runner=runner))
        self.assertTrue(out["ok"], out.get("detail"))
        self.assertEqual(len(out["tasks"]), 3)
        # balanced routing across the two providers rated for `standard`,
        # with the `deep` one gated to claude. Both real spawn paths run.
        self.assertEqual([t["provider"] for t in out["tasks"]],
                         ["claude", "claude", "codex"])
        self.assertEqual(out["counts"], {"claude": 2, "codex": 1})
        # order preserved, and each result belongs to its own task
        self.assertEqual([t["instruction"] for t in out["tasks"]],
                         ["competitor one", "competitor two", "competitor three"])
        self.assertEqual([t["status"] for t in out["tasks"]],
                         ["done", "done", "done"])
        self.assertEqual(out["tasks"][1]["result"], "ack")           # claude
        self.assertEqual(out["tasks"][2]["result"], "hello from codex")
        # the synthesis prompt carries every result, in order
        block = fanout.compose("original", "compare three competitors",
                               out["tasks"])
        self.assertIn("competitor one", block)
        self.assertLess(block.index("competitor one"),
                        block.index("competitor three"))
        self.assertTrue(block.startswith("original"))

    def test_e2e_one_dead_provider_does_not_lose_the_others(self):
        import fanout
        plan = json.dumps([{"instruction": "a", "capability": "standard"},
                           {"instruction": "b", "capability": "deep"},
                           {"instruction": "c", "capability": "standard"}])

        async def runner(pid, prompt, workdir, perm_mode, orch):
            import worker
            if prompt.startswith("You are planning how to execute one job"):
                return {"ok": True, "text": plan, "error": None, "provider": pid}
            if pid == "codex":
                # the stub's own "die before a thread" script -- a real refusal
                os.environ["SUTRA_FAKE_CODEX_SCRIPT"] = "no-thread"
            try:
                return await worker.run_one(pid, prompt, workdir, perm_mode,
                                            on_spawn=orch.add, on_done=orch.done)
            finally:
                os.environ["SUTRA_FAKE_CODEX_SCRIPT"] = "ok"

        with self._billing({"claude": "subscription", "codex": "subscription",
                            "deepseek": "metered"}):
            out = _run(fanout.run("three things", "claude", self.work, "plan",
                                  runner=runner))
        self.assertTrue(out["ok"], "a partial success must still synthesise")
        # a (standard) and b (deep) -> claude, both succeed; c (standard) ->
        # codex, which the runner kills with the stub's own "die before a
        # thread" script. One dead provider, two intact results.
        self.assertEqual([t["status"] for t in out["tasks"]],
                         ["done", "done", "failed"])
        self.assertEqual([t["provider"] for t in out["tasks"]],
                         ["claude", "claude", "codex"])
        block = fanout.results_block("three things", out["tasks"])
        self.assertIn("NOT COMPLETED", block)
        self.assertIn("2 succeeded, 1 did not", block)


if __name__ == "__main__":
    unittest.main()
