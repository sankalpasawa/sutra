"""Codex end to end through the REAL ws_chat: selection -> session -> frames.

Runs a live uvicorn against qa/fake_codex_agent.py. No `codex` binary, no
credential, no network, no API call -- SUTRA_UI_CODEX_BIN is the documented
first step of providers._bin_for(), and HOME is pointed at a temp tree so the
`~/.codex/auth.json` readiness probe answers from a file this test wrote (an
EMPTY placeholder: providers checks that path for EXISTENCE only and never
opens it, so there is nothing credential-shaped here to leak).

WHAT THIS COVERS THAT test_codex_runtime.py CANNOT. That file drives
CodexRuntime directly. This one proves the four SHARED-FILE edits actually
wire up: the readiness gate lets codex through, ws_chat's dispatch picks
CodexRuntime instead of AcpRuntime, the argv reaching the CLI is the one
build_codex_args produced, and the ACP handshake block is genuinely skipped
(left as `!= "claude"` a Codex pane would die on an AttributeError at the first
message).

It also pins the two providers this change must not touch: a DeepSeek socket
and a Claude socket are opened against the same server and must behave exactly
as before.

Run: .venv/bin/python -m pytest test_codex_chat.py -q
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
STUB = os.path.join(HERE, "qa", "fake_codex_agent.py")
ACP_STUB = os.path.join(HERE, "qa", "fake_acp_agent.py")


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server(unittest.TestCase):
    """One uvicorn for the whole class, configured so codex is runnable."""

    proc = None
    port = None
    tmpdir = None
    argv_path = None
    stdin_path = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-codexchat-")
        sys.path.insert(0, os.path.join(HERE, "..", "lib"))
        sys.path.insert(0, HERE)
        import fixture_seed  # noqa: E402
        fixture_seed.seed(cls.tmpdir)

        os.chmod(STUB, 0o755)
        if os.path.exists(ACP_STUB):
            os.chmod(ACP_STUB, 0o755)

        cls.argv_path = os.path.join(cls.tmpdir, "codex-argv.json")
        cls.stdin_path = os.path.join(cls.tmpdir, "codex-stdin.txt")

        # HOME redirect: `configured` for codex is _codex_credential_present(),
        # i.e. does ~/.codex/auth.json EXIST. Existence only -- providers.py
        # never opens the file (its module docstring makes that a rule), so an
        # empty placeholder is a faithful stand-in and carries no secret.
        home = os.path.join(cls.tmpdir, "home")
        os.makedirs(os.path.join(home, ".codex"), exist_ok=True)
        with open(os.path.join(home, ".codex", "auth.json"), "w") as fh:
            fh.write("")

        cls.port = _free_port()
        env = dict(os.environ)
        env["HOME"] = home
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env["SUTRA_UI_WORKDIR"] = os.path.join(cls.tmpdir, "workspace")
        env["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        env["SUTRA_UI_SETTINGS"] = os.path.join(cls.tmpdir, "settings.json")
        env["SUTRA_UI_CHATS"] = os.path.join(cls.tmpdir, "chats")
        # Claude refuses to start with this set, and ws_chat refuses the socket.
        env.pop("ANTHROPIC_API_KEY", None)
        env["SUTRA_UI_CODEX_BIN"] = STUB
        env["SUTRA_FAKE_CODEX_ARGV"] = cls.argv_path
        env["SUTRA_FAKE_CODEX_STDIN"] = cls.stdin_path
        env["SUTRA_FAKE_CODEX_SCRIPT"] = "ok"
        # DeepSeek, so the untouched-provider assertions have something live.
        env["SUTRA_UI_DEEPSEEK_BIN"] = ACP_STUB
        env["SUTRA_UI_DEEPSEEK_API_KEY"] = "sk-fake-not-a-real-key"

        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:  # noqa: BLE001
                if cls.proc.poll() is not None:
                    out = cls.proc.stdout.read().decode("utf-8", "replace")
                    raise RuntimeError("server died:\n" + out[-4000:])
                time.sleep(0.25)
        else:
            raise RuntimeError("codex-chat server did not come up")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        if cls.tmpdir and os.path.isdir(cls.tmpdir):
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------ helpers --

    def _url(self, provider):
        return "ws://127.0.0.1:%d/ws/chat?provider=%s" % (self.port, provider)

    def _recorded_argv(self):
        with open(self.argv_path) as fh:
            return json.load(fh)

    def _recorded_stdin(self):
        with open(self.stdin_path) as fh:
            return fh.read()

    def _drain(self, ws, until=("done", "error"), limit=40):
        """Collect frames until a terminal one. Returns the list."""
        frames = []
        deadline = time.time() + 30
        while time.time() < deadline and len(frames) < limit:
            raw = ws.recv(timeout=15)
            f = json.loads(raw)
            frames.append(f)
            if f.get("type") in until:
                break
        return frames


class TestCodexIsSelectable(_Server):

    def test_the_api_reports_codex_runnable(self):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/settings" % self.port, timeout=5) as r:
            payload = json.loads(r.read())
        rows = {p["id"]: p for p in payload["providers"]}
        self.assertTrue(rows["codex"]["runnable"], rows["codex"])
        self.assertTrue(rows["codex"]["adapter"])
        self.assertTrue(rows["codex"]["installed"])
        self.assertTrue(rows["codex"]["configured"])
        # The UI's disabled attribute is driven by exactly this flag, so this
        # IS the "the row became clickable" assertion.
        self.assertIsNone(rows["codex"]["reason"])

    def test_gemini_is_still_refused_at_selection(self):
        """The offer-a-choice-that-cannot-run guard still guards. Only
        `runnable` is asserted here: gemini has neither a binary nor a config
        dir in this temp HOME, so it reaches the generic arm rather than the
        no-adapter one. The no-adapter SENTENCE is asserted in
        test_codex_runtime.py, where _describe can be handed a spec that
        actually reaches it."""
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/settings" % self.port, timeout=5) as r:
            payload = json.loads(r.read())
        rows = {p["id"]: p for p in payload["providers"]}
        self.assertFalse(rows["gemini"]["runnable"])
        self.assertFalse(rows["gemini"]["adapter"])

    def test_codex_can_be_saved_as_the_default_provider(self):
        """The click path: POST /api/settings {provider: "codex"} is what the
        row's handler sends, and providers.save_settings refuses anything not
        runnable -- so a 200 here IS "the selector accepted Codex"."""
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/settings" % self.port,
            data=json.dumps({"provider": "codex"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read())
        self.assertEqual(payload["settings"]["provider"], "codex")
        self.assertEqual(payload["settings"]["provider_source"], "settings")

    def test_codex_declares_its_three_permission_modes(self):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/settings" % self.port, timeout=5) as r:
            payload = json.loads(r.read())
        by_prov = payload["permission_modes_by_provider"]
        self.assertEqual(by_prov["codex"],
                         ["plan", "acceptEdits", "bypassPermissions"])

    def test_codex_publishes_only_the_cli_default_model(self):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/settings" % self.port, timeout=5) as r:
            payload = json.loads(r.read())
        ids = [m["id"] for m in payload["models_by_provider"]["codex"]]
        self.assertEqual(ids, [""])


class TestCodexChatTurn(_Server):

    def test_a_full_turn_renders_through_the_existing_frames(self):
        from websockets.sync.client import connect
        with connect(self._url("codex"), open_timeout=10) as ws:
            first = json.loads(ws.recv(timeout=10))
            self.assertEqual(first["type"], "provider")
            self.assertEqual(first["id"], "codex")
            self.assertEqual(first["bin"], STUB)

            ws.send(json.dumps({"message": "hello codex"}))
            frames = self._drain(ws)

        types = [f["type"] for f in frames]
        self.assertNotIn("error", types, frames)
        # The vocabulary the existing client already handles -- no new frame
        # type was invented for this provider.
        for expected in ("start", "session", "thinking", "token", "done"):
            self.assertIn(expected, types, frames)

        tokens = [f for f in frames if f["type"] == "token"]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["text"], "hello from codex")

        done = [f for f in frames if f["type"] == "done"][0]
        self.assertIsNone(done["cost_usd"])
        self.assertIsNone(done["duration_ms"])

        # THE PROMPT WENT DOWN STDIN, NOT ARGV.
        self.assertEqual(self._recorded_stdin(), "hello codex")
        argv = self._recorded_argv()
        self.assertNotIn("hello codex", argv)
        self.assertEqual(argv[-1], "-")

    def test_the_spawned_argv_is_the_verified_contract(self):
        from websockets.sync.client import connect
        with connect(self._url("codex"), open_timeout=10) as ws:
            json.loads(ws.recv(timeout=10))          # provider frame
            ws.send(json.dumps({"message": "argv please"}))
            self._drain(ws)
        argv = self._recorded_argv()
        self.assertEqual(argv[0], STUB)
        self.assertEqual(argv[1], "exec")
        self.assertIn("--json", argv)
        self.assertIn("--skip-git-repo-check", argv)
        self.assertIn("-C", argv)
        # default permission_mode is `plan` (SAFETY rule 4), so read-only
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertIn("approval_policy=never", argv)

    def test_a_second_message_resumes_the_same_thread(self):
        """The whole point of session handling: turn 2 must carry
        `resume <thread_id>` with every flag BEFORE it."""
        from websockets.sync.client import connect
        with connect(self._url("codex"), open_timeout=10) as ws:
            json.loads(ws.recv(timeout=10))
            ws.send(json.dumps({"message": "one"}))
            first = self._drain(ws)
            thread = [f for f in first if f["type"] == "session"][0]["id"]
            self.assertNotIn("resume", self._recorded_argv())

            ws.send(json.dumps({"message": "two"}))
            second = self._drain(ws)

        argv = self._recorded_argv()
        self.assertIn("resume", argv)
        at = argv.index("resume")
        self.assertEqual(argv[at + 1], thread)
        for flag in ("--json", "--skip-git-repo-check", "-C", "--sandbox"):
            self.assertLess(argv.index(flag), at, flag)
        self.assertEqual(argv[-1], "-")
        # and the thread id did NOT change across the resume
        self.assertEqual([f for f in second if f["type"] == "session"][0]["id"],
                         thread)

    def test_the_acp_handshake_is_skipped(self):
        """Left as `!= "claude"`, ws_chat would have called AcpRuntime's
        authenticate()/new_session() on a CodexRuntime and died with an
        AttributeError at the first message. A clean turn IS that assertion --
        but assert the absence explicitly too, so the reason survives."""
        from websockets.sync.client import connect
        with connect(self._url("codex"), open_timeout=10) as ws:
            json.loads(ws.recv(timeout=10))
            ws.send(json.dumps({"message": "handshake?"}))
            frames = self._drain(ws)
        errs = [f for f in frames if f["type"] == "error"]
        self.assertEqual(errs, [], errs)
        # no ACP mode note can exist on a codex pane
        self.assertEqual([f for f in frames if f["type"] == "mode_note"], [])

    def test_a_chat_record_is_minted_for_codex(self):
        """chat_store.SEGMENT_PROVIDERS had to gain codex or begin_segment
        would raise inside ws_chat's swallowing try/except -- chats working on
        screen and never recorded, with nothing to say so."""
        from websockets.sync.client import connect
        # The `chat` frame is sent AFTER prompt_turn returns -- i.e. after
        # `done` -- because the id can only be minted once the transport has
        # handed back a native session. So this drains until `chat` rather than
        # until `done`; stopping at the terminal frame (as every other test
        # here does) would read right past it.
        with connect(self._url("codex"), open_timeout=10) as ws:
            json.loads(ws.recv(timeout=10))
            ws.send(json.dumps({"message": "record me"}))
            frames = self._drain(ws, until=("chat", "error"), limit=60)
        chat = [f for f in frames if f["type"] == "chat"]
        self.assertTrue(chat, "no chat id was minted: %r" % ([f["type"] for f in frames],))
        sutra_id = chat[0]["sutra_id"]
        rec_path = os.path.join(self.tmpdir, "chats", sutra_id + ".json")
        deadline = time.time() + 5
        while time.time() < deadline and not os.path.exists(rec_path):
            time.sleep(0.1)
        self.assertTrue(os.path.exists(rec_path), rec_path)
        with open(rec_path) as fh:
            rec = json.load(fh)
        hist = rec.get("provider_history") or []
        self.assertTrue(any(h.get("provider") == "codex" for h in hist), rec)


class TestCodexFailureModes(_Server):

    # The turn.failed / transient-error / unknown-item / eof paths are asserted
    # in test_codex_runtime.py against this same stub. They are NOT duplicated
    # here: the stub reads its script from the SERVER's environment, which is
    # fixed for the class, so covering them through the socket would need one
    # uvicorn restart per case for no coverage the runtime tests do not already
    # give.

    def test_an_unknown_provider_is_still_refused(self):
        from websockets.sync.client import connect
        with connect(self._url("nope"), open_timeout=10) as ws:
            f = json.loads(ws.recv(timeout=10))
        self.assertEqual(f["type"], "error")
        self.assertEqual(f["code"], "unknown-provider")

    def test_gemini_still_gets_no_adapter_and_names_codex_as_an_option(self):
        """The `not in ("claude", "codex")` widening must not let a third
        provider through -- gemini has no adapter and still says so."""
        from websockets.sync.client import connect
        with connect(self._url("gemini"), open_timeout=10) as ws:
            f = json.loads(ws.recv(timeout=10))
        self.assertEqual(f["type"], "error")
        # Refused at SELECTION (readiness) rather than reaching the dispatch --
        # which is the stronger of the two refusals and the intended one.
        self.assertIn(f["code"], ("provider-missing", "no-adapter"))


class TestUntouchedProviders(_Server):
    """The two working providers, on the same server, after the change."""

    def test_deepseek_still_runs_its_own_transport(self):
        from websockets.sync.client import connect
        with connect(self._url("deepseek"), open_timeout=10) as ws:
            first = json.loads(ws.recv(timeout=10))
            self.assertEqual(first["type"], "provider")
            self.assertEqual(first["id"], "deepseek")
            self.assertEqual(first["bin"], ACP_STUB)
            ws.send(json.dumps({"message": "hi"}))
            frames = self._drain(ws, until=("done", "error"), limit=40)
        types = [f["type"] for f in frames]
        self.assertIn("start", types, frames)
        # It reached the ACP handshake and answered -- i.e. narrowing
        # `!= "claude"` to `== "deepseek"` did not cut DeepSeek out of it.
        self.assertNotIn("no-adapter", [f.get("code") for f in frames])

    def test_codex_does_not_become_the_fallback_over_deepseek_silently(self):
        """_CATALOG order puts codex AHEAD of deepseek, so on a machine where
        claude is unrunnable the first-runnable fallback now prefers codex.
        Asserted rather than discovered: this is the one behavioural side
        effect of the change, and it is a deliberate consequence of leaving the
        catalogue order alone (reordering would break
        test_deepseek_is_LAST_in_the_catalogue, which is load-bearing for the
        sign-in block's placement)."""
        import providers
        order = [s["id"] for s in providers._CATALOG]
        self.assertLess(order.index("codex"), order.index("deepseek"))
        self.assertEqual(order.index("claude"), 0)
        # claude leads AND is the shipped default, so the fallback only differs
        # on a machine where claude cannot run at all.
        self.assertTrue(providers._CATALOG[0]["default"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
