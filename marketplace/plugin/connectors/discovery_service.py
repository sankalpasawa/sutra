"""Discovery (P2): installations, repositories, organizations.

Mixed into ConnectorService. Everything here reads; nothing mutates GitHub.
"""
from datetime import timedelta

from .database.repositories import canonical
from .errors import TransactionNotFound
from .models import StatusReason, iso, utcnow


class DiscoveryMixin:
    """Repository, organization and installation discovery.

    Split from the lifecycle so neither file has to be read to understand the
    other. ConnectorService inherits both.
    """

    #: Cache TTLs, design 07 §7.2. Deliberately short: a stale repository list
    #: is a confusing UI, and these calls are cheap against a 5,000/hr budget.
    TTL_INSTALLATIONS = 900
    TTL_REPOSITORIES = 600
    TTL_ORGANIZATIONS = 900

    _CURSOR_SECRET_KEY = "cursor-hmac"
    #: Marker row recording that we asked GitHub and it answered -- including
    #: when the answer was "none". Without it, `not installations` is true on
    #: every request for an authorized-but-not-installed connector, so the
    #: cache is defeated exactly when there is nothing to cache and every page
    #: view costs a live GitHub round-trip (~0.85s, and rate-limit budget).
    _SYNC_MARKER = "installations_sync"

    def _cursor_secret(self) -> bytes:
        """Per-install HMAC key, minted once and kept where credentials are kept.

        In the database it would be readable by anything that can read the
        database, which is the population a signed cursor is meant to constrain.
        """
        import base64
        import os as _os
        from .credentials.store import CredentialNotFound
        try:
            return base64.b64decode(self.credentials.get_secret(self._CURSOR_SECRET_KEY))
        except CredentialNotFound:
            secret = _os.urandom(32)
            self.credentials.put_secret(self._CURSOR_SECRET_KEY,
                                        base64.b64encode(secret).decode("ascii"))
            return secret

    # ------------------------------------------------------------------ #
    def sync_installations(self, operator_id, connector_id):
        from .github.discovery import Discovery
        credential = self.credential_for(operator_id, connector_id)
        installations = Discovery(self.client).list_installations(credential.access_token)

        now = iso(utcnow())
        known = set()
        for installation in installations:
            known.add(installation.installation_id)
            self.db.execute(
                "INSERT INTO connector_installations (connector_id, installation_id, "
                " account_login, account_id, account_type, repository_selection, "
                " permissions_json, suspended_at, sso_required, synced_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(connector_id, installation_id) DO UPDATE SET "
                " account_login=excluded.account_login, "
                " repository_selection=excluded.repository_selection, "
                " permissions_json=excluded.permissions_json, "
                " suspended_at=excluded.suspended_at, synced_at=excluded.synced_at",
                (connector_id, installation.installation_id, installation.account_login,
                 installation.account_id, installation.account_type,
                 installation.repository_selection,
                 canonical(installation.permissions),
                 now if installation.suspended else None,
                 1 if installation.sso_required else 0, now))

        # An installation that vanished means the app was uninstalled there.
        # Without webhooks (hosted-only) this sync is the only way we learn.
        rows = self.db.execute(
            "SELECT installation_id FROM connector_installations WHERE connector_id = ?",
            (connector_id,)).fetchall()
        removed = [r["installation_id"] for r in rows if r["installation_id"] not in known]
        self._mark_synced(connector_id, len(installations))
        for installation_id in removed:
            self.db.execute(
                "DELETE FROM connector_installations WHERE connector_id = ? "
                "AND installation_id = ?", (connector_id, installation_id))
        if removed:
            self.events.append(operator_id, "CONNECTOR_STATE_CHANGED", "SUCCESS",
                               connector_id=connector_id,
                               reason_code=StatusReason.ORG_ACCESS_REMOVED.value,
                               detail={"removed_installations": removed})
        return installations

    def _sync_is_fresh(self, connector_id) -> bool:
        row = self.db.execute(
            "SELECT expires_at FROM connector_metadata WHERE connector_id = ? "
            "AND kind = ? AND external_id = 'self'",
            (connector_id, self._SYNC_MARKER)).fetchone()
        return bool(row and row["expires_at"] > iso(utcnow()))

    def _mark_synced(self, connector_id, count):
        now = utcnow()
        self.db.execute(
            "INSERT INTO connector_metadata (connector_id, kind, external_id, "
            " payload_json, fetched_at, expires_at) VALUES (?,?,'self',?,?,?) "
            "ON CONFLICT(connector_id, kind, external_id) DO UPDATE SET "
            " payload_json=excluded.payload_json, fetched_at=excluded.fetched_at, "
            " expires_at=excluded.expires_at",
            (connector_id, self._SYNC_MARKER, canonical({"count": count}),
             iso(now), iso(now + timedelta(seconds=self.TTL_INSTALLATIONS))))

    def _installations_for(self, operator_id, connector_id, refresh):
        """Cached installations, re-syncing only when stale or forced.

        The freshness marker is what distinguishes "we have not asked" from
        "we asked and the answer was none" -- two states that look identical
        in an empty list and have very different costs.
        """
        if not refresh and self._sync_is_fresh(connector_id):
            return self.cached_installations(connector_id)
        installations = self.sync_installations(operator_id, connector_id)
        return installations

    def cached_installations(self, connector_id):
        from .models import Installation
        rows = self.db.execute(
            "SELECT * FROM connector_installations WHERE connector_id = ?",
            (connector_id,)).fetchall()
        import json as _json
        return [Installation(
            installation_id=r["installation_id"], account_login=r["account_login"],
            account_id=r["account_id"], account_type=r["account_type"],
            repository_selection=r["repository_selection"],
            permissions=_json.loads(r["permissions_json"]),
            suspended=bool(r["suspended_at"]), sso_required=bool(r["sso_required"]),
        ) for r in rows]

    # ------------------------------------------------------------------ #
    def list_repositories(self, operator_id, connector_id, installation_id=None,
                          cursor=None, refresh=False, page_limit=1):
        from .github.discovery import Discovery
        from .github.pagination import decode_cursor, encode_cursor

        connector = self.connectors.get(operator_id, connector_id, self.config.provider)
        if connector is None:
            raise TransactionNotFound(connector_id)

        # Validate the cursor FIRST. The not-installed early return below used
        # to short-circuit before this, so a forged cursor got a cheerful 200
        # instead of a rejection -- harmless, since it was never dereferenced,
        # but a client cannot tell a bad cursor from an empty result.
        secret = self._cursor_secret()
        start_url = None
        if cursor:
            start_url = decode_cursor(secret, connector_id, cursor, connector.api_base)

        installations = self._installations_for(operator_id, connector_id, refresh)
        if installation_id is not None:
            installations = [i for i in installations
                             if i.installation_id == int(installation_id)]

        if not installations:
            # Authorised but not installed. Say which, and offer the fix.
            return {"repositories": [], "next_cursor": None,
                    "empty_reason": "NOT_INSTALLED",
                    "user_action": "INSTALL_APP",
                    "install_url": "https://github.com/settings/installations"}

        credential = self.credential_for(operator_id, connector_id)
        discovery = Discovery(self.client)

        repositories, next_url, access = [], None, "ok"
        for installation in installations:
            found, next_url, access = discovery.list_repositories(
                credential.access_token, installation, start_url, page_limit)
            repositories.extend(found)
            if access == "sso_required":
                self.db.execute(
                    "UPDATE connector_installations SET sso_required = 1 "
                    "WHERE connector_id = ? AND installation_id = ?",
                    (connector_id, installation.installation_id))
            if start_url:          # a cursor resumes exactly one installation
                break

        self._cache_repositories(connector_id, repositories)
        self.events.append(operator_id, "REPOSITORY_ACCESSED", "SUCCESS",
                           connector_id=connector_id,
                           detail={"count": len(repositories)})
        return {
            "repositories": [r.public_dict() for r in repositories],
            "next_cursor": (encode_cursor(secret, connector_id, next_url)
                            if next_url else None),
            "empty_reason": None if repositories else "NO_REPOSITORIES_SELECTED",
            "user_action": None if repositories else "ADD_REPOSITORY",
        }

    def _cache_repositories(self, connector_id, repositories):
        now = utcnow()
        expires = iso(now + timedelta(seconds=self.TTL_REPOSITORIES))
        for repository in repositories:
            self.db.execute(
                "INSERT INTO connector_metadata (connector_id, kind, external_id, "
                " payload_json, fetched_at, expires_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(connector_id, kind, external_id) DO UPDATE SET "
                " payload_json=excluded.payload_json, fetched_at=excluded.fetched_at, "
                " expires_at=excluded.expires_at",
                (connector_id, "repository", repository.repo_id,
                 canonical(repository.public_dict()), iso(now), expires))

    # ------------------------------------------------------------------ #
    def list_organizations(self, operator_id, connector_id, refresh=False):
        from .github.discovery import Discovery
        connector = self.connectors.get(operator_id, connector_id, self.config.provider)
        if connector is None:
            raise TransactionNotFound(connector_id)

        installations = self._installations_for(operator_id, connector_id, refresh)

        credential = self.credential_for(operator_id, connector_id)
        organizations = Discovery(self.client).list_organizations(
            credential.access_token, installations)
        personal = [i for i in installations if i.account_type != "Organization"]
        return {
            "organizations": [o.public_dict() for o in organizations],
            "personal_installation": personal[0].public_dict() if personal else None,
        }
