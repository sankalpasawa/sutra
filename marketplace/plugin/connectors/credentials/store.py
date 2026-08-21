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
    #: A connection can hold more than one credential. Slack issues a BOT token
    #: and a USER token from a single authorization, and they have different
    #: reach and different attribution -- storing them in one slot would force
    #: a choice between them at write time.
    DEFAULT_SLOT = "default"

    @classmethod
    def _credential_key(cls, connector_id: str, slot: str = DEFAULT_SLOT) -> str:
        return ("cred:%s" % connector_id if slot == cls.DEFAULT_SLOT
                else "cred:%s:%s" % (connector_id, slot))

    def save(self, connector_id: str, credential: Credential,
             slot: str = DEFAULT_SLOT) -> None:
        self.put_secret(self._credential_key(connector_id, slot),
                        json.dumps(credential.to_secret_json(), separators=(",", ":")))

    def get(self, connector_id: str, slot: str = DEFAULT_SLOT) -> Credential:
        raw = self.get_secret(self._credential_key(connector_id, slot))
        return Credential.from_secret_json(json.loads(raw))

    def delete(self, connector_id: str, slot: str = DEFAULT_SLOT) -> None:
        self.delete_secret(self._credential_key(connector_id, slot))

    def delete_all(self, connector_id: str, slots=()) -> None:
        """Disconnect must destroy EVERY credential a connection holds, not
        just the default one. A forgotten slot is a live token after the user
        was told the connector was gone."""
        self.delete(connector_id)
        for slot in slots:
            self.delete(connector_id, slot)

    def rotate(self, connector_id: str, credential: Credential,
               slot: str = DEFAULT_SLOT) -> None:
        """Replace in place. The previous material must not survive."""
        self.save(connector_id, credential, slot)


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
