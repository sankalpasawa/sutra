"""Slack Web API client.

Slack's error convention is the thing to get right: it returns **HTTP 200 with
`{"ok": false, "error": "..."}`** for most failures, including invalid_auth and
token_revoked. A client that checks status codes sees success everywhere. Every
response here is judged on `ok`, not on the status line.
"""
import urllib.parse
from typing import Dict, Optional

from ..config import SlackConfig
from ..errors import (
    AuthorizationDenied, ConnectorError, CredentialInvalid, PermissionDenied,
    ProviderUnavailable, RateLimited, RefreshExpired, ValidationFailed,
)
from ..github.http import Transport, UrllibTransport
from ..models import Credential, ProviderIdentity

#: Slack error strings -> our taxonomy. Anything unlisted becomes a generic
#: ConnectorError carrying the provider's own string, so an unknown failure is
#: reported verbatim rather than mislabelled as something we recognise.
_ERRORS = {
    "invalid_auth": CredentialInvalid,
    "not_authed": CredentialInvalid,
    "token_revoked": CredentialInvalid,
    "token_expired": CredentialInvalid,
    "account_inactive": CredentialInvalid,
    "missing_scope": PermissionDenied,
    "not_allowed_token_type": PermissionDenied,
    "no_permission": PermissionDenied,
    "access_denied": AuthorizationDenied,
    "invalid_code": ValidationFailed,
    "bad_redirect_uri": ValidationFailed,
    "invalid_client_id": ValidationFailed,
    "bad_client_secret": ValidationFailed,
    "invalid_refresh_token": RefreshExpired,
    "ratelimited": RateLimited,
    "rate_limited": RateLimited,
    "fatal_error": ProviderUnavailable,
    "service_unavailable": ProviderUnavailable,
}


class SlackClient:
    def __init__(self, config: Optional[SlackConfig] = None,
                 transport: Optional[Transport] = None):
        self.config = config or SlackConfig()
        self.transport = transport or UrllibTransport()

    # ---------------------------------------------------------------- #
    def _post_form(self, url, fields, token=None):
        body = urllib.parse.urlencode(
            {k: v for k, v in fields.items() if v is not None}).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                   "Accept": "application/json",
                   "User-Agent": self.config.user_agent}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        try:
            return self.transport.request("POST", url, headers, body)
        except ConnectionError as exc:
            raise ProviderUnavailable(str(exc))

    @staticmethod
    def _judge(payload: Dict, where: str):
        """Slack signals failure in the BODY, not the status line."""
        if payload.get("ok"):
            return payload
        code = payload.get("error") or "unknown_error"
        exc = _ERRORS.get(code, ConnectorError)
        detail = {"provider_error": code, "where": where}
        if payload.get("needed"):
            detail["needed_scope"] = payload["needed"]
        if payload.get("provided"):
            detail["provided_scope"] = payload["provided"]
        raise exc("slack: %s" % code, **detail)

    # ---------------------------------------------------------------- #
    # authorization
    # ---------------------------------------------------------------- #
    def authorize_url(self, state: str, bot_scopes, user_scopes) -> str:
        """Slack takes bot scopes in `scope` and user scopes in `user_scope`.

        Both are sent because one authorization yields both tokens. `state` is
        the ONLY binding between this request and the code that comes back --
        Slack offers no PKCE.
        """
        params = {
            "client_id": self.config.client_id,
            "scope": ",".join(bot_scopes),
            "user_scope": ",".join(user_scopes),
            "redirect_uri": self.config.redirect_uri,
            "state": state,
        }
        return "%s?%s" % (self.config.authorize_url, urllib.parse.urlencode(params))

    def exchange_code(self, code: str) -> Dict:
        """Returns {bot: Credential|None, user: Credential|None, team, ids}.

        A client_secret is required; Slack has no public-client mode. It comes
        from ~/.sutra/provider-secrets.env and never from the repo.
        """
        if not self.config.client_secret:
            raise ValidationFailed(
                "no Slack client secret configured. Put it in "
                "~/.sutra/provider-secrets.env as SUTRA_SLACK_CLIENT_SECRET "
                "(mode 600).")
        payload = self._post_form(self.config.access_token_url, {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "redirect_uri": self.config.redirect_uri,
        }).json()
        self._judge(payload, "oauth.v2.access")
        return self._unpack(payload)

    @staticmethod
    def _unpack(payload: Dict) -> Dict:
        bot = None
        if payload.get("access_token"):
            bot = Credential.from_token_response({
                "access_token": payload["access_token"],
                "refresh_token": payload.get("refresh_token"),
                "expires_in": payload.get("expires_in"),
                "token_type": payload.get("token_type", "bot"),
            })
        authed = payload.get("authed_user") or {}
        user = None
        if authed.get("access_token"):
            user = Credential.from_token_response({
                "access_token": authed["access_token"],
                "refresh_token": authed.get("refresh_token"),
                "expires_in": authed.get("expires_in"),
                "token_type": authed.get("token_type", "user"),
            })
        team = payload.get("team") or {}
        return {
            "bot": bot, "user": user,
            "team_id": team.get("id"), "team_name": team.get("name"),
            "authed_user_id": authed.get("id"),
            "bot_user_id": payload.get("bot_user_id"),
            "bot_scopes": (payload.get("scope") or "").split(",") if payload.get("scope") else [],
            "user_scopes": (authed.get("scope") or "").split(",") if authed.get("scope") else [],
            #: Absent expires_in means the workspace/app did not apply token
            #: rotation. Recorded rather than assumed, because "the token never
            #: expires" is a materially different risk posture.
            "rotation_enabled": bool(payload.get("expires_in") or authed.get("expires_in")),
        }

    def refresh(self, refresh_token: str) -> Dict:
        if not self.config.client_secret:
            raise ValidationFailed("no Slack client secret configured")
        payload = self._post_form(self.config.access_token_url, {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }).json()
        self._judge(payload, "oauth.v2.access:refresh")
        return self._unpack(payload)

    # ---------------------------------------------------------------- #
    # identity
    # ---------------------------------------------------------------- #
    def auth_test(self, token: str) -> Dict:
        payload = self._post_form(self.config.api_base + "/auth.test", {},
                                  token=token).json()
        return self._judge(payload, "auth.test")

    def identity(self, user_token: str, exchanged: Dict) -> ProviderIdentity:
        """Identity is the SLACK USER, keyed on team_id + user_id.

        A Slack user id is only unique within a workspace, so the same person in
        two workspaces is two connectors -- correctly, because the grants differ.
        Keying on user id alone would collide across workspaces.
        """
        info = self.auth_test(user_token)
        team_id = info.get("team_id") or exchanged.get("team_id") or ""
        user_id = info.get("user_id") or ""
        return ProviderIdentity(
            account_id="%s:%s" % (team_id, user_id),
            username=info.get("user") or "",
            display_name=info.get("team") or exchanged.get("team_name"),
            node_id=team_id,
            account_type="user",
        )
