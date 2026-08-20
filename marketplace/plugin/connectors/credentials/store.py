"""The CredentialStore port.

One interface, three adapters: Keychain (macOS, today), Memory (tests), and
KMS-envelope over Postgres (hosted, later). Nothing above this port knows which
is in use -- that is what makes the local->hosted move an adapter swap.

There is deliberately no export(), dump(), or list_all() method. A credential
export path is the most dangerous code this module could contain, so it does
not exist; the local->hosted migration is a re-auth event (ADR-034).
"""
import json
from typing import Dict, Optional

from ..models import Credential


class CredentialNotFound(KeyError):
    pass


class CredentialStore:
    """Protocol.

    Adapters implement the three raw-secret methods; the Credential API is
    built on top of them here, so an adapter cannot get the serialisation
    subtly different from another adapter's.

    Raw secrets exist because a device_code is also credential material: it is
    redeemable for a token by anyone holding it, and the client id it pairs
    with is public. Keeping it in the database would put a redeemable secret in
    the one store the design promises holds none.
    """

    # -- raw secrets: what adapters implement ----------------------------
    def put_secret(self, key: str, secret: str) -> None:
        raise NotImplementedError

    def get_secret(self, key: str) -> str:
        raise NotImplementedError

    def delete_secret(self, key: str) -> None:
        """Irreversible. Must succeed even when the key is absent."""
        raise NotImplementedError

    # -- credentials: built on the above ---------------------------------
    @staticmethod
    def _credential_key(connector_id: str) -> str:
        return "cred:%s" % connector_id

    def save(self, connector_id: str, credential: Credential) -> None:
        self.put_secret(self._credential_key(connector_id),
                        json.dumps(credential.to_secret_json(), separators=(",", ":")))

    def get(self, connector_id: str) -> Credential:
        raw = self.get_secret(self._credential_key(connector_id))
        return Credential.from_secret_json(json.loads(raw))

    def delete(self, connector_id: str) -> None:
        self.delete_secret(self._credential_key(connector_id))

    def rotate(self, connector_id: str, credential: Credential) -> None:
        """Replace in place. The previous material must not survive."""
        self.save(connector_id, credential)


class MemoryCredentialStore(CredentialStore):
    """Test adapter. Never used in a running app -- an in-process dict is not
    a credential store, and a test that passes against it proves the interface,
    not the storage."""

    def __init__(self):
        self._items: Dict[str, str] = {}

    def put_secret(self, key, secret):
        self._items[key] = secret

    def get_secret(self, key):
        try:
            return self._items[key]
        except KeyError:
            raise CredentialNotFound(key)

    def delete_secret(self, key):
        self._items.pop(key, None)

    def __len__(self):
        return len(self._items)
