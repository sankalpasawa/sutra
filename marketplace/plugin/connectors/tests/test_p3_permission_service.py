"""P3 suite: settings resolution from disk, working set, grants, capability API."""
import json
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

from connectors.errors import ConnectorError  # noqa: E402
from connectors.permission_service import (  # noqa: E402
    ConnectorPermissions, SettingsResolver,
)
from connectors.permissions.modes import Mode, Outcome  # noqa: E402

from tests.test_p2_discovery import INSTALLATION, ORG_INSTALLATION, REPO, connected_service  # noqa: E402
from tests.test_p1_connector import OPERATOR  # noqa: E402


def write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.project = os.path.join(self.root, "project")
        self.home = os.path.join(self.root, "home")
        self.managed = os.path.join(self.root, "managed-settings.json")
        os.makedirs(self.project); os.makedirs(self.home)
        self.resolver = SettingsResolver(self.project, self.home, self.managed)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ====================================================================== #
class TestSettingsResolution(Fixture):

    def test_absent_files_are_not_an_error(self):
        settings = self.resolver.load()
        self.assertEqual(settings.rules, [])
        self.assertIs(settings.default_mode, Mode.DEFAULT)

    def test_rules_union_across_sources(self):
        write(self.resolver.user_path(), {"permissions": {"allow": ["github.get_file"]}})
        write(self.resolver.project_path(),
              {"permissions": {"deny": ["github.get_file(*:**/.env)"]}})
        settings = self.resolver.load()
        self.assertEqual(len(settings.rules), 2)
        self.assertEqual({r.source for r in settings.rules}, {"user", "project"})

    def test_managed_wins_default_mode(self):
        write(self.resolver.project_path(), {"permissions": {"defaultMode": "bypassPermissions"}})
        write(self.managed, {"permissions": {"defaultMode": "plan"}})
        self.assertIs(self.resolver.load().default_mode, Mode.PLAN)

    def test_managed_rules_only_discards_the_rest(self):
        write(self.managed, {"permissions": {"allowManagedPermissionRulesOnly": True,
                                             "deny": ["github.delete_branch"]}})
        write(self.resolver.project_path(), {"permissions": {"allow": ["github.create_commit"]}})
        settings = self.resolver.load()
        self.assertEqual([r.source for r in settings.rules], ["managed"])

    def test_a_user_can_lock_themselves_out_of_bypass(self):
        write(self.resolver.user_path(),
              {"permissions": {"disableBypassPermissionsMode": "disable"}})
        write(self.managed, {"permissions": {"defaultMode": "default"}})
        settings = self.resolver.load()
        self.assertTrue(settings.disable_bypass)
        self.assertIs(settings.effective_mode(Mode.BYPASS), Mode.DEFAULT)

    def test_malformed_settings_fail_closed(self):
        """An unreadable settings file must never read as 'no policy' -- no
        policy is the widest state there is."""
        path = self.resolver.project_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("{ not json")
        with self.assertRaises(ConnectorError):
            self.resolver.load()

    def test_non_object_settings_rejected(self):
        path = self.resolver.user_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("[1,2,3]")
        with self.assertRaises(ConnectorError):
            self.resolver.load()

    def test_session_rules_are_highest_after_managed(self):
        write(self.resolver.user_path(), {"permissions": {"allow": ["github.get_file"]}})
        settings = self.resolver.load({"deny": ["github.get_file"]})
        sources = {r.source for r in settings.rules}
        self.assertIn("session", sources)


# ====================================================================== #
class TestPersistence(Fixture):

    def test_dont_ask_again_writes_to_local_not_project(self):
        """A rule one operator accepted in a modal is not team policy."""
        path = self.resolver.persist_rule("github.get_file(acme/api)")
        self.assertTrue(path.endswith("settings.local.json"))
        self.assertFalse(os.path.exists(self.resolver.project_path()))
        with open(path) as handle:
            self.assertIn("github.get_file(acme/api)", json.load(handle)["permissions"]["allow"])

    def test_persisted_rule_is_0600(self):
        path = self.resolver.persist_rule("github.get_file(acme/api)")
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")

    def test_persisting_twice_does_not_duplicate(self):
        self.resolver.persist_rule("github.get_file(acme/api)")
        path = self.resolver.persist_rule("github.get_file(acme/api)")
        with open(path) as handle:
            self.assertEqual(len(json.load(handle)["permissions"]["allow"]), 1)

    def test_persisted_rule_takes_effect(self):
        from connectors.permissions.rules import RuleKind
        self.resolver.persist_rule("github.create_pull_request(acme/api)")
        settings = self.resolver.load()
        self.assertEqual(len(settings.by_kind(RuleKind.ALLOW)), 1)


# ====================================================================== #
class TestConnectorPermissions(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db, self.transport, self.service, self.connector_id = connected_service()
        self.resolver = SettingsResolver(os.path.join(self.root, "p"),
                                         os.path.join(self.root, "h"),
                                         os.path.join(self.root, "managed.json"))
        self.perms = ConnectorPermissions(self.service, OPERATOR, self.connector_id,
                                          self.resolver)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _install(self, installation=INSTALLATION, repos=(REPO,)):
        self.transport.push(200, {"installations": [installation]})
        self.transport.push(200, {"repositories": list(repos)})
        self.service.list_repositories(OPERATOR, self.connector_id)

    def test_working_set_from_selected_repositories(self):
        self._install()
        self.assertEqual(self.perms.granted_repos(), ["tchandrakar/sutra"])

    def test_repository_selection_all_is_scoped_to_the_account(self):
        """'all' means every repo IN THAT ACCOUNT, not every repo on GitHub."""
        self.transport.push(200, {"installations": [ORG_INSTALLATION]})
        self.service.sync_installations(OPERATOR, self.connector_id)
        self.assertEqual(self.perms.granted_repos(), ["acme-corp/*"])

    def test_read_inside_the_working_set_is_allowed(self):
        self._install()
        decision = self.perms.evaluate("github.get_file",
                                       {"repository": "tchandrakar/sutra", "path": "a.py"})
        self.assertIs(decision.outcome, Outcome.ALLOW)

    def test_read_outside_the_working_set_prompts(self):
        self._install()
        decision = self.perms.evaluate("github.get_file",
                                       {"repository": "someone/else", "path": "a.py"})
        self.assertIs(decision.outcome, Outcome.ASK)
        self.assertEqual(decision.reason, "read_outside_working_set")

    def test_no_installations_means_no_working_set(self):
        """Nothing granted yet, so nothing is free. Fails closed."""
        decision = self.perms.evaluate("github.get_file",
                                       {"repository": "tchandrakar/sutra", "path": "a"})
        self.assertIs(decision.outcome, Outcome.ASK)

    def test_deny_rule_from_disk_beats_the_working_set(self):
        self._install()
        write(self.resolver.user_path(),
              {"permissions": {"deny": ["github.get_file(*:**/.env)"]}})
        decision = self.perms.evaluate(
            "github.get_file", {"repository": "tchandrakar/sutra", "path": "cfg/.env"})
        self.assertIs(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.step, 1)

    def test_session_grant_satisfies_a_write(self):
        self._install()
        args = {"repository": "tchandrakar/sutra", "base": "dev"}
        self.assertIs(self.perms.evaluate("github.create_pull_request", args).outcome,
                      Outcome.ASK)
        self.perms.grant_for_session("github.create_pull_request", "tchandrakar/sutra")
        self.assertIs(self.perms.evaluate("github.create_pull_request", args).outcome,
                      Outcome.ALLOW)

    def test_destructive_tools_cannot_be_persisted(self):
        with self.assertRaises(ConnectorError):
            self.perms.grant_persistently("github.merge_pull_request(acme/api)")

    def test_unusable_rule_cannot_be_persisted(self):
        with self.assertRaises(ConnectorError):
            self.perms.grant_persistently("github.get_file(path:x)")

    def test_evaluations_are_audited(self):
        self._install()
        self.perms.evaluate("github.get_file",
                            {"repository": "tchandrakar/sutra", "path": "a"})
        types = [r["event_type"] for r in
                 self.db.execute("SELECT event_type FROM connector_events")]
        self.assertIn("TOOL_EVALUATED", types)

    def test_denials_are_audited_as_denials(self):
        self._install()
        write(self.resolver.user_path(), {"permissions": {"deny": ["github.get_file"]}})
        self.perms.evaluate("github.get_file",
                            {"repository": "tchandrakar/sutra", "path": "a"})
        rows = [dict(r) for r in self.db.execute(
            "SELECT event_type, result FROM connector_events")]
        self.assertTrue(any(r["event_type"] == "TOOL_DENIED" and r["result"] == "DENIED"
                            for r in rows))

    def test_summary_is_the_capability_read_model(self):
        self._install()
        write(self.resolver.user_path(),
              {"permissions": {"deny": ["github.delete_branch"],
                               "allow": ["github.get_file(tchandrakar/*)"]}})
        summary = self.perms.summary()
        self.assertEqual(summary["granted_repositories"], ["tchandrakar/sutra"])
        self.assertIn("github.delete_branch", summary["removed_tools"])
        self.assertNotIn("github.delete_branch", summary["visible_tools"])
        self.assertEqual(len(summary["rules"]["allow"]), 1)
        self.assertEqual(summary["truth_class"], "authoritative")

    def test_summary_surfaces_unusable_rules_rather_than_hiding_them(self):
        write(self.resolver.user_path(), {"permissions": {"allow": ["*"]}})
        summary = self.perms.summary()
        self.assertEqual(len(summary["warnings"]), 1)
        self.assertEqual(summary["rules"]["allow"], [])

    def test_summary_leaks_no_credentials(self):
        self._install()
        blob = json.dumps(self.perms.summary())
        for secret in ("ghu_", "ghr_", "client_secret"):
            self.assertNotIn(secret, blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
