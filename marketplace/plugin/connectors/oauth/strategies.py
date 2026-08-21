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
from dataclasses import dataclass, field
from typing import Optional

from ..config import ProviderConfig
from ..github.client import GitHubClient
from ..models import Credential


@dataclass
class AuthResult:
    """What a completed authorization yields.

    Not just a Credential, because a provider may issue more than one from a
    single authorization: Slack returns a BOT token and a USER token with
    different reach and different attribution. `primary` goes in the default
    credential slot; `extra` maps slot name -> Credential for the rest.

    `meta` carries provider details the service persists but does not interpret
    (team id, granted scopes, whether rotation was actually applied).
    """
    primary: "Credential"
    extra: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AuthChallenge:
    """What the user must act on.

    Two shapes, one type, so ConnectorService does not branch on provider:

      mode="device"    the user reads `user_code` and types it at
                       `verification_uri`. GitHub.
      mode="redirect"  the user's browser is sent to `authorize_url` and the
                       provider redirects back to a loopback listener. Slack,
                       and Google later.

    `handle` is the server-side secret the service stores and hands back to
    poll(): a device_code for device flow, a state value for redirect flow.
    It never reaches a response body.
    """
    mode: str = "device"
    handle: str = ""
    expires_in: int = 900
    interval: int = 5
    # device
    user_code: Optional[str] = None
    verification_uri: Optional[str] = None
    # redirect
    authorize_url: Optional[str] = None

    def public_dict(self, include_url: bool = False):
        """The redirect flow's authorize URL is WITHHELD by default.

        The URL necessarily contains `state`, and for a provider with no PKCE
        `state` is the only value binding the returned code to our request. Any
        local process that can read an API response would otherwise learn it
        and could present a state that validates.

        The browser is opened by the service, so the happy path never needs the
        URL to cross the API boundary. `include_url` exists for the fallback
        where the browser did not open and the user must click a link -- an
        explicit, user-initiated widening rather than the default.
        """
        out = {"mode": self.mode,
               "expires_in": self.expires_in,
               "poll_interval_seconds": self.interval}
        if self.mode == "device":
            # A user_code is MEANT to be read aloud; it is useless without the
            # matching device_code, which never leaves the keychain.
            out["user_code"] = self.user_code
            out["verification_uri"] = self.verification_uri
        else:
            out["browser_opened"] = True
            if include_url:
                out["authorize_url"] = self.authorize_url
        return out


class AuthStrategy:
    name = "abstract"

    def begin(self, scope: str = "") -> AuthChallenge:
        raise NotImplementedError

    def poll(self, handle: str):
        """One non-blocking check. Raises AuthorizationPending until done.

        Device flow asks the provider; redirect flow asks the local listener.
        The service cannot tell the difference, which is the point.
        """
        raise NotImplementedError

    #: Back-compat alias; device flow's original name.
    def complete(self, secret: str) -> Credential:
        return self.poll(secret)

    def identity(self, result: "AuthResult"):
        """Resolve the provider account this authorization belongs to.

        Lives on the strategy because it is irreducibly provider-specific:
        GitHub asks GET /user, Slack asks auth.test with the USER token and
        keys on team+user. Putting it here is what lets ConnectorService
        complete a connection without knowing which provider it is talking to.
        """
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
            mode="device",
            handle=payload["device_code"],
            user_code=payload["user_code"],
            verification_uri=payload.get("verification_uri", self.config.verification_url),
            expires_in=int(payload.get("expires_in", 900)),
            interval=int(payload.get("interval", 5)),
        )

    def poll(self, handle: str) -> "AuthResult":
        """One poll. Raises AuthorizationPending / SlowDown for the caller to pace."""
        return AuthResult(primary=self.client.poll_for_token(handle))

    def identity(self, result: "AuthResult"):
        return self.client.get_user(result.primary.access_token)

    def refresh(self, credential: Credential) -> Credential:
        if not credential.refresh_token:
            from ..errors import RefreshExpired
            raise RefreshExpired("credential has no refresh token")
        return self.client.refresh(credential.refresh_token)
