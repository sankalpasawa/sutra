"""GOLDEN REPLAY -- what the three provider adapters emit today, frozen.

WHY THIS FILE EXISTS
The provider cleanup (2026-09-14) rewrites the dispatch layer: app.ws_chat's
dozen provider branches move behind one adapter interface, and the three runtime
classes are reshaped around it. Every one of those edits is meant to be
BEHAVIOUR-PRESERVING for people already using Sutra. "Meant to be" is not a
check. This file is the check.

It drives the REAL runtime classes -- session_runtime.SessionRuntime,
codex_runtime.CodexRuntime, acp_runtime.AcpRuntime -- against fake provider CLIs
over real pipes, records the exact sequence of client frames each one emits, and
compares that sequence against a committed JSON file under tests/golden/. It
also records the exact argv app.build_agent_args / build_codex_args /
build_acp_args produce for a matrix of inputs, and compares those too.

Nothing here mocks a runtime method. The only things replaced are the provider
binaries themselves, so the translation logic under test is the shipping code
from the first byte on the pipe to the last frame on the socket.


HOW TO RUN IT
    .venv/bin/python -m pytest -q test_provider_golden.py

HOW TO RE-RECORD (only when a change to the frames is INTENDED)
    SUTRA_GOLDEN_UPDATE=1 .venv/bin/python -m pytest -q test_provider_golden.py
then read `git diff tests/golden/` line by line. A re-record is a claim that the
wire changed on purpose; the diff is the evidence for it.

THE ADDITIVE ESCAPE HATCH
    SUTRA_GOLDEN_ADDITIVE=1 .venv/bin/python -m pytest -q test_provider_golden.py
The provider-cleanup spec (section D) says the `tool` frame GAINS fields --
`kind`, `title`, `detail`, `meta` -- while every existing field keeps its value,
and no frame is added, removed or reordered. That is the one change this file is
designed to permit. In additive mode a frame may carry keys the golden does not
have, but every key the golden DOES have must still be present with the same
value, and the frame list must still match in length, order and type. A frame
that disappeared, a value that changed, or a reordering still fails. Use it to
prove a spec-D change is additive; do not leave it on in CI.


WHAT IS NORMALISED, AND HOW
A golden can only be byte-for-byte if the volatile parts are removed FIRST.
`_normalise()` walks every recorded object and rewrites four classes of value.
It is applied to the recorded frames AND to the recorded argv, with the same
rules, so the two cannot drift apart.

 1. PATHS. Six real directories are replaced with stable tokens, longest match
    first so a nested path cannot be half-substituted:
        the per-run workdir           -> <workdir>
        this run's temp root          -> <tmp>
        org_api.registry_root()       -> <native_home>
        this checkout's directory     -> <app_dir>
        sys.executable                -> <python>
        the operator's home           -> <home>
    Both the literal path and its os.path.realpath are substituted, because
    macOS resolves /tmp through /private/tmp and the two reach the frames by
    different routes (one from our own argv, one from the child's getcwd()).

 2. GENERATED IDS. A full UUID, or any run of 16-or-more lowercase hex digits,
    becomes <id:1>, <id:2>, ... numbered in FIRST-SEEN order within one golden.
    The ordinal is the point: it proves the same id was carried through the
    turn (the `session` frame's id is the same one the `done` frame reports)
    without pinning the value, which is minted fresh on every run. The scripted
    fakes use fixed, non-hex session ids where they can, so in practice this
    rule fires only on ids the OS or the runtime generates.

 3. DURATIONS. Any value under a `duration_ms` key becomes "<duration_ms>" when
    it is not None. None stays None, because "this provider reports no duration"
    is itself part of the contract (Codex and DeepSeek both send None there).

 4. PROCESS EXIT AND STDERR are recorded, but a returncode is kept verbatim (it
    is part of the contract) while stderr text goes through the path rules
    above.

WHAT IS *NOT* NORMALISED, ON PURPOSE
Token counts, costs, `num_turns`, tool ids, tool names, summaries, exit codes,
`ok` flags, quota blocks and every frame `type`. Those are the contract. The
fakes emit fixed values for all of them, so any change in the golden is a change
in the translation code, never in the fixture.

ONE STUBBED FUNCTION, AND WHY
`providers.codex_efforts_for()` reads codex_models' on-disk cache, so the set of
reasoning efforts a Codex model accepts depends on what `model/list` last
returned on this machine. That is real behaviour, but it is not behaviour
build_codex_args owns, and a golden pinned to it would flap whenever the cache
refreshed. So the argv matrix pins it to a fixed tuple for the duration of that
one test and says so in the recorded case. Everything else -- the sandbox
mapping, the flag ORDER, the resume-goes-last rule, the writable-roots line --
is the real function.

WHY THE SPAWN IS NOT runtime.spawn()
All three runtimes call create_subprocess_exec with `process_group=0`, which is
Python 3.11+. The shared .venv here is 3.9.6, where that kwarg raises
TypeError -- which is why test_provider_spawn_group.py and test_acp_stderr.py
already fail in this environment. That is an environment problem, not a
behaviour one, and this file must not inherit it: a safety net that cannot run
protects nothing. So `_spawn_plain()` creates the child with the same stdio
wiring and the same 8 MiB line limit, minus the one kwarg the interpreter
refuses, and assigns it to `rt.proc` exactly as spawn() would. The process-group
property itself is already asserted by test_provider_spawn_group.py; it is not
this file's question.

WHICH FAKES
  Claude   qa/fake_claude_agent.py       plain answer, session capture, resume
                                         accepted, resume REFUSED
           tests/golden/fake_claude_rich.py   thinking, tools, tool failure,
                                         api_retry, result-is_error, background
                                         subagent, and a 14-tool matrix
  Codex    qa/fake_codex_agent.py        every one of its six scripts
  DeepSeek qa/fake_acp_agent.py          handshake, session/new, session/load,
                                         mode application, mode divergence
           tests/golden/fake_acp_rich.py prompt turn: chunks, tool call,
                                         permission request, quota, refusal,
                                         JSON-RPC error
Each fixture file carries its own header on why it exists beside the qa stub it
does not replace.
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_DIR = os.path.join(HERE, "tests", "golden")
QA_DIR = os.path.join(HERE, "qa")

FAKE_CLAUDE = os.path.join(QA_DIR, "fake_claude_agent.py")
FAKE_CODEX = os.path.join(QA_DIR, "fake_codex_agent.py")
FAKE_ACP = os.path.join(QA_DIR, "fake_acp_agent.py")
FAKE_CLAUDE_RICH = os.path.join(GOLDEN_DIR, "fake_claude_rich.py")
FAKE_ACP_RICH = os.path.join(GOLDEN_DIR, "fake_acp_rich.py")

UPDATE = os.environ.get("SUTRA_GOLDEN_UPDATE") == "1"
ADDITIVE = os.environ.get("SUTRA_GOLDEN_ADDITIVE") == "1"

# IMPORT-TIME ISOLATION, before `import app`. app.py runs _ensure_workdir() at
# module level and providers resolves its settings path at import, so an
# unguarded import would touch the operator's real workspace and settings file.
# Same preamble as test_codex_runtime / test_acp_stderr / test_provider_spawn_group.
_ENV_TMP = tempfile.mkdtemp(prefix="p0-golden-")
_WORKDIR = os.path.join(_ENV_TMP, "workspace")
os.makedirs(_WORKDIR, exist_ok=True)
os.environ["SUTRA_UI_WORKDIR"] = _WORKDIR
os.environ["SUTRA_UI_WORKDIR_ROOT"] = _ENV_TMP
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ["SUTRA_UI_CHATS"] = os.path.join(_ENV_TMP, "chats")
os.environ["SUTRA_UI_ROUTINES"] = os.path.join(_ENV_TMP, "routines")
os.environ.setdefault("SUTRA_NATIVE_HOME", os.path.join(_ENV_TMP, "native"))
os.environ.setdefault("SUTRA_SHADOW_HOME", os.path.join(_ENV_TMP, "shadow"))

sys.path.insert(0, HERE)

import app                                  # noqa: E402
import providers                            # noqa: E402
import acp_runtime                          # noqa: E402
from acp_runtime import AcpRuntime          # noqa: E402
from codex_runtime import CodexRuntime      # noqa: E402
from session_runtime import SessionRuntime  # noqa: E402


# ------------------------------------------------------------ normalisation --

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-f]{16,}")

#: Keys whose value is a wall-clock measurement and can never be pinned.
_VOLATILE_KEYS = ("duration_ms",)


def _path_subs():
    """(real path, token) pairs, longest first so nesting cannot half-match."""
    import org_api
    raw = [
        (_WORKDIR, "<workdir>"),
        (_ENV_TMP, "<tmp>"),
        (str(org_api.registry_root()), "<native_home>"),
        (HERE, "<app_dir>"),
        (sys.executable, "<python>"),
        (os.path.expanduser("~"), "<home>"),
    ]
    pairs = {}
    for path, token in raw:
        if not path:
            continue
        for variant in (path, os.path.realpath(path)):
            pairs[variant] = token
    return sorted(pairs.items(), key=lambda kv: -len(kv[0]))


class _Normaliser:
    """One id numbering per golden file -- see rule 2 in the module header."""

    def __init__(self):
        self.subs = _path_subs()
        self.ids = {}

    def _text(self, value):
        for real, token in self.subs:
            if real in value:
                value = value.replace(real, token)

        def sub(match):
            raw = match.group(0)
            if raw not in self.ids:
                self.ids[raw] = "<id:%d>" % (len(self.ids) + 1)
            return self.ids[raw]

        return _UUID_RE.sub(sub, value)

    def walk(self, obj, key=None):
        if key in _VOLATILE_KEYS and obj is not None:
            return "<%s>" % key
        if isinstance(obj, dict):
            return {k: self.walk(v, k) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.walk(v, key) for v in obj]
        if isinstance(obj, str):
            return self._text(obj)
        return obj


def _normalise(obj):
    """JSON-round-tripped so the recorded types match what a golden file can
    hold (a tuple is a list once it has been through disk)."""
    return json.loads(json.dumps(_Normaliser().walk(obj)))


# ---------------------------------------------------------------- the driver --

def _run(coro_factory):
    """One coroutine in a fresh loop. The runtimes build an asyncio.Event in
    __init__, so they must be constructed INSIDE the loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


async def _spawn_plain(args, cwd, env=None):
    """The runtimes' own spawn, minus `process_group=0`. See the module header
    for why that one kwarg is dropped here and nowhere else."""
    return await asyncio.create_subprocess_exec(
        *args, cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=8 * 1024 * 1024,
        env=dict(os.environ, **(env or {})))


class _Recorder:
    """The websocket's send_json, replaced by a list. Frames arrive here in the
    exact order the adapter emitted them."""

    def __init__(self):
        self.frames = []
        self.boundaries = []

    async def emit(self, frame):
        self.frames.append(frame)

    def observer(self, frame):
        # Subscribers see every frame the primary sees PLUS the internal
        # _turn_boundary, which never reaches the primary. Only the boundary is
        # kept, so the recording is not doubled.
        if frame.get("type") == "_turn_boundary":
            self.boundaries.append(frame)


def _result(out):
    """The 5-tuple every adapter's turn returns, as a named dict."""
    session_id, got_text, got_result, result_error, eof = out
    return {"session_id": session_id, "got_text": got_text,
            "got_result": got_result, "result_error": result_error, "eof": eof}


async def _drain(proc):
    """Close stdin, reap, and return what the child said on the way out."""
    try:
        if proc.stdin is not None and not proc.stdin.is_closing():
            proc.stdin.close()
    except (OSError, AttributeError, RuntimeError):
        pass
    try:
        err = await asyncio.wait_for(proc.stderr.read(), 5)
    except Exception:
        err = b""
    try:
        await asyncio.wait_for(proc.wait(), 5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    return {"returncode": proc.returncode,
            "stderr": err.decode("utf-8", "replace").strip()}


# ------------------------------------------------------------------- Claude --

async def _claude_turn(binary, env, script_env=None, resume=None, send=True,
                       message="hello"):
    args = app.build_agent_args(binary, message, "plan", session_id=resume,
                                stream_input=True)
    rec = _Recorder()
    rt = SessionRuntime()
    rt.subscribe(rec.observer)
    rt.proc = await _spawn_plain(args, _WORKDIR, dict(env, **(script_env or {})))
    rt.key = tuple(a for a in args if a not in ("--resume", resume))
    sent_error = None
    if send:
        try:
            await rt.send_user_frame(message)
        except Exception as exc:            # a refused --resume dies first
            sent_error = type(exc).__name__
    out = await rt.demux_turn(rec.emit, None)
    exit_info = await _drain(rt.proc)
    return {
        "argv": args,
        "send_error": sent_error,
        "frames": rec.frames,
        "boundaries": rec.boundaries,
        "result": _result(out),
        "exit": exit_info,
        "state": rt.state,
        "open_tools": sorted(rt.open_tools),
    }


# -------------------------------------------------------------------- Codex --

async def _codex_turn(perm_mode="plan", script="ok", model=None, session_id=None,
                      opts=None, message="hello"):
    argv_log = os.path.join(_ENV_TMP, "codex-argv-%s.jsonl" % script)
    stdin_log = os.path.join(_ENV_TMP, "codex-stdin-%s.txt" % script)
    for path in (argv_log, stdin_log):
        if os.path.exists(path):
            os.remove(path)
    args = app.build_codex_args(FAKE_CODEX, perm_mode, _WORKDIR, model=model,
                                session_id=session_id, opts=opts)
    rec = _Recorder()
    rt = CodexRuntime()
    rt.subscribe(rec.observer)
    rt.proc = await _spawn_plain(args, _WORKDIR, {
        "SUTRA_FAKE_CODEX_SCRIPT": script,
        "SUTRA_FAKE_CODEX_ARGV": argv_log,
        "SUTRA_FAKE_CODEX_STDIN": stdin_log})
    rt.key = tuple(args)
    out = await rt.prompt_turn(message, rec.emit, session_id)
    exit_info = await _drain(rt.proc)
    spawned = []
    if os.path.exists(argv_log):
        with open(argv_log, encoding="utf-8") as fh:
            spawned = [json.loads(line) for line in fh if line.strip()]
    delivered = ""
    if os.path.exists(stdin_log):
        with open(stdin_log, encoding="utf-8") as fh:
            delivered = fh.read()
    return {
        "argv": args,
        "argv_as_spawned": spawned,
        "prompt_on_stdin": delivered,
        "frames": rec.frames,
        "boundaries": rec.boundaries,
        "result": _result(out),
        "exit": exit_info,
        "state": rt.state,
        "session_id_field": rt.session_id,
        "last_warning": rt.last_warning,
        "open_tools": sorted(rt.open_tools),
    }


# ----------------------------------------------------------------- DeepSeek --

async def _acp_connect(binary, env, model=None):
    """spawn() + the reader/stderr tasks + initialize, minus process_group."""
    args = app.build_acp_args(binary, model)
    rt = AcpRuntime()
    rt.proc = await _spawn_plain(args, _WORKDIR, env)
    rt.key = tuple(args)
    rt._stderr_chunks = []
    rt._stderr_task = asyncio.ensure_future(rt._pump_stderr())
    rt._reader_task = asyncio.ensure_future(rt._reader_loop())
    caps = await rt.initialize()
    return rt, args, caps


async def _acp_close(rt):
    for task in (rt._reader_task, rt._stderr_task):
        if task is not None:
            task.cancel()
    return await _drain(rt.proc)


async def _acp_session(binary, env, perm_mode="plan", resume=None, model=None,
                       script=None, prompt=None, authenticate=True):
    script_env = dict(env)
    if script:
        script_env["SUTRA_GOLDEN_ACP_SCRIPT"] = script
    rt, args, caps = await _acp_connect(binary, script_env, model)
    rec = _Recorder()
    rt.subscribe(rec.observer)

    unauthed_new = None
    if not authenticate:
        # The measured first-run failure: session/new before authenticate comes
        # back as a Gemini error on a DeepSeek key. Recorded, then fixed.
        resp = await rt._call("session/new", {"cwd": _WORKDIR, "mcpServers": []})
        unauthed_new = resp.get("error")
    else:
        await rt.authenticate("a-key-whose-value-is-never-recorded")

    session_id = None
    session_error = None
    if authenticate:
        try:
            session_id = await rt.new_session(_WORKDIR, perm_mode,
                                              session_id=resume, mcp_servers=[])
        except RuntimeError as exc:
            session_error = str(exc)

    turn = None
    if prompt is not None and session_id:
        turn = _result(await rt.prompt_turn(prompt, rec.emit))

    exit_info = await _acp_close(rt)
    return {
        "argv": args,
        "agent_capabilities": caps,
        "unauthenticated_session_new_error": unauthed_new,
        "session_id": session_id,
        "session_error": session_error,
        "acp_mode": rt.acp_mode,
        "acp_mode_note": rt.acp_mode_note,
        "effective_permission_mode": rt.effective_permission_mode,
        "frames": rec.frames,
        "boundaries": rec.boundaries,
        "result": turn,
        "exit": exit_info,
        "state": rt.state,
    }


# ------------------------------------------------------------ the base class --

class GoldenCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        # A checkout that lost the executable bit (a zip, a copy, a patch
        # applied with a tool that drops modes) would fail here for a reason
        # that has nothing to do with the code under test.
        for fixture in (FAKE_CLAUDE_RICH, FAKE_ACP_RICH):
            if os.path.exists(fixture) and not os.access(fixture, os.X_OK):
                os.chmod(fixture, 0o755)

    def _assert_additive(self, expected, actual, path="$"):
        if isinstance(expected, dict):
            self.assertIsInstance(actual, dict, "%s: shape changed" % path)
            for key, value in expected.items():
                self.assertIn(key, actual, "%s.%s was dropped" % (path, key))
                self._assert_additive(value, actual[key], "%s.%s" % (path, key))
            return
        if isinstance(expected, list):
            self.assertIsInstance(actual, list, "%s: shape changed" % path)
            self.assertEqual(len(expected), len(actual),
                             "%s: %d entries became %d -- additive mode permits "
                             "NEW FIELDS, never a new, missing or reordered frame"
                             % (path, len(expected), len(actual)))
            for i, value in enumerate(expected):
                self._assert_additive(value, actual[i], "%s[%d]" % (path, i))
            return
        self.assertEqual(expected, actual, "%s changed" % path)

    def check(self, name, actual):
        """Compare one recording against tests/golden/<name>.json."""
        path = os.path.join(GOLDEN_DIR, name + ".json")
        actual = _normalise(actual)
        if UPDATE:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(actual, indent=2) + "\n")
            return actual
        self.assertTrue(
            os.path.exists(path),
            "no golden at %s -- record it with SUTRA_GOLDEN_UPDATE=1 and read "
            "the diff before committing it" % path)
        with open(path, encoding="utf-8") as fh:
            expected = json.load(fh)
        if ADDITIVE:
            self._assert_additive(expected, actual)
        else:
            self.assertEqual(
                expected, actual,
                "%s no longer matches its golden. If this change is the "
                "spec-D one (the `tool` frame gaining kind/title/detail/meta "
                "while every existing field keeps its value), re-run with "
                "SUTRA_GOLDEN_ADDITIVE=1 to prove it is additive, then "
                "re-record with SUTRA_GOLDEN_UPDATE=1." % name)
        return actual


# ------------------------------------------------------------------- Claude --

class TestClaudeGolden(GoldenCase):
    """session_runtime.SessionRuntime, driven over a real pipe."""

    ENV = {"SUTRA_FAKE_CLAUDE_SESSION": "claude-golden-session"}

    def test_minimal_stub_plain_answer(self):
        """qa/fake_claude_agent.py: sysinit, session capture, token, done."""
        out = _run(lambda: _claude_turn(FAKE_CLAUDE, self.ENV))
        self.check("claude_minimal_text", out)
        self.assertEqual([f["type"] for f in out["frames"]],
                         ["session", "sysinit", "token", "done"])

    def test_resume_accepted_keeps_the_id(self):
        """--resume with an id the CLI knows: the SAME id comes back, and the
        argv carries --resume. The reuse key is stored resume-free."""
        env = dict(self.ENV, SUTRA_FAKE_CLAUDE_KNOWN="claude-golden-session")
        out = _run(lambda: _claude_turn(FAKE_CLAUDE, env,
                                        resume="claude-golden-session"))
        self.check("claude_resume_accepted", out)
        self.assertIn("--resume", out["argv"])
        self.assertEqual(out["result"]["session_id"], "claude-golden-session")

    def test_resume_refused_is_eof_with_stderr(self):
        """A --resume id the CLI cannot resolve: stderr, non-zero, and NOTHING
        on stdout. The turn must read as eof with no frames -- that is what
        app.py's resume_unverified branch keys off."""
        env = dict(self.ENV, SUTRA_FAKE_CLAUDE_KNOWN="some-other-id")
        out = _run(lambda: _claude_turn(FAKE_CLAUDE, env, resume="a-foreign-id",
                                        send=False))
        self.check("claude_resume_refused", out)
        self.assertEqual(out["frames"], [])
        self.assertTrue(out["result"]["eof"])
        self.assertEqual(out["exit"]["returncode"], 1)

    def _rich(self, script):
        return _run(lambda: _claude_turn(
            FAKE_CLAUDE_RICH, {}, {"SUTRA_GOLDEN_CLAUDE_SCRIPT": script}))

    def test_rich_text(self):
        out = self._rich("text")
        self.check("claude_rich_text", out)

    def test_rich_thinking(self):
        """A thinking block is PRESENCE ONLY -- the text must never be
        forwarded."""
        out = self._rich("thinking")
        self.check("claude_rich_thinking", out)
        thinking = [f for f in out["frames"] if f["type"] == "thinking"]
        self.assertEqual(len(thinking), 1)
        self.assertEqual(list(thinking[0].keys()), ["type"])

    def test_rich_tool_call_and_result(self):
        """tool start then tool end, correlated by id, with the shell command
        forwarded in full and the result text attached."""
        out = self._rich("tool")
        self.check("claude_rich_tool", out)
        tools = [f for f in out["frames"] if f["type"] == "tool"]
        self.assertEqual([t["phase"] for t in tools], ["start", "end"])
        self.assertEqual(tools[0]["id"], tools[1]["id"])
        self.assertEqual(tools[0]["command"], "echo hello")
        self.assertTrue(tools[1]["ok"])

    def test_rich_tool_failure(self):
        out = self._rich("tool_fail")
        self.check("claude_rich_tool_fail", out)
        end = [f for f in out["frames"] if f.get("phase") == "end"][0]
        self.assertFalse(end["ok"])

    def test_rich_api_retry(self):
        """A rate-limit backoff must reach the pane as `retrying`, or a waiting
        turn is indistinguishable from a wedged one."""
        out = self._rich("retry")
        self.check("claude_rich_retry", out)
        self.assertEqual(out["frames"][2]["type"], "retrying")

    def test_rich_result_error(self):
        """A `result` carrying is_error must NOT produce a `done` frame; the
        reason rides out on the 5-tuple instead."""
        out = self._rich("error")
        self.check("claude_rich_error", out)
        self.assertNotIn("done", [f["type"] for f in out["frames"]])
        self.assertTrue(out["result"]["result_error"])

    def test_rich_background_subagent(self):
        """The launch RECEIPT must not close the tool; the later
        task_notification must."""
        out = self._rich("subagent")
        self.check("claude_rich_subagent", out)
        ends = [f for f in out["frames"]
                if f["type"] == "tool" and f["phase"] == "end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]["output"], "found it in app.py")

    def test_rich_tools_matrix(self):
        """One tool_use per family in the spec's kind table. TODAY every one of
        them arrives as the same flat `tool` frame -- which is the thing the
        spec says will change, and the reason this recording exists."""
        out = self._rich("tools_matrix")
        self.check("claude_rich_tools_matrix", out)
        starts = [f for f in out["frames"]
                  if f["type"] == "tool" and f["phase"] == "start"]
        self.assertEqual(len(starts), 14)
        self.assertEqual(len(set(f["id"] for f in starts)), 14)


# -------------------------------------------------------------------- Codex --

class TestCodexGolden(GoldenCase):
    """codex_runtime.CodexRuntime, driven over a real pipe."""

    def test_ok_script(self):
        """thread.started -> session, turn.started -> thinking, agent_message
        -> token, turn.completed -> done with the per-turn token counts."""
        out = _run(lambda: _codex_turn(script="ok"))
        self.check("codex_ok", out)
        self.assertEqual([f["type"] for f in out["frames"]],
                         ["session", "thinking", "token", "done"])

    def test_prompt_is_delivered_on_stdin_not_argv(self):
        """The prompt must reach the child on stdin. In argv it works until it
        dies at E2BIG, which is the failure switch.py exists to predict."""
        out = _run(lambda: _codex_turn(script="ok", message="a prompt body"))
        self.assertEqual(out["prompt_on_stdin"], "a prompt body")
        self.assertNotIn("a prompt body", out["argv"])
        self.assertEqual(out["argv"][-1], "-")

    def test_command_execution_item(self):
        out = _run(lambda: _codex_turn(script="tool"))
        self.check("codex_tool", out)
        tools = [f for f in out["frames"] if f["type"] == "tool"]
        self.assertEqual([t["phase"] for t in tools], ["start", "end"])
        self.assertEqual(tools[0]["name"], "command_execution")
        self.assertTrue(tools[1]["ok"])

    def test_turn_failed(self):
        """turn.failed is terminal and its message is NESTED under .error --
        unlike the transient top-level `error`, whose message is flat."""
        out = _run(lambda: _codex_turn(script="failed"))
        self.check("codex_failed", out)
        self.assertEqual(out["result"]["result_error"],
                         "unexpected status 401 Unauthorized")
        self.assertTrue(out["result"]["got_result"])

    def test_transient_error_does_not_end_the_turn(self):
        out = _run(lambda: _codex_turn(script="transient"))
        self.check("codex_transient", out)
        self.assertIn("retrying", [f["type"] for f in out["frames"]])
        self.assertIsNone(out["result"]["result_error"])

    def test_unknown_items_are_dropped_not_fatal(self):
        out = _run(lambda: _codex_turn(script="unknown-items"))
        self.check("codex_unknown_items", out)
        self.assertTrue(out["result"]["got_result"])

    def test_eof_mid_turn(self):
        """SIGTERM's measured shape: stdout ends with no terminal event."""
        out = _run(lambda: _codex_turn(script="eof"))
        self.check("codex_eof", out)
        self.assertTrue(out["result"]["eof"])
        self.assertFalse(out["result"]["got_result"])

    def test_resume_carries_the_thread_id(self):
        """`resume <id>` goes LAST, after every flag, and the same thread id
        comes back."""
        out = _run(lambda: _codex_turn(script="ok", session_id="thread-abc"))
        self.check("codex_resume", out)
        self.assertEqual(out["argv"][-3:], ["resume", "thread-abc", "-"])
        self.assertEqual(out["result"]["session_id"], "thread-abc")


# ----------------------------------------------------------------- DeepSeek --

class TestAcpGolden(GoldenCase):
    """acp_runtime.AcpRuntime, driven over a real pipe."""

    def test_handshake_and_new_session(self):
        """qa/fake_acp_agent.py: initialize, the unauthenticated refusal that
        a DeepSeek key alone still hits, authenticate, session/new, set_mode."""
        out = _run(lambda: _acp_session(FAKE_ACP, {}, perm_mode="plan",
                                        authenticate=False))
        self.check("acp_unauthenticated", out)
        self.assertEqual(out["unauthenticated_session_new_error"]["code"], -32000)

    def test_new_session_applies_the_mode(self):
        out = _run(lambda: _acp_session(FAKE_ACP, {}, perm_mode="acceptEdits"))
        self.check("acp_new_session_accept_edits", out)
        self.assertEqual(out["acp_mode"], "autoEdit")
        self.assertIsNone(out["acp_mode_note"])

    def test_mode_without_an_equivalent_is_reported(self):
        """dontAsk has no ACP mode. The session runs `default` and the
        divergence must be STATED, never swallowed."""
        out = _run(lambda: _acp_session(FAKE_ACP, {}, perm_mode="dontAsk"))
        self.check("acp_mode_no_equivalent", out)
        self.assertEqual(out["acp_mode"], "default")
        self.assertEqual(out["acp_mode_note"]["asked"], "dontAsk")

    def test_session_load_resume(self):
        """session/load is tried first for a known id; the id is kept from what
        was requested, because zLoadSessionResponse does not echo it back."""
        out = _run(lambda: _acp_session(FAKE_ACP, {}, resume="an-old-session"))
        self.check("acp_session_load", out)
        self.assertEqual(out["session_id"], "an-old-session")

    def test_argv_carries_the_model(self):
        out = _run(lambda: _acp_session(FAKE_ACP, {}, model="deepseek-v4-pro"))
        self.check("acp_argv_model", out)
        self.assertEqual(out["argv"][-2:], ["-m", "deepseek-v4-pro"])

    def test_prompt_turn_chunks_and_tool(self):
        """The rich fixture: message chunk, thought chunk, a dropped `plan`
        update, tool start, tool end, and done with the sanitised quota."""
        out = _run(lambda: _acp_session(FAKE_ACP_RICH, {}, script="plain",
                                        prompt="write the file"))
        self.check("acp_prompt_plain", out)
        self.assertEqual([f["type"] for f in out["frames"]],
                         ["token", "thinking", "tool", "tool", "token", "done"])
        quota = out["frames"][-1]["quota"]
        self.assertNotIn("an_unknown_key", quota["model_usage"][0])

    def test_permission_request_declined_under_plan(self):
        """plan DECLINES the tool -- and today's audit line says "approved".

        A BUG THIS GOLDEN FOUND, 2026-09-14, recorded rather than fixed
        (acp_runtime.py belongs to W1, not to this workstream).

        The DECISION is right. _choose_permission_option("plan", "edit", ...)
        picks the offered option whose kind is `reject_once`, so what crosses
        the wire is the cancel option and the tool really is refused -- the
        argv_acp_permission_options golden pins that for all six modes.

        The LABEL is wrong. _answer_request_permission sets

            approved = option_id is not None

        and a rejection has an optionId too, so `approved` is True for every
        decision the function can make. The audit `notice` therefore reads
        "approved permission request ... -- mode 'plan'" on a call that was
        declined. It has never been seen, because `notice` has no client
        handler (session_runtime.py's own KNOWN GAP block says the same of its
        three emit sites), so the line is parsed and dropped.

        Asserted as it behaves today so the golden is honest. When W1 fixes it,
        this test and acp_permission_plan.json both change in the same commit,
        and the diff is the record of the fix.
        """
        out = _run(lambda: _acp_session(FAKE_ACP_RICH, {}, perm_mode="plan",
                                        script="permission",
                                        prompt="write the file"))
        self.check("acp_permission_plan", out)
        # The wire: a reject option was chosen.
        self.assertEqual(
            acp_runtime._choose_permission_option(
                "plan", "edit",
                [{"optionId": "proceed_once", "kind": "allow_once"},
                 {"optionId": "cancel", "kind": "reject_once"}],
                "Write /tmp/written.txt"),
            "cancel")
        # The label: FIXED on 2026-09-14. It used to read "approved" for a request
        # that was declined, because `approved = option_id is not None` is true of a
        # rejection too (a rejection carries an option id). The audit line now reads
        # the chosen option's ACP kind, so the decision and the label agree.
        notice = [f for f in out["frames"] if f["type"] == "notice"][0]
        self.assertTrue(
            notice["text"].startswith("declined"),
            "a declined permission request must not be audited as approved: " + notice["text"])

    def test_permission_request_approved_under_accept_edits(self):
        out = _run(lambda: _acp_session(FAKE_ACP_RICH, {},
                                        perm_mode="acceptEdits",
                                        script="permission",
                                        prompt="write the file"))
        self.check("acp_permission_accept_edits", out)
        notice = [f for f in out["frames"] if f["type"] == "notice"][0]
        self.assertTrue(notice["text"].startswith("approved"))

    def test_sutra_mcp_carve_out_beats_the_mode(self):
        """A sutra MCP tool is approved even under plan -- the same carve-out
        build_agent_args applies with --allowedTools on Claude."""
        out = _run(lambda: _acp_session(FAKE_ACP_RICH, {}, perm_mode="plan",
                                        script="sutra_mcp",
                                        prompt="propose something"))
        self.check("acp_permission_sutra_mcp", out)
        notice = [f for f in out["frames"] if f["type"] == "notice"][0]
        self.assertTrue(notice["text"].startswith("approved"))

    def test_refusal_stop_reason(self):
        out = _run(lambda: _acp_session(FAKE_ACP_RICH, {}, script="refusal",
                                        prompt="do a bad thing"))
        self.check("acp_refusal", out)
        self.assertEqual(out["result"]["result_error"], "stopReason=refusal")

    def test_jsonrpc_error_on_prompt(self):
        out = _run(lambda: _acp_session(FAKE_ACP_RICH, {}, script="rpc_error",
                                        prompt="hello"))
        self.check("acp_rpc_error", out)
        self.assertEqual(out["result"]["result_error"],
                         "DeepSeek API returned 429")


# ------------------------------------------------------------- argv matrices --

_CLAUDE_FULL_OPTS = {
    "fork_session": True,
    "fallback_model": "sonnet",
    "effort": "high",
    "add_dir": ["~/Desktop", "/etc"],          # /etc is outside $HOME: dropped
    "allowed_tools": ["Bash", "Read"],
    "disallowed_tools": ["WebFetch"],
    "append_system_prompt": "be brief",
    "max_budget_usd": 2.5,
}

_CODEX_FULL_OPTS = {
    "reasoning_summary": "detailed",
    "verbosity": "low",
    "reasoning_effort": "high",
    "not_a_real_key": "must never reach argv",
}

#: What providers.codex_efforts_for() is pinned to for the argv matrix. See the
#: "ONE STUBBED FUNCTION" note in the module header.
_STUB_CODEX_EFFORTS = ("low", "medium", "high", "xhigh")


class TestArgvGolden(GoldenCase):
    """The exact argv each builder produces, across every permission mode, with
    and without a model, with and without turn options, resume and fresh."""

    def test_claude_argv_matrix(self):
        cases = []
        for perm in providers.PERMISSION_MODES:
            for model in (None, "opus"):
                for session_id in (None, "a-claude-session"):
                    for opts_name, opts in (("none", None),
                                            ("full", _CLAUDE_FULL_OPTS)):
                        for stream in (True, False):
                            cases.append({
                                "case": {"perm_mode": perm, "model": model,
                                         "session_id": session_id,
                                         "opts": opts_name,
                                         "stream_input": stream},
                                "argv": app.build_agent_args(
                                    "claude", "the prompt", perm,
                                    session_id=session_id, model=model,
                                    opts=opts, stream_input=stream),
                            })
        # extra_settings is the Shadow-worker path: it MERGES into the same
        # inline --settings object rather than emitting a second one.
        cases.append({
            "case": {"perm_mode": "plan", "extra_settings": True},
            "argv": app.build_agent_args(
                "claude", "the prompt", "plan", stream_input=True,
                extra_settings={"permissions": {"allow": ["Bash"]}}),
        })
        self.check("argv_claude", cases)
        self.assertEqual(len(cases), 6 * 2 * 2 * 2 * 2 + 1)
        for entry in cases:
            self.assertEqual(entry["argv"].count("--allowedTools") <= 1, True)
            self.assertEqual(entry["argv"].count("--settings") <= 1, True)

    def test_codex_argv_matrix(self):
        saved = providers.codex_efforts_for
        providers.codex_efforts_for = lambda model_id=None: _STUB_CODEX_EFFORTS
        try:
            cases = []
            for perm in providers.PERMISSION_MODES:
                for model in (None, "gpt-5.6-terra"):
                    for session_id in (None, "a-codex-thread"):
                        for opts_name, opts in (("none", None),
                                                ("full", _CODEX_FULL_OPTS)):
                            cases.append({
                                "case": {"perm_mode": perm, "model": model,
                                         "session_id": session_id,
                                         "opts": opts_name,
                                         "codex_efforts_stub":
                                             list(_STUB_CODEX_EFFORTS)},
                                "argv": app.build_codex_args(
                                    "codex", perm, _WORKDIR, model=model,
                                    session_id=session_id, opts=opts),
                            })
            self.check("argv_codex", cases)
        finally:
            providers.codex_efforts_for = saved
        self.assertEqual(len(cases), 6 * 2 * 2 * 2)
        for entry in cases:
            self.assertEqual(entry["argv"][-1], "-")
            if entry["case"]["session_id"]:
                self.assertEqual(entry["argv"][-3], "resume")

    def test_codex_sandbox_and_mode_notes(self):
        """The mode -> sandbox mapping and the divergence copy the pane shows
        when Codex cannot honour a globally stored mode."""
        rows = []
        for perm in providers.PERMISSION_MODES:
            rows.append({
                "perm_mode": perm,
                "sandbox": app._CODEX_SANDBOX_FOR_MODE.get(perm),
                "supported": perm in providers.permission_modes_for("codex"),
                "mode_note": app.codex_mode_note(perm),
            })
        self.check("argv_codex_mode_notes", rows)

    def test_codex_turn_config_matrix(self):
        saved = providers.codex_efforts_for
        providers.codex_efforts_for = lambda model_id=None: _STUB_CODEX_EFFORTS
        try:
            rows = []
            for opts in (None, {}, _CODEX_FULL_OPTS,
                         {"reasoning_summary": "bogus"},
                         {"verbosity": ""},
                         {"reasoning_effort": "ultracode"},
                         {"reasoning_effort": "xhigh"},
                         "not a dict"):
                rows.append({"opts": opts,
                             "pairs": app.codex_turn_config(opts, "gpt-5.6-terra")})
            self.check("argv_codex_turn_config", rows)
        finally:
            providers.codex_efforts_for = saved

    def test_acp_argv_matrix(self):
        cases = []
        for model in (None, "", "deepseek-v4-pro", "deepseek-v4-flash"):
            cases.append({"case": {"model": model},
                          "argv": app.build_acp_args("deepseek", model)})
        self.check("argv_acp", cases)

    def test_acp_permission_option_matrix(self):
        """DeepSeek has no per-turn argv, so this is its equivalent decision
        surface: which offered option Sutra picks, per mode and tool kind."""
        options = [{"optionId": "proceed_once", "kind": "allow_once"},
                   {"optionId": "proceed_always", "kind": "allow_always"},
                   {"optionId": "cancel", "kind": "reject_once"}]
        rows = []
        for perm in providers.PERMISSION_MODES:
            for kind in ("edit", "delete", "move", "execute", "read", "fetch",
                         "search", "think", "other", None):
                for title in (None, "Write /tmp/x", "propose (sutra MCP Server)"):
                    rows.append({
                        "perm_mode": perm, "tool_kind": kind, "title": title,
                        "chosen": acp_runtime._choose_permission_option(
                            perm, kind, options, title),
                    })
        self.check("argv_acp_permission_options", rows)
        self.assertEqual(len(rows), 6 * 10 * 3)

    def test_acp_mode_map(self):
        self.check("argv_acp_mode_map", {
            "mode_for_permission_mode":
                acp_runtime._ACP_MODE_FOR_PERMISSION_MODE,
            "default_mode": acp_runtime._DEFAULT_ACP_MODE,
            "allow_kinds": acp_runtime._ALLOW_KINDS,
            "reject_kinds": acp_runtime._REJECT_KINDS,
            "sutra_mcp_title_suffix": acp_runtime._SUTRA_MCP_TITLE_SUFFIX,
        })

    def test_permission_modes_per_provider(self):
        """Which modes each provider offers. Stored globally, so the panel has
        to know per provider which of them can actually be honoured."""
        self.check("argv_permission_modes_by_provider", {
            "all": list(providers.PERMISSION_MODES),
            "unsafe": list(providers.UNSAFE_PERMISSION_MODES),
            "by_provider": providers.all_permission_modes_by_provider(),
            "claude": list(providers.permission_modes_for("claude")),
            "codex": list(providers.permission_modes_for("codex")),
            "deepseek": list(providers.permission_modes_for("deepseek")),
        })


if __name__ == "__main__":
    # `python test_provider_golden.py --update` is the writer, for anyone who
    # would rather not remember the environment variable.
    if "--update" in sys.argv:
        sys.argv.remove("--update")
        UPDATE = True
        os.environ["SUTRA_GOLDEN_UPDATE"] = "1"
    unittest.main()
