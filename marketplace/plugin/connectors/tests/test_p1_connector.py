"""P1 suite: schema, transactions, device flow, identity, lifecycle.

No network. FakeTransport scripts every GitHub response, so the tests assert
our behaviour rather than GitHub's availability. The live handshake is an
integration test and is marked as one.
"""
import json
import os
import sys
import unittest
from datetime import timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

from connectors.config import ProviderConfig  # noqa: E402
from connectors.credentials.store import CredentialNotFound, MemoryCredentialStore  # noqa: E402
from connectors.database import Database  # noqa: E402
from connectors.database.repositories import (  # noqa: E402
    ConnectorRepository, EventRepository, TransactionRepository, new_id,
)
from connectors.errors import (  # noqa: E402
    AccountMismatch, AuthorizationDenied, DeviceFlowDisabled, PermissionDenied,
    RateLimited, RefreshExpired, SSORequired, SecondaryRateLimited,
    TransactionAlreadyRedeemed, TransactionExpired, TransactionNotFound,
)
from connectors.github.client import GitHubClient  # noqa: E402
from connectors.github.http import FakeTransport, HttpResponse  # noqa: E402
from connectors.models import (  # noqa: E402
    Connector, ConnectorStatus, Credential, OAuthTransaction, TransactionStatus,
    iso, utcnow,
)
from connectors.oauth.strategies import DeviceFlowStrategy  # noqa: E402
from connectors.service import ConnectorService  # noqa: E402

OPERATOR = "op_test"

DEVICE_CODE_RESPONSE = {
    "device_code": "DC-40-CHARS", "user_code": "WDJB-MJHT",
    "verification_uri": "https://github.com/login/device",
    "expires_in": 900, "interval": 5,
}
TOKEN_RESPONSE = {
    "access_token": "ghu_ACCESSTOKEN", "expires_in": 28800,
    "refresh_token": "ghr_REFRESHTOKEN", "refresh_token_expires_in": 15897600,
    "scope": "", "token_type": "bearer",
}
USER_RESPONSE = {
    "id": 583231, "login": "octocat", "node_id": "MDQ6VXNlcjU4MzIzMQ==",
    "name": "The Octocat", "avatar_url": "https://avatars/1", "type": "User",
}


def build(transport=None):
    db = Database()
    db.migrate()
    transport = transport or FakeTransport()
    config = ProviderConfig(client_id="Iv23li4V24WX8yjaWoby")
    client = GitHubClient(config, transport)
    service = ConnectorService(db, MemoryCredentialStore(),
                               DeviceFlowStrategy(client, config), client, config)
    return db, transport, service


def script_successful_connect(transport, user=None):
    transport.push(200, DEVICE_CODE_RESPONSE)
    transport.push(200, TOKEN_RESPONSE)
    transport.push(200, user or USER_RESPONSE)


# ====================================================================== #
class TestSchema(unittest.TestCase):

    def test_migrations_are_idempotent(self):
        from connectors.database.migrations import MIGRATIONS
        db = Database()
        self.assertEqual(db.migrate(), len(MIGRATIONS))
        self.assertEqual(db.migrate(), 0)

    def test_foreign_keys_are_on(self):
        """SQLite defaults them OFF, which makes every REFERENCES decorative."""
        db = Database()
        db.migrate()
        self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_unique_account_key_blocks_a_duplicate_row(self):
        db = Database(); db.migrate()
        repo = ConnectorRepository(db)
        repo.ensure_operator(OPERATOR)
        make = lambda: Connector(id=new_id("conn"), operator_id=OPERATOR, provider="github",
                                 provider_account_id="583231", provider_username="octocat",
                                 status=ConnectorStatus.ACTIVE)
        repo.create(make())
        with self.assertRaises(Exception):
            repo.create(make())


# ====================================================================== #
class TestTransactionFSM(unittest.TestCase):

    def setUp(self):
        self.db = Database(); self.db.migrate()
        self.repo = TransactionRepository(self.db)
        ConnectorRepository(self.db).ensure_operator(OPERATOR)
        now = utcnow()
        self.tx = self.repo.create(OAuthTransaction(
            id=new_id("tx"), operator_id=OPERATOR, provider="github", strategy="device",
            status=TransactionStatus.CREATED, created_at=now,
            expires_at=now + timedelta(minutes=15)))

    def test_legal_transition(self):
        self.assertTrue(self.repo.transition(
            self.tx.id, TransactionStatus.CREATED, TransactionStatus.AUTHORIZATION_STARTED))

    def test_illegal_transition_raises(self):
        with self.assertRaises(ValueError):
            self.repo.transition(self.tx.id, TransactionStatus.CREATED,
                                 TransactionStatus.COMPLETED)

    def test_redemption_is_single_use(self):
        """A replay must update zero rows. The guard is in the WHERE clause, not
        in a read-then-write that two pollers could both pass."""
        self.repo.transition(self.tx.id, TransactionStatus.CREATED,
                             TransactionStatus.AUTHORIZATION_STARTED)
        self.assertTrue(self.repo.transition(
            self.tx.id, TransactionStatus.AUTHORIZATION_STARTED,
            TransactionStatus.CODE_EXCHANGED))
        self.assertFalse(self.repo.transition(
            self.tx.id, TransactionStatus.AUTHORIZATION_STARTED,
            TransactionStatus.CODE_EXCHANGED))

    def test_claim_raises_on_replay(self):
        self.repo.transition(self.tx.id, TransactionStatus.CREATED,
                             TransactionStatus.AUTHORIZATION_STARTED)
        self.repo.claim(self.tx.id, TransactionStatus.AUTHORIZATION_STARTED,
                        TransactionStatus.CODE_EXCHANGED)
        with self.assertRaises(TransactionAlreadyRedeemed):
            self.repo.claim(self.tx.id, TransactionStatus.AUTHORIZATION_STARTED,
                            TransactionStatus.CODE_EXCHANGED)

    def test_another_operator_cannot_see_the_transaction(self):
        self.assertIsNone(self.repo.get("op_other", self.tx.id))

    def test_secrets_are_destroyed_on_completion(self):
        self.db.execute("UPDATE oauth_transactions SET state_hash = 'abc' WHERE id = ?",
                        (self.tx.id,))
        self.repo.destroy_secrets(self.tx.id)
        row = self.db.execute("SELECT state_hash, device_code_enc FROM oauth_transactions "
                              "WHERE id = ?", (self.tx.id,)).fetchone()
        self.assertIsNone(row["state_hash"])
        self.assertIsNone(row["device_code_enc"])

    def test_stale_transactions_expire(self):
        self.db.execute("UPDATE oauth_transactions SET expires_at = ? WHERE id = ?",
                        (iso(utcnow() - timedelta(minutes=1)), self.tx.id))
        self.assertEqual(self.repo.expire_stale(), 1)


# ====================================================================== #
class TestErrorClassification(unittest.TestCase):
    """The four 403 branches. Only two are retryable; retrying the others is
    how a GitHub App gets flagged for abuse."""

    def classify(self, status, headers=None, payload=None):
        GitHubClient.classify(HttpResponse(status, headers or {},
                                           json.dumps(payload or {}).encode()))

    def test_secondary_rate_limit(self):
        with self.assertRaises(SecondaryRateLimited):
            self.classify(403, {"Retry-After": "60"})

    def test_primary_rate_limit(self):
        with self.assertRaises(RateLimited):
            self.classify(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1"})

    def test_sso_required_is_not_a_rate_limit(self):
        with self.assertRaises(SSORequired):
            self.classify(403, {"X-GitHub-SSO": "required; url=https://github.com/orgs/x/sso"})

    def test_plain_403_is_permission_and_not_retryable(self):
        with self.assertRaises(PermissionDenied) as ctx:
            self.classify(403, {}, {"message": "Resource not accessible"})
        self.assertFalse(ctx.exception.retryable)

    def test_404_is_not_reported_as_absence(self):
        from connectors.errors import NotFoundOrForbidden
        with self.assertRaises(NotFoundOrForbidden) as ctx:
            self.classify(404)
        self.assertNotIn("does not exist", ctx.exception.message)

    def test_header_lookup_is_case_insensitive(self):
        with self.assertRaises(SecondaryRateLimited):
            self.classify(429, {"retry-after": "30"})


# ====================================================================== #
class TestDeviceFlow(unittest.TestCase):

    def test_client_secret_is_never_transmitted(self):
        """Verified facts F3 and F4: the device flow and its refresh need none.
        This test is what stops a refactor quietly reintroducing one."""
        db, transport, service = build()
        script_successful_connect(transport)
        started = service.begin_connect(OPERATOR)
        service.poll_connect(OPERATOR, started["transaction_id"])
        self.assertFalse(transport.transmitted("client_secret"))

    def test_pending_then_success(self):
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        transport.push(200, {"error": "authorization_pending"})
        transport.push(200, TOKEN_RESPONSE)
        transport.push(200, USER_RESPONSE)

        started = service.begin_connect(OPERATOR)
        self.assertEqual(started["user_code"], "WDJB-MJHT")
        pending = service.poll_connect(OPERATOR, started["transaction_id"])
        self.assertEqual(pending["status"], "AUTHORIZATION_STARTED")
        done = service.poll_connect(OPERATOR, started["transaction_id"])
        self.assertEqual(done["status"], "COMPLETED")

    def test_slow_down_widens_the_interval(self):
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        transport.push(200, {"error": "slow_down"})
        started = service.begin_connect(OPERATOR)
        result = service.poll_connect(OPERATOR, started["transaction_id"])
        self.assertEqual(result["poll_interval_seconds"], 10)

    def test_access_denied_rejects_the_transaction(self):
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        transport.push(200, {"error": "access_denied"})
        started = service.begin_connect(OPERATOR)
        with self.assertRaises(AuthorizationDenied):
            service.poll_connect(OPERATOR, started["transaction_id"])
        tx = service.transactions.get(OPERATOR, started["transaction_id"])
        self.assertIs(tx.status, TransactionStatus.REJECTED)

    def test_device_flow_disabled_is_its_own_error(self):
        """A misconfigured app must not read as a user problem."""
        db, transport, service = build()
        transport.push(200, {"error": "device_flow_disabled"})
        with self.assertRaises(DeviceFlowDisabled):
            service.begin_connect(OPERATOR)

    def test_device_code_never_reaches_the_response(self):
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        started = service.begin_connect(OPERATOR)
        self.assertNotIn("device_code", json.dumps(started))

    def test_device_code_is_not_in_the_database(self):
        """It is redeemable material and the client id it pairs with is public."""
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        service.begin_connect(OPERATOR)
        row = db.execute("SELECT * FROM oauth_transactions").fetchone()
        self.assertIsNone(row["device_code_enc"])
        dump = " ".join(str(v) for v in tuple(row))
        self.assertNotIn("DC-40-CHARS", dump)

    def test_begin_is_idempotent_per_operator(self):
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        first = service.begin_connect(OPERATOR)
        second = service.begin_connect(OPERATOR)     # no second device-code call scripted
        self.assertEqual(first["transaction_id"], second["transaction_id"])

    def test_expired_transaction_raises_and_purges(self):
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        started = service.begin_connect(OPERATOR)
        db.execute("UPDATE oauth_transactions SET expires_at = ? WHERE id = ?",
                   (iso(utcnow() - timedelta(seconds=1)), started["transaction_id"]))
        with self.assertRaises(TransactionExpired):
            service.poll_connect(OPERATOR, started["transaction_id"])

    def test_another_operator_cannot_poll_it(self):
        db, transport, service = build()
        transport.push(200, DEVICE_CODE_RESPONSE)
        started = service.begin_connect(OPERATOR)
        with self.assertRaises(TransactionNotFound):
            service.poll_connect("op_attacker", started["transaction_id"])


# ====================================================================== #
class TestIdentityAndAccounts(unittest.TestCase):

    def connect(self, service, transport, user):
        script_successful_connect(transport, user)
        started = service.begin_connect(OPERATOR)
        return service.poll_connect(OPERATOR, started["transaction_id"])

    def test_numeric_id_is_the_identity(self):
        db, transport, service = build()
        result = self.connect(service, transport, USER_RESPONSE)
        row = db.execute("SELECT provider_account_id FROM connectors").fetchone()
        self.assertEqual(row["provider_account_id"], "583231")

    def test_a_rename_does_not_orphan_the_connector(self):
        """login is mutable; the numeric id is not. A rename must find the same row."""
        db, transport, service = build()
        first = self.connect(service, transport, USER_RESPONSE)
        renamed = dict(USER_RESPONSE, login="octocat-new")
        second = self.connect(service, transport, renamed)
        self.assertEqual(first["connector_id"], second["connector_id"])
        self.assertEqual(len(service.list_connectors(OPERATOR)), 1)
        self.assertEqual(service.list_connectors(OPERATOR)[0]["account"]["username"],
                         "octocat-new")

    def test_second_account_does_not_overwrite_the_first(self):
        """The §25 hazard, made structurally impossible by the UNIQUE key."""
        db, transport, service = build()
        self.connect(service, transport, USER_RESPONSE)
        other = dict(USER_RESPONSE, id=991204, login="octo-at-acme")
        self.connect(service, transport, other)
        connectors = service.list_connectors(OPERATOR)
        self.assertEqual(len(connectors), 2)
        self.assertEqual({c["account"]["id"] for c in connectors}, {"583231", "991204"})

    def test_reconnect_with_a_different_account_is_rejected(self):
        db, transport, service = build()
        first = self.connect(service, transport, USER_RESPONSE)
        script_successful_connect(transport, dict(USER_RESPONSE, id=991204, login="someone"))
        started = service.begin_connect(OPERATOR, reconnect_of=first["connector_id"])
        with self.assertRaises(AccountMismatch):
            service.poll_connect(OPERATOR, started["transaction_id"])

    def test_label_survives_a_process_boundary(self):
        """Regression: the label was held in an in-memory dict, so the
        begin/poll CLI split dropped it silently. Transaction state belongs in
        the transaction row. Two SEPARATE service objects over one database
        stand in for the two processes."""
        db = Database(); db.migrate()
        transport = FakeTransport()
        config = ProviderConfig(client_id="Iv23li4V24WX8yjaWoby")
        client = GitHubClient(config, transport)
        store = MemoryCredentialStore()
        script_successful_connect(transport)

        beginner = ConnectorService(db, store, DeviceFlowStrategy(client, config),
                                    client, config)
        started = beginner.begin_connect(OPERATOR, label="work")

        poller = ConnectorService(db, store, DeviceFlowStrategy(client, config),
                                  client, config)
        result = poller.poll_connect(OPERATOR, started["transaction_id"])
        self.assertEqual(result["connector"]["label"], "work")

    def test_connector_public_dict_leaks_nothing(self):
        db, transport, service = build()
        self.connect(service, transport, USER_RESPONSE)
        blob = json.dumps(service.list_connectors(OPERATOR))
        for secret in ("ghu_", "ghr_", "DC-40-CHARS", "client_secret"):
            self.assertNotIn(secret, blob)


# ====================================================================== #
class TestCredentialLifecycle(unittest.TestCase):

    def connect(self):
        db, transport, service = build()
        script_successful_connect(transport)
        started = service.begin_connect(OPERATOR)
        result = service.poll_connect(OPERATOR, started["transaction_id"])
        return db, transport, service, result["connector_id"]

    def test_credential_lands_in_the_store_not_the_database(self):
        db, transport, service, connector_id = self.connect()
        self.assertEqual(service.credentials.get(connector_id).access_token,
                         "ghu_ACCESSTOKEN")
        row = db.execute("SELECT * FROM connector_credentials").fetchone()
        self.assertIsNone(row["access_token_enc"])
        self.assertIsNotNone(row["keychain_ref"])

    def test_routine_expiry_refreshes_without_a_state_change(self):
        """An 8h expiry is normal operation and must stay invisible to the user."""
        db, transport, service, connector_id = self.connect()
        stale = Credential("ghu_OLD", refresh_token="ghr_OLD",
                           access_expires_at=utcnow() - timedelta(minutes=1))
        service.credentials.save(connector_id, stale)
        transport.push(200, dict(TOKEN_RESPONSE, access_token="ghu_NEW"))
        fresh = service.credential_for(OPERATOR, connector_id)
        self.assertEqual(fresh.access_token, "ghu_NEW")
        self.assertIs(service.get_connector(OPERATOR, connector_id).status,
                      ConnectorStatus.ACTIVE)

    def test_refresh_failure_moves_to_reauth_required(self):
        db, transport, service, connector_id = self.connect()
        stale = Credential("ghu_OLD", refresh_token="ghr_DEAD",
                           access_expires_at=utcnow() - timedelta(minutes=1))
        service.credentials.save(connector_id, stale)
        transport.push(200, {"error": "bad_refresh_token"})
        with self.assertRaises(RefreshExpired):
            service.credential_for(OPERATOR, connector_id)
        connector = service.get_connector(OPERATOR, connector_id)
        self.assertIs(connector.status, ConnectorStatus.REAUTH_REQUIRED)
        self.assertEqual(connector.status_reason, "REFRESH_EXPIRED")

    def test_another_operator_cannot_obtain_the_credential(self):
        db, transport, service, connector_id = self.connect()
        with self.assertRaises(TransactionNotFound):
            service.credential_for("op_attacker", connector_id)

    def test_disconnect_destroys_the_credential(self):
        db, transport, service, connector_id = self.connect()
        result = service.disconnect(OPERATOR, connector_id)
        self.assertTrue(result["credentials_deleted"])
        with self.assertRaises(CredentialNotFound):
            service.credentials.get(connector_id)

    def test_disconnect_is_honest_about_remote_revocation(self):
        """Local mode cannot revoke on GitHub -- that needs a client_secret it is
        never issued. Claiming otherwise would be the comfortable copy and a lie."""
        db, transport, service, connector_id = self.connect()
        result = service.disconnect(OPERATOR, connector_id)
        self.assertFalse(result["provider_authorization_revoked"])
        self.assertIn("github.com", result["revoke_instructions_url"])

    def test_disconnect_is_idempotent(self):
        db, transport, service, connector_id = self.connect()
        service.disconnect(OPERATOR, connector_id)
        self.assertEqual(service.disconnect(OPERATOR, connector_id)["status"],
                         "DISCONNECTED")

    def test_disconnected_connector_yields_no_credential(self):
        db, transport, service, connector_id = self.connect()
        service.disconnect(OPERATOR, connector_id)
        with self.assertRaises(Exception):
            service.credential_for(OPERATOR, connector_id)

    def test_connector_row_survives_for_audit(self):
        db, transport, service, connector_id = self.connect()
        service.disconnect(OPERATOR, connector_id)
        self.assertIsNotNone(service.get_connector(OPERATOR, connector_id))
        self.assertEqual(service.list_connectors(OPERATOR), [])


# ====================================================================== #
class TestAudit(unittest.TestCase):

    def test_connect_and_disconnect_are_audited_and_chained(self):
        db, transport, service = build()
        script_successful_connect(transport)
        started = service.begin_connect(OPERATOR)
        result = service.poll_connect(OPERATOR, started["transaction_id"])
        service.disconnect(OPERATOR, result["connector_id"])
        events = EventRepository(db)
        types = [r["event_type"] for r in
                 db.execute("SELECT event_type FROM connector_events ORDER BY id")]
        self.assertIn("CONNECTOR_CREATED", types)
        self.assertIn("CONNECTOR_DISCONNECTED", types)
        self.assertTrue(events.verify_chain())

    def test_tampering_breaks_the_chain(self):
        db, transport, service = build()
        events = EventRepository(db)
        events.append(OPERATOR, "CONNECTOR_CREATED", "SUCCESS", connector_id="c1")
        events.append(OPERATOR, "FILE_READ", "SUCCESS", connector_id="c1")
        db.execute("DROP TRIGGER connector_events_no_update")
        db.execute("UPDATE connector_events SET result = 'DENIED' WHERE id = 1")
        self.assertFalse(events.verify_chain())

    def test_audit_rows_carry_no_secrets(self):
        db, transport, service = build()
        script_successful_connect(transport)
        started = service.begin_connect(OPERATOR)
        service.poll_connect(OPERATOR, started["transaction_id"])
        blob = " ".join(str(tuple(r)) for r in db.execute("SELECT * FROM connector_events"))
        for secret in ("ghu_", "ghr_", "DC-40-CHARS"):
            self.assertNotIn(secret, blob)


# ====================================================================== #
class TestCredentialRedaction(unittest.TestCase):

    def setUp(self):
        self.credential = Credential("ghu_SECRET", refresh_token="ghr_SECRET")

    def test_repr_str_and_format_redact(self):
        for rendered in (repr(self.credential), str(self.credential),
                         "{}".format(self.credential), f"{self.credential}"):
            self.assertNotIn("ghu_SECRET", rendered)

    def test_not_json_serialisable(self):
        with self.assertRaises(TypeError):
            json.dumps(self.credential)

    def test_not_picklable(self):
        import pickle
        with self.assertRaises(TypeError):
            pickle.dumps(self.credential)

    def test_expiry_uses_a_skew(self):
        nearly = Credential("ghu_X", access_expires_at=utcnow() + timedelta(seconds=30))
        self.assertTrue(nearly.is_expired())
        healthy = Credential("ghu_X", access_expires_at=utcnow() + timedelta(hours=1))
        self.assertFalse(healthy.is_expired())


if __name__ == "__main__":
    unittest.main(verbosity=2)
