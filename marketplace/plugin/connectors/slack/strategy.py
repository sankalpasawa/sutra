"""Slack loopback authorization strategy.

Fits the same begin() -> poll() contract as GitHub's device flow, so
ConnectorService needs no provider branch: begin() returns a URL to open
instead of a code to read, and poll() asks the local listener instead of the
provider.

WHAT `state` IS DOING HERE

With GitHub's device flow there is no redirect and nothing to intercept. Here a
browser hands an authorization code to a port on this machine, and Slack offers
no PKCE -- so `state` is the ONLY value binding the code that comes back to the
request we made. It is 256-bit, single-use, hashed at rest by the transaction
store, and compared with hmac.compare_digest rather than `==`.

Comparing with `==` would leak the value one byte at a time to a caller who can
retry, which on a loopback port is any process running as this user.
"""
import hmac
import secrets
import threading
import webbrowser
from typing import Dict, Optional

from ..config import SlackConfig
from ..errors import AuthorizationDenied, AuthorizationPending, ConnectorError, ValidationFailed
from ..oauth.loopback import LoopbackCatcher, LoopbackError
from ..oauth.strategies import AuthChallenge, AuthResult, AuthStrategy
from .client import SlackClient

#: Bot scopes: Sutra's own identity. Writing lives here so an agent's actions
#: are attributable to Sutra rather than to a person.
BOT_SCOPES = ("chat:write", "channels:read", "channels:history",
              "groups:history", "users:read")

#: User scopes: reach. A bot only ever sees conversations it was added to, so
#: reading and search have to be user-scoped. Deliberately no chat:write here.
USER_SCOPES = ("channels:read", "channels:history", "groups:read", "groups:history",
               "im:read", "im:history", "mpim:read", "mpim:history",
               "search:read", "users:read")


class SlackLoopbackStrategy(AuthStrategy):
    name = "loopback"

    def __init__(self, client: Optional[SlackClient] = None,
                 config: Optional[SlackConfig] = None,
                 open_browser: bool = True):
        self.config = config or SlackConfig()
        self.client = client or SlackClient(self.config)
        self.open_browser = open_browser
        #: state -> catcher. In-process: the listener lives in this process and
        #: dies with it, so a restart mid-flow correctly loses the flow rather
        #: than leaving a stray port open.
        self._pending: Dict[str, LoopbackCatcher] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def begin(self, scope: str = "") -> AuthChallenge:
        state = secrets.token_urlsafe(32)

        # Bind BEFORE the browser opens. If the port is taken we fail here,
        # with nothing sent anywhere -- rather than opening a browser that
        # will deliver a code to whoever holds the port.
        catcher = LoopbackCatcher(self.config.redirect_port,
                                  self.config.redirect_path, timeout=600).start()
        with self._lock:
            self._pending[state] = catcher

        url = self.client.authorize_url(state, BOT_SCOPES, USER_SCOPES)
        if self.open_browser:
            webbrowser.open(url)
        return AuthChallenge(mode="redirect", handle=state,
                             authorize_url=url, expires_in=600, interval=2)

    # ------------------------------------------------------------------ #
    def poll(self, handle: str):
        """Non-blocking. AuthorizationPending until the browser comes back."""
        with self._lock:
            catcher = self._pending.get(handle)
        if catcher is None:
            raise ValidationFailed(
                "no authorization in flight for this transaction; restart the "
                "connection (the listener does not survive an app restart)")

        if not catcher._server.done.is_set():
            raise AuthorizationPending("waiting for the browser callback")

        captured = dict(catcher._server.captured)
        self._discard(handle)

        if captured.get("error"):
            if captured["error"] in ("access_denied", "user_denied"):
                raise AuthorizationDenied("you declined the authorization")
            raise ValidationFailed("callback failed: %s" % captured["error"])

        returned_state = captured.get("state") or ""
        # Timing-safe: on a loopback port the caller can retry, and == leaks
        # the value a byte at a time.
        if not hmac.compare_digest(returned_state, handle):
            raise ValidationFailed(
                "state mismatch: the callback did not correspond to this "
                "authorization request")

        exchanged = self.client.exchange_code(captured["code"])
        bot, user = exchanged.get("bot"), exchanged.get("user")
        if not bot and not user:
            raise ConnectorError("slack returned no usable token")

        # Bot in the default slot: it is the app's own identity and the token
        # every WRITE goes through, so the common path does not need the
        # broader user token in hand.
        primary = bot or user
        extra = {"user": user} if (user and bot) else {}
        return AuthResult(primary=primary, extra=extra, meta={
            k: exchanged[k] for k in
            ("team_id", "team_name", "authed_user_id", "bot_user_id",
             "bot_scopes", "user_scopes", "rotation_enabled")
            if k in exchanged})

    def identity(self, result: AuthResult):
        """auth.test with the USER token where we have one.

        The bot token would answer with the BOT's identity, which is Sutra --
        not the person who connected. A connector must be keyed to the human.
        """
        user = result.extra.get("user") or result.primary
        return self.client.identity(user.access_token, result.meta)

    def can_resume(self, handle: str) -> bool:
        """Only while this process still holds the listener for that state."""
        with self._lock:
            return handle in self._pending

    def cancel(self, handle: str):
        self._discard(handle)

    def close_all(self):
        """Release every in-flight listener.

        Called on shutdown. Without it an abandoned connect attempt keeps a
        loopback port bound for the rest of its timeout, and the next attempt
        cannot bind the port its registered redirect URI names.
        """
        with self._lock:
            catchers = list(self._pending.values())
            self._pending.clear()
        for catcher in catchers:
            catcher.close()

    def _discard(self, handle: str):
        with self._lock:
            catcher = self._pending.pop(handle, None)
        if catcher is not None:
            catcher.close()

    # ------------------------------------------------------------------ #
    def refresh(self, credential):
        if not credential.refresh_token:
            from ..errors import RefreshExpired
            raise RefreshExpired(
                "this Slack token has no refresh token: the app was installed "
                "without token rotation, so the credential does not expire and "
                "cannot be rotated")
        return self.client.refresh(credential.refresh_token)
