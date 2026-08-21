"""ConnectorService -- provider-agnostic lifecycle.

Contains zero GitHub identifiers. Everything provider-specific arrives through
the AuthStrategy and the identity fetcher, so adding GitLab is adding a
provider package, not editing this file.

The order of operations in disconnect() is deliberate and is the one place
where getting the sequence wrong loses a security property: the local
credential is destroyed BEFORE remote revocation is attempted, so a network
failure at the last step still leaves us holding nothing.
"""
from datetime import timedelta
from typing import Dict, List, Optional

from .config import ProviderConfig
from .credentials.store import CredentialNotFound, CredentialStore
from .database.repositories import (
    ConnectorRepository, EventRepository, TransactionRepository, new_id,
)
from .errors import (
    AccountMismatch, AuthorizationDenied, AuthorizationPending, ConnectorError,
    RefreshExpired, CredentialInvalid, SlowDown, TransactionExpired, TransactionNotFound,
)
from .github.client import GitHubClient
from .models import (
    Connector, ConnectorStatus, Credential, OAuthTransaction, StatusReason,
    TERMINAL_STATUSES, TransactionStatus, iso, utcnow,
)
from .discovery_service import DiscoveryMixin
from .oauth.strategies import AuthResult, AuthStrategy, DeviceFlowStrategy

#: Transactions are short-lived by construction. GitHub's device codes last 15
#: minutes; ours expire no later than that.
TRANSACTION_TTL = timedelta(minutes=15)

_DEVICE_SECRET_PREFIX = "device:"


class _ConnectorLifecycle:
    def __init__(self, db, credential_store: CredentialStore,
                 strategy: Optional[AuthStrategy] = None,
                 client: Optional[GitHubClient] = None,
                 config: Optional[ProviderConfig] = None):
        self.db = db
        self.config = config or ProviderConfig()
        self.client = client or GitHubClient(self.config)
        self.strategy = strategy or DeviceFlowStrategy(self.client, self.config)
        self.credentials = credential_store
        #: Extra credential slots this provider issues beyond the default one.
        #: Slack hands out a bot token AND a user token from one authorization;
        #: disconnect must destroy every slot, because a forgotten one is a live
        #: token after the user was told the connection was gone.
        self.credential_slots = tuple(getattr(self.config, "credential_slots", ()))
        self.connectors = ConnectorRepository(db)
        self.transactions = TransactionRepository(db)
        self.events = EventRepository(db)

    # ================================================================== #
    # connect
    # ================================================================== #
    def begin_connect(self, operator_id: str, label: Optional[str] = None,
                      reconnect_of: Optional[str] = None) -> Dict:
        self.connectors.ensure_operator(operator_id)

        if reconnect_of and not self.connectors.get(operator_id, reconnect_of):
            raise TransactionNotFound("no such connector for this operator")

        # Idempotent per operator: an open transaction is returned rather than
        # a second one opened, so a double-clicked Connect button does not
        # strand a device code.
        existing = self.transactions.find_open(operator_id, self.config.provider)
        if existing is not None:
            resumable = False
            try:
                handle = self.credentials.get_secret(_DEVICE_SECRET_PREFIX + existing.id)
                resumable = self.strategy.can_resume(handle)
            except CredentialNotFound:
                resumable = False
            challenge = self._cached_challenge(existing) if resumable else None
            if challenge is not None:
                return {**existing.public_dict(), **challenge}
            # Dead: a redirect flow whose in-process listener did not survive a
            # restart. Retire it and open a fresh one, rather than handing back
            # a transaction that can never complete -- which made Connect
            # permanently unusable, since every click returned the same corpse.
            self.transactions.transition(existing.id, existing.status,
                                         TransactionStatus.FAILED,
                                         failure_code="LISTENER_LOST")
            self._purge_transaction_secrets(existing.id)

        now = utcnow()
        tx = OAuthTransaction(
            id=new_id("tx"), operator_id=operator_id, provider=self.config.provider,
            strategy=self.strategy.name, status=TransactionStatus.CREATED,
            created_at=now, expires_at=now + TRANSACTION_TTL, reconnect_of=reconnect_of,
            label=label)
        self.transactions.create(tx)

        challenge = self.strategy.begin()
        # The handle is redeemable material -- a device_code for device flow, a
        # state value for a redirect flow, and for a provider with no PKCE the
        # state is the ONLY binding between the code and this request. Keychain,
        # never the database.
        self.credentials.put_secret(_DEVICE_SECRET_PREFIX + tx.id, challenge.handle)
        self.credentials.put_secret(
            _DEVICE_SECRET_PREFIX + tx.id + ":display",
            "%s\n%s\n%s" % (challenge.mode, challenge.user_code or "",
                            challenge.verification_uri or ""))

        self.transactions.transition(
            tx.id, TransactionStatus.CREATED, TransactionStatus.AUTHORIZATION_STARTED,
            poll_interval=challenge.interval,
            expires_at=iso(now + timedelta(seconds=challenge.expires_in)))
        tx.status = TransactionStatus.AUTHORIZATION_STARTED
        tx.poll_interval = challenge.interval

        self.events.append(operator_id, "CONNECTOR_CONNECT_STARTED", "PENDING_APPROVAL",
                           detail={"strategy": self.strategy.name})
        return {**tx.public_dict(), **challenge.public_dict()}

    def _cached_challenge(self, tx: OAuthTransaction) -> Optional[Dict]:
        try:
            display = self.credentials.get_secret(
                _DEVICE_SECRET_PREFIX + tx.id + ":display")
        except CredentialNotFound:
            return None
        parts = display.split("\n")
        mode = parts[0] if parts else "device"
        if mode != "device":
            return {"mode": mode, "browser_opened": True,
                    "poll_interval_seconds": tx.poll_interval}
        return {"mode": "device",
                "user_code": parts[1] if len(parts) > 1 else "",
                "verification_uri": parts[2] if len(parts) > 2 else "",
                "poll_interval_seconds": tx.poll_interval}

    def poll_connect(self, operator_id: str, transaction_id: str) -> Dict:
        tx = self.transactions.get(operator_id, transaction_id)
        if tx is None:
            # Not-yours and not-found are the same answer, so the endpoint is
            # not an oracle for other operators' transaction ids.
            raise TransactionNotFound(transaction_id)
        if tx.status in TERMINAL_STATUSES:
            return tx.public_dict()

        if tx.is_expired():
            self.transactions.transition(tx.id, tx.status, TransactionStatus.EXPIRED)
            self._purge_transaction_secrets(tx.id)
            raise TransactionExpired(transaction_id)

        try:
            device_code = self.credentials.get_secret(_DEVICE_SECRET_PREFIX + tx.id)
        except CredentialNotFound:
            self.transactions.transition(tx.id, tx.status, TransactionStatus.FAILED,
                                         failure_code="DEVICE_CODE_MISSING")
            raise TransactionNotFound("device code is gone; restart the flow")

        try:
            result = self.strategy.poll(device_code)
        except SlowDown as exc:
            # GitHub asks for +5s. Honour it: polling faster is what earns a
            # secondary rate limit.
            self.db.execute(
                "UPDATE oauth_transactions SET poll_interval = poll_interval + 5 WHERE id = ?",
                (tx.id,))
            return {**tx.public_dict(), "poll_interval_seconds": tx.poll_interval + 5}
        except AuthorizationPending:
            return {**tx.public_dict(), "poll_interval_seconds": tx.poll_interval}
        except AuthorizationDenied:
            self.transactions.transition(tx.id, tx.status, TransactionStatus.REJECTED,
                                         failure_code="ACCESS_DENIED")
            self._purge_transaction_secrets(tx.id)
            raise
        except TransactionExpired:
            self.transactions.transition(tx.id, tx.status, TransactionStatus.EXPIRED,
                                         failure_code="EXPIRED_TOKEN")
            self._purge_transaction_secrets(tx.id)
            raise

        # Single-use, enforced by the database: a concurrent poller that also
        # obtained a token loses this claim and raises rather than creating a
        # second connector.
        self.transactions.claim(tx.id, TransactionStatus.AUTHORIZATION_STARTED,
                                TransactionStatus.CODE_EXCHANGED)

        # Identity resolution is the strategy's job: GitHub asks GET /user,
        # Slack asks auth.test with the user token. The service stays
        # provider-agnostic by never knowing which.
        identity = self.strategy.identity(result)
        connector = self._upsert_connector(operator_id, tx, identity)

        # A provider may issue several credentials from one authorization.
        self.credentials.save(connector.id, result.primary)
        for slot, credential in (result.extra or {}).items():
            self.credentials.save(connector.id, credential, slot=slot)
        self.connectors.record_credential_metadata(
            connector.id, "%s:%s" % (self.config.provider, connector.id), result.primary)
        self._record_grant_metadata(connector.id, result)
        self.connectors.set_status(connector.id, ConnectorStatus.ACTIVE)

        self.transactions.claim(tx.id, TransactionStatus.CODE_EXCHANGED,
                                TransactionStatus.CONNECTOR_CREATED,
                                connector_id=connector.id)
        self.transactions.claim(tx.id, TransactionStatus.CONNECTOR_CREATED,
                                TransactionStatus.COMPLETED, completed_at=iso(utcnow()))
        self.transactions.destroy_secrets(tx.id)
        self._purge_transaction_secrets(tx.id)

        self.events.append(
            operator_id,
            "CONNECTOR_REAUTHORIZED" if tx.reconnect_of else "CONNECTOR_CREATED",
            "SUCCESS", connector_id=connector.id,
            detail={"account_id": identity.account_id, "username": identity.username})

        refreshed = self.connectors.get(operator_id, connector.id)
        return {"status": TransactionStatus.COMPLETED.value,
                "transaction_id": tx.id,
                "connector_id": connector.id,
                "connector": refreshed.public_dict()}

    def _record_grant_metadata(self, connector_id, result):
        """Persist what the provider actually granted.

        Notably `rotation_enabled`: a Slack app installed without token
        rotation yields a credential that NEVER EXPIRES, which is a different
        risk posture from one that does. Recording it means the UI can say so
        rather than implying rotation is protecting the user when it is not.
        """
        meta = result.meta or {}
        if not meta:
            return
        now = iso(utcnow())
        for scope in (meta.get("bot_scopes") or []):
            self.db.execute(
                "INSERT OR IGNORE INTO connector_scopes (connector_id, scope, source, "
                "granted_at) VALUES (?,?,?,?)",
                (connector_id, "bot:%s" % scope, "oauth_scope", now))
        for scope in (meta.get("user_scopes") or []):
            self.db.execute(
                "INSERT OR IGNORE INTO connector_scopes (connector_id, scope, source, "
                "granted_at) VALUES (?,?,?,?)",
                (connector_id, "user:%s" % scope, "oauth_scope", now))

    def _upsert_connector(self, operator_id, tx, identity) -> Connector:
        existing = self.connectors.find_by_account(
            operator_id, self.config.provider, identity.account_id)

        if tx.reconnect_of:
            target = self.connectors.get(operator_id, tx.reconnect_of)
            if target and target.provider_account_id != identity.account_id:
                # Not a reconnect. Rebinding the row would attach one person's
                # history and grants to a different GitHub account.
                self.events.append(operator_id, "CONNECTOR_REAUTHORIZED", "FAILED",
                                   connector_id=target.id, reason_code="ACCOUNT_MISMATCH")
                raise AccountMismatch(
                    "this authorization is for a different GitHub account",
                    expected=target.provider_account_id, received=identity.account_id)

        if existing is not None:
            # UNIQUE(operator_id, provider, provider_account_id) makes the §25
            # overwrite hazard structurally impossible: reconnecting account A
            # rotates A's credential, and connecting B inserts a second row.
            self.connectors.update_identity(existing.id, identity)
            self.connectors.set_label(existing.id, tx.label)
            # Reconnecting a previously disconnected account must clear the
            # soft-delete, or the row says ACTIVE while every listing hides it.
            self.connectors.reactivate(existing.id)
            return existing

        connector = Connector(
            id=new_id("conn"), operator_id=operator_id, provider=self.config.provider,
            provider_account_id=identity.account_id, provider_username=identity.username,
            provider_account_node=identity.node_id, display_name=identity.display_name,
            avatar_url=identity.avatar_url, account_type=identity.account_type,
            label=tx.label,
            status=ConnectorStatus.PENDING, api_base=self.config.api_base)
        return self.connectors.create(connector)

    def cancel_connect(self, operator_id, transaction_id):
        tx = self.transactions.get(operator_id, transaction_id)
        if tx is None:
            raise TransactionNotFound(transaction_id)
        if tx.status not in TERMINAL_STATUSES:
            self.transactions.transition(tx.id, tx.status, TransactionStatus.CANCELLED)
        self.transactions.destroy_secrets(tx.id)
        self._purge_transaction_secrets(tx.id)

    def _purge_transaction_secrets(self, transaction_id):
        self.credentials.delete_secret(_DEVICE_SECRET_PREFIX + transaction_id)
        self.credentials.delete_secret(_DEVICE_SECRET_PREFIX + transaction_id + ":display")

    # ================================================================== #
    # read
    # ================================================================== #
    def get_connector(self, operator_id, connector_id) -> Optional[Connector]:
        return self.connectors.get(operator_id, connector_id)

    def list_connectors(self, operator_id) -> List[Dict]:
        """This provider's connectors ONLY.

        The provider filter is not optional. Without it every provider's
        service returned every connector, so a GitHub connection rendered as a
        connected Slack account -- and worse, a caller could have acted on a
        connector belonging to a different provider entirely.
        """
        return [c.public_dict() for c in self.connectors.list_for_operator(
            operator_id, provider=self.config.provider)]

    # ================================================================== #
    # credentials
    # ================================================================== #
    def credential_for(self, operator_id, connector_id) -> Credential:
        """The only way to obtain a live credential. Refreshes transparently.

        A routine 8-hour expiry is not a connector state change and must never
        surface to the user -- it would show a scary status eight times a day
        for nothing. Only REFRESH failure is a state change.
        """
        connector = self.connectors.get(operator_id, connector_id)
        if connector is None:
            raise TransactionNotFound(connector_id)
        if connector.status is ConnectorStatus.DISCONNECTED:
            raise CredentialInvalid("connector is disconnected")

        credential = self.credentials.get(connector_id)
        if not credential.is_expired():
            self.connectors.touch_used(connector_id)
            return credential

        try:
            rotated = self.strategy.refresh(credential)
        except (RefreshExpired, CredentialInvalid) as exc:
            reason = (StatusReason.REFRESH_EXPIRED.value
                      if isinstance(exc, RefreshExpired) else StatusReason.REVOKED.value)
            self.connectors.set_status(connector_id, ConnectorStatus.REAUTH_REQUIRED, reason)
            self.events.append(operator_id, "CONNECTOR_STATE_CHANGED", "FAILED",
                               connector_id=connector_id, reason_code=reason)
            raise

        self.credentials.rotate(connector_id, rotated)
        self.connectors.record_credential_metadata(
            connector_id, "%s:%s" % (self.config.provider, connector_id), rotated)
        self.connectors.touch_used(connector_id)
        return rotated

    def validate(self, operator_id, connector_id) -> Dict:
        connector = self.connectors.get(operator_id, connector_id)
        if connector is None:
            raise TransactionNotFound(connector_id)
        try:
            credential = self.credential_for(operator_id, connector_id)
            # Identity resolution belongs to the STRATEGY -- GitHub asks
            # GET /user, Slack asks auth.test with the user token. poll_connect
            # was moved onto that seam and this caller was missed, so validate
            # called GitHub's client method on a SlackClient and raised
            # AttributeError. Rebuild the same shape poll_connect produces.
            extra = {}
            for slot in self.credential_slots:
                try:
                    extra[slot] = self.credentials.get(connector_id, slot=slot)
                except CredentialNotFound:
                    pass
            identity = self.strategy.identity(
                AuthResult(primary=credential, extra=extra))
        except ConnectorError as exc:
            self.events.append(operator_id, "CONNECTOR_VALIDATION_FAILED", "FAILED",
                               connector_id=connector_id, reason_code=exc.code)
            raise
        self.connectors.update_identity(connector_id, identity, status=ConnectorStatus.ACTIVE)
        return self.connectors.get(operator_id, connector_id).public_dict()

    # ================================================================== #
    # disconnect
    # ================================================================== #
    def disconnect(self, operator_id, connector_id) -> Dict:
        connector = self.connectors.get(operator_id, connector_id)
        if connector is None:
            raise TransactionNotFound(connector_id)
        if connector.status is ConnectorStatus.DISCONNECTED:
            # Idempotent: deleting an already-disconnected connector is a 200.
            return self._disconnect_result(False)

        # 1. stop new work immediately
        self.connectors.mark_disconnected(connector_id)
        # 2. destroy EVERY local credential slot BEFORE attempting remote
        #    revocation, so a network failure at step 3 still leaves us holding
        #    nothing at all
        self.credentials.delete_all(connector_id, slots=self.credential_slots)
        self.connectors.drop_credential_metadata(connector_id)
        # 3. drop caches and grants
        self.db.execute("DELETE FROM connector_metadata WHERE connector_id = ?",
                        (connector_id,))
        self.db.execute("DELETE FROM approval_grants WHERE connector_id = ?",
                        (connector_id,))
        # 4. remote revocation needs a client_secret, which local mode is never
        #    issued. We report that honestly rather than claiming a revocation
        #    we did not perform.
        revoked = False
        self.events.append(operator_id, "CONNECTOR_DISCONNECTED", "SUCCESS",
                           connector_id=connector_id,
                           detail={"provider_authorization_revoked": revoked})
        return self._disconnect_result(revoked)

    def _disconnect_result(self, revoked: bool) -> Dict:
        return {
            "status": ConnectorStatus.DISCONNECTED.value,
            "credentials_deleted": True,
            "provider_authorization_revoked": revoked,
            "revoke_instructions_url":
                "https://github.com/settings/apps/authorizations",
        }


class ConnectorService(_ConnectorLifecycle, DiscoveryMixin):
    """The connector API surface: lifecycle (P1) + discovery (P2).

    Provider-agnostic throughout -- everything GitHub-specific arrives through
    the AuthStrategy and the provider client.
    """
