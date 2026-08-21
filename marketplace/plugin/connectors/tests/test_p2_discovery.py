"""P2 suite: installations, repositories, organizations, pagination, cursors."""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

from connectors.config import ProviderConfig  # noqa: E402
from connectors.credentials.store import MemoryCredentialStore  # noqa: E402
from connectors.database import Database  # noqa: E402
from connectors.errors import TransactionNotFound  # noqa: E402
from connectors.github.client import GitHubClient  # noqa: E402
from connectors.github.discovery import Discovery, capabilities_for  # noqa: E402
from connectors.github.http import FakeTransport  # noqa: E402
from connectors.github.pagination import (  # noqa: E402
    InvalidCursor, decode_cursor, encode_cursor, parse_link_header,
)
from connectors.models import Installation  # noqa: E402
from connectors.oauth.strategies import DeviceFlowStrategy  # noqa: E402
from connectors.service import ConnectorService  # noqa: E402

from tests.test_p1_connector import (  # noqa: E402
    OPERATOR, TOKEN_RESPONSE, USER_RESPONSE, DEVICE_CODE_RESPONSE,
    script_successful_connect,
)

API = "https://api.github.com"

INSTALLATION = {
    "id": 42,
    "account": {"login": "tchandrakar", "id": 64305513, "type": "User"},
    "repository_selection": "selected",
    "permissions": {"metadata": "read", "contents": "write",
                    "pull_requests": "write", "issues": "write"},
}
ORG_INSTALLATION = {
    "id": 77,
    "account": {"login": "acme-corp", "id": 900, "type": "Organization"},
    "repository_selection": "all",
    "permissions": {"metadata": "read", "contents": "read"},
}
REPO = {
    "id": 1296269, "name": "sutra", "full_name": "tchandrakar/sutra",
    "owner": {"login": "tchandrakar"}, "private": True, "visibility": "private",
    "default_branch": "main", "archived": False,
    "permissions": {"admin": True, "push": True, "pull": True},
}


def connected_service():
    db = Database(); db.migrate()
    transport = FakeTransport()
    config = ProviderConfig(client_id="Iv23li4V24WX8yjaWoby")
    client = GitHubClient(config, transport)
    service = ConnectorService(db, MemoryCredentialStore(),
                               DeviceFlowStrategy(client, config), client, config)
    script_successful_connect(transport)
    started = service.begin_connect(OPERATOR)
    result = service.poll_connect(OPERATOR, started["transaction_id"])
    return db, transport, service, result["connector_id"]


# ====================================================================== #
class TestLinkHeader(unittest.TestCase):

    def test_parses_rel_next(self):
        header = ('<https://api.github.com/user/repos?page=2>; rel="next", '
                  '<https://api.github.com/user/repos?page=9>; rel="last"')
        links = parse_link_header(header)
        self.assertEqual(links["next"], "https://api.github.com/user/repos?page=2")
        self.assertEqual(links["last"], "https://api.github.com/user/repos?page=9")

    def test_absent_header_is_not_an_error(self):
        self.assertEqual(parse_link_header(None), {})
        self.assertEqual(parse_link_header(""), {})


# ====================================================================== #
class TestCursors(unittest.TestCase):
    """A cursor wraps a URL our authenticated client will dereference. Four
    independent checks, because one of them will eventually be the last line."""

    SECRET = b"k" * 32

    def test_round_trip(self):
        url = API + "/user/installations/42/repositories?page=2"
        cursor = encode_cursor(self.SECRET, "conn_1", url)
        self.assertEqual(decode_cursor(self.SECRET, "conn_1", cursor, API), url)

    def test_tampered_signature_rejected(self):
        cursor = encode_cursor(self.SECRET, "conn_1", API + "/x")
        body, _, sig = cursor.partition(".")
        forged = body + "." + ("A" * len(sig))
        with self.assertRaises(InvalidCursor):
            decode_cursor(self.SECRET, "conn_1", forged, API)

    def test_tampered_payload_rejected(self):
        cursor = encode_cursor(self.SECRET, "conn_1", API + "/x")
        _, _, sig = cursor.partition(".")
        import base64
        evil = base64.urlsafe_b64encode(
            json.dumps({"c": "conn_1", "u": "https://evil.test/x"},
                       separators=(",", ":"), sort_keys=True).encode()
        ).decode().rstrip("=")
        with self.assertRaises(InvalidCursor):
            decode_cursor(self.SECRET, "conn_1", evil + "." + sig, API)

    def test_cursor_from_another_connector_rejected(self):
        cursor = encode_cursor(self.SECRET, "conn_OTHER", API + "/x")
        with self.assertRaises(InvalidCursor):
            decode_cursor(self.SECRET, "conn_1", cursor, API)

    def test_offhost_url_rejected_even_when_correctly_signed(self):
        """Defence in depth: if the key ever leaked, the origin check still
        stops our authenticated client being pointed at an attacker's host."""
        cursor = encode_cursor(self.SECRET, "conn_1", "https://evil.test/steal")
        with self.assertRaises(InvalidCursor):
            decode_cursor(self.SECRET, "conn_1", cursor, API)

    def test_http_downgrade_rejected(self):
        cursor = encode_cursor(self.SECRET, "conn_1", "http://api.github.com/x")
        with self.assertRaises(InvalidCursor):
            decode_cursor(self.SECRET, "conn_1", cursor, API)

    def test_malformed_cursor_rejected(self):
        for bad in ("", "abc", "abc.", ".abc", "!!!.???"):
            with self.assertRaises(InvalidCursor):
                decode_cursor(self.SECRET, "conn_1", bad, API)

    def test_secret_is_stable_across_calls(self):
        db, transport, service, connector_id = connected_service()
        self.assertEqual(service._cursor_secret(), service._cursor_secret())

    def test_secret_is_not_in_the_database(self):
        db, transport, service, connector_id = connected_service()
        service._cursor_secret()
        blob = " ".join(str(tuple(r)) for r in db.execute(
            "SELECT * FROM connector_metadata"))
        self.assertNotIn("cursor", blob)


# ====================================================================== #
class TestCapabilityMapping(unittest.TestCase):

    def test_write_implies_read(self):
        caps = capabilities_for({"contents": "write"})
        self.assertIn("github.repository.contents.read", caps)
        self.assertIn("github.repository.commits.write", caps)

    def test_read_does_not_imply_write(self):
        caps = capabilities_for({"contents": "read"})
        self.assertIn("github.repository.contents.read", caps)
        self.assertNotIn("github.repository.commits.write", caps)

    def test_one_permission_backs_several_capabilities(self):
        """contents:write underpins branch AND commit writes with very
        different blast radii -- which is why a scope is not a capability."""
        caps = capabilities_for({"contents": "write"})
        self.assertIn("github.repository.branches.write", caps)
        self.assertIn("github.repository.commits.write", caps)

    def test_ungranted_permission_yields_nothing(self):
        self.assertEqual(capabilities_for({}), [])
        self.assertNotIn("github.issues.write", capabilities_for({"issues": "read"}))


# ====================================================================== #
class TestDiscovery(unittest.TestCase):

    def test_installations_follow_link_pagination(self):
        transport = FakeTransport()
        transport.push(200, {"total_count": 2, "installations": [INSTALLATION]},
                       headers={"Link": '<%s/user/installations?page=2>; rel="next"' % API})
        transport.push(200, {"total_count": 2, "installations": [ORG_INSTALLATION]})
        client = GitHubClient(ProviderConfig(), transport)
        installations = Discovery(client).list_installations("ghu_x")
        self.assertEqual([i.installation_id for i in installations], [42, 77])

    def test_page_numbers_are_never_constructed(self):
        """Only rel=next is followed. A constructed ?page=n skips and duplicates
        when the set changes mid-walk."""
        transport = FakeTransport()
        transport.push(200, {"installations": [INSTALLATION]})   # no Link header
        client = GitHubClient(ProviderConfig(), transport)
        Discovery(client).list_installations("ghu_x")
        self.assertEqual(len(transport.calls), 1)

    def test_repository_carries_permissions_and_capabilities(self):
        transport = FakeTransport()
        transport.push(200, {"repositories": [REPO]})
        client = GitHubClient(ProviderConfig(), transport)
        installation = Discovery._to_installation(INSTALLATION)
        repos, next_url, access = Discovery(client).list_repositories("ghu_x", installation)
        repo = repos[0]
        self.assertEqual(repo.full_name, "tchandrakar/sutra")
        self.assertEqual(repo.visibility, "private")
        self.assertEqual(repo.user_permission, "admin")
        self.assertEqual(repo.installation_id, 42)
        self.assertIn("github.pull_requests.write", repo.capabilities)
        self.assertIsNone(next_url)
        self.assertEqual(access, "ok")

    def test_sso_marks_access_rather_than_dropping_repos(self):
        """A silently missing repo is a support ticket; a labelled one is a
        fixable state."""
        transport = FakeTransport()
        transport.push(403, {"message": "SAML enforcement"},
                       headers={"X-GitHub-SSO": "required; url=https://github.com/orgs/x/sso"})
        client = GitHubClient(ProviderConfig(), transport)
        installation = Discovery._to_installation(ORG_INSTALLATION)
        repos, next_url, access = Discovery(client).list_repositories("ghu_x", installation)
        self.assertEqual(access, "sso_required")
        self.assertEqual(repos, [])

    def test_orgs_without_an_installation_are_labelled_not_omitted(self):
        transport = FakeTransport()
        transport.push(200, [{"id": 900, "login": "acme-corp", "avatar_url": "a"},
                             {"id": 901, "login": "acme-labs", "avatar_url": "b"}])
        client = GitHubClient(ProviderConfig(), transport)
        installations = [Discovery._to_installation(ORG_INSTALLATION)]
        orgs = Discovery(client).list_organizations("ghu_x", installations)
        by_login = {o.login: o for o in orgs}
        self.assertEqual(by_login["acme-corp"].access, "ok")
        self.assertEqual(by_login["acme-labs"].access, "not_installed")

    def test_installation_on_a_concealed_membership_is_still_listed(self):
        transport = FakeTransport()
        transport.push(200, [])          # /user/orgs returns nothing
        client = GitHubClient(ProviderConfig(), transport)
        installations = [Discovery._to_installation(ORG_INSTALLATION)]
        orgs = Discovery(client).list_organizations("ghu_x", installations)
        self.assertEqual([o.login for o in orgs], ["acme-corp"])


# ====================================================================== #
class TestServiceDiscovery(unittest.TestCase):

    def test_not_installed_returns_an_actionable_empty_state(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"total_count": 0, "installations": []})
        result = service.list_repositories(OPERATOR, connector_id)
        self.assertEqual(result["repositories"], [])
        self.assertEqual(result["empty_reason"], "NOT_INSTALLED")
        self.assertEqual(result["user_action"], "INSTALL_APP")
        self.assertIn("github.com", result["install_url"])

    def test_repositories_are_listed_and_cached(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": [INSTALLATION]})
        transport.push(200, {"repositories": [REPO]})
        result = service.list_repositories(OPERATOR, connector_id)
        self.assertEqual(result["repositories"][0]["full_name"], "tchandrakar/sutra")
        cached = db.execute(
            "SELECT COUNT(*) c FROM connector_metadata WHERE kind='repository'").fetchone()
        self.assertEqual(cached["c"], 1)

    def test_installations_persist_for_the_connector(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": [INSTALLATION, ORG_INSTALLATION]})
        service.sync_installations(OPERATOR, connector_id)
        rows = db.execute("SELECT installation_id FROM connector_installations "
                          "WHERE connector_id = ?", (connector_id,)).fetchall()
        self.assertEqual(sorted(r["installation_id"] for r in rows), [42, 77])

    def test_uninstall_is_detected_and_audited(self):
        """Without webhooks (hosted-only) this sync is the only way we learn the
        app was uninstalled."""
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": [INSTALLATION, ORG_INSTALLATION]})
        service.sync_installations(OPERATOR, connector_id)
        transport.push(200, {"installations": [INSTALLATION]})
        service.sync_installations(OPERATOR, connector_id)
        rows = db.execute("SELECT installation_id FROM connector_installations "
                          "WHERE connector_id = ?", (connector_id,)).fetchall()
        self.assertEqual([r["installation_id"] for r in rows], [42])
        reasons = [r["reason_code"] for r in db.execute(
            "SELECT reason_code FROM connector_events")]
        self.assertIn("ORG_ACCESS_REMOVED", reasons)

    def test_empty_installations_do_not_re_sync_every_call(self):
        """An authorized-but-not-installed connector defeated the cache: `not
        installations` was true on every request, so every page view cost a
        live GitHub round-trip. The freshness marker distinguishes "not asked"
        from "asked, answer was none"."""
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"total_count": 0, "installations": []})
        first = service.list_repositories(OPERATOR, connector_id)
        self.assertEqual(first["empty_reason"], "NOT_INSTALLED")
        calls_after_first = len(transport.calls)
        # No further responses scripted: a second GitHub call would raise.
        second = service.list_repositories(OPERATOR, connector_id)
        self.assertEqual(second["empty_reason"], "NOT_INSTALLED")
        self.assertEqual(len(transport.calls), calls_after_first,
                         "second call must not hit GitHub again")

    def test_refresh_forces_a_re_sync(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": []})
        service.list_repositories(OPERATOR, connector_id)
        before = len(transport.calls)
        transport.push(200, {"installations": [INSTALLATION]})
        transport.push(200, {"repositories": [REPO]})
        result = service.list_repositories(OPERATOR, connector_id, refresh=True)
        self.assertGreater(len(transport.calls), before)
        self.assertEqual(len(result["repositories"]), 1)

    def test_organizations_also_honour_the_marker(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": []})
        transport.push(200, [])
        service.list_organizations(OPERATOR, connector_id)
        before = len(transport.calls)
        transport.push(200, [])          # only /user/orgs should be called again
        service.list_organizations(OPERATOR, connector_id)
        self.assertEqual(len(transport.calls), before + 1)

    def test_next_cursor_is_opaque_and_signed(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": [INSTALLATION]})
        transport.push(200, {"repositories": [REPO]}, headers={
            "Link": '<%s/user/installations/42/repositories?page=2>; rel="next"' % API})
        result = service.list_repositories(OPERATOR, connector_id)
        cursor = result["next_cursor"]
        self.assertIsNotNone(cursor)
        self.assertNotIn("api.github.com", cursor)   # opaque: no raw URL
        self.assertIn(".", cursor)                   # signed

    def test_tampered_cursor_is_never_dereferenced(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": [INSTALLATION]})
        service.sync_installations(OPERATOR, connector_id)
        before = len(transport.calls)
        with self.assertRaises(InvalidCursor):
            service.list_repositories(OPERATOR, connector_id, cursor="forged.cursor")
        self.assertEqual(len(transport.calls), before, "no request may be made")

    def test_another_operator_gets_nothing(self):
        db, transport, service, connector_id = connected_service()
        with self.assertRaises(TransactionNotFound):
            service.list_repositories("op_attacker", connector_id)
        with self.assertRaises(TransactionNotFound):
            service.list_organizations("op_attacker", connector_id)

    def test_organizations_separate_membership_from_access(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": [ORG_INSTALLATION]})
        transport.push(200, [{"id": 900, "login": "acme-corp"},
                             {"id": 901, "login": "acme-labs"}])
        result = service.list_organizations(OPERATOR, connector_id)
        access = {o["login"]: o["access"] for o in result["organizations"]}
        self.assertEqual(access, {"acme-corp": "ok", "acme-labs": "not_installed"})

    def test_discovery_output_leaks_no_credentials(self):
        db, transport, service, connector_id = connected_service()
        transport.push(200, {"installations": [INSTALLATION]})
        transport.push(200, {"repositories": [REPO]})
        blob = json.dumps(service.list_repositories(OPERATOR, connector_id))
        for secret in ("ghu_", "ghr_", "client_secret"):
            self.assertNotIn(secret, blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
