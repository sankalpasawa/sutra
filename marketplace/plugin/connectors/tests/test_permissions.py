"""Permission engine suite.

stdlib unittest only -- sutra-ui's suite refuses to import httpx/requests/
fastapi.testclient, and this package must stay importable from it.

Run:  python3 -m unittest discover -s tests -t . -v    (from connectors/)

The tests that matter most are the adversarial ones: a broad deny beating a
narrow allow, a hook failing to widen, and bypass mode failing to auto-approve
a destructive tool. Those three are the guarantees; the rest is plumbing.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

from connectors.permissions.engine import (  # noqa: E402
    DEFAULT_PROTECTED_REFS, Decision, HookResult, PermissionEngine, ToolCall,
)
from connectors.permissions.matcher import (  # noqa: E402
    match_param, match_qualifier, match_repo, match_tool,
)
from connectors.permissions.modes import Mode, Outcome  # noqa: E402
from connectors.permissions.rules import RuleKind, parse_rule  # noqa: E402
from connectors.permissions.settings import SettingsSource, load_settings  # noqa: E402
from connectors.permissions.tools import GITHUB_TOOLS, ToolRegistry  # noqa: E402


def settings(**blocks):
    """Build settings from {source_name: permissions_dict}."""
    return load_settings([
        SettingsSource(name, {"permissions": perms}) for name, perms in blocks.items()
    ])


def engine(**blocks):
    return PermissionEngine(settings(**blocks))


READ = ToolCall("github.get_file", {"repository": "acme/api", "path": "src/main.py"})
WRITE = ToolCall("github.create_pull_request", {"repository": "acme/api", "base": "develop"})
MERGE = ToolCall("github.merge_pull_request", {"repository": "acme/api", "base": "main"})


# ====================================================================== #
class TestRuleParsing(unittest.TestCase):

    def test_bare_rule(self):
        rule = parse_rule("github.get_file", RuleKind.DENY)
        self.assertFalse(rule.ignored)
        self.assertTrue(rule.is_bare)

    def test_star_specifier_equals_bare(self):
        self.assertTrue(parse_rule("github.get_file(*)", RuleKind.DENY).is_bare)

    def test_resource_form(self):
        rule = parse_rule("github.get_file(acme/api:src/**)", RuleKind.ALLOW)
        self.assertFalse(rule.ignored)
        self.assertEqual(rule.repo_pattern, "acme/api")
        self.assertEqual(rule.qualifier_pattern, "src/**")

    def test_param_form_on_deny(self):
        rule = parse_rule("github.create_pull_request(draft:false)", RuleKind.DENY)
        self.assertFalse(rule.ignored)
        self.assertEqual(rule.param_name, "draft")
        self.assertEqual(rule.param_value, "false")

    def test_param_form_rejected_on_allow(self):
        """Matching one parameter does not establish a call is safe overall."""
        rule = parse_rule("github.create_pull_request(draft:false)", RuleKind.ALLOW)
        self.assertTrue(rule.ignored)
        self.assertIn("allow", rule.warning)

    def test_primary_field_not_matchable_in_param_form(self):
        """Claude ignores Bash(command:...) because it would be bypassable."""
        for raw in ("github.get_file(repository:acme/api)",
                    "github.get_file(path:src/**)",
                    "github.create_branch(branch:release/1)",
                    "github.get_file(connector_id:conn_1)"):
            rule = parse_rule(raw, RuleKind.DENY)
            self.assertTrue(rule.ignored, raw)
            self.assertIn("primary resource field", rule.warning)

    def test_unanchored_allow_glob_rejected(self):
        for raw in ("*", "gith*", "*.get_file"):
            self.assertTrue(parse_rule(raw, RuleKind.ALLOW).ignored, raw)

    def test_anchored_allow_glob_accepted(self):
        for raw in ("github.get_*", "github.*"):
            self.assertFalse(parse_rule(raw, RuleKind.ALLOW).ignored, raw)

    def test_tool_glob_always_allowed_in_deny(self):
        self.assertFalse(parse_rule("*", RuleKind.DENY).ignored)

    def test_malformed_rules_are_ignored_not_widened(self):
        for raw in ("", "   ", "github.get_file(acme)", "github.get_file(acme/api:)"):
            rule = parse_rule(raw, RuleKind.ALLOW)
            self.assertTrue(rule.ignored, repr(raw))
            self.assertIsNotNone(rule.warning)


# ====================================================================== #
class TestMatchers(unittest.TestCase):

    def test_repo_match_is_case_insensitive(self):
        self.assertTrue(match_repo("Acme/*", "acme/api"))
        self.assertTrue(match_repo("acme/API", "ACME/api"))

    def test_bare_repo_pattern_matches_everything(self):
        self.assertTrue(match_repo(None, "anything/at-all"))
        self.assertTrue(match_repo(None, None))

    def test_specific_repo_rule_does_not_match_a_repoless_call(self):
        """A rule naming a repo must not authorise a call that has none."""
        self.assertFalse(match_repo("acme/api", None))
        self.assertTrue(match_repo("*", None))

    def test_single_star_does_not_cross_a_separator(self):
        self.assertTrue(match_qualifier("src/*", "src/main.py"))
        self.assertFalse(match_qualifier("src/*", "src/deep/main.py"))

    def test_double_star_crosses_separators(self):
        self.assertTrue(match_qualifier("src/**", "src/deep/main.py"))

    def test_leading_double_star_also_matches_at_root(self):
        """`**/.env` must catch `.env` as well as `config/.env`."""
        self.assertTrue(match_qualifier("**/.env", ".env"))
        self.assertTrue(match_qualifier("**/.env", "config/.env"))
        self.assertTrue(match_qualifier("**/.env", "a/b/c/.env"))

    def test_qualifier_rule_fails_closed_on_missing_value(self):
        """A rule that asked to be specific must not widen to the whole repo."""
        self.assertFalse(match_qualifier("src/**", None))
        self.assertTrue(match_qualifier(None, None))

    def test_omitted_parameter_never_matches(self):
        self.assertFalse(match_param("*", None))
        self.assertTrue(match_param("false", False))
        self.assertTrue(match_param("true", True))

    def test_tool_glob_must_match_full_name(self):
        self.assertTrue(match_tool("github.get_*", "github.get_file"))
        self.assertFalse(match_tool("github.get_", "github.get_file"))
        self.assertTrue(match_tool("*", "github.get_file"))


# ====================================================================== #
class TestPrecedence(unittest.TestCase):
    """deny -> ask -> allow. First match wins. Specificity never reorders."""

    def test_broad_deny_beats_narrow_allow(self):
        eng = engine(project={
            "allow": ["github.create_pull_request(acme/api)"],
            "deny": ["github.create_*"],
        })
        decision = eng.evaluate(WRITE)
        self.assertIs(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.step, 1)

    def test_matching_ask_beats_more_specific_allow(self):
        eng = engine(project={
            "allow": ["github.create_pull_request(acme/api:develop)"],
            "ask": ["github.create_pull_request"],
        })
        decision = eng.evaluate(WRITE)
        self.assertIs(decision.outcome, Outcome.ASK)
        self.assertEqual(decision.step, 4)

    def test_deny_rules_cannot_carry_allowlist_exceptions(self):
        """The documented consequence: you cannot punch a hole in a deny."""
        eng = engine(project={
            "deny": ["github.get_file(acme/*)"],
            "allow": ["github.get_file(acme/api:README.md)"],
        })
        call = ToolCall("github.get_file", {"repository": "acme/api", "path": "README.md"})
        self.assertIs(eng.evaluate(call).outcome, Outcome.DENY)

    def test_allow_rule_permits_when_nothing_denies(self):
        eng = engine(project={"allow": ["github.create_pull_request(acme/*)"]})
        decision = eng.evaluate(WRITE)
        self.assertIs(decision.outcome, Outcome.ALLOW)
        self.assertEqual(decision.step, 6)


# ====================================================================== #
class TestModes(unittest.TestCase):

    def test_plan_blocks_writes_above_allow_rules(self):
        eng = engine(project={"allow": ["github.create_pull_request"]})
        decision = eng.evaluate(WRITE, mode=Mode.PLAN)
        self.assertIs(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.step, 2, "an allow rule must not enable a write in plan mode")

    def test_plan_permits_reads(self):
        self.assertIs(engine().evaluate(READ, mode=Mode.PLAN).outcome, Outcome.ALLOW)

    def test_dont_ask_denies_without_an_allow_rule(self):
        self.assertIs(engine().evaluate(WRITE, mode=Mode.DONT_ASK).outcome, Outcome.DENY)

    def test_dont_ask_honours_allow_rules(self):
        eng = engine(project={"allow": ["github.create_pull_request(acme/*)"]})
        self.assertIs(eng.evaluate(WRITE, mode=Mode.DONT_ASK).outcome, Outcome.ALLOW)

    def test_dont_ask_denies_destructive_even_when_allowed(self):
        eng = engine(project={"allow": ["github.merge_pull_request(acme/*)"]})
        decision = eng.evaluate(MERGE, mode=Mode.DONT_ASK)
        self.assertIs(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.step, 3)

    def test_bypass_does_not_auto_approve_destructive_tools(self):
        """The actions no mode auto-approves. This is the whole mitigation for
        having shipped bypassPermissions at all."""
        eng = engine(project={"allow": ["github.merge_pull_request"]})
        decision = eng.evaluate(MERGE, mode=Mode.BYPASS)
        self.assertIs(decision.outcome, Outcome.ASK)
        self.assertEqual(decision.step, 3)

    def test_bypass_still_obeys_deny_rules(self):
        eng = engine(project={"deny": ["github.create_pull_request"]})
        self.assertIs(eng.evaluate(WRITE, mode=Mode.BYPASS).outcome, Outcome.DENY)

    def test_bypass_allows_ordinary_writes(self):
        self.assertIs(engine().evaluate(WRITE, mode=Mode.BYPASS).outcome, Outcome.ALLOW)

    def test_accept_edits_allows_content_writes(self):
        self.assertIs(engine().evaluate(WRITE, mode=Mode.ACCEPT_EDITS).outcome, Outcome.ALLOW)

    def test_default_mode_prompts_on_writes_and_not_on_reads(self):
        eng = engine()
        self.assertIs(eng.evaluate(READ).outcome, Outcome.ALLOW)
        self.assertIs(eng.evaluate(WRITE).outcome, Outcome.ASK)

    def test_session_grant_satisfies_default_mode(self):
        eng = engine()
        grants = {"github.create_pull_request|acme/api"}
        self.assertIs(eng.evaluate(WRITE, session_grants=grants).outcome, Outcome.ALLOW)

    def test_auto_mode_escalates_when_tainted(self):
        eng = engine()
        self.assertIs(eng.evaluate(WRITE, mode=Mode.AUTO).outcome, Outcome.ALLOW)
        self.assertIs(eng.evaluate(WRITE, mode=Mode.AUTO, tainted=True).outcome, Outcome.ASK)

    def test_mode_aliases_and_unknown(self):
        self.assertIs(Mode.parse("manual"), Mode.DEFAULT)
        self.assertIs(Mode.parse("acceptEdits"), Mode.ACCEPT_EDITS)
        with self.assertRaises(ValueError):
            Mode.parse("yolo")


# ====================================================================== #
class TestHooks(unittest.TestCase):
    """Hooks narrow. They never widen."""

    def test_hook_block_beats_every_allow_rule(self):
        eng = engine(project={"allow": ["github.get_file"]})
        decision = eng.evaluate(READ, hook=HookResult.BLOCK)
        self.assertIs(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.step, 0)

    def test_hook_allow_cannot_override_a_deny_rule(self):
        eng = engine(project={"deny": ["github.get_file"]})
        self.assertIs(eng.evaluate(READ, hook=HookResult.ALLOW).outcome, Outcome.DENY)

    def test_hook_allow_cannot_override_an_ask_rule(self):
        eng = engine(project={"ask": ["github.get_file"]})
        self.assertIs(eng.evaluate(READ, hook=HookResult.ALLOW).outcome, Outcome.ASK)

    def test_hook_allow_skips_the_prompt_when_nothing_else_matches(self):
        decision = engine().evaluate(WRITE, hook=HookResult.ALLOW)
        self.assertIs(decision.outcome, Outcome.ALLOW)
        self.assertEqual(decision.step, 5)

    def test_hook_ask_escalates_an_otherwise_allowed_call(self):
        """This is the taint gate: it can raise the bar, never lower it."""
        eng = engine(project={"allow": ["github.create_pull_request"]})
        decision = eng.evaluate(WRITE, hook=HookResult.ASK)
        self.assertIs(decision.outcome, Outcome.ASK)
        self.assertEqual(decision.step, 4)


# ====================================================================== #
class TestToolVisibility(unittest.TestCase):

    def test_bare_deny_removes_the_tool_from_context(self):
        eng = engine(project={"deny": ["github.delete_branch"]})
        self.assertNotIn("github.delete_branch", eng.visible_tools())

    def test_glob_deny_removes_every_matching_tool(self):
        eng = engine(project={"deny": ["github.create_*"]})
        visible = eng.visible_tools()
        self.assertNotIn("github.create_branch", visible)
        self.assertNotIn("github.create_pull_request", visible)
        self.assertIn("github.get_file", visible)

    def test_scoped_deny_leaves_the_tool_visible(self):
        eng = engine(project={"deny": ["github.get_file(acme/*)"]})
        self.assertIn("github.get_file", eng.visible_tools())

    def test_destructive_tools_that_do_not_exist_cannot_be_reached(self):
        names = ToolRegistry(GITHUB_TOOLS).names()
        for absent in ("github.repository.create", "github.repository.delete",
                       "github.org.settings.write"):
            self.assertNotIn(absent, names)


# ====================================================================== #
class TestSettingsHierarchy(unittest.TestCase):

    def test_rules_union_across_sources(self):
        eng = engine(
            user={"allow": ["github.get_file"]},
            managed={"deny": ["github.get_file(acme/*)"]},
        )
        self.assertIs(eng.evaluate(READ).outcome, Outcome.DENY)

    def test_managed_wins_default_mode(self):
        resolved = settings(
            user={"defaultMode": "bypassPermissions"},
            managed={"defaultMode": "plan"},
        )
        self.assertIs(resolved.default_mode, Mode.PLAN)

    def test_allow_managed_rules_only_discards_other_sources(self):
        resolved = settings(
            managed={"allowManagedPermissionRulesOnly": True, "deny": ["github.delete_branch"]},
            project={"allow": ["github.create_pull_request"]},
        )
        self.assertTrue(resolved.allow_managed_rules_only)
        self.assertEqual([r.source for r in resolved.rules], ["managed"])

    def test_locks_are_ored_not_overridden(self):
        """A user can lock themselves out of bypass; a higher-precedence
        source must not silently undo the lock."""
        resolved = settings(
            managed={"defaultMode": "default"},
            user={"disableBypassPermissionsMode": "disable"},
        )
        self.assertTrue(resolved.disable_bypass)
        self.assertIs(resolved.effective_mode(Mode.BYPASS), Mode.DEFAULT)

    def test_disable_auto_falls_back_to_default(self):
        resolved = settings(user={"disableAutoMode": "disable"})
        self.assertIs(resolved.effective_mode(Mode.AUTO), Mode.DEFAULT)

    def test_ignored_rules_surface_as_warnings(self):
        resolved = settings(project={"allow": ["*"], "deny": ["github.get_file(path:x)"]})
        self.assertEqual(len(resolved.warnings), 2)
        self.assertEqual(len(resolved.by_kind(RuleKind.ALLOW)), 0)

    def test_unknown_default_mode_warns_and_keeps_default(self):
        resolved = settings(project={"defaultMode": "yolo"})
        self.assertIs(resolved.default_mode, Mode.DEFAULT)
        self.assertTrue(any("yolo" in w for w in resolved.warnings))


# ====================================================================== #
class TestProtectedRefsAndFailClosed(unittest.TestCase):

    def test_commit_to_a_protected_ref_requires_interaction(self):
        """Blast radius is the target, not the verb."""
        eng = engine(project={"allow": ["github.create_commit"]})
        to_main = ToolCall("github.create_commit", {"repository": "acme/api", "branch": "main"})
        decision = eng.evaluate(to_main, mode=Mode.BYPASS)
        self.assertIs(decision.outcome, Outcome.ASK)
        self.assertEqual(decision.step, 3)

    def test_commit_to_a_feature_branch_does_not(self):
        eng = engine(project={"allow": ["github.create_commit"]})
        to_feature = ToolCall("github.create_commit",
                              {"repository": "acme/api", "branch": "sutra/fix"})
        self.assertIs(eng.evaluate(to_feature).outcome, Outcome.ALLOW)

    def test_unknown_tool_is_denied(self):
        decision = engine(project={"allow": ["*"]}).evaluate(ToolCall("github.rm_rf", {}))
        self.assertIs(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason, "unknown_tool")

    def test_empty_settings_do_not_mean_permissive(self):
        eng = engine()
        self.assertIs(eng.evaluate(WRITE).outcome, Outcome.ASK)
        self.assertIs(eng.evaluate(MERGE).outcome, Outcome.ASK)

    def test_read_outside_the_working_set_prompts(self):
        """Claude prompts for a path outside the working directory rather than
        refusing it. The connector's granted repositories are that directory."""
        eng = PermissionEngine(settings(), granted_repos=("acme/*",))
        inside = ToolCall("github.get_file", {"repository": "acme/api", "path": "x"})
        outside = ToolCall("github.get_file", {"repository": "evil/api", "path": "x"})
        self.assertIs(eng.evaluate(inside).outcome, Outcome.ALLOW)
        decision = eng.evaluate(outside)
        self.assertIs(decision.outcome, Outcome.ASK)
        self.assertEqual(decision.reason, "read_outside_working_set")

    def test_working_set_does_not_override_a_deny_rule(self):
        eng = PermissionEngine(
            settings(project={"deny": ["github.get_file(*:**/.env)"]}),
            granted_repos=("acme/*",),
        )
        secret = ToolCall("github.get_file", {"repository": "acme/api", "path": ".env"})
        self.assertIs(eng.evaluate(secret).outcome, Outcome.DENY)

    def test_unrestricted_working_set_must_be_deliberate(self):
        """granted_repos=None is unrestricted; it is not the same as empty."""
        self.assertIsNone(PermissionEngine(settings()).granted_repos)
        self.assertTrue(PermissionEngine(settings()).unrestricted)
        eng = PermissionEngine(settings(), granted_repos=())
        self.assertFalse(eng.unrestricted)
        outside = ToolCall("github.get_file", {"repository": "any/repo", "path": "x"})
        self.assertIs(eng.evaluate(outside).outcome, Outcome.ASK)

    def test_for_connector_refuses_an_unrestricted_engine(self):
        """The fail-open default must not be reachable from the real path."""
        with self.assertRaises(ValueError):
            PermissionEngine.for_connector(settings(), None)
        eng = PermissionEngine.for_connector(settings(), ["acme/*"])
        self.assertFalse(eng.unrestricted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
