"""Authorization strategies.

Two implementations behind one port, chosen per deployment:

  device     local  -- no redirect URI, no client_secret, no callback endpoint,
                       and therefore nothing for a local process to intercept
                       or a URI handler to hijack (design 01 §1.6)
  web_pkce   hosted -- Authorization Code + PKCE S256 against a real
                       confidential client. Not implemented in P1.

Choosing device flow locally is not a workaround. It is the correct flow for a
client that cannot hold a secret, and it deletes an entire attack surface.
"""
from dataclasses import dataclass
from typing import Optional

from ..config import ProviderConfig
from ..github.client import GitHubClient
from ..models import Credential


@dataclass(frozen=True)
class AuthChallenge:
    """What the user must act on. Contains no secret the UI cannot show:
    user_code is meant to be read aloud; device_code never reaches the UI."""
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    #: Server-side only. The service puts this in the keychain, never in the DB
    #: and never in a response body.
    device_code: str

    def public_dict(self):
        return {
            "user_code": self.user_code,
            "verification_uri": self.verification_uri,
            "expires_in": self.expires_in,
            "poll_interval_seconds": self.interval,
        }


class AuthStrategy:
    name = "abstract"

    def begin(self, scope: str = "") -> AuthChallenge:
        raise NotImplementedError

    def complete(self, secret: str) -> Credential:
        raise NotImplementedError

    def refresh(self, credential: Credential) -> Credential:
        raise NotImplementedError


class DeviceFlowStrategy(AuthStrategy):
    name = "device"

    def __init__(self, client: Optional[GitHubClient] = None,
                 config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig()
        self.client = client or GitHubClient(self.config)

    def begin(self, scope: str = "") -> AuthChallenge:
        payload = self.client.request_device_code(scope)
        return AuthChallenge(
            user_code=payload["user_code"],
            verification_uri=payload.get("verification_uri", self.config.verification_url),
            expires_in=int(payload.get("expires_in", 900)),
            interval=int(payload.get("interval", 5)),
            device_code=payload["device_code"],
        )

    def complete(self, secret: str) -> Credential:
        """One poll. Raises AuthorizationPending / SlowDown for the caller to pace."""
        return self.client.poll_for_token(secret)

    def refresh(self, credential: Credential) -> Credential:
        if not credential.refresh_token:
            from ..errors import RefreshExpired
            raise RefreshExpired("credential has no refresh token")
        return self.client.refresh(credential.refresh_token)
