"""Slack connect flow: loopback redirect, dual tokens, identity.

The loopback listener is driven with a REAL HTTP request rather than mocked, so
the Host check, the single-request lifetime and the state comparison are all
actually exercised. Only the Slack API itself is faked.
"""
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

from connectors.config import SlackConfig  # noqa: E402
from connectors.credentials.store import CredentialNotFound, MemoryCredentialStore  # noqa: E402
from connectors.database import Database  # noqa: E402
from connectors.errors import (  # noqa: E402
    AuthorizationDenied, AuthorizationPending, CredentialInvalid,
    PermissionDenied, ValidationFailed,
)
from connectors.github.http import FakeTransport  # noqa: E402
from connectors.oauth.loopback import LoopbackCatcher, LoopbackError, port_is_free  # noqa: E402
from connectors.service import ConnectorService  # noqa: E402
from connectors.slack.client import SlackClient  # noqa: E402
from connectors.slack.strategy import BOT_SCOPES, USER_SCOPES, SlackLoopbackStrategy  # noqa: E402

OPERATOR = "op_test"
PORT = 8791          # not 8765: never collide with a real flow on this machine

TOKEN_OK = {
    "ok": True,
    "access_token": "xoxb-BOTTOKEN", "token_type": "bot",
    "scope": "chat:write,channels:read", "bot_user_id": "B123",
    "expires_in": 43200, "refresh_token": "xoxe-BOTREFRESH",
    "team": {"id": "T0BRPAZSNBY", "name": "AfterQuery"},
    "authed_user": {"id": "U999", "scope": "search:read,im:history",
                    "access_token": "xoxp-USERTOKEN", "token_type": "user",
                    "expires_in": 43200, "refresh_token": "xoxe-USERREFRESH"},
}
AUTH_TEST_OK = {"ok": True, "url": "https://afterquery.slack.com/",
                "team": "AfterQuery", "user": "tishant",
                "team_id": "T0BRPAZSNBY", "user_id": "U999"}


def config(secret="shhh"):
    return SlackConfig(client_id="11873373906406.11873418567958",
                       client_secret=secret, redirect_port=PORT)


#: Every strategy built in a test, so teardown can release listeners. An
#: abandoned begin() holds the port for its whole timeout, and the next test
#: cannot bind it.
_BUILT = []


def build(secret="shhh"):
    db = Database(); db.migrate()
    transport = FakeTransport()
    cfg = config(secret)
    client = SlackClient(cfg, transport)
    strategy = SlackLoopbackStrategy(client, cfg, open_browser=False)
    service = ConnectorService(db, MemoryCredentialStore(), strategy, client, cfg)
    _BUILT.append(strategy)
    return db, transport, strategy, service


def release_all():
    while _BUILT:
        try:
            _BUILT.pop().close_all()
        except Exception:
            pass
    for _ in range(40):
        if port_is_free(PORT):
            return
        time.sleep(0.05)


def deliver(state, code="CODE1", error=None, path="/slack/callback", host=None):
    """Hit the real listener the way Slack's redirect would."""
    query = "error=%s&state=%s" % (error, state) if error else "code=%s&state=%s" % (code, state)
    url = "http://localhost:%d%s?%s" % (PORT, path, query)
    request = urllib.request.Request(url)
    if host:
        request.add_header("Host", host)
    for _ in range(30):
        try:
            return urllib.request.urlopen(request, timeout=3).read()
        except urllib.error.HTTPError as exc:
            return exc.read()
        except Exception:
            time.sleep(0.1)
    raise AssertionError("listener never answered")


# ====================================================================== #
class TestAuthorizeUrl(unittest.TestCase):
    def tearDown(self): release_all()

    def test_url_carries_both_scope_sets_and_no_secret(self):
        import urllib.parse as up
        client = SlackClient(config(), FakeTransport())
        url = client.authorize_url("STATE", BOT_SCOPES, USER_SCOPES)
        q = up.parse_qs(up.urlsplit(url).query)
        self.assertEqual(q["scope"][0].split(","), list(BOT_SCOPES))
        self.assertEqual(q["user_scope"][0].split(","), list(USER_SCOPES))
        self.assertEqual(q["state"][0], "STATE")
        self.assertNotIn("client_secret", q)

    def test_no_user_chat_write(self):
        """An agent posting as the human is not something anyone asked for."""
        self.assertNotIn("chat:write", USER_SCOPES)
        self.assertIn("chat:write", BOT_SCOPES)

    def test_state_is_not_in_the_public_challenge(self):
        """With no PKCE, state is the only binding. It must not cross the API."""
        _, _, strategy, _ = build()
        challenge = strategy.begin()
        try:
            self.assertNotIn(challenge.handle, json.dumps(challenge.public_dict()))
            self.assertNotIn("authorize_url", challenge.public_dict())
            self.assertIn("authorize_url", challenge.public_dict(include_url=True))
        finally:
            strategy.cancel(challenge.handle)


# ====================================================================== #
class TestLoopbackCapture(unittest.TestCase):
    def tearDown(self): release_all()

    def test_happy_path_yields_both_tokens(self):
        db, transport, strategy, service = build()
        challenge = strategy.begin()
        transport.push(200, TOKEN_OK)
        deliver(challenge.handle)
        result = strategy.poll(challenge.handle)
        self.assertEqual(result.primary.access_token, "xoxb-BOTTOKEN")
        self.assertEqual(result.extra["user"].access_token, "xoxp-USERTOKEN")
        self.assertTrue(result.meta["rotation_enabled"])
        self.assertEqual(result.meta["team_id"], "T0BRPAZSNBY")

    def test_pending_until_the_browser_returns(self):
        db, transport, strategy, service = build()
        challenge = strategy.begin()
        with self.assertRaises(AuthorizationPending):
            strategy.poll(challenge.handle)
        strategy.cancel(challenge.handle)

    def test_state_mismatch_is_rejected(self):
        """The whole defence, given Slack has no PKCE."""
        db, transport, strategy, service = build()
        challenge = strategy.begin()
        deliver("NOT-THE-REAL-STATE")
        with self.assertRaises(ValidationFailed) as ctx:
            strategy.poll(challenge.handle)
        self.assertIn("state mismatch", ctx.exception.message)
        self.assertEqual(len(transport.calls), 0, "no code may be exchanged")

    def test_user_denial(self):
        db, transport, strategy, service = build()
        challenge = strategy.begin()
        deliver(challenge.handle, error="access_denied")
        with self.assertRaises(AuthorizationDenied):
            strategy.poll(challenge.handle)

    def test_foreign_host_probe_is_rejected_without_killing_the_flow(self):
        """DNS rebinding: a hostile page resolving its own name to 127.0.0.1.

        The probe must be refused AND must not consume the listener. An earlier
        version served exactly one request, so a single probe stranded the
        user's real callback forever -- a denial of service costing the
        attacker one HTTP request.
        """
        db, transport, strategy, service = build()
        challenge = strategy.begin()

        deliver(challenge.handle, host="evil.example.com")
        with self.assertRaises(AuthorizationPending):
            strategy.poll(challenge.handle)          # still waiting, not broken
        self.assertEqual(len(transport.calls), 0, "no code may be exchanged")

        # The genuine callback still lands afterwards.
        transport.push(200, TOKEN_OK)
        deliver(challenge.handle)
        result = strategy.poll(challenge.handle)
        self.assertEqual(result.primary.access_token, "xoxb-BOTTOKEN")

    def test_wrong_path_probe_also_leaves_the_flow_alive(self):
        db, transport, strategy, service = build()
        challenge = strategy.begin()
        deliver(challenge.handle, path="/not-the-callback")
        with self.assertRaises(AuthorizationPending):
            strategy.poll(challenge.handle)
        transport.push(200, TOKEN_OK)
        deliver(challenge.handle)
        self.assertEqual(strategy.poll(challenge.handle).primary.access_token,
                         "xoxb-BOTTOKEN")

    def test_port_busy_fails_before_any_browser_opens(self):
        held = LoopbackCatcher(PORT, "/slack/callback", timeout=5).start()
        try:
            _, _, strategy, _ = build()
            with self.assertRaises(LoopbackError) as ctx:
                strategy.begin()
            self.assertIn("cannot bind", str(ctx.exception))
        finally:
            held.close()

    def test_listener_closes_after_one_callback(self):
        db, transport, strategy, service = build()
        challenge = strategy.begin()
        transport.push(200, TOKEN_OK)
        deliver(challenge.handle)
        strategy.poll(challenge.handle)
        for _ in range(20):
            if port_is_free(PORT):
                break
            time.sleep(0.05)
        self.assertTrue(port_is_free(PORT), "listener outlived its one callback")


# ====================================================================== #
class TestSlackErrors(unittest.TestCase):
    def tearDown(self): release_all()

    """Slack reports failure as HTTP 200 with ok:false. A status-code check
    would read every one of these as success."""

    def judge(self, payload):
        SlackClient._judge(payload, "test")

    def test_invalid_auth(self):
        with self.assertRaises(CredentialInvalid):
            self.judge({"ok": False, "error": "invalid_auth"})

    def test_missing_scope_is_permission_not_credential(self):
        with self.assertRaises(PermissionDenied) as ctx:
            self.judge({"ok": False, "error": "missing_scope",
                        "needed": "search:read", "provided": "chat:write"})
        self.assertEqual(ctx.exception.detail["needed_scope"], "search:read")

    def test_unknown_error_is_reported_verbatim(self):
        from connectors.errors import ConnectorError
        with self.assertRaises(ConnectorError) as ctx:
            self.judge({"ok": False, "error": "some_new_slack_error"})
        self.assertIn("some_new_slack_error", ctx.exception.message)

    def test_missing_secret_says_where_to_put_it(self):
        client = SlackClient(config(secret=None), FakeTransport())
        with self.assertRaises(ValidationFailed) as ctx:
            client.exchange_code("CODE")
        self.assertIn("provider-secrets.env", ctx.exception.message)

    def test_absent_expiry_means_rotation_is_off(self):
        """A Slack app without rotation yields a token that never expires."""
        payload = dict(TOKEN_OK)
        payload.pop("expires_in")
        payload["authed_user"] = {k: v for k, v in TOKEN_OK["authed_user"].items()
                                  if k != "expires_in"}
        self.assertFalse(SlackClient._unpack(payload)["rotation_enabled"])


# ====================================================================== #
class TestEndToEndConnect(unittest.TestCase):
    def tearDown(self): release_all()

    def connect(self):
        db, transport, strategy, service = build()
        started = service.begin_connect(OPERATOR)
        state = service.credentials.get_secret("device:" + started["transaction_id"])
        transport.push(200, TOKEN_OK)          # oauth.v2.access
        transport.push(200, AUTH_TEST_OK)      # auth.test
        deliver(state)
        return db, transport, service, service.poll_connect(OPERATOR, started["transaction_id"])

    def test_connector_is_created_and_keyed_on_team_and_user(self):
        db, transport, service, result = self.connect()
        self.assertEqual(result["status"], "COMPLETED")
        row = db.execute("SELECT * FROM connectors").fetchone()
        self.assertEqual(row["provider"], "slack")
        self.assertEqual(row["provider_account_id"], "T0BRPAZSNBY:U999")
        self.assertEqual(row["provider_username"], "tishant")

    def test_both_tokens_are_stored_in_separate_slots(self):
        db, transport, service, result = self.connect()
        cid = result["connector_id"]
        self.assertEqual(service.credentials.get(cid).access_token, "xoxb-BOTTOKEN")
        self.assertEqual(service.credentials.get(cid, slot="user").access_token,
                         "xoxp-USERTOKEN")

    def test_granted_scopes_are_recorded_with_their_token_type(self):
        db, transport, service, result = self.connect()
        scopes = [r["scope"] for r in db.execute(
            "SELECT scope FROM connector_scopes ORDER BY scope")]
        self.assertIn("bot:chat:write", scopes)
        self.assertIn("user:search:read", scopes)

    def test_disconnect_erases_both_tokens(self):
        db, transport, service, result = self.connect()
        cid = result["connector_id"]
        service.disconnect(OPERATOR, cid)
        for slot in (None, "user"):
            with self.assertRaises(CredentialNotFound):
                service.credentials.get(cid) if slot is None \
                    else service.credentials.get(cid, slot=slot)

    def test_no_token_reaches_the_database_or_the_response(self):
        db, transport, service, result = self.connect()
        blob = json.dumps(result) + " ".join(
            str(tuple(r)) for r in db.execute("SELECT * FROM connectors"))
        for secret in ("xoxb-", "xoxp-", "xoxe-", "shhh"):
            self.assertNotIn(secret, blob)

    def test_a_dead_transaction_is_retired_not_handed_back(self):
        """begin_connect is idempotent, and a redirect listener is in-process.
        Together they made Connect permanently unusable after a restart: the
        open transaction was returned forever and could never complete."""
        db, transport, strategy, service = build()
        first = service.begin_connect(OPERATOR)
        tx_id = first["transaction_id"]

        # Simulate the restart: the process kept the row, lost the listener.
        strategy.close_all()

        second = service.begin_connect(OPERATOR)
        self.assertNotEqual(second["transaction_id"], tx_id,
                            "a transaction nobody can finish was handed back")
        row = db.execute("SELECT status, failure_code FROM oauth_transactions "
                         "WHERE id = ?", (tx_id,)).fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["failure_code"], "LISTENER_LOST")
        strategy.cancel(service.credentials.get_secret("device:" + second["transaction_id"]))

    def test_a_live_transaction_is_still_reused(self):
        """Idempotency must survive the fix: a double-clicked Connect should
        not strand a second listener."""
        db, transport, strategy, service = build()
        first = service.begin_connect(OPERATOR)
        second = service.begin_connect(OPERATOR)
        self.assertEqual(first["transaction_id"], second["transaction_id"])

    def test_a_provider_never_lists_another_providers_connectors(self):
        """A GitHub connection rendered as a connected Slack account because
        list_connectors did not filter by provider."""
        db, transport, service, result = self.connect()
        from connectors.database.repositories import ConnectorRepository, new_id
        from connectors.models import Connector, ConnectorStatus
        ConnectorRepository(db).create(Connector(
            id=new_id("conn"), operator_id=OPERATOR, provider="github",
            provider_account_id="999", provider_username="octocat",
            status=ConnectorStatus.ACTIVE))

        listed = service.list_connectors(OPERATOR)          # a SLACK service
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["account"]["username"], "tishant")
        self.assertNotIn("octocat", json.dumps(listed))

    def test_transaction_state_is_destroyed_on_completion(self):
        db, transport, service, result = self.connect()
        row = db.execute("SELECT state_hash, device_code_enc FROM oauth_transactions").fetchone()
        self.assertIsNone(row["state_hash"])
        self.assertIsNone(row["device_code_enc"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
