"""The provider adapters: the registry, the access map, the tool kinds, the
settings switches, the shared process helper, and the per-connection `perm`.

WHAT THIS FILE IS FOR. ws_chat used to branch on the provider id in about a
dozen places. Those branches moved onto one adapter per provider, and the thing
that can silently go wrong in a move like that is not "it crashes" -- it is "one
provider quietly got another's rule". So most of what is below is a TABLE: every
provider, every access id, every tool name, asserted at once, so a rule that
leaks from one adapter to another fails here rather than on someone's screen.

WHAT IS NOT HERE, deliberately: the frame-by-frame behaviour of a real turn.
test_runtime_characterization.py, test_codex_runtime.py, test_codex_chat.py and
test_chat_local_provider.py already freeze that, and they run against the same
code after this change. This file covers what those cannot see -- the adapter
surface itself.

A NOTE ON THE SKIPS. The shared .venv is Python 3.9, and
`asyncio.create_subprocess_exec(..., process_group=0)` needs 3.11. Every test
that actually SPAWNS is skipped there rather than failing with a TypeError that
says nothing about this change; the same failure is already pre-existing across
78 tests in the repo's own suite on this interpreter. Nothing else is skipped:
the argv, the tables and the refusal paths all run.

Run: .venv/bin/python -m pytest test_provider_adapters.py -q
"""
import asyncio
import contextlib
import importlib
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
ACP_STUB = os.path.join(HERE, "qa", "fake_acp_agent.py")
CODEX_STUB = os.path.join(HERE, "qa", "fake_codex_agent.py")

_ENV_TMP = tempfile.mkdtemp(prefix="provider-adapters-")
os.environ.setdefault("SUTRA_UI_WORKDIR", os.path.join(_ENV_TMP, "workspace"))
os.environ.setdefault("SUTRA_UI_WORKDIR_ROOT", _ENV_TMP)
os.environ.setdefault("SUTRA_UI_SETTINGS", os.path.join(_ENV_TMP, "settings.json"))
os.environ.setdefault("SUTRA_NATIVE_HOME", os.path.join(_ENV_TMP, "native"))
os.environ.setdefault("SUTRA_SHADOW_HOME", os.path.join(_ENV_TMP, "shadow"))

sys.path.insert(0, HERE)

import provider_adapters as PA          # noqa: E402
import proc_group                       # noqa: E402
import providers                        # noqa: E402
import tool_kinds                       # noqa: E402
from acp_runtime import AcpRuntime      # noqa: E402
from codex_runtime import CodexRuntime  # noqa: E402
from session_runtime import SessionRuntime  # noqa: E402

#: `process_group=` on create_subprocess_exec landed in Python 3.11. The shared
#: .venv is 3.9, where every spawning test in this repo already fails with
#: `TypeError: unexpected keyword argument 'process_group'`. Skipping is honest;
#: asserting through it would be noise.
CAN_SPAWN = sys.version_info >= (3, 11)
needs_spawn = unittest.skipUnless(
    CAN_SPAWN, "create_subprocess_exec(process_group=) needs Python 3.11+; "
               "this .venv is %d.%d" % sys.version_info[:2])


@contextlib.contextmanager
def _loop():
    """A fresh event loop for one test, WITHOUT poisoning the process.

    This used to end with `asyncio.set_event_loop(None)`, which on Python 3.9
    makes every later `asyncio.get_event_loop()` in this process raise
    "There is no current event loop in thread 'MainThread'". Every runtime's
    __init__ builds an `asyncio.Event`, so that took out five tests in OTHER
    files -- test_provider_spawn_group and test_chat_scope -- which is a worse
    failure than anything this file tests. Whatever loop was installed before is
    put back; if there was none, a usable one is left behind, which is the state
    a fresh process starts in anyway.
    """
    try:
        prev = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        prev = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()
        if prev is not None and not prev.is_closed():
            asyncio.set_event_loop(prev)
        else:
            asyncio.set_event_loop(asyncio.new_event_loop())


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ===========================================================================
# 1. The registry
# ===========================================================================

class TestRegistry(unittest.TestCase):
    """`provider_adapters.get(pid)` is the ONE lookup ws_chat makes. If it
    answers wrongly, every rule below is applied to the wrong provider."""

    def test_the_three_shipping_providers_have_an_adapter(self):
        for pid in ("claude", "codex", "deepseek"):
            self.assertIsNotNone(PA.get(pid), pid)
            self.assertEqual(PA.get(pid).id, pid)

    def test_each_adapter_names_its_own_runtime_class(self):
        """The branch this replaces was
        `SessionRuntime() if claude else CodexRuntime() if codex else
        AcpRuntime()`. Same truth table, asserted directly."""
        self.assertIs(PA.get("claude").runtime_class, SessionRuntime)
        self.assertIs(PA.get("codex").runtime_class, CodexRuntime)
        self.assertIs(PA.get("deepseek").runtime_class, AcpRuntime)
        self.assertIs(PA._ADAPTERS["cursor"].runtime_class, AcpRuntime)

    def test_new_runtime_returns_a_fresh_instance_each_time(self):
        """One runtime per chat channel. A shared one would put two panes on one
        subprocess."""
        with _loop() as loop:
            a = PA.get("claude").new_runtime()
            b = PA.get("claude").new_runtime()
            self.assertIsNot(a, b)

    def test_an_unknown_provider_has_no_adapter(self):
        """None is what makes ws_chat's `no-adapter` refusal fire. gemini is
        catalogued and deliberately has no adapter; the rest are nonsense."""
        for pid in ("gemini", "", "pi", "notaprovider", None):
            self.assertIsNone(PA.get(pid), pid)

    def test_cursor_is_registered_but_gated_on_its_binary(self):
        """Registered so it is ready and testable; returned by get() only where
        `cursor-agent` actually exists, because an adapter that is offered and
        then fails at spawn is worse than one that is not offered."""
        self.assertIn("cursor", PA.all_ids())
        installed = bool(shutil.which("cursor-agent"))
        self.assertEqual(PA.get("cursor") is not None, installed)
        self.assertEqual("cursor" in PA.ids(), installed)

    def test_ids_never_offers_something_get_would_refuse(self):
        for pid in PA.ids():
            self.assertIsNotNone(PA.get(pid), pid)


# ===========================================================================
# 2. The access map (SPEC section A)
# ===========================================================================

class TestAccessMap(unittest.TestCase):
    """The shared buttons, and what each one STORES. The whole point of the
    access id is that settings.json keeps the existing native mode, so an
    install that already chose one keeps working."""

    #: The contract table, transcribed once. A "-" means the provider does not
    #: offer that option at all.
    TABLE = {
        "claude":   {"read": "plan", "edits": "acceptEdits",
                     "auto": "auto", "full": "bypassPermissions"},
        "codex":    {"read": "plan", "edits": "acceptEdits",
                     "auto": None,   "full": "bypassPermissions"},
        "deepseek": {"read": "plan", "edits": "acceptEdits",
                     "auto": None,   "full": "bypassPermissions"},
    }

    def test_every_access_id_maps_to_the_contracted_native_mode(self):
        for pid, row in self.TABLE.items():
            for access_id, native in row.items():
                self.assertEqual(PA.native_mode_for(pid, access_id), native,
                                 "%s / %s" % (pid, access_id))

    def test_only_claude_offers_approve_for_me(self):
        """`auto` is Claude's own mode. Codex's approval policies all wait for
        an answer on a channel a headless run does not have, and DeepSeek's
        ACP modes are the same three."""
        self.assertEqual(
            [pid for pid in ("claude", "codex", "deepseek")
             if PA.get(pid).native_mode_for("auto")], ["claude"])

    def test_a_provider_only_offers_modes_it_can_actually_enforce(self):
        """The map must not name a mode providers.permission_modes_for() says
        the provider cannot do -- that would offer a button that silently runs
        as something else."""
        for pid in ("claude", "codex", "deepseek"):
            adapter = PA.get(pid)
            for access_id, native in adapter.access_map.items():
                self.assertTrue(adapter.supports_mode(native),
                                "%s offers %s -> %s, which it cannot enforce"
                                % (pid, access_id, native))

    def test_the_advanced_modes_keep_working_and_stay_out_of_the_list(self):
        """`manual` and `dontAsk` are valid STORED values (routines use
        dontAsk) and are deliberately not in the shared four."""
        for mode in ("manual", "dontAsk"):
            self.assertIn(mode, providers.PERMISSION_MODES)
            self.assertIsNone(PA.get("claude").access_id_for(mode), mode)
            self.assertNotIn(mode, PA.get("claude").access_map.values())

    def test_the_reverse_lookup_round_trips(self):
        for pid in ("claude", "codex", "deepseek"):
            a = PA.get(pid)
            for access_id, native in a.access_map.items():
                self.assertEqual(a.access_id_for(native), access_id)

    def test_the_shared_order_is_preserved_per_provider(self):
        """read -> edits -> auto -> full, with the rows a provider lacks simply
        absent. A different order per provider would move the buttons under the
        operator when they switch."""
        self.assertEqual([o["id"] for o in PA.get("claude").access_options()],
                         ["read", "edits", "auto", "full"])
        self.assertEqual([o["id"] for o in PA.get("codex").access_options()],
                         ["read", "edits", "full"])
        self.assertEqual([o["id"] for o in PA.get("deepseek").access_options()],
                         ["read", "edits", "full"])

    def test_full_access_is_the_only_one_that_warns(self):
        warns = [o["id"] for o in PA.access_options() if o["warn"]]
        self.assertEqual(warns, ["full"])


# ===========================================================================
# 3. The tool-kind classifier (SPEC section D)
# ===========================================================================

class TestToolKinds(unittest.TestCase):
    """A table test over REAL tool names.

    The Claude names come from a live `claude -p ... --output-format
    stream-json --verbose` system/init frame on 2.1.270 (2026-09-14), not from
    memory. The ACP names are the protocol's own kind vocabulary. The Codex
    names are its item types, of which only `command_execution` has actually
    been observed on this build.
    """

    CLAUDE = [
        ("Task", "subagent"), ("Agent", "subagent"), ("TaskOutput", "subagent"),
        ("TaskStop", "subagent"), ("ListAgents", "subagent"),
        ("Bash", "command"), ("BashOutput", "command"), ("KillShell", "command"),
        ("Edit", "file_edit"), ("Write", "file_edit"), ("MultiEdit", "file_edit"),
        ("NotebookEdit", "notebook"),
        ("Read", "file_read"),
        ("Grep", "search"), ("Glob", "search"),
        ("WebSearch", "web_search"), ("WebFetch", "web_fetch"),
        ("ExitPlanMode", "plan"), ("TodoWrite", "todo"),
        ("mcp__sutra__make_routine", "mcp"), ("mcp__x__y", "mcp"),
        # Real tools on this build that are deliberately NOT one of the card
        # shapes. They must land on `other` and render as they do today.
        ("Skill", "other"), ("Workflow", "other"), ("Artifact", "other"),
        ("ToolSearch", "other"), ("CronCreate", "other"),
        # And the ones nobody has ever heard of.
        ("SomeToolFromTheFuture", "other"), ("", "other"),
    ]

    CODEX = [
        ("command_execution", "command"),
        ("file_change", "file_edit"), ("patch_apply", "file_edit"),
        ("file_read", "file_read"), ("file_search", "search"),
        ("web_search", "web_search"), ("web_fetch", "web_fetch"),
        ("multi_agent", "subagent"),
        ("agent_message", "other"), ("error", "other"), ("", "other"),
    ]

    ACP = [
        ("execute", "command"), ("edit", "file_edit"), ("delete", "file_edit"),
        ("move", "file_edit"), ("read", "file_read"), ("search", "search"),
        ("fetch", "web_fetch"), ("think", "other"), ("other", "other"),
        ("", "other"),
    ]

    def test_claude_names(self):
        for name, kind in self.CLAUDE:
            self.assertEqual(PA.classify_tool("claude", name)["kind"], kind, name)

    def test_codex_item_types(self):
        for name, kind in self.CODEX:
            self.assertEqual(PA.classify_tool("codex", name)["kind"], kind, name)

    def test_acp_kinds_on_both_acp_providers(self):
        for pid in ("deepseek", "cursor"):
            for name, kind in self.ACP:
                self.assertEqual(PA.classify_tool(pid, name)["kind"], kind,
                                 "%s / %s" % (pid, name))

    def test_a_provider_never_reads_anothers_table(self):
        """`read` is a FILE READ in ACP and an unknown name to Claude;
        `command_execution` is a codex item type and nothing to Claude. A table
        leaking between providers is the failure this whole file guards."""
        self.assertEqual(PA.classify_tool("deepseek", "read")["kind"], "file_read")
        self.assertEqual(PA.classify_tool("claude", "read")["kind"], "file_read")
        self.assertEqual(PA.classify_tool("codex", "read")["kind"], "other")
        self.assertEqual(
            PA.classify_tool("claude", "command_execution")["kind"], "other")

    def test_every_kind_it_returns_is_in_the_declared_set(self):
        for pid, rows in (("claude", self.CLAUDE), ("codex", self.CODEX),
                          ("deepseek", self.ACP)):
            for name, _ in rows:
                self.assertIn(PA.classify_tool(pid, name)["kind"], tool_kinds.KINDS)

    # ---- titles and meta ---------------------------------------------------

    def test_a_shell_command_is_its_own_title(self):
        got = PA.classify_tool("claude", "Bash", {"command": "pytest -q  x.py"})
        self.assertEqual(got["title"], "pytest -q x.py")   # whitespace collapsed
        self.assertEqual(got["meta"]["command"], "pytest -q x.py")

    def test_a_file_tool_shows_the_file_name_and_keeps_the_path(self):
        got = PA.classify_tool("claude", "Read", {"file_path": "/a/b/c/thing.py"})
        self.assertEqual(got["title"], "thing.py")
        self.assertEqual(got["meta"]["path"], "/a/b/c/thing.py")

    def test_a_subagent_names_which_agent(self):
        got = PA.classify_tool("claude", "Task",
                               {"subagent_type": "explore",
                                "description": "find the thing",
                                "prompt": "a very long preamble " * 50})
        self.assertEqual(got["kind"], "subagent")
        self.assertEqual(got["meta"]["agent"], "explore")
        self.assertIn("explore", got["title"])
        self.assertNotIn("preamble", got["title"])

    def test_an_mcp_tool_names_the_server(self):
        got = PA.classify_tool("claude", "mcp__sutra__make_routine")
        self.assertEqual(got["meta"], {"server": "sutra", "tool": "make_routine"})
        self.assertIn("sutra", got["title"])

    def test_a_search_carries_its_pattern_and_a_web_search_its_query(self):
        self.assertEqual(
            PA.classify_tool("claude", "Grep", {"pattern": "TODO"})["meta"]["pattern"],
            "TODO")
        self.assertEqual(
            PA.classify_tool("claude", "WebSearch", {"query": "acp spec"})["meta"]["query"],
            "acp spec")

    def test_an_acp_fetch_with_a_query_is_a_web_search(self):
        """The one place ACP's vocabulary is coarser than the card set."""
        self.assertEqual(PA.classify_tool("deepseek", "fetch")["kind"], "web_fetch")
        self.assertEqual(
            PA.classify_tool("deepseek", "fetch", {"query": "x"})["kind"],
            "web_search")

    def test_the_callers_summary_is_the_title_fallback(self):
        """So a card header and the `summary` beside it cannot disagree."""
        got = PA.classify_tool("claude", "Workflow", None, {"title": "build docs"})
        self.assertEqual(got["kind"], "other")
        self.assertEqual(got["title"], "build docs")

    def test_an_exit_code_becomes_cheap_detail(self):
        got = PA.classify_tool("codex", "command_execution", None, {"exit_code": 3})
        self.assertEqual(got["detail"], "exit 3")
        self.assertEqual(got["meta"]["exit_code"], 3)

    def test_it_never_raises_on_junk(self):
        """The contract that matters most: a tool with an unexpected shape must
        not take a turn down."""
        for bad in (None, 5, [], "x" * 100000, {"a": object()}):
            got = PA.classify_tool("claude", "Bash", bad)
            self.assertIn(got["kind"], tool_kinds.KINDS)
            self.assertIsInstance(got["title"], str)
        self.assertEqual(PA.classify_tool("claude", None)["kind"], "other")
        self.assertEqual(PA.classify_tool(None, None)["kind"], "other")

    def test_the_table_is_exported_for_the_ui(self):
        t = tool_kinds.kind_table()
        self.assertEqual(t["kinds"], list(tool_kinds.KINDS))
        self.assertEqual(t["claude"]["task"], "subagent")
        self.assertEqual(t["acp"]["execute"], "command")
        # a copy, so a caller cannot mutate the live table through the API
        t["claude"]["task"] = "nonsense"
        self.assertEqual(PA.classify_tool("claude", "Task")["kind"], "subagent")


# ===========================================================================
# 4. The per-provider settings switches reaching argv (SPEC section C)
# ===========================================================================

class TestSettingsSwitches(unittest.TestCase):
    """Every switch below was verified against the real CLI before it was
    written; the notes are in PROVIDER_SETTINGS_SCHEMA. What these tests pin is
    the OTHER half: that the default produces today's argv byte for byte, and
    that flipping one produces exactly the flags it claims and nothing else."""

    CLAUDE_DEFAULTS = {"chrome": False, "subagents": True, "workflows": True}
    CODEX_DEFAULTS = {"memory": True, "subagents": True}

    def _claude(self, **switches):
        s = dict(self.CLAUDE_DEFAULTS, **switches)
        return PA.get("claude").spawn_args(
            "/bin/claude", "hi", "plan", "/tmp/wd", settings=s)

    def _codex(self, **switches):
        s = dict(self.CODEX_DEFAULTS, **switches)
        return PA.get("codex").spawn_args(
            "/bin/codex", "hi", "plan", "/tmp/wd", settings=s)

    # ---- the defaults must change nothing ----------------------------------

    def test_claude_defaults_produce_todays_argv_exactly(self):
        """The one assertion that protects every existing install: an operator
        who has never touched these switches gets the argv they have always
        got."""
        self.assertEqual(self._claude(), PA.build_agent_args(
            "/bin/claude", "hi", "plan", session_id=None, model=None,
            opts=None, stream_input=True))

    def test_codex_defaults_produce_todays_argv_exactly(self):
        self.assertEqual(self._codex(), PA.build_codex_args(
            "/bin/codex", "plan", "/tmp/wd", model=None, session_id=None,
            opts=None))

    def test_an_absent_provider_settings_key_means_every_default(self):
        """A settings.json with no `provider_settings` at all -- which is every
        settings.json that exists today."""
        self.assertEqual(PA.provider_settings("claude"), self.CLAUDE_DEFAULTS)
        self.assertEqual(PA.provider_settings("codex"), self.CODEX_DEFAULTS)
        self.assertEqual(PA.provider_settings("deepseek"), {})

    # ---- claude ------------------------------------------------------------

    def test_chrome_on_adds_the_flag_and_nothing_else(self):
        base, on = self._claude(), self._claude(chrome=True)
        self.assertEqual(on, base + ["--chrome"])

    def test_subagents_off_denies_the_real_subagent_tools(self):
        args = self._claude(subagents=False)
        denied = args[args.index("--disallowedTools") + 1:]
        self.assertEqual(denied, ["Task", "Agent", "TaskOutput", "TaskStop",
                                  "ListAgents"])

    def test_workflows_off_denies_the_workflow_tool(self):
        args = self._claude(workflows=False)
        self.assertIn("--disallowedTools", args)
        self.assertIn("Workflow", args[args.index("--disallowedTools") + 1:])

    def test_both_off_emit_ONE_disallowedTools_flag(self):
        """Two occurrences is a conflict the CLI resolves by dropping one, with
        no error either way -- which would silently lose half the deny-list."""
        args = self._claude(subagents=False, workflows=False)
        self.assertEqual(args.count("--disallowedTools"), 1)
        denied = args[args.index("--disallowedTools") + 1:]
        self.assertIn("Task", denied)
        self.assertIn("Workflow", denied)

    def test_a_switch_never_drops_the_turns_own_deny_list(self):
        """The operator's per-turn --disallowedTools and the settings switch
        must BOTH survive, in one flag."""
        args = PA.get("claude").spawn_args(
            "/bin/claude", "hi", "plan", "/tmp/wd",
            opts={"disallowed_tools": ["Bash", "Write"]},
            settings=dict(self.CLAUDE_DEFAULTS, subagents=False))
        self.assertEqual(args.count("--disallowedTools"), 1)
        denied = args[args.index("--disallowedTools") + 1:]
        self.assertEqual(denied[:2], ["Bash", "Write"])
        self.assertIn("Task", denied)

    def test_the_switch_does_not_leak_into_the_callers_opts(self):
        """extra_opts must COPY. Mutating the payload would make the second turn
        on a connection differ from the first."""
        opts = {"disallowed_tools": ["Bash"]}
        PA.get("claude").spawn_args(
            "/bin/claude", "hi", "plan", "/tmp/wd", opts=opts,
            settings=dict(self.CLAUDE_DEFAULTS, subagents=False))
        self.assertEqual(opts, {"disallowed_tools": ["Bash"]})

    # ---- codex -------------------------------------------------------------

    def test_codex_memory_off_emits_both_measured_keys(self):
        args = self._codex(memory=False)
        self.assertIn("memories.use_memories=false", args)
        self.assertIn("memories.generate_memories=false", args)

    def test_codex_subagents_off_emits_the_feature_flag(self):
        self.assertIn("features.multi_agent=false", self._codex(subagents=False))

    def test_codex_switches_land_BEFORE_resume(self):
        """`codex exec resume` accepts no flags after it -- measured: a flag
        after `resume` makes codex print a plain-text error and emit no JSON at
        all. Appending switches at the end, as Claude's builder does, would
        break every resumed turn."""
        args = PA.get("codex").spawn_args(
            "/bin/codex", "hi", "plan", "/tmp/wd", session_id="thread-1",
            settings=dict(self.CODEX_DEFAULTS, memory=False, subagents=False))
        self.assertEqual(args[-3:], ["resume", "thread-1", "-"])
        for flag in ("memories.use_memories=false", "features.multi_agent=false"):
            self.assertLess(args.index(flag), args.index("resume"), flag)

    # ---- the dropped one ---------------------------------------------------

    def test_claudes_memory_switch_is_not_offered(self):
        """Planned, and DROPPED: claude 2.1.270 has no memory flag. Offering a
        switch that emits nothing is worse than not offering it."""
        keys = [s["key"] for s in PA.PROVIDER_SETTINGS_SCHEMA["claude"]]
        self.assertNotIn("memory", keys)
        self.assertIn(("claude", "memory"), PA.PROVIDER_SETTINGS_DROPPED)

    # ---- the stored file ---------------------------------------------------

    def test_values_are_read_out_of_settings_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with open(path, "w") as fh:
                json.dump({"permission_mode": "plan",
                           "provider_settings": {"claude": {"chrome": True,
                                                            "subagents": False}}},
                          fh)
            saved = os.environ.get("SUTRA_UI_SETTINGS")
            os.environ["SUTRA_UI_SETTINGS"] = path
            try:
                importlib.reload(providers)
                got = PA.provider_settings("claude")
            finally:
                if saved is None:
                    os.environ.pop("SUTRA_UI_SETTINGS", None)
                else:
                    os.environ["SUTRA_UI_SETTINGS"] = saved
                importlib.reload(providers)
        self.assertEqual(got, {"chrome": True, "subagents": False,
                               "workflows": True})

    def test_a_hand_edited_file_cannot_put_junk_into_an_argv(self):
        """Only known keys, only booleans. Anything else falls back to the
        default rather than reaching a CLI."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with open(path, "w") as fh:
                json.dump({"provider_settings": {"claude": {
                    "chrome": "yes-please", "nonsense": True,
                    "workflows": ["not", "a", "bool"]}}}, fh)
            saved = os.environ.get("SUTRA_UI_SETTINGS")
            os.environ["SUTRA_UI_SETTINGS"] = path
            try:
                importlib.reload(providers)
                got = PA.provider_settings("claude")
            finally:
                if saved is None:
                    os.environ.pop("SUTRA_UI_SETTINGS", None)
                else:
                    os.environ["SUTRA_UI_SETTINGS"] = saved
                importlib.reload(providers)
        self.assertEqual(got, self.CLAUDE_DEFAULTS)
        self.assertNotIn("nonsense", got)

    def test_a_corrupt_settings_file_means_defaults_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with open(path, "w") as fh:
                fh.write("{not json at all")
            saved = os.environ.get("SUTRA_UI_SETTINGS")
            os.environ["SUTRA_UI_SETTINGS"] = path
            try:
                importlib.reload(providers)
                got = PA.provider_settings("claude")
            finally:
                if saved is None:
                    os.environ.pop("SUTRA_UI_SETTINGS", None)
                else:
                    os.environ["SUTRA_UI_SETTINGS"] = saved
                importlib.reload(providers)
        self.assertEqual(got, self.CLAUDE_DEFAULTS)


# ===========================================================================
# 5. service_tier (SPEC section E, the turn-option half)
# ===========================================================================

class TestServiceTier(unittest.TestCase):

    def test_only_codex_declares_it(self):
        self.assertTrue(PA.get("codex").supports_service_tier)
        self.assertFalse(PA.get("claude").supports_service_tier)
        self.assertFalse(PA.get("deepseek").supports_service_tier)

    def test_fast_reaches_the_argv_as_a_quoted_toml_scalar(self):
        args = PA.get("codex").spawn_args(
            "/bin/codex", "hi", "plan", "/tmp/wd",
            opts={"service_tier": "fast"})
        self.assertIn('service_tier="fast"', args)

    def test_an_unlisted_tier_is_dropped_rather_than_forwarded(self):
        """Measured on codex-cli 0.154.0: the CLI does NOT refuse an unknown
        value -- it carries it to the request and drops it with a warning. So
        the allow-list here is the only thing that can say no."""
        for bad in ("priority", "flex", "nonsense", "", 1, None):
            args = PA.get("codex").spawn_args(
                "/bin/codex", "hi", "plan", "/tmp/wd",
                opts={"service_tier": bad})
            self.assertNotIn("service_tier", " ".join(map(str, args)), repr(bad))

    def test_no_service_tier_option_means_no_flag(self):
        self.assertNotIn(
            "service_tier",
            " ".join(PA.get("codex").spawn_args(
                "/bin/codex", "hi", "plan", "/tmp/wd", opts={})))


# ===========================================================================
# 6. resume, spawn env, and the small spawn-time facts
# ===========================================================================

class TestSpawnFacts(unittest.TestCase):

    def test_only_claude_rebuilds_its_argv_to_resume(self):
        """Codex bakes `resume <id>` into the spawn argv (its process is
        one-shot, so the reuse test can never mis-fire); ACP has no --resume
        flag at all. Both answer None, which leaves ws_chat's `args` alone."""
        kw = dict(model=None, session_id="sess-1", opts=None)
        claude = PA.get("claude").resume_args("/bin/claude", "hi", "plan",
                                              "/tmp/wd", **kw)
        self.assertIsNotNone(claude)
        self.assertEqual(claude[claude.index("--resume") + 1], "sess-1")
        self.assertIsNone(PA.get("codex").resume_args("/bin/codex", "hi", "plan",
                                                      "/tmp/wd", **kw))
        self.assertIsNone(PA.get("deepseek").resume_args("/bin/deepseek", "hi",
                                                         "plan", "/tmp/wd", **kw))

    def test_claudes_spawn_argv_carries_no_resume(self):
        """The reuse test compares a RESUME-FREE key. A resume-bearing one made
        it permanently unequal and cold-started claude on every message."""
        args = PA.get("claude").spawn_args("/bin/claude", "hi", "plan", "/tmp/wd",
                                           session_id="sess-1")
        self.assertNotIn("--resume", args)

    def test_codexs_spawn_argv_does_carry_resume(self):
        args = PA.get("codex").spawn_args("/bin/codex", "hi", "plan", "/tmp/wd",
                                          session_id="thread-1")
        self.assertEqual(args[-3:], ["resume", "thread-1", "-"])

    def test_only_deepseek_gets_an_environment_overlay(self):
        self.assertIsNone(PA.get("claude").spawn_env("k"))
        self.assertIsNone(PA.get("codex").spawn_env("k"))
        self.assertEqual(PA.get("deepseek").spawn_env("k"),
                         {"DEEPSEEK_API_KEY": "k"})
        self.assertIsNone(PA.get("deepseek").spawn_env(None))

    def test_the_node_shim_providers_are_the_two_measured_ones(self):
        """Both publish a `#!/usr/bin/env node` shim; Claude's CLI does not."""
        self.assertFalse(PA.get("claude").needs_bundled_node)
        self.assertTrue(PA.get("codex").needs_bundled_node)
        self.assertTrue(PA.get("deepseek").needs_bundled_node)

    def test_only_acp_providers_want_the_handshake(self):
        self.assertFalse(PA.get("claude").needs_acp_handshake)
        self.assertFalse(PA.get("codex").needs_acp_handshake)
        self.assertTrue(PA.get("deepseek").needs_acp_handshake)
        self.assertTrue(PA._ADAPTERS["cursor"].needs_acp_handshake)

    def test_the_mode_note_is_the_providers_own_answer(self):
        """Claude enforces every mode, so None. Codex has no equivalent for
        `dontAsk` and says so rather than running it silently."""
        self.assertIsNone(PA.get("claude").mode_note("dontAsk"))
        note = PA.get("codex").mode_note("dontAsk")
        self.assertIsNotNone(note)
        self.assertEqual(note["running"], "plan")
        self.assertIsNone(PA.get("codex").mode_note("plan"))

    def test_the_failure_label_is_frozen_at_todays_text(self):
        """The line used to be a literal codex-or-claude ternary, so a DeepSeek
        failure has always said "claude exited N". Wrong, known wrong, and NOT
        corrected here -- a working provider's error text is not this change's
        business and the goldens record it."""
        self.assertEqual(PA.get("claude").exit_label, "claude")
        self.assertEqual(PA.get("codex").exit_label, "codex")
        self.assertEqual(PA.get("deepseek").exit_label, "claude")


# ===========================================================================
# 7. Cursor
# ===========================================================================

class TestCursorAdapter(unittest.TestCase):
    """`cursor-agent acp` through the EXISTING ACP runtime.

    NOT VERIFIED LIVE: cursor-agent is not installed on the machine this was
    written on. What is asserted here is the argv shape and that the adapter
    reuses AcpRuntime unchanged; whether `cursor-agent acp` is the right command
    on a real install is the one thing still untested, and it is named as such
    in the adapter's own docstring.
    """

    def setUp(self):
        self.a = PA._ADAPTERS["cursor"]

    def test_it_drives_the_existing_acp_runtime(self):
        self.assertIs(self.a.runtime_class, AcpRuntime)
        self.assertTrue(self.a.needs_acp_handshake)

    def test_the_argv_is_the_acp_subcommand(self):
        self.assertEqual(self.a.spawn_args("/x/cursor-agent", "hi", "plan", "/wd"),
                         ["/x/cursor-agent", "acp"])

    def test_no_model_flag_is_invented(self):
        """DeepSeek's -m was measured on the wire. Cursor's equivalent was not,
        and a guessed flag is either ignored or fails the spawn."""
        args = self.a.spawn_args("/x/cursor-agent", "hi", "plan", "/wd",
                                 model="some-model")
        self.assertEqual(args, ["/x/cursor-agent", "acp"])

    def test_it_does_not_inherit_deepseeks_flags(self):
        self.assertNotIn("--skip-trust", self.a.spawn_args("/x/c", "h", "plan", "/w"))
        self.assertIn("--skip-trust",
                      PA.get("deepseek").spawn_args("/x/d", "h", "plan", "/w"))

    def test_it_shares_the_acp_tool_table(self):
        for name, kind in (("execute", "command"), ("edit", "file_edit"),
                           ("read", "file_read")):
            self.assertEqual(PA.classify_tool("cursor", name)["kind"], kind)

    def test_its_runtime_is_labelled_cursor(self):
        with _loop() as loop:
            self.assertEqual(self.a.new_runtime().provider_id, "cursor")
            self.assertEqual(PA.get("deepseek").new_runtime().provider_id,
                             "deepseek")

    @needs_spawn
    def test_it_completes_an_acp_handshake_against_a_FAKE_agent(self):
        """The transport half, proven. The fake ACP agent stands in for
        cursor-agent: the point is that CursorAdapter's argv + AcpRuntime reach
        an initialized session with no cursor-specific code in the runtime."""
        async def go():
            rt = self.a.new_runtime()
            args = self.a.spawn_args(VENV_PY, "hi", "plan", _ENV_TMP)
            # The fake is a python script, so the real binary slot is the
            # interpreter and the script is argv[1]; `acp` rides along exactly
            # where it would on a real install and the fake ignores it.
            args = [VENV_PY, ACP_STUB] + args[1:]
            try:
                await rt.spawn(args, _ENV_TMP, tuple(args))
                self.assertTrue(rt.alive)
                # The fake is DeepSeek-shaped: it refuses session/new until an
                # `authenticate` has crossed, reproducing the real fork's
                # "Gemini API key is missing" refusal. cursor-agent may need no
                # key at all, which is exactly why this half is the TRANSPORT
                # claim and not an auth claim -- so authenticate first and let
                # the assertion stay on "an initialized session came back".
                await rt.authenticate("not-a-real-key")
                await rt.new_session(_ENV_TMP, "plan")
                self.assertTrue(rt.session_id)
            finally:
                rt.kill_group()

        with _loop() as loop:
            loop.run_until_complete(asyncio.wait_for(go(), 30))


# ===========================================================================
# 8. The shared process helper
# ===========================================================================

class TestSharedProcessHelper(unittest.TestCase):
    """`alive`, `kill_group`, `stop`, `clear`, `subscribe`, `unsubscribe`,
    `_fanout`, `_observe` and the spawn were COPIED into all three runtime
    files. These assert there is now exactly one of each."""

    RUNTIMES = (SessionRuntime, CodexRuntime, AcpRuntime)

    def test_all_three_use_the_shared_base(self):
        for cls in self.RUNTIMES:
            self.assertTrue(issubclass(cls, proc_group.ProcRuntime), cls)

    def test_the_lifecycle_methods_are_ONE_implementation(self):
        """Same function object on all three -- not three that happen to agree
        today. This is what makes a fix impossible to apply only twice."""
        for name in ("alive", "kill_group", "clear", "subscribe", "unsubscribe",
                     "_fanout", "_notify_subscribers", "_observe", "stop",
                     "_spawn_process"):
            impls = {getattr(cls, name) for cls in self.RUNTIMES}
            self.assertEqual(len(impls), 1,
                             "%s has %d implementations" % (name, len(impls)))

    def test_the_one_deliberate_difference_is_declared(self):
        """ACP sets self.state directly at each transition, so its fanout must
        NOT also infer state -- a second writer would fight the first."""
        self.assertTrue(SessionRuntime.OBSERVES_FRAMES)
        self.assertTrue(CodexRuntime.OBSERVES_FRAMES)
        self.assertFalse(AcpRuntime.OBSERVES_FRAMES)

    def test_acp_is_the_only_one_with_an_in_band_cancel(self):
        """Claude and Codex have no control channel; killing the group is the
        only interrupt they have."""
        self.assertIs(SessionRuntime._before_kill, proc_group.ProcRuntime._before_kill)
        self.assertIs(CodexRuntime._before_kill, proc_group.ProcRuntime._before_kill)
        self.assertIsNot(AcpRuntime._before_kill, proc_group.ProcRuntime._before_kill)

    def test_kill_group_is_idempotent_on_every_runtime(self):
        with _loop() as loop:
            for cls in self.RUNTIMES:
                rt = cls()
                self.assertFalse(rt.alive, cls)
                self.assertFalse(rt.kill_group(), cls)
                self.assertFalse(rt.kill_group(), cls)

    def test_stop_records_the_intent_on_every_runtime(self):
        """The flag must be set even when there is nothing to kill: the stdout
        loop can end between the signal and the assignment and would otherwise
        report the operator's own interrupt as a crash."""
        with _loop() as loop:
            for cls in self.RUNTIMES:
                rt = cls()
                rt.stop()
                self.assertTrue(rt.stopped, cls)
                self.assertEqual(rt.state, "stopped", cls)

    def test_clear_forgets_the_process_but_not_the_thread(self):
        """Codex's thread id outlives every process that served it; dropping it
        here would silently start a new conversation on the next message."""
        with _loop() as loop:
            rt = CodexRuntime()
            rt.proc, rt.key, rt.session_id = object(), ("k",), "thread-1"
            rt.clear()
            self.assertIsNone(rt.proc)
            self.assertIsNone(rt.key)
            self.assertEqual(rt.session_id, "thread-1")

    def test_the_fanout_delivers_to_primary_and_subscribers_on_all_three(self):
        async def go(cls):
            rt = cls()
            primary, seen = [], []
            rt.subscribe(seen.append)

            async def prim(f):
                primary.append(f)
            emit = rt._fanout(prim)
            await emit({"type": "token", "text": "a"})
            return primary, seen

        with _loop() as loop:
            for cls in self.RUNTIMES:
                primary, seen = loop.run_until_complete(go(cls))
                self.assertEqual(primary, [{"type": "token", "text": "a"}], cls)
                self.assertEqual(seen, primary, cls)

    def test_a_broken_subscriber_never_costs_the_turn(self):
        async def go(cls):
            rt = cls()
            good = []

            def boom(_):
                raise RuntimeError("observer exploded")
            rt.subscribe(boom)
            rt.subscribe(good.append)

            async def prim(f):
                pass
            await rt._fanout(prim)({"type": "token", "text": "a"})
            return good

        with _loop() as loop:
            for cls in self.RUNTIMES:
                self.assertEqual(len(loop.run_until_complete(go(cls))), 1, cls)

    def test_a_primary_exception_still_propagates(self):
        """Frozen behaviour: a dead socket must end the turn loop."""
        async def go(cls):
            rt = cls()

            async def prim(f):
                raise ConnectionResetError("socket gone")
            with self.assertRaises(ConnectionResetError):
                await rt._fanout(prim)({"type": "token", "text": "a"})

        with _loop() as loop:
            for cls in self.RUNTIMES:
                loop.run_until_complete(go(cls))

    @needs_spawn
    def test_every_runtime_spawns_into_its_own_process_group(self):
        """The property the three copies existed to protect, now asserted once
        against the one implementation. test_provider_spawn_group.py asserts the
        same thing through each class's own spawn()."""
        async def go(cls):
            rt = cls()
            captured = {}
            real = asyncio.create_subprocess_exec

            async def fake(*a, **kw):
                captured.update(kw)
                raise OSError("stop here")
            asyncio.create_subprocess_exec = fake
            try:
                with self.assertRaises(OSError):
                    await rt._spawn_process(["/bin/echo", "hi"], _ENV_TMP, ("k",))
            finally:
                asyncio.create_subprocess_exec = real
            return captured

        with _loop() as loop:
            for cls in self.RUNTIMES:
                kw = loop.run_until_complete(go(cls))
                self.assertEqual(kw.get("process_group"), 0, cls)
                self.assertNotIn("start_new_session", kw)
                self.assertEqual(kw.get("limit"), proc_group.STREAM_LIMIT, cls)


# ===========================================================================
# 9. The ACP audit line: approved vs declined
# ===========================================================================

class TestAcpPermissionAudit(unittest.TestCase):
    """`approved = option_id is not None` was True for a REJECTION too, because
    a rejection is a selected option like any other. The decision was always
    right; the sentence describing it was not, which is the worse half to get
    wrong in an audit line."""

    def setUp(self):
        import acp_runtime
        self.f = acp_runtime._option_is_approval

    OPTIONS = [
        {"optionId": "yes", "kind": "allow_once"},
        {"optionId": "yes-always", "kind": "allow_always"},
        {"optionId": "no", "kind": "reject_once"},
        {"optionId": "no-always", "kind": "reject_always"},
    ]

    def test_an_allow_option_reads_as_approved(self):
        for oid in ("yes", "yes-always"):
            self.assertTrue(self.f(oid, self.OPTIONS), oid)

    def test_a_reject_option_reads_as_DECLINED(self):
        """The bug: both of these used to report "approved"."""
        for oid in ("no", "no-always"):
            self.assertFalse(self.f(oid, self.OPTIONS), oid)

    def test_no_answer_at_all_is_not_an_approval(self):
        self.assertFalse(self.f(None, self.OPTIONS))

    def test_an_agent_that_omits_kind_falls_back_to_the_id(self):
        opts = [{"optionId": "reject_once"}, {"optionId": "allow_once"}]
        self.assertFalse(self.f("reject_once", opts))
        self.assertTrue(self.f("allow_once", opts))

    def test_an_unreadable_option_is_reported_as_not_approved(self):
        """Over-reporting an approval is the direction that misleads."""
        self.assertFalse(self.f("deny_everything", []))
        self.assertFalse(self.f("cancel", []))

    def test_the_chooser_really_does_reject_under_plan(self):
        """The other half of the pair: the DECISION. If this ever flips, the
        audit line being right stops mattering."""
        import acp_runtime
        chosen = acp_runtime._choose_permission_option("plan", "execute",
                                                       self.OPTIONS)
        self.assertEqual(chosen, "no")
        self.assertFalse(self.f(chosen, self.OPTIONS))


# ===========================================================================
# 10. The per-connection `perm` query parameter (SPEC section E)
# ===========================================================================

class TestPermQueryParam(unittest.TestCase):
    """Runs a real uvicorn with codex pointed at the fake agent, and opens real
    sockets. Every case below is decided BEFORE any process is spawned, which is
    why this class runs on Python 3.9 while the turn tests do not."""

    proc = None
    port = None
    tmpdir = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-perm-")
        sys.path.insert(0, os.path.join(HERE, "..", "lib"))
        sys.path.insert(0, HERE)
        import fixture_seed
        fixture_seed.seed(cls.tmpdir)

        for stub in (CODEX_STUB, ACP_STUB):
            if os.path.exists(stub):
                os.chmod(stub, 0o755)

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
        env.pop("ANTHROPIC_API_KEY", None)
        # THE CONSENT GATE, ENGAGED ON PURPOSE. This class is about what the
        # per-connection `perm=` param does when a mode is NOT consented to,
        # so the gate has to be on for the clamp cases to mean anything.
        #
        # It used to be enough to pop the opt-in, because the gate was the
        # shipped default. Since 2026-09-18 it is an opt-out (Full access is
        # the default and it runs -- providers.unsafe_modes_allowed), so the
        # clamped posture must be ASKED for or every clamp assertion below
        # silently tests the open one.
        env.pop("SUTRA_UI_ALLOW_UNSAFE_PERM_MODES", None)
        env["SUTRA_UI_SAFE_PERM_MODES"] = "1"
        # ...and a STORED mode, so "keeps the stored setting" names a real
        # stored value rather than the shipped default seen through the clamp.
        with open(env["SUTRA_UI_SETTINGS"], "w") as fh:
            json.dump({"permission_mode": "plan"}, fh)
        env["SUTRA_UI_CODEX_BIN"] = CODEX_STUB
        env["SUTRA_UI_DEEPSEEK_BIN"] = ACP_STUB
        env["SUTRA_UI_DEEPSEEK_API_KEY"] = "sk-fake-not-a-real-key"

        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:   # noqa: BLE001
                if cls.proc.poll() is not None:
                    out = cls.proc.stdout.read().decode("utf-8", "replace")
                    raise RuntimeError("server died:\n" + out[-4000:])
                time.sleep(0.25)
        else:
            raise RuntimeError("perm-param server did not come up")

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

    def _first_frame(self, provider="codex", perm=None):
        """Open a socket and read ONE frame. That frame is either the `provider`
        status line (accepted) or an `error` (refused), which is exactly the
        distinction every case below turns on."""
        from websockets.sync.client import connect
        url = "ws://127.0.0.1:%d/ws/chat?provider=%s" % (self.port, provider)
        if perm is not None:
            url += "&perm=" + perm
        with connect(url, open_timeout=10) as ws:
            return json.loads(ws.recv(timeout=15))

    # ---- absent means today's behaviour ------------------------------------

    def test_no_perm_keeps_the_stored_setting(self):
        """The whole feature is additive: every existing caller sends no `perm`
        and must take the unchanged path."""
        f = self._first_frame()
        self.assertEqual(f["type"], "provider")
        self.assertEqual(f["permission_mode"], "plan")
        self.assertIsNone(f["permission_requested"])
        self.assertFalse(f["permission_clamped"])

    # ---- accepted ----------------------------------------------------------

    def test_a_supported_mode_is_used_for_this_connection(self):
        f = self._first_frame(perm="plan")
        self.assertEqual(f["type"], "provider")
        self.assertEqual(f["permission_mode"], "plan")
        self.assertEqual(f["permission_requested"], "plan")

    def _stored_mode(self):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/settings" % self.port, timeout=5) as r:
            return json.loads(r.read())

    def test_it_does_not_write_the_setting(self):
        """PER CONNECTION ONLY. If this leaked into settings.json, one pane
        would silently re-arm every other pane and every routine.

        BEFORE vs AFTER, not before vs a literal. This asserted `"plan"`, which
        held only because plan was also the shipped default -- so once the
        default moved (2026-09-18) the test failed while the behaviour it
        guards was untouched. Comparing the two reads says what it means and
        cannot go stale again.
        """
        before = self._stored_mode()["settings"]["permission_mode"]
        self._first_frame(perm="plan")
        payload = self._stored_mode()
        self.assertEqual(payload["settings"]["permission_mode"], before,
                         "a per-connection perm= leaked into the setting")
        path = payload["settings"]["settings_path"]
        try:
            with open(path) as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = {}
        self.assertNotIn("perm", raw)

    # ---- refused -----------------------------------------------------------

    def test_an_unknown_mode_is_refused_not_silently_ignored(self):
        for bad in ("yolo", "PLAN", "acceptedits", "x"):
            f = self._first_frame(perm=bad)
            self.assertEqual(f["type"], "error", bad)
            self.assertEqual(f["code"], "unknown-perm-mode", bad)

    def test_a_mode_this_provider_cannot_enforce_is_refused(self):
        """`auto` is Claude's. A Codex pane that silently ran `plan` instead
        would be showing a chip nothing is enforcing -- the exact failure the
        mode_note frame exists for, except here we can refuse instead."""
        f = self._first_frame(provider="codex", perm="auto")
        self.assertEqual(f["type"], "error")
        self.assertEqual(f["code"], "perm-mode-unsupported")
        self.assertIn("auto", f["detail"])

    def test_the_same_mode_is_accepted_on_the_provider_that_has_it(self):
        """The other half: `auto` is refused on Codex because of the PROVIDER,
        not because the mode is bad."""
        self.assertIn("auto", PA.get("claude").native_modes())
        self.assertNotIn("auto", PA.get("codex").native_modes())

    # ---- the consent gate --------------------------------------------------

    def test_an_unconsented_unsafe_mode_is_clamped_and_SAID(self):
        """Same gate, same clamp as a stored value -- and the clamp is reported
        rather than silent, because a pane asserting authority the agent does
        not have is what this whole surface exists to prevent."""
        for unsafe in ("acceptEdits", "bypassPermissions"):
            f = self._first_frame(provider="codex", perm=unsafe)
            self.assertEqual(f["type"], "provider", unsafe)
            self.assertEqual(f["permission_mode"], "plan", unsafe)
            self.assertEqual(f["permission_requested"], unsafe, unsafe)
            self.assertTrue(f["permission_clamped"], unsafe)
            self.assertFalse(f["writes_files"], unsafe)


if __name__ == "__main__":
    unittest.main()
