"""The two lanes that stopped buying what they never used (2026-09-19).

WHAT THIS PINS, and why it is one file rather than two. Shadow spends its
tokens in three places -- the worker, the one-shot decider, and the chats --
and September's transcripts said where:

    WORKER (delegate)    48 sessions   1,389 calls   141.6M   83.9%
    DECIDER (one-shot)  758 sessions     758 calls    20.9M   12.4%
    SHADOW chat          41 sessions     187 calls     6.3M    3.8%

Two facts in that table are waste rather than work:

  * the decider paid ~28,260 tokens per call to answer a ~1,622-token
    question, because it was spawned as a full Claude Code agent -- every
    tool schema, the skills catalog, the agent roster, the MCP servers, the
    founder's settings and hooks -- all of which make_decider's own
    docstring forbids it from using;

  * the worker ran with NO compaction boundary in any of 48 sessions, its
    context climbing 27.8k -> 327k inside one mission, with 9.4% of its
    calls served above 200k.

Neither is a behaviour the founder asked for, and neither is visible to
them. So the fix is a transport change on both lanes and NOTHING else: the
decide prompt, the validator, the JSON contract, the mission loop, the turn
budget, the checks and the say path are all untouched. These tests are the
guard on that "and nothing else".

Run: .venv/bin/python -m pytest test_shadow_lean_lanes.py -q
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault("SUTRA_SHADOW_HOME", "/tmp/sutra-lean-lanes-home")

import app                                             # noqa: E402
import provider_adapters                               # noqa: E402
import shadow_runner                                   # noqa: E402


def _flag(args, name):
    """The value after `name`, or None when the flag is absent."""
    return args[args.index(name) + 1] if name in args else None


class TestReasoningArgv(unittest.TestCase):
    """provider_adapters.build_reasoning_args -- the builder itself."""

    def setUp(self):
        self.args = provider_adapters.build_reasoning_args(
            "/usr/bin/claude", "SYS")

    def test_01_no_tools_are_reachable(self):
        """The saving AND the guarantee. `--tools ""` is what takes the
        built-in schemas out of the prompt, and it is also what makes "the
        decider cannot act" structural instead of conventional."""
        self.assertEqual("", _flag(self.args, "--tools"))

    def test_02_no_settings_sources(self):
        """No user/project/local settings -> no plugins, no hooks, no
        CLAUDE.md, no skills catalog, no agent roster."""
        self.assertEqual("", _flag(self.args, "--setting-sources"))

    def test_03_no_mcp_server_can_be_reached(self):
        """--strict-mcp-config with no --mcp-config: not the machine's
        global ~/.claude.json either."""
        self.assertIn("--strict-mcp-config", self.args)
        self.assertNotIn("--mcp-config", self.args)

    def test_04_the_system_prompt_REPLACES_claude_codes(self):
        self.assertEqual("SYS", _flag(self.args, "--system-prompt"))
        self.assertNotIn("--append-system-prompt", self.args)

    def test_05_narrowest_permission_mode_by_default(self):
        self.assertEqual("plan", _flag(self.args, "--permission-mode"))

    def test_06_still_speaks_the_persistent_stream_protocol(self):
        """SessionRuntime's demux is unchanged, so the frames it needs must
        be too -- this is the one thing a leaner argv could silently break."""
        self.assertEqual("stream-json", _flag(self.args, "--input-format"))
        self.assertEqual("stream-json", _flag(self.args, "--output-format"))
        self.assertIn("--verbose", self.args)
        self.assertIn("--include-partial-messages", self.args)
        self.assertIn("-p", self.args)

    def test_07_carries_no_session_and_no_resume(self):
        """One process per decision, never reused -- the property
        make_decider's docstring defends. A --resume here would grow one
        context across every turn of every mission, which is the thing the
        one-shot exists to avoid."""
        self.assertNotIn("--resume", self.args)
        self.assertNotIn("--fork-session", self.args)


class TestDeciderUsesTheLeanLane(unittest.TestCase):

    def test_08_app_wires_the_decider_to_decide_args(self):
        src = Path(app.__file__).read_text()
        self.assertIn("make_decider(_decide_args, _shadow_workdir(),", src)
        self.assertEqual(1, src.count("set_default_decider("))

    def test_09_the_prompt_ITSELF_is_untouched(self):
        """The whole claim of this change is that Shadow reads the same
        thing. _DECIDE_PROMPT is what it reads, and the system prompt says
        nothing about how to decide -- every rule stays in the user turn."""
        self.assertIn("You are Shadow, driving one target chat toward an "
                      "outcome.", shadow_runner._DECIDE_PROMPT)
        sysp = app.SHADOW_DECIDER_SYSTEM_PROMPT
        for rule in ("done_when", "confirms_check", "ask_founder",
                     "instruction"):
            self.assertNotIn(
                rule, sysp,
                "decision rules belong in _DECIDE_PROMPT, not the envelope")

    def test_10_the_reply_contract_is_unchanged(self):
        """_first_decision still parses a fenced object, so a lane that
        answers with prose around the fence is as acceptable as it was."""
        got = shadow_runner._first_decision(
            'here you go\n```json\n{"action": "instruct"}\n```\n')
        self.assertEqual({"action": "instruct"}, got)


class TestWorkerCompaction(unittest.TestCase):

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_AUTOCOMPACT", None)

    def test_11_default_is_inside_the_cli_band(self):
        self.assertEqual("150000", app.worker_autocompact())

    def test_12_off_is_reachable_and_restores_todays_argv(self):
        """A founder who wants the old unbounded window needs one env var."""
        os.environ["SUTRA_SHADOW_AUTOCOMPACT"] = "0"
        self.assertIsNone(app.worker_autocompact())

    def test_13_junk_and_out_of_band_values_pass_no_flag(self):
        """Out of the CLI's documented 100k-1M band the argv parser would
        reject the spawn -- a dead worker is worse than a wide window."""
        for raw in ("banana", "", "99999", "1000001", "-1"):
            os.environ["SUTRA_SHADOW_AUTOCOMPACT"] = raw
            self.assertIsNone(app.worker_autocompact(), raw)

    def test_14_only_the_worker_carries_it(self):
        """The supervisor's context IS the founder's conversation with
        Shadow, and the reasoning lane is one turn long. Neither compacts."""
        bin_ = "/usr/bin/claude"
        worker = provider_adapters.build_agent_args(
            bin_, "", "plan", stream_input=True, autocompact="150000")
        self.assertEqual("150000", _flag(worker, "--autocompact"))
        supervisor = provider_adapters.build_agent_args(
            bin_, "", "plan", stream_input=True)
        self.assertNotIn("--autocompact", supervisor)
        self.assertNotIn("--autocompact",
                         provider_adapters.build_reasoning_args(bin_, "SYS"))

    def test_15_omitting_it_is_byte_identical_to_before(self):
        """The rule every addition to this builder has followed."""
        bin_ = "/usr/bin/claude"
        self.assertEqual(
            provider_adapters.build_agent_args(bin_, "hi", "plan"),
            provider_adapters.build_agent_args(bin_, "hi", "plan",
                                               autocompact=None))


if __name__ == "__main__":
    unittest.main()
