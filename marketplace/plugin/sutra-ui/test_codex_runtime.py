"""CodexRuntime and build_codex_args, asserted against the MEASURED protocol.

Everything here runs against qa/fake_codex_agent.py as a real subprocess: no
`codex` binary, no credential, no network, no API call. The stub is deliberately
as strict as codex-cli 0.153.2 was measured to be (bad --sandbox value, bad
approval_policy, exec flags after `resume`, missing --skip-git-repo-check all
refuse the way the real CLI refuses), so an argv mistake fails HERE rather than
in front of an operator.

WHY THE ARGV ASSERTIONS READ A RECORDING RATHER THAN build_codex_args' RETURN
VALUE. DeepSeek already paid for that lesson: build_acp_args dropped a model its
caller had correctly computed, validated and ANNOUNCED, so every test that
stopped short of the spawn passed for the bug's whole life. The stub records the
argv it was actually launched with, from inside the launched process, and these
tests read that file back.

Run: .venv/bin/python -m pytest test_codex_runtime.py -q
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

# IMPORT-TIME ISOLATION, before `import app`. Same reasoning as
# test_shadow_delegate.py: app.py runs _ensure_workdir() at module level and
# providers resolves its paths from env, so an unguarded import would create
# ~/sutra-ui-workspace and read the operator's real settings.json. Plain
# assignment, not setdefault -- an inherited value would defeat the point.
_ENV_TMP = tempfile.mkdtemp(prefix="codex-runtime-env-")
os.environ["SUTRA_UI_WORKDIR"] = os.path.join(_ENV_TMP, "workspace")
os.environ["SUTRA_UI_WORKDIR_ROOT"] = _ENV_TMP
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ["SUTRA_NATIVE_HOME"] = os.path.join(_ENV_TMP, "native")
os.environ["SUTRA_SHADOW_HOME"] = os.path.join(_ENV_TMP, "shadow")

sys.path.insert(0, HERE)

import app                      # noqa: E402  (env above must be set first)
import chat_store               # noqa: E402
import providers                # noqa: E402
from codex_runtime import CodexRuntime, _extract_usage   # noqa: E402

STUB = os.path.join(HERE, "qa", "fake_codex_agent.py")


def _stub_ready():
    os.chmod(STUB, 0o755)
    return STUB


# --------------------------------------------------------------- harness ----

class _Collector:
    """The PRIMARY emit, standing in for websocket.send_json."""

    def __init__(self):
        self.frames = []

    async def __call__(self, frame):
        self.frames.append(frame)

    def of(self, ftype):
        return [f for f in self.frames if f.get("type") == ftype]

    def types(self):
        return [f.get("type") for f in self.frames]


def _in_loop(coro_fn):
    """Run `coro_fn()` on a fresh loop, constructing runtimes INSIDE it.

    Not incidental. On Python 3.9 asyncio.Event() binds to the CURRENT event
    loop at construction time, so `CodexRuntime()` built after a previous
    asyncio.run() has finished raises "There is no current event loop". That is
    not a runtime defect and it is not worked around in codex_runtime.py: the
    only production constructor is ws_chat, which is `async def`, so every real
    CodexRuntime is built inside a running loop -- exactly as SessionRuntime and
    AcpRuntime are, both of which create the same asyncio.Event in __init__.
    The tests therefore construct where production constructs, rather than
    making this provider's lifecycle diverge from its two siblings' to suit a
    test harness.

    A FRESH LOOP IS INSTALLED AFTERWARDS, and that is about being a good
    citizen in a shared pytest process rather than about anything here.
    asyncio.run() leaves the thread with NO current loop, and some existing
    suites in this repo construct asyncio primitives at module or fixture level
    -- `pytest test_stream_readline.py test_codex_login.py` already errors on
    exactly that, on HEAD, with neither file touched by this change. This file
    must not add a second trigger for that latent interaction, so it puts a
    usable loop back instead of relying on collection order.
    """
    try:
        return asyncio.run(coro_fn())
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _run_turn(script, perm_mode="plan", model=None, session_id=None,
              prompt="hello", workdir=None):
    """Spawn the stub through build_codex_args and drive one real turn.

    Returns (collector, five_tuple, recorded_argv, recorded_stdin, runtime).
    """
    tmp = tempfile.mkdtemp(prefix="codex-turn-")
    wd = workdir or tmp
    argv_path = os.path.join(tmp, "argv.json")
    stdin_path = os.path.join(tmp, "stdin.txt")

    args = app.build_codex_args(_stub_ready(), perm_mode, wd,
                                model=model, session_id=session_id)
    col = _Collector()
    box = {}

    async def go():
        rt = CodexRuntime()          # inside the loop -- see _in_loop
        box["rt"] = rt
        await rt.spawn(args, wd, tuple(args), env={
            "SUTRA_FAKE_CODEX_SCRIPT": script,
            "SUTRA_FAKE_CODEX_ARGV": argv_path,
            "SUTRA_FAKE_CODEX_STDIN": stdin_path,
        })
        try:
            return await asyncio.wait_for(
                rt.prompt_turn(prompt, col, session_id), 30)
        finally:
            rt.kill_group()

    out = _in_loop(go)
    rt = box["rt"]

    recorded_argv = None
    if os.path.exists(argv_path):
        with open(argv_path) as fh:
            recorded_argv = json.load(fh)
    recorded_stdin = None
    if os.path.exists(stdin_path):
        with open(stdin_path) as fh:
            recorded_stdin = fh.read()
    return col, out, recorded_argv, recorded_stdin, rt


# ---------------------------------------------------------- registration ----

class TestCodexRegistration(unittest.TestCase):
    """The provider is selectable, and its declarations say what was measured."""

    def test_codex_is_in_ADAPTERS(self):
        """The inverse of the old test_codex_is_not_in_ADAPTERS. It guarded a
        DELIBERATE absence whose stated precondition -- "until a CodexRuntime, a
        build_codex_args() and a third arm in the ws_chat dispatch exist" -- is
        now met, so the guard flips rather than being deleted."""
        self.assertIn("codex", providers.ADAPTERS)

    def test_the_three_preconditions_actually_exist(self):
        """Membership above is only honest if its backing does exist. Asserted
        so a future revert of the transport cannot leave codex selectable."""
        self.assertTrue(callable(app.build_codex_args))
        self.assertTrue(hasattr(CodexRuntime, "prompt_turn"))
        self.assertTrue(hasattr(CodexRuntime, "send_prompt"))

    def test_claude_and_deepseek_are_still_adapters(self):
        """The set was WIDENED, never rewritten."""
        self.assertIn("claude", providers.ADAPTERS)
        self.assertIn("deepseek", providers.ADAPTERS)

    def test_gemini_is_still_not_an_adapter(self):
        """The offer-a-choice-that-cannot-run guard still guards something."""
        self.assertNotIn("gemini", providers.ADAPTERS)

    def test_catalogue_declarations_are_pinned_by_value(self):
        """Pinned by VALUE, not by referencing providers._CODEX_*: comparing a
        constant with itself would quietly stop guarding anything. Same idiom
        as the DeepSeek entry's test."""
        entry = next(s for s in providers._CATALOG if s["id"] == "codex")
        self.assertEqual(entry["name"], "OpenAI Codex")
        self.assertEqual(entry["bin"], "codex")
        self.assertEqual(entry["config_dir"], "~/.codex")
        self.assertFalse(entry["default"])
        self.assertEqual(entry["model_flag"], "-m")
        # "tokens" since 2026-09-08, was "none". codex reports per-turn token
        # counts on turn.completed and NOTHING else -- no price, no rate-limit
        # window, no plan allowance -- and those counts were already reaching
        # the client on the done frame's `quota` with nothing rendering them.
        # This is the declaration that lets the pane show them AS TOKENS.
        # "window-percent" or "balance" here would put Anthropic's percentage
        # or DeepSeek's money on a Codex pane, which is what it must never be.
        self.assertEqual(entry["usage_kind"], "tokens")
        # NO LONGER EMPTY, and the old comment had it backwards: one process
        # per turn means a spawn-time `-c` IS a per-turn control. All three keys
        # are codex's own. `reasoning_effort` joined on 2026-09-09: it is a real
        # key whose VALUES codex does not enumerate in its rejection message
        # (measured: "__bogus__" was accepted), so it waited for model/list to
        # supply a per-model list rather than being guessed at.
        self.assertEqual(entry["turn_options"],
                         ("reasoning_summary", "verbosity", "reasoning_effort"))
        self.assertEqual(entry["permission_modes"],
                         ("plan", "acceptEdits", "bypassPermissions"))
        # The CATALOGUE still declares exactly one id. models_for("codex")
        # composes this with the operator's own codex config on top -- see
        # TestCodexModelDiscovery -- so this assertion is about the static
        # floor, not about what the picker ends up offering.
        self.assertEqual([m["id"] for m in entry["models"]], [""])

    def test_permission_modes_are_declared_not_defaulted(self):
        """THE TRAP THIS CLOSES. permission_modes_for() falls back to ALL SIX
        for a provider declaring (), and that default is safe only while the
        provider is unreachable. codex is now reachable, so an empty
        declaration would put auto/manual/dontAsk on a Codex pane -- a control
        displaying a posture nothing enforces, the exact DeepSeek bug the
        per-provider list was written to end."""
        modes = providers.permission_modes_for("codex")
        self.assertEqual(set(modes), {"plan", "acceptEdits", "bypassPermissions"})
        for absent in ("auto", "manual", "dontAsk"):
            self.assertNotIn(absent, modes)
        # And the published map must carry codex, or the client applies its own
        # permissive fallback and offers all six anyway.
        self.assertIn("codex", providers.all_permission_modes_by_provider())

    def test_no_invented_model_ids(self):
        """codex-cli 0.153.2 publishes no model list, and `-m` accepts unknown
        ids with only a warning -- so an invented roster would silently degrade
        sessions. Exactly one entry, and it means "let codex decide"."""
        ids = [m["id"] for m in providers.models_for("codex")]
        self.assertEqual(ids, [""])
        self.assertEqual(providers.selectable_model_ids_for("codex"),
                         frozenset({""}))

    def test_clean_model_gates_unknown_ids(self):
        self.assertIsNone(providers.clean_model("gpt-5-codex", "codex"))
        self.assertIsNone(providers.clean_model("o3", "codex"))
        # "" is legal and means "no flag"; clean_model returns None for it,
        # which build_codex_args reads as "omit -m".
        self.assertIsNone(providers.clean_model("", "codex"))

    def test_segment_providers_match_adapters(self):
        """chat_store.begin_segment RAISES outside this tuple, and ws_chat
        swallows bookkeeping errors -- so a missing entry means Codex chats work
        on screen and are never recorded, with nothing to say so."""
        self.assertEqual(set(chat_store.SEGMENT_PROVIDERS),
                         set(providers.ADAPTERS))
        self.assertIn("codex", chat_store.SEGMENT_PROVIDERS)

    def test_the_no_adapter_sentence_names_three_protocols(self):
        """The arm codex USED to reach, and gemini still does.

        Its sentence said "this panel speaks two protocols, Claude's
        stream-json and DeepSeek's ACP" -- true until the Codex adapter landed
        and then off by one, on the same screen where Codex renders as ready to
        use. providers.py has corrected this string once before for exactly the
        same reason (when DeepSeek landed), so it is asserted rather than left
        to drift a third time.

        Driven through _describe with a HANDED-IN spec, because on a normal
        machine gemini has no binary and no config directory and falls to the
        generic arm instead -- which is why the socket test cannot cover this.
        """
        cfg = tempfile.mkdtemp(prefix="codex-gemini-cfg-")
        os.environ["SUTRA_UI_GEMINI_BIN"] = sys.executable
        try:
            out = providers._describe({
                "id": "gemini", "name": "Gemini CLI", "bin": "gemini",
                "config_dir": cfg, "default": False,
                "models": (), "model_flag": None, "usage_kind": "none",
                "turn_options": (), "permission_modes": (),
            })
        finally:
            os.environ.pop("SUTRA_UI_GEMINI_BIN", None)
        self.assertTrue(out["installed"])
        self.assertTrue(out["configured"])
        self.assertFalse(out["adapter"])
        self.assertFalse(out["runnable"])
        self.assertIn("three protocols", out["reason"])
        self.assertIn("Codex's `exec --json`", out["reason"])
        # And the codex-specific version pin that used to hang off this string
        # is gone with it -- codex can no longer reach this arm at all.
        self.assertNotIn("codex-cli 0.153.2", out["reason"])

    def test_codex_never_reaches_the_no_adapter_arm(self):
        """Whatever else is true of the machine, a codex row can no longer say
        "no chat adapter yet" -- it is in ADAPTERS."""
        row = providers.provider_by_id("codex")
        self.assertTrue(row["adapter"])
        self.assertNotIn("no chat adapter yet", row["reason"] or "")

    def test_shadow_is_still_claude_only(self):
        """Widening ADAPTERS must not widen Shadow. Shadow has ONE transport
        (build_agent_args + SessionRuntime + demux_turn), so its answer stays
        narrower and codex gets the honest 503."""
        self.assertEqual(app.SHADOW_PROVIDERS, frozenset({"claude"}))
        self.assertNotEqual(app.SHADOW_PROVIDERS, providers.ADAPTERS)


# ------------------------------------------------------------------ argv ----

class TestBuildCodexArgs(unittest.TestCase):

    WD = "/tmp/codex-wd"

    def test_the_invariant_prefix(self):
        a = app.build_codex_args("codex", "plan", self.WD)
        self.assertEqual(a[:6],
                         ["codex", "exec", "--json", "--skip-git-repo-check",
                          "-C", self.WD])

    def test_skip_git_repo_check_is_always_present(self):
        """MANDATORY, not defensive: without it codex refuses with "Not inside a
        trusted directory..." and emits nothing, and the Sutra workdir is
        frequently not a git repo."""
        for mode in ("plan", "acceptEdits", "bypassPermissions", "dontAsk"):
            self.assertIn("--skip-git-repo-check",
                          app.build_codex_args("codex", mode, self.WD))

    def test_plan_maps_to_read_only(self):
        a = app.build_codex_args("codex", "plan", self.WD)
        self.assertIn("--sandbox", a)
        self.assertEqual(a[a.index("--sandbox") + 1], "read-only")
        self.assertIn("approval_policy=never", a)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", a)
        # read-only must not name writable roots
        self.assertFalse(any("writable_roots" in x for x in a))

    def test_acceptEdits_maps_to_workspace_write_with_explicit_roots(self):
        a = app.build_codex_args("codex", "acceptEdits", self.WD)
        self.assertEqual(a[a.index("--sandbox") + 1], "workspace-write")
        self.assertIn("approval_policy=never", a)
        roots = [x for x in a if x.startswith("sandbox_workspace_write.writable_roots=")]
        self.assertEqual(len(roots), 1)
        # A TOML array of basic strings, JSON-escaped so an operator path
        # cannot break the value.
        self.assertEqual(roots[0],
                         'sandbox_workspace_write.writable_roots=%s'
                         % json.dumps([self.WD]))

    def test_writable_roots_escapes_a_hostile_path(self):
        wd = '/tmp/we"ird\\path'
        a = app.build_codex_args("codex", "acceptEdits", wd)
        roots = next(x for x in a if x.startswith("sandbox_workspace_write"))
        self.assertEqual(json.loads(roots.split("=", 1)[1]), [wd])

    def test_bypass_uses_the_flag_and_not_a_sandbox_value(self):
        """--dangerously-bypass-approvals-and-sandbox REPLACES the sandbox
        rather than selecting one, so passing --sandbox beside it would be
        asking for two different things at once."""
        a = app.build_codex_args("codex", "bypassPermissions", self.WD)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", a)
        self.assertNotIn("--sandbox", a)
        self.assertFalse(any("approval_policy" in x for x in a))

    def test_an_unhonoured_mode_narrows_and_never_widens(self):
        """permission_mode is stored GLOBALLY, so `dontAsk` chosen while Claude
        was selected reaches a Codex pane. Widening on an unrecognised value is
        the one direction this must never be wrong in."""
        for mode in ("auto", "manual", "dontAsk", "", None, "nonsense"):
            a = app.build_codex_args("codex", mode, self.WD)
            self.assertEqual(a[a.index("--sandbox") + 1], "read-only", mode)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", a)

    def test_model_omitted_when_absent_and_present_when_given(self):
        self.assertNotIn("-m", app.build_codex_args("codex", "plan", self.WD))
        self.assertNotIn("-m", app.build_codex_args("codex", "plan", self.WD,
                                                    model=""))
        a = app.build_codex_args("codex", "plan", self.WD, model="some-model")
        self.assertEqual(a[a.index("-m") + 1], "some-model")

    def test_resume_comes_after_every_flag(self):
        """THE ORDERING TRAP, measured: `codex exec resume --last --json`
        printed a plain-text error and emitted NO JSON, because `resume`
        accepts only -c/--last/--all/--enable/--disable/-i/--strict-config."""
        a = app.build_codex_args("codex", "acceptEdits", self.WD,
                                 model="m", session_id="THREAD-1")
        at = a.index("resume")
        self.assertEqual(a[at + 1], "THREAD-1")
        for flag in ("--json", "--skip-git-repo-check", "-C", "--sandbox", "-m"):
            self.assertLess(a.index(flag), at,
                            "%s must precede the resume subcommand" % flag)

    def test_no_resume_subcommand_on_a_cold_turn(self):
        self.assertNotIn("resume", app.build_codex_args("codex", "plan", self.WD))

    def test_stdin_marker_is_the_final_element(self):
        for kwargs in ({}, {"model": "m"}, {"session_id": "T"},
                       {"model": "m", "session_id": "T"}):
            a = app.build_codex_args("codex", "plan", self.WD, **kwargs)
            self.assertEqual(a[-1], "-", kwargs)

    def test_the_prompt_is_never_in_argv(self):
        """build_codex_args takes no prompt AT ALL -- the strongest form of this
        guarantee. A message in argv works for short turns and dies at exec with
        E2BIG on a long one (the failure switch.py's ARGV_SAFETY_FRACTION
        predicts); stdin has no such ceiling."""
        import inspect
        params = inspect.signature(app.build_codex_args).parameters
        for forbidden in ("msg", "prompt", "message", "text"):
            self.assertNotIn(forbidden, params)

    def test_a_huge_prompt_cannot_reach_argv(self):
        """The E2BIG case, end to end: a payload far past ARG_MAX still
        produces a small argv and arrives intact on stdin."""
        big = "x" * 300_000
        col, out, argv, stdin, rt = _run_turn("ok", prompt=big)
        self.assertEqual(stdin, big)
        self.assertTrue(all(len(tok) < 4096 for tok in argv), "argv grew")
        self.assertEqual(out[2], True)          # got_result


class TestCodexModeNote(unittest.TestCase):

    def test_no_note_for_a_mode_codex_honours(self):
        for mode in ("plan", "acceptEdits", "bypassPermissions"):
            self.assertIsNone(app.codex_mode_note(mode))

    def test_a_note_states_the_divergence(self):
        note = app.codex_mode_note("dontAsk")
        self.assertIsNotNone(note)
        self.assertEqual(note["asked"], "dontAsk")
        self.assertEqual(note["running"], "plan")
        self.assertIn("no equivalent", note["reason"])


# -------------------------------------------------------------- transport ----

class TestCodexTurnTranslation(unittest.TestCase):

    def test_thread_started_is_captured_and_published(self):
        """ALWAYS the first line, and the id Sutra resumes from. Adopted
        unconditionally because a resume reports the SAME id (measured)."""
        col, out, argv, stdin, rt = _run_turn("ok")
        sess = col.of("session")
        self.assertEqual(len(sess), 1)
        self.assertTrue(sess[0]["id"])
        self.assertEqual(out[0], sess[0]["id"])   # returned in the 5-tuple
        self.assertEqual(rt.session_id, sess[0]["id"])

    def test_turn_started_becomes_thinking(self):
        """The ONLY thinking signal a Codex pane gets: reasoning items never
        reach stdout on this surface, so without this the pane sits blank until
        the first whole message lands."""
        col, out, argv, stdin, rt = _run_turn("ok")
        self.assertEqual(len(col.of("thinking")), 1)
        self.assertLess(col.types().index("thinking"),
                        col.types().index("token"))

    def test_agent_message_is_one_token_frame_with_the_whole_text(self):
        """No deltas exist on this surface (0 across 3 measured turns), so the
        text is forwarded whole and exactly once -- not chopped up to imitate
        Claude, and not duplicated."""
        col, out, argv, stdin, rt = _run_turn("ok")
        tokens = col.of("token")
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["text"], "hello from codex")
        self.assertEqual(out[1], True)            # got_text

    def test_prompt_is_delivered_on_stdin_verbatim(self):
        col, out, argv, stdin, rt = _run_turn("ok", prompt="  hi\nthere  ")
        self.assertEqual(stdin, "  hi\nthere  ")

    def test_no_text_is_duplicated_across_multiple_messages(self):
        """A turn with two agent_message items yields two token frames and no
        repeats -- the measured shape (both probe turns emitted two)."""
        col, out, argv, stdin, rt = _run_turn("tool")
        texts = [f["text"] for f in col.of("token")]
        self.assertEqual(texts, ["DONE"])
        self.assertEqual(len(texts), len(set(texts)))

    def test_command_execution_start_and_end(self):
        col, out, argv, stdin, rt = _run_turn("tool")
        tools = col.of("tool")
        self.assertEqual([t["phase"] for t in tools], ["start", "end"])
        start, end = tools
        self.assertEqual(start["id"], "item_1")
        self.assertEqual(start["name"], "command_execution")
        self.assertEqual(start["command"], "/bin/zsh -lc 'echo hello'")
        self.assertEqual(start["summary"], "/bin/zsh -lc 'echo hello'")
        self.assertIsNone(start["caller"])
        # END correlates on the SAME id, or the UI shows a tool that never
        # finishes.
        self.assertEqual(end["id"], "item_1")
        self.assertTrue(end["ok"])
        self.assertEqual(end["output"], "hello")

    def test_open_tools_are_cleared_at_the_turn_boundary(self):
        col, out, argv, stdin, rt = _run_turn("tool")
        self.assertEqual(rt.open_tools, set())

    def test_a_failed_command_is_not_ok(self):
        """Both signals matter: a `failed` status with exit_code None and an
        exit_code 3 with status completed are both failures."""
        async def go():
            rt = CodexRuntime()
            col = _Collector()
            rt._emit = rt._fanout(col)
            await rt._emit_tool_end({"id": "i", "status": "failed",
                                     "exit_code": None})
            await rt._emit_tool_end({"id": "j", "status": "completed",
                                     "exit_code": 3})
            await rt._emit_tool_end({"id": "k", "status": "completed",
                                     "exit_code": 0})
            return col
        col = asyncio.run(go())
        self.assertEqual([f["ok"] for f in col.of("tool")],
                         [False, False, True])

    def test_aggregated_output_is_capped_through_the_shared_helper(self):
        async def go():
            rt = CodexRuntime()
            col = _Collector()
            rt._emit = rt._fanout(col)
            await rt._emit_tool_end({"id": "i", "status": "completed",
                                     "exit_code": 0,
                                     "aggregated_output": "A" * 9000})
            return col
        col = asyncio.run(go())
        out = col.of("tool")[0]["output"]
        self.assertLess(len(out), 9000)
        self.assertIn("truncated", out)

    def test_turn_completed_closes_the_turn_with_no_invented_figures(self):
        col, out, argv, stdin, rt = _run_turn("ok")
        done = col.of("done")
        self.assertEqual(len(done), 1)
        self.assertIsNone(done[0]["duration_ms"])
        self.assertIsNone(done[0]["num_turns"])
        self.assertIsNone(done[0]["cost_usd"])
        self.assertEqual(done[0]["quota"]["output_tokens"], 3)
        session_id, got_text, got_result, result_error, eof = out
        self.assertTrue(got_result)
        self.assertIsNone(result_error)
        self.assertFalse(eof)

    def test_turn_failed_uses_the_nested_message(self):
        """TERMINAL, and its message is nested under .error -- unlike the
        transient top-level `error`, whose message is flat. Confusing the two is
        the easiest bug in this transport."""
        col, out, argv, stdin, rt = _run_turn("failed")
        session_id, got_text, got_result, result_error, eof = out
        self.assertTrue(got_result)
        self.assertFalse(eof)
        self.assertEqual(result_error, "unexpected status 401 Unauthorized")
        self.assertEqual(col.of("done"), [])

    def test_transient_error_does_not_terminate_the_turn(self):
        """THE REGRESSION THIS FILE EXISTS FOR MOST. codex emits
        "Reconnecting... N/5" up to five times per transport across two
        transports on a turn that has not failed. Mapping it to an error frame
        would end a turn codex is still retrying -- up to ten times."""
        col, out, argv, stdin, rt = _run_turn("transient")
        session_id, got_text, got_result, result_error, eof = out
        self.assertTrue(got_result)
        self.assertIsNone(result_error)
        self.assertFalse(eof)
        self.assertEqual([f["text"] for f in col.of("token")], ["recovered"])
        self.assertEqual(len(col.of("retrying")), 1)
        self.assertIn("Reconnecting", col.of("retrying")[0]["detail"])
        self.assertEqual(len(col.of("done")), 1)

    def test_item_type_error_is_a_warning_not_a_result_error(self):
        """Measured instances are diagnostics on turns that then ran normally:
        "Model metadata ... not found" and "Falling back from WebSockets to
        HTTPS transport"."""
        async def go():
            rt = CodexRuntime()
            col = _Collector()
            rt._emit = rt._fanout(col)
            await rt._translate_item("item.completed",
                                     {"id": "i", "type": "error",
                                      "message": "Falling back to HTTPS"})
            return rt, col
        rt, col = asyncio.run(go())
        self.assertEqual(col.frames, [])
        self.assertEqual(rt.last_warning, "Falling back to HTTPS")

    def test_a_failure_with_no_message_falls_back_to_the_warning(self):
        col, out, argv, stdin, rt = _run_turn("failed")
        # The `failed` script emits the warning BEFORE turn.failed, and
        # turn.failed carries its own message, so the message wins.
        self.assertEqual(out[3], "unexpected status 401 Unauthorized")

    def test_unknown_item_types_do_not_crash_or_end_the_turn(self):
        """reasoning / file_change / mcp_tool_call / web_search / todo_list are
        in the measured union but were never exercised on the wire, so they are
        DROPPED rather than guessed at -- and dropping must be safe."""
        col, out, argv, stdin, rt = _run_turn("unknown-items")
        session_id, got_text, got_result, result_error, eof = out
        self.assertTrue(got_result)
        self.assertIsNone(result_error)
        self.assertEqual([f["text"] for f in col.of("token")], ["still here"])
        self.assertEqual(col.of("tool"), [])

    def test_eof_without_a_terminal_event(self):
        """The measured SIGTERM shape: stdout ends after item.started with no
        turn.completed and no turn.failed. Reported as eof so ws_chat's
        existing arm drains stderr, reaps and (when stopped) sends `stopped`."""
        col, out, argv, stdin, rt = _run_turn("eof")
        session_id, got_text, got_result, result_error, eof = out
        self.assertTrue(eof)
        self.assertFalse(got_result)
        self.assertIsNone(result_error)
        self.assertFalse(got_text)
        # the tool that never finished is still closed out on our side
        self.assertEqual(rt.open_tools, set())

    def test_resume_reports_the_same_thread_id(self):
        """Measured: probe T2 resumed T1 and thread.started carried the
        IDENTICAL id. That is what makes the id safe to adopt unconditionally
        and what makes continuity work."""
        col, out, argv, stdin, rt = _run_turn("ok", session_id="THREAD-42")
        self.assertEqual(out[0], "THREAD-42")
        self.assertEqual(col.of("session")[0]["id"], "THREAD-42")
        self.assertIn("resume", argv)
        self.assertEqual(argv[argv.index("resume") + 1], "THREAD-42")

    def test_the_spawned_argv_is_what_was_built(self):
        """Read from the RECORDING, not from build_codex_args' return value --
        the DeepSeek model bug lived entirely in the gap between the two."""
        col, out, argv, stdin, rt = _run_turn("ok", perm_mode="acceptEdits")
        self.assertEqual(argv[1:4], ["exec", "--json", "--skip-git-repo-check"])
        self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
        self.assertEqual(argv[-1], "-")
        self.assertNotIn("hello", argv)

    def test_the_process_is_reaped_after_a_terminal_event(self):
        """`codex exec` is one process per TURN and ws_chat reaps only on eof,
        so a successful turn that left the child unwaited would leak one per
        message."""
        col, out, argv, stdin, rt = _run_turn("ok")
        self.assertIsNotNone(rt.proc.returncode)
        self.assertFalse(rt.alive)

    def test_subscribers_see_the_turn_boundary(self):
        """Shadow attaches through subscribe() and waits on _turn_boundary."""
        seen = []
        tmp = tempfile.mkdtemp(prefix="codex-sub-")
        args = app.build_codex_args(_stub_ready(), "plan", tmp)

        async def go():
            rt = CodexRuntime()
            rt.subscribe(lambda f: seen.append(f.get("type")))
            await rt.spawn(args, tmp, tuple(args),
                           env={"SUTRA_FAKE_CODEX_SCRIPT": "ok"})
            try:
                await asyncio.wait_for(rt.prompt_turn("hi", _Collector(), None), 30)
            finally:
                rt.kill_group()
        asyncio.run(go())
        self.assertIn("_turn_boundary", seen)
        self.assertIn("token", seen)

    def test_state_returns_to_idle(self):
        col, out, argv, stdin, rt = _run_turn("ok")
        self.assertEqual(rt.state, "idle")

    def test_stop_marks_the_operator_intent_before_killing(self):
        async def go():
            rt = CodexRuntime()
            rt.stop()
            return rt
        rt = _in_loop(go)
        self.assertTrue(rt.stopped)
        self.assertEqual(rt.state, "stopped")

    def test_clear_keeps_the_thread_id(self):
        """The codex thread outlives every process that served it; dropping it
        on clear() would silently start a new conversation next message."""
        async def go():
            rt = CodexRuntime()
            rt.session_id = "T1"
            rt.proc, rt.key = object(), ("a",)
            rt.clear()
            return rt
        rt = _in_loop(go)
        self.assertIsNone(rt.proc)
        self.assertIsNone(rt.key)
        self.assertEqual(rt.session_id, "T1")


class TestUsageExtraction(unittest.TestCase):

    def test_known_int_fields_only(self):
        got = _extract_usage({
            "input_tokens": 1, "cached_input_tokens": 2,
            "cache_write_input_tokens": 3, "output_tokens": 4,
            "reasoning_output_tokens": 5,
            # A key this build has not been taught to read must not reach a
            # client frame just because codex added it.
            "a_new_field": 9, "nested": {"x": 1},
        })
        self.assertEqual(got, {"input_tokens": 1, "cached_input_tokens": 2,
                               "cache_write_input_tokens": 3,
                               "output_tokens": 4,
                               "reasoning_output_tokens": 5})

    def test_non_dict_and_empty(self):
        self.assertIsNone(_extract_usage(None))
        self.assertIsNone(_extract_usage("nope"))
        self.assertIsNone(_extract_usage({}))
        self.assertIsNone(_extract_usage({"output_tokens": "3"}))
        self.assertIsNone(_extract_usage({"output_tokens": True}))


# ------------------------------------------------------------ stub fidelity --

class TestStubIsAsStrictAsTheRealCli(unittest.TestCase):
    """A stub more permissive than the thing it stands in for silently deletes
    a class of test -- qa/fake_acp_agent.py's header records what that cost
    DeepSeek. These assert the stub refuses what codex-cli 0.153.2 refuses, so
    the argv tests above are worth something."""

    def _run(self, argv, prompt=""):
        import subprocess
        p = subprocess.run([sys.executable, _stub_ready()] + argv,
                           input=prompt, capture_output=True, text=True,
                           env=dict(os.environ,
                                    SUTRA_FAKE_CODEX_SCRIPT="ok"))
        return p

    def test_a_bad_sandbox_value_is_refused_with_no_json(self):
        p = self._run(["exec", "--json", "--skip-git-repo-check",
                       "--sandbox", "nonsense", "-"])
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), "")
        self.assertIn("invalid value 'nonsense'", p.stderr)

    def test_a_bad_approval_policy_is_refused_with_no_json(self):
        p = self._run(["exec", "--json", "--skip-git-repo-check",
                       "-c", "approval_policy=bogus_value", "-"])
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), "")
        self.assertIn("unknown variant `bogus_value`", p.stderr)

    def test_exec_flags_after_resume_emit_no_json(self):
        """The ordering trap, as the real CLI behaves: plain-text error, no
        JSONL at all."""
        p = self._run(["exec", "resume", "--last", "--json", "-"])
        self.assertEqual(p.stdout.strip(), "")
        self.assertIn("trusted directory", p.stderr)

    def test_missing_skip_git_repo_check_is_refused(self):
        p = self._run(["exec", "--json", "-"])
        self.assertEqual(p.stdout.strip(), "")
        self.assertIn("--skip-git-repo-check", p.stderr)

    def test_the_argv_this_build_produces_is_accepted(self):
        """The premise of every test above: our real argv passes the strict
        stub. If build_codex_args drifts into something codex would reject,
        this fails."""
        argv = app.build_codex_args("IGNORED", "acceptEdits", "/tmp/x",
                                    model=None, session_id=None)
        p = self._run(argv[1:], prompt="hi")
        self.assertEqual(p.returncode, 0, p.stderr)
        first = json.loads(p.stdout.splitlines()[0])
        self.assertEqual(first["type"], "thread.started")

    def test_stdout_is_pure_jsonl(self):
        """codex writes every human string to stderr. A parser that ever merges
        the streams breaks here rather than in production."""
        argv = app.build_codex_args("IGNORED", "plan", "/tmp/x")
        p = self._run(argv[1:], prompt="hi")
        for line in p.stdout.splitlines():
            if line.strip():
                json.loads(line)          # raises if anything human leaked in
        self.assertIn("Reading additional input from stdin", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCodexTurnConfig(unittest.TestCase):
    """The two per-turn controls, and the allow-list that is the only thing
    standing between a client payload and a silently different run.

    BOTH KEYS AND BOTH ENUMS ARE CODEX'S OWN, read out of the CLI's rejection
    of a bad value on 0.153.2 (2026-09-08) WITHOUT spending a model turn --
    `--strict-config` validates before anything is sent, and the probe resumed
    a nonexistent thread so the run died at "No prompt provided via stdin":

        -c totally_made_up_key=1
          -> unknown configuration field `totally_made_up_key`
        -c model_reasoning_summary='"__bogus__"'
          -> unknown variant, expected one of `auto`, `concise`, `detailed`, `none`
        -c model_verbosity='"__bogus__"'
          -> unknown variant, expected one of `low`, `medium`, `high`

    `model_reasoning_effort` is a REAL key by the same probe -- it was not
    refused as unknown -- but it ACCEPTED "__bogus__" as a value, so there is no
    authoritative list of its levels and it is deliberately not offered.
    """

    def test_both_values_become_toml_config_overrides(self):
        self.assertEqual(
            app.codex_turn_config({"reasoning_summary": "concise",
                                   "verbosity": "low"}),
            ["-c", 'model_reasoning_summary="concise"',
             "-c", 'model_verbosity="low"'])

    def test_every_enumerated_value_is_accepted(self):
        for v in providers.CODEX_REASONING_SUMMARY:
            if not v:
                continue
            self.assertIn('model_reasoning_summary="%s"' % v,
                          app.codex_turn_config({"reasoning_summary": v}))
        for v in providers.CODEX_VERBOSITY:
            if not v:
                continue
            self.assertIn('model_verbosity="%s"' % v,
                          app.codex_turn_config({"verbosity": v}))

    def test_a_value_outside_the_enum_is_dropped_not_forwarded(self):
        """codex would TAKE an unknown value and run on a fallback, which is a
        turn that quietly did something other than what the control said."""
        self.assertEqual(app.codex_turn_config({"reasoning_summary": "chatty"}), [])
        self.assertEqual(app.codex_turn_config({"verbosity": "MEDIUM"}), [])

    def test_the_empty_choice_emits_nothing(self):
        """"" is a real option meaning "leave it to codex"."""
        self.assertEqual(
            app.codex_turn_config({"reasoning_summary": "", "verbosity": "  "}), [])

    def test_junk_types_and_absence_are_survived(self):
        for payload in (None, {}, "nope", 7, {"verbosity": 3},
                        {"verbosity": None}, {"verbosity": ["low"]}):
            self.assertEqual(app.codex_turn_config(payload), [], repr(payload))

    def test_claudes_options_are_never_emitted_for_codex(self):
        """A Claude value stored on a pane that switched provider must not
        become a codex flag -- permission_mode already taught this lesson."""
        self.assertEqual(app.codex_turn_config(
            {"effort": "high", "max_budget_usd": 5,
             "allowed_tools": ["Read"], "append_system_prompt": "hi"}), [])

    def test_the_options_land_before_resume(self):
        """`codex exec resume` accepts NO flags after it -- measured. An option
        emitted after `resume` would make the whole turn unparseable."""
        args = app.build_codex_args("/x/codex", "plan", "/wd", session_id="T1",
                                    opts={"verbosity": "high"})
        self.assertLess(args.index("model_verbosity=\"high\""),
                        args.index("resume"))
        self.assertEqual(args[-1], "-")

    def test_no_options_leaves_the_argv_exactly_as_it_was(self):
        """The enhancement must be invisible on a pane that sets nothing."""
        self.assertEqual(
            app.build_codex_args("/x/codex", "plan", "/wd"),
            app.build_codex_args("/x/codex", "plan", "/wd", opts={}))

    def test_the_provider_declares_exactly_these_three(self):
        self.assertEqual(providers.turn_options_for("codex"),
                         ("reasoning_summary", "verbosity", "reasoning_effort"))

    def test_reasoning_effort_is_validated_per_model_not_by_a_constant(self):
        """WAS test_reasoning_effort_is_not_offered, and the reason it was not
        offered has been removed rather than ignored.

        The key was always real -- a made-up key is refused as "unknown
        configuration field" and this one was not -- but it ACCEPTED
        "__bogus__" as a value, so there was no enumeration to validate
        against and a guessed list of levels would have been the invented
        capability this package refuses. model/list supplies the enumeration,
        PER MODEL, so the allow-list is a lookup rather than a constant. That
        is the invariant now: no module-level tuple of efforts anywhere.
        """
        self.assertIn("reasoning_effort", providers.turn_options_for("codex"))
        self.assertFalse(
            [n for n in dir(providers)
             if "EFFORT" in n.upper() and isinstance(getattr(providers, n), tuple)],
            "an effort list became a constant; it must stay per-model")
        # With nothing discovered there is nothing to allow, and the option is
        # dropped rather than passed through.
        self.assertEqual(app.codex_turn_config({"reasoning_effort": "high"},
                                               "no-such-model"), [])

    def test_the_other_providers_turn_options_are_untouched(self):
        self.assertEqual(providers.turn_options_for("deepseek"), ())
        self.assertIn("effort", providers.turn_options_for("claude"))
        self.assertNotIn("verbosity", providers.turn_options_for("claude"))


class TestCodexUsageDeclaration(unittest.TestCase):
    """usage_kind went "none" -> "tokens". The counts were ALREADY on the wire
    and nothing rendered them; this is what lets the pane show them as tokens
    rather than borrowing another provider's meaning."""

    def test_codex_declares_tokens(self):
        self.assertEqual(providers.usage_kind_for("codex"), "tokens")

    def test_it_is_not_a_percentage_and_not_a_balance(self):
        """Either would put Anthropic's window or DeepSeek's money on a Codex
        pane -- the exact confusion usage_kind exists to prevent."""
        self.assertNotIn(providers.usage_kind_for("codex"),
                         ("window-percent", "balance"))

    def test_the_other_providers_are_untouched(self):
        self.assertEqual(providers.usage_kind_for("claude"), "window-percent")
        self.assertEqual(providers.usage_kind_for("deepseek"), "balance")

    def test_the_done_frame_still_reports_no_price(self):
        """codex publishes no dollar figure anywhere in turn.completed, so the
        runtime must keep sending None rather than deriving one."""
        src = open("codex_runtime.py").read()
        self.assertIn('"cost_usd": None', src)
