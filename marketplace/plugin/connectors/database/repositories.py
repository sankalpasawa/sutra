"""Repositories.

Two properties here are load-bearing and both are enforced by the DATABASE
rather than by application logic:

  Single-use transaction redemption is `UPDATE ... WHERE status = <expected>`
  with a rowcount check. A replay updates zero rows. Reading the row, checking
  the status in Python, then writing would leave a window between the check and
  the write that two concurrent pollers can both pass through.

  Audit rows are hash-chained AND protected by triggers. The chain makes
  tampering detectable; the trigger makes it fail.

Every connector query carries an operator_id predicate. A query without one is
a cross-user data path, and test_forbidden_calls asserts none exists.
"""
import hashlib
import json
import uuid
from typing import List, Optional

from ..errors import TransactionAlreadyRedeemed, TransactionNotFound
from ..models import (
    Connector, ConnectorStatus, LEGAL_TRANSITIONS, OAuthTransaction,
    TransactionStatus, iso, parse_iso, utcnow,
)


def new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:24])


def canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class ConnectorRepository:
    def __init__(self, db):
        self.db = db

    # -- writes ----------------------------------------------------------
    def ensure_operator(self, operator_id: str, handle: Optional[str] = None) -> str:
        now = iso(utcnow())
        self.db.execute(
            "INSERT OR IGNORE INTO operators (id, handle, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)", (operator_id, handle or operator_id, now, now))
        return operator_id

    def create(self, connector: Connector) -> Connector:
        now = utcnow()
        connector.created_at = connector.created_at or now
        connector.updated_at = now
        self.db.execute(
            "INSERT INTO connectors (id, operator_id, provider, provider_account_id, "
            " provider_account_node, provider_username, display_name, avatar_url, "
            " account_type, label, status, status_reason, api_base, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (connector.id, connector.operator_id, connector.provider,
             connector.provider_account_id, connector.provider_account_node,
             connector.provider_username, connector.display_name, connector.avatar_url,
             connector.account_type, connector.label, connector.status.value,
             connector.status_reason, connector.api_base,
             iso(connector.created_at), iso(connector.updated_at)))
        return connector

    def update_identity(self, connector_id: str, identity, status=None, status_reason=None):
        """Refresh the mutable display fields. username is NOT identity."""
        self.db.execute(
            "UPDATE connectors SET provider_username = ?, display_name = ?, avatar_url = ?, "
            " provider_account_node = ?, status = COALESCE(?, status), status_reason = ?, "
            " updated_at = ?, last_validated_at = ? WHERE id = ?",
            (identity.username, identity.display_name, identity.avatar_url,
             identity.node_id, status.value if status else None, status_reason,
             iso(utcnow()), iso(utcnow()), connector_id))

    def set_label(self, connector_id: str, label):
        if label is None:
            return
        self.db.execute("UPDATE connectors SET label = ?, updated_at = ? WHERE id = ?",
                        (label, iso(utcnow()), connector_id))

    def set_status(self, connector_id: str, status: ConnectorStatus, reason=None):
        self.db.execute(
            "UPDATE connectors SET status = ?, status_reason = ?, updated_at = ? WHERE id = ?",
            (status.value, reason, iso(utcnow()), connector_id))

    def touch_used(self, connector_id: str):
        self.db.execute("UPDATE connectors SET last_used_at = ? WHERE id = ?",
                        (iso(utcnow()), connector_id))

    def mark_disconnected(self, connector_id: str):
        now = iso(utcnow())
        self.db.execute(
            "UPDATE connectors SET status = ?, disconnected_at = ?, updated_at = ? WHERE id = ?",
            (ConnectorStatus.DISCONNECTED.value, now, now, connector_id))

    def record_credential_metadata(self, connector_id, keychain_ref, credential):
        now = iso(utcnow())
        self.db.execute(
            "INSERT INTO connector_credentials (connector_id, credential_type, keychain_ref, "
            " access_expires_at, refresh_expires_at, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(connector_id) DO UPDATE SET keychain_ref = excluded.keychain_ref, "
            " access_expires_at = excluded.access_expires_at, "
            " refresh_expires_at = excluded.refresh_expires_at, "
            " rotated_at = excluded.updated_at, updated_at = excluded.updated_at",
            (connector_id, credential.credential_type, keychain_ref,
             iso(credential.access_expires_at), iso(credential.refresh_expires_at), now, now))

    def drop_credential_metadata(self, connector_id):
        self.db.execute("DELETE FROM connector_credentials WHERE connector_id = ?",
                        (connector_id,))

    # -- reads -----------------------------------------------------------
    def _row_to_connector(self, row) -> Connector:
        return Connector(
            id=row["id"], operator_id=row["operator_id"], provider=row["provider"],
            provider_account_id=row["provider_account_id"],
            provider_account_node=row["provider_account_node"],
            provider_username=row["provider_username"], display_name=row["display_name"],
            avatar_url=row["avatar_url"], account_type=row["account_type"],
            label=row["label"], status=ConnectorStatus(row["status"]),
            status_reason=row["status_reason"], api_base=row["api_base"],
            created_at=parse_iso(row["created_at"]), updated_at=parse_iso(row["updated_at"]),
            last_used_at=parse_iso(row["last_used_at"]),
            last_validated_at=parse_iso(row["last_validated_at"]),
            disconnected_at=parse_iso(row["disconnected_at"]))

    def get(self, operator_id: str, connector_id: str) -> Optional[Connector]:
        """Always scoped by operator. Callers get None for another operator's
        connector, which the API renders as 404 rather than 403 -- a 403 would
        confirm the id exists and turn the endpoint into an enumeration oracle."""
        row = self.db.execute(
            "SELECT * FROM connectors WHERE id = ? AND operator_id = ?",
            (connector_id, operator_id)).fetchone()
        return self._row_to_connector(row) if row else None

    def find_by_account(self, operator_id, provider, provider_account_id):
        row = self.db.execute(
            "SELECT * FROM connectors WHERE operator_id = ? AND provider = ? "
            "AND provider_account_id = ?",
            (operator_id, provider, provider_account_id)).fetchone()
        return self._row_to_connector(row) if row else None

    def list_for_operator(self, operator_id, provider=None, include_disconnected=False):
        sql = "SELECT * FROM connectors WHERE operator_id = ?"
        params = [operator_id]
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if not include_disconnected:
            sql += " AND disconnected_at IS NULL"
        sql += " ORDER BY created_at ASC"
        return [self._row_to_connector(r) for r in self.db.execute(sql, params).fetchall()]


class TransactionRepository:
    def __init__(self, db):
        self.db = db

    def create(self, tx: OAuthTransaction) -> OAuthTransaction:
        self.db.execute(
            "INSERT INTO oauth_transactions (id, operator_id, provider, strategy, state_hash, "
            " device_code_enc, code_verifier_enc, redirect_uri, requested_scopes, reconnect_of, "
            " status, poll_interval, label, created_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tx.id, tx.operator_id, tx.provider, tx.strategy, tx.state_hash,
             tx.device_code_enc, tx.code_verifier_enc, tx.redirect_uri, None,
             tx.reconnect_of, tx.status.value, tx.poll_interval, tx.label,
             iso(tx.created_at), iso(tx.expires_at)))
        return tx

    def _row_to_tx(self, row) -> OAuthTransaction:
        return OAuthTransaction(
            id=row["id"], operator_id=row["operator_id"], provider=row["provider"],
            strategy=row["strategy"], status=TransactionStatus(row["status"]),
            created_at=parse_iso(row["created_at"]), expires_at=parse_iso(row["expires_at"]),
            state_hash=row["state_hash"], device_code_enc=row["device_code_enc"],
            code_verifier_enc=row["code_verifier_enc"], redirect_uri=row["redirect_uri"],
            reconnect_of=row["reconnect_of"], connector_id=row["connector_id"],
            failure_code=row["failure_code"], completed_at=parse_iso(row["completed_at"]),
            poll_interval=row["poll_interval"], label=row["label"])

    def get(self, operator_id: str, transaction_id: str) -> Optional[OAuthTransaction]:
        row = self.db.execute(
            "SELECT * FROM oauth_transactions WHERE id = ? AND operator_id = ?",
            (transaction_id, operator_id)).fetchone()
        return self._row_to_tx(row) if row else None

    def find_open(self, operator_id, provider):
        """An operator with an open transaction gets that one back rather than a
        second: POST /authorize is idempotent per operator."""
        row = self.db.execute(
            "SELECT * FROM oauth_transactions WHERE operator_id = ? AND provider = ? "
            "AND status IN ('CREATED','AUTHORIZATION_STARTED') AND expires_at > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (operator_id, provider, iso(utcnow()))).fetchone()
        return self._row_to_tx(row) if row else None

    def transition(self, transaction_id, expected, new, **fields):
        """Guarded transition. Returns True only if THIS call moved the row.

        The WHERE clause carries the expected status, so redemption is
        single-use at the database level: a replay updates zero rows.
        """
        if new not in LEGAL_TRANSITIONS.get(expected, set()):
            raise ValueError("illegal transition %s -> %s" % (expected.value, new.value))
        assignments = ["status = ?"]
        params = [new.value]
        for key, value in fields.items():
            assignments.append("%s = ?" % key)
            params.append(value)
        params.extend([transaction_id, expected.value])
        cursor = self.db.execute(
            "UPDATE oauth_transactions SET %s WHERE id = ? AND status = ?"
            % ", ".join(assignments), params)
        return cursor.rowcount == 1

    def claim(self, transaction_id, expected, new, **fields):
        """transition(), but a failure is an error rather than a False.

        Used where a lost race means a replay attempt, not a benign no-op.
        """
        if not self.transition(transaction_id, expected, new, **fields):
            row = self.db.execute("SELECT status FROM oauth_transactions WHERE id = ?",
                                  (transaction_id,)).fetchone()
            if row is None:
                raise TransactionNotFound(transaction_id)
            raise TransactionAlreadyRedeemed(
                "transaction %s is %s, expected %s" % (transaction_id, row["status"],
                                                       expected.value))

    def destroy_secrets(self, transaction_id):
        """The row survives for audit. Its secrets do not."""
        self.db.execute(
            "UPDATE oauth_transactions SET state_hash = NULL, code_verifier_enc = NULL, "
            "device_code_enc = NULL WHERE id = ?", (transaction_id,))

    def expire_stale(self, now=None):
        cursor = self.db.execute(
            "UPDATE oauth_transactions SET status = 'EXPIRED' "
            "WHERE status IN ('CREATED','AUTHORIZATION_STARTED') AND expires_at <= ?",
            (iso(now or utcnow()),))
        return cursor.rowcount


class EventRepository:
    """Append-only, hash-chained audit."""

    def __init__(self, db):
        self.db = db

    def append(self, operator_id, event_type, result, connector_id=None, agent_id=None,
               session_id=None, resource=None, operation=None, reason_code=None,
               request_id=None, detail=None):
        prev = self.db.execute(
            "SELECT row_hash FROM connector_events ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = prev["row_hash"] if prev else None
        occurred_at = iso(utcnow())
        detail_json = canonical(detail) if detail else None
        payload = canonical({
            "operator_id": operator_id, "connector_id": connector_id, "agent_id": agent_id,
            "session_id": session_id, "event_type": event_type, "resource": resource,
            "operation": operation, "result": result, "reason_code": reason_code,
            "request_id": request_id, "detail_json": detail_json, "occurred_at": occurred_at,
        })
        row_hash = hashlib.sha256(
            ((prev_hash or "") + payload).encode("utf-8")).hexdigest()
        self.db.execute(
            "INSERT INTO connector_events (operator_id, connector_id, agent_id, session_id, "
            " event_type, resource, operation, result, reason_code, request_id, detail_json, "
            " occurred_at, prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (operator_id, connector_id, agent_id, session_id, event_type, resource, operation,
             result, reason_code, request_id, detail_json, occurred_at, prev_hash, row_hash))
        return row_hash

    def list_for_connector(self, connector_id, limit=50):
        return self.db.execute(
            "SELECT * FROM connector_events WHERE connector_id = ? "
            "ORDER BY id DESC LIMIT ?", (connector_id, limit)).fetchall()

    def verify_chain(self) -> bool:
        prev_hash = None
        for row in self.db.execute("SELECT * FROM connector_events ORDER BY id ASC"):
            payload = canonical({
                "operator_id": row["operator_id"], "connector_id": row["connector_id"],
                "agent_id": row["agent_id"], "session_id": row["session_id"],
                "event_type": row["event_type"], "resource": row["resource"],
                "operation": row["operation"], "result": row["result"],
                "reason_code": row["reason_code"], "request_id": row["request_id"],
                "detail_json": row["detail_json"], "occurred_at": row["occurred_at"],
            })
            expected = hashlib.sha256(
                ((prev_hash or "") + payload).encode("utf-8")).hexdigest()
            if row["prev_hash"] != prev_hash or row["row_hash"] != expected:
                return False
            prev_hash = row["row_hash"]
        return True
