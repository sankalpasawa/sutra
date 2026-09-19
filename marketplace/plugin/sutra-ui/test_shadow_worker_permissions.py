"""A Shadow WORKER inherits the founder's project permissions. Shadow does not.

THE BUG (forensic, 2026-09-14). Claude resolves project settings from the
process cwd and does not walk up to the git root. A normal chat runs at the
repo root and gets <repo>/.claude/settings.json, whose permissions.allow
carries a bare `Bash`. A Shadow-created worker runs in the delegate workdir,
which has no .claude/ at all, so it got NO permission rules -- and with `-p`
there is nobody to answer the prompt that follows. Measured across real
transcripts: 0 Bash denials in 76 repo-root sessions, 16 in 116 sessions in
the delegate workdir.

THE FIX. The worker is handed the same `permissions` object through the
--settings flag it was ALREADY being passed (the CLI documents that flag as
"load ADDITIONAL settings from", i.e. it merges). Its cwd never moves.

THE SPLIT THIS FILE EXISTS TO PIN. `_shadow_args` is shared by the
supervisor, the decider and the worker. Only the worker acts on the
founder's problem, so only `_worker_args` inherits. If a later edit lets
Shadow's own two processes inherit too, tests 7 and 8 go red -- that is the
line between "Shadow supervises" and "Shadow has a shell in the repo".
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import app
import providers


PROJECT_SETTINGS = {
    "permissions": {
        "allow": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        "deny": ["Read(**/node_modules/**)", "Read(**/.DS_Store)"],
    },
    # the half that must NOT travel: repo-root-relative, and (in the real
    # file) paths under a home that does not exist on this machine
    "hooks": {
        "PreToolUse": [{"matcher": "Edit|Write|Bash", "hooks": [
            {"type": "command",
             "command": "bash .claude/hooks/enforce-boundaries.sh"}]}],
        "Stop": [{"matcher": "", "hooks": [
            {"type": "command", "command": "bash .claude/hooks/coverage-gate.sh"}]}],
    },
}


def settings_of(args):
    """The parsed inline --settings object, or None."""
    if "--settings" not in args:
        return None
    return json.loads(args[args.index("--settings") + 1])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        # proj/.claude/settings.json  with  proj/sub  as the worker cwd,
        # mirroring "delegate workdir is a subdirectory of the project"
        self.proj = root / "proj"
        self.worker_cwd = self.proj / "sub"
        self.worker_cwd.mkdir(parents=True)
        (self.proj / ".claude").mkdir()
        self.settings_file = self.proj / ".claude" / "settings.json"
        self.settings_file.write_text(json.dumps(PROJECT_SETTINGS))

        self._orig_wd = app._shadow_workdir_for_delegates
        app._shadow_workdir_for_delegates = lambda: str(self.worker_cwd)
        self.addCleanup(setattr, app, "_shadow_workdir_for_delegates",
                        self._orig_wd)

        # a resolvable claude, and a settings.json Shadow can read a mode from
        self._orig_settings = providers.SETTINGS_PATH
        sp = root / "sutra-settings.json"
        sp.write_text(json.dumps({"permission_mode": "plan"}))
        providers.SETTINGS_PATH = sp
        self.sp = sp
        self.addCleanup(setattr, providers, "SETTINGS_PATH",
                        self._orig_settings)

        self._d, self._b = (providers.active_provider_detail,
                            providers.provider_by_id)
        providers.active_provider_detail = lambda: {
            "id": "claude", "source": "settings", "ignored": []}
        providers.provider_by_id = lambda pid: {
            "id": "claude", "name": "Claude Code",
            "bin_path": "/opt/homebrew/bin/claude",
            "runnable": True, "reason": None}
        self.addCleanup(setattr, providers, "active_provider_detail", self._d)
        self.addCleanup(setattr, providers, "provider_by_id", self._b)

        # THE AUTONOMY CEILING IS READ ON EVERY _worker_args CALL, so the home
        # it reads from has to be this test's, not the founder's. Without
        # this the argv these tests assert on would depend on whatever level
        # the machine running them happens to be set to.
        self._orig_home = os.environ.get("SUTRA_SHADOW_HOME")
        os.environ["SUTRA_SHADOW_HOME"] = str(root / "shadow")
        os.makedirs(os.environ["SUTRA_SHADOW_HOME"], exist_ok=True)
        self.addCleanup(self._restore_home)

    def _restore_home(self):
        if self._orig_home is None:
            os.environ.pop("SUTRA_SHADOW_HOME", None)
        else:
            os.environ["SUTRA_SHADOW_HOME"] = self._orig_home

    def set_autonomy(self, level):
        """The founder's level, for this test only."""
        import mission_engine
        mission_engine.set_autonomy(level)

    def settings_file_write(self, mode):
        """The app-global permission mode Shadow inherits from."""
        self.sp.write_text(json.dumps({"permission_mode": mode}))

    def unsafe(self, allowed):
        """The gate that decides whether the write-capable modes resolve at
        all. Driven by the env vars, the out-of-band half that needs no
        consent phrase (same idiom as test_shadow_permission_inherit).

        TAKES TWO VARS SINCE 2026-09-18, because the gate became an OPT-OUT
        when Full access became the shipped default. `unsafe(False)` has to
        ENGAGE the clamp (SUTRA_UI_SAFE_PERM_MODES=1) to mean what it has
        always meant here -- "the write-capable modes do not resolve". Popping
        the old opt-in alone would now leave them resolving, and every test
        that asks for the clamped half of a cross product would quietly assert
        against the unclamped one.
        """
        if allowed:
            os.environ[providers.UNSAFE_MODES_ENV] = "1"
            os.environ.pop(providers.CLAMP_MODES_ENV, None)
        else:
            os.environ.pop(providers.UNSAFE_MODES_ENV, None)
            os.environ[providers.CLAMP_MODES_ENV] = "1"
        self.addCleanup(os.environ.pop, providers.UNSAFE_MODES_ENV, None)
        self.addCleanup(os.environ.pop, providers.CLAMP_MODES_ENV, None)

    def tearDown(self):
        self.tmp.cleanup()


class TestWorkerInheritsProjectPermissions(Base):

    def test_01_worker_receives_the_project_permissions(self):
        cfg = settings_of(app._worker_args())
        self.assertIsNotNone(cfg, "the worker must carry --settings")
        self.assertIn("permissions", cfg)
        self.assertEqual(cfg["permissions"],
                         PROJECT_SETTINGS["permissions"],
                         "the same object a normal chat there would get")

    def test_02_worker_receives_the_Bash_allow_rule(self):
        """THE BUG, in one assertion."""
        cfg = settings_of(app._worker_args())
        self.assertIn("Bash", cfg["permissions"]["allow"])

    def test_03_worker_receives_the_deny_rules(self):
        """deny is purely restrictive -- inheriting it is safe and intended."""
        cfg = settings_of(app._worker_args())
        self.assertIn("Read(**/node_modules/**)", cfg["permissions"]["deny"])

    def test_04_project_hooks_are_NOT_copied(self):
        """They are repo-root-relative or point at a home that does not exist
        here; copied in, they would fail on every Edit/Write/Bash."""
        cfg = settings_of(app._worker_args())
        blob = json.dumps(cfg)
        self.assertNotIn("enforce-boundaries", blob)
        self.assertNotIn("coverage-gate", blob)
        self.assertEqual(len(cfg["hooks"]["PreToolUse"]), 1,
                         "only Shadow's own hook survives")

    def test_05_the_shadow_mcp_hook_survives(self):
        cfg = settings_of(app._worker_args())
        pre = cfg["hooks"]["PreToolUse"][0]
        self.assertEqual(pre["matcher"], "mcp__sutra__.*")
        self.assertIn("mcp_allow_hook.py", pre["hooks"][0]["command"])

    def test_06_worker_cwd_is_unchanged(self):
        """The fix must not move the worker. Both halves: the resolver still
        answers the delegate workdir, and every spawn site still passes it.

        THE FOUR SITES ARE NOW ONE (2026-09-16). They were four byte-identical
        copies; folding them into `_delegate_spawn` is what lets the
        permission-mode stamp be added in one place instead of three plus a
        forgotten one. Counting call sites was only ever a proxy for "no spawn
        bypasses the workdir", so that is asserted directly now: exactly one
        site passes it, and nothing else calls the spawn primitive."""
        self.assertEqual(app._shadow_workdir_for_delegates(),
                         str(self.worker_cwd))
        src = Path(app.__file__).read_text()
        self.assertEqual(
            src.count("_worker_args, _shadow_workdir_for_delegates(),"), 1,
            "the one delegate spawn passes the unchanged workdir")
        self.assertEqual(
            src.count("shadow_runner.spawn_delegate_session("), 1,
            "no spawn may bypass _delegate_spawn and its stamp")
        self.assertNotIn("_shadow_args, _shadow_workdir_for_delegates(),", src)


class TestShadowItselfStaysIsolated(Base):

    def test_07_supervisor_does_NOT_receive_repo_permissions(self):
        """ShadowSession is built from _shadow_args, which must not inherit."""
        cfg = settings_of(app._shadow_args())
        self.assertIsNotNone(cfg, "the MCP hook is still carried")
        self.assertNotIn("permissions", cfg,
                         "Shadow's own session must not gain repo authority")

    def test_08_decider_does_NOT_receive_repo_permissions(self):
        """The decider is spawned from the same _shadow_args callable."""
        cfg = settings_of(app._shadow_args())
        self.assertNotIn("permissions", cfg)
        src = Path(app.__file__).read_text()
        # WHICH BUILDER, not which signature. This used to pin the whole
        # call including its closing paren, so 42f2d0f2 adding the runtime
        # factory (`new_runtime=`) broke it while the property it guards --
        # the decider is built from _shadow_args, never _worker_args -- was
        # never in question. Pin the property.
        self.assertIn("make_decider(_shadow_args, _shadow_workdir(),", src)
        self.assertNotIn("make_decider(_worker_args", src,
                         "the decider must never get repo authority")

    def test_09_the_attach_path_is_untouched(self):
        """ensure_runtime resumes a chat the FOUNDER made, in that session's
        own cwd, so the CLI resolves its project natively -- nothing to
        inject, and injecting would be applying the WRONG project's rules."""
        src = Path(app.__file__).read_text()
        self.assertIn("lambda sid: _shadow_args(session_id=sid)", src)


class TestDegradesSafely(Base):

    def test_10_no_project_settings_preserves_existing_behaviour(self):
        self.settings_file.unlink()
        cfg = settings_of(app._worker_args())
        self.assertNotIn("permissions", cfg)
        self.assertEqual(cfg, settings_of(app._shadow_args()),
                         "byte-identical to the pre-fix argv")

    def test_11_malformed_json_does_not_crash(self):
        self.settings_file.write_text("{ not json at all ")
        cfg = settings_of(app._worker_args())
        self.assertNotIn("permissions", cfg)

    def test_12_permissions_of_the_wrong_type_is_ignored(self):
        self.settings_file.write_text(json.dumps({"permissions": "all of them"}))
        cfg = settings_of(app._worker_args())
        self.assertNotIn("permissions", cfg)

    def test_13_a_settings_file_with_no_permissions_key(self):
        self.settings_file.write_text(json.dumps({"hooks": {}}))
        cfg = settings_of(app._worker_args())
        self.assertNotIn("permissions", cfg)

    def test_14_the_walk_stops_before_HOME(self):
        """~/.claude/settings.json is the USER layer the CLI loads itself;
        picking it up as a "project" file would duplicate a layer."""
        home = os.path.realpath(os.path.expanduser("~"))
        self.assertEqual(app.project_permissions_for(home), {})
        self.assertEqual(app.project_permissions_for(""), {})
        self.assertEqual(app.project_permissions_for(None), {})


class TestNoWideningSnuckIn(Base):

    def test_15_no_bypassPermissions_anywhere_in_the_worker_argv(self):
        args = app._worker_args()
        self.assertNotIn("bypassPermissions", " ".join(map(str, args)))

    def test_16_no_dangerously_skip_permissions(self):
        for args in (app._worker_args(), app._shadow_args()):
            joined = " ".join(map(str, args))
            self.assertNotIn("--dangerously-skip-permissions", joined)
            self.assertNotIn("--allow-dangerously-skip-permissions", joined)

    def test_17_no_shadow_specific_permission_mode(self):
        """The mode comes from the one shared accessor, THEN the founder's
        autonomy ceiling lowers it. Still a LAYER, not a second mode.

        REWRITTEN 2026-09-16, not extended. This used to assert the worker's
        mode equalled the bare accessor, full stop -- which was right while
        nothing could narrow it. Autonomy can (L0/L1/L2 cap the worker at
        `plan`), so the old equality would have failed for a founder at L2
        and, worse, would have been a test DEMANDING that the level be
        ignored. The invariant it was really protecting is not "the mode
        equals the accessor", it is "there is no second SOURCE of permission"
        -- and that is now asserted as: the result is the accessor's answer,
        clamped, and the clamp only ever narrows (test_17e).
        """
        # at L3 the ceiling is not in play, so the historical equality holds
        # exactly as it always did
        self.set_autonomy("L3")
        args = app._worker_args()
        self.assertEqual(
            args[args.index("--permission-mode") + 1],
            providers.effective_permission_mode(
                providers.load_settings()["permission_mode"]),
            "at L3 the worker must get the founder's own resolved mode")
        src = Path(app.__file__).read_text()
        # THE NAMES THAT WOULD MEAN A SECOND SETTING. `worker_permission_mode`
        # left this list on 2026-09-16 and the invariant it stood for is
        # asserted directly instead, in the tests below -- a name ban cannot
        # tell a new trust domain from a mission REMEMBERING what the
        # founder's own setting resolved to when its worker was spawned, and
        # the second is what re-adoption needs to stop silently downgrading a
        # working delegate to read-only.
        for junk in ("shadow.permission_mode", "shadow_permission_mode",
                     "SHADOW_PERMISSION_MODE"):
            self.assertNotIn(junk, src)

    def test_17b_the_remembered_mode_IS_the_shared_accessor(self):
        """Not a second source of truth: the same call, then the ceiling."""
        self.set_autonomy("L3")
        self.assertEqual(
            app.worker_permission_mode(),
            providers.effective_permission_mode(
                providers.load_settings()["permission_mode"]))

    def test_17e_the_autonomy_ceiling_ONLY_EVER_NARROWS(self):
        """THE PROPERTY THAT MAKES THE CEILING SAFE, stated over the whole
        cross product rather than argued in a docstring.

        For every supported mode, both authorization states and every level,
        what the worker gets must be either the unclamped answer or `plan` --
        never something wider, and never a mode outside the supported set. A
        future edit that lets a level RAISE a mode fails here.
        """
        unclamped_seen = set()
        for mode in providers.PERMISSION_MODES:
            for allowed in (True, False):
                for level in ("L0", "L1", "L2", "L3"):
                    with self.subTest(mode=mode, unsafe=allowed, level=level):
                        self.settings_file_write(mode)
                        self.unsafe(allowed)
                        self.set_autonomy(level)
                        base = providers.effective_permission_mode(
                            providers.load_settings()["permission_mode"])
                        got = app.worker_permission_mode()
                        unclamped_seen.add(base)
                        self.assertIn(got, providers.PERMISSION_MODES,
                                      "the ceiling invented a mode")
                        if level == "L3":
                            self.assertEqual(got, base,
                                             "L3 must not narrow anything")
                        else:
                            self.assertEqual(
                                got, providers.PERMISSION_MODE_FLOOR,
                                "a read-only level must cap the worker at "
                                "plan")
                        # the one-way rule: an unsafe mode can never come OUT
                        # of a level that did not have it going in
                        if base not in providers.UNSAFE_PERMISSION_MODES:
                            self.assertNotIn(
                                got, providers.UNSAFE_PERMISSION_MODES,
                                "the ceiling widened a safe mode")
        self.assertTrue(unclamped_seen, "the sweep never ran")

    def test_17f_a_read_only_level_caps_the_ARGV_too(self):
        """Not just the resolver: the flag the CLI actually receives."""
        self.settings_file_write("acceptEdits")
        self.unsafe(True)
        self.set_autonomy("L2")
        args = app._worker_args()
        self.assertEqual(args[args.index("--permission-mode") + 1], "plan",
                         "L2 Draft must reach the CLI as plan")

    def test_17g_a_remembered_mode_is_re_clamped_by_the_CURRENT_level(self):
        """RE-ADOPTION. A worker stamped acceptEdits at L3 and resumed after
        the founder drops to L2 must come back read-only: the LOWER of what
        it was given and what is allowed now wins. Without this, lowering
        autonomy would leave every already-running delegate writing."""
        self.settings_file_write("acceptEdits")
        self.unsafe(True)
        self.set_autonomy("L2")
        args = app._worker_args(permission_mode="acceptEdits")
        self.assertEqual(args[args.index("--permission-mode") + 1], "plan",
                         "a remembered acceptEdits survived a drop to L2")

    def test_17h_the_ceiling_never_touches_shadows_own_processes(self):
        """The supervisor and the decider are not acting on the founder's
        problem, so how much Shadow may DO must not change what it may
        THINK. test_shadow_permission_inherit pins the equivalence for
        _shadow_args; this is the same line, asserted from this side."""
        self.settings_file_write("acceptEdits")
        self.unsafe(True)
        self.set_autonomy("L0")
        sup = app._shadow_args()
        self.assertEqual(sup[sup.index("--permission-mode") + 1],
                         "acceptEdits",
                         "the autonomy ceiling leaked into the supervisor")

    def test_17c_a_remembered_mode_is_STILL_clamped_at_the_point_of_use(self):
        """The property that makes remembering safe. A stamp taken while
        unsafe modes were allowed must not survive them being turned off --
        so the override goes through effective_permission_mode exactly as the
        stored setting does.

        The clamp is engaged explicitly (self.unsafe(False)) because since
        2026-09-18 it is an opt-out -- "turned off" is now a posture the test
        has to ask for rather than the ambient state."""
        self.unsafe(False)
        self.assertFalse(providers.unsafe_modes_allowed(),
                         "this test is meaningless if unsafe modes are on")
        args = app._worker_args(permission_mode="bypassPermissions")
        self.assertEqual(args[args.index("--permission-mode") + 1],
                         providers.PERMISSION_MODE_FLOOR,
                         "an unsafe remembered mode must be clamped, not "
                         "handed to the CLI")

    def test_17d_no_new_settings_key_is_ever_read(self):
        """A LAYER, not a mode: nothing reads a worker-specific key out of
        settings.json, so there is no second thing an operator can set."""
        src = Path(app.__file__).read_text()
        for key in ('"worker_permission_mode"', "'worker_permission_mode'"):
            self.assertNotIn("load_settings()[%s]" % key, src)
            self.assertNotIn("settings.get(%s)" % key, src)

    def test_18_mcp_restrictions_are_intact(self):
        args = app._worker_args()
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("--allowedTools", args)
        self.assertIn("mcp__sutra__*", args)

    def test_19_the_full_worker_argv_is_exactly_what_we_expect(self):
        """One --settings, in its original position, carrying BOTH keys."""
        args = app._worker_args()
        self.assertEqual(args[0], "/opt/homebrew/bin/claude")
        self.assertEqual(args[1], "-p")
        self.assertEqual(args.count("--settings"), 1,
                         "one --settings; a second would be silently dropped")
        # unchanged flag ORDER: --settings still sits with the mcp block,
        # before the stream flags
        self.assertLess(args.index("--strict-mcp-config"),
                        args.index("--settings"))
        self.assertLess(args.index("--settings"),
                        args.index("--input-format"))
        cfg = settings_of(args)
        self.assertEqual(sorted(cfg.keys()), ["hooks", "permissions"])
        self.assertEqual(args[args.index("--output-format") + 1], "stream-json")
        self.assertNotIn("--resume", args, "a new delegate is born cold")

    def test_20_worker_and_shadow_argv_differ_ONLY_by_permissions(self):
        """The strongest statement of the split: identical argv except the
        one key the worker is meant to gain."""
        w, s = app._worker_args(), app._shadow_args()
        self.assertEqual(len(w), len(s))
        wi, si = w.index("--settings"), s.index("--settings")
        self.assertEqual(wi, si, "same position")
        self.assertEqual(w[:wi] + w[wi + 2:], s[:si] + s[si + 2:],
                         "every other flag is identical")
        wc, sc = settings_of(w), settings_of(s)
        self.assertEqual(wc["hooks"], sc["hooks"])
        self.assertIn("permissions", wc)
        self.assertNotIn("permissions", sc)


if __name__ == "__main__":
    unittest.main()
