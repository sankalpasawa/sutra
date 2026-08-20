"""GitHub API client.

Two rules that are easy to get wrong and expensive to get wrong:

  1. Follow `Link: rel="next"`. Never construct `?page=n` -- constructed page
     numbers skip and duplicate entries when the set changes mid-walk.
  2. Pin X-GitHub-Api-Version. An unpinned client inherits GitHub's behaviour
     changes on GitHub's schedule, in production, with no deploy of ours to
     correlate against.

The device-flow calls deliberately send NO client_secret. That is not an
omission -- verified fact F3 says the device flow needs none, and F4 says
device-flow refresh needs none either. A test asserts the secret is never
transmitted, so a future refactor cannot quietly reintroduce it.
"""
import urllib.parse
from typing import Dict, Optional

from ..config import (
    DEVICE_GRANT_TYPE, GITHUB_API_VERSION, ProviderConfig, REFRESH_GRANT_TYPE,
)
from ..errors import (
    AuthorizationDenied, AuthorizationPending, ConnectorError, CredentialInvalid,
    DeviceFlowDisabled, NotFoundOrForbidden, PermissionDenied, ProviderUnavailable,
    RateLimited, RefreshExpired, SecondaryRateLimited, SlowDown, SSORequired,
    TransactionExpired, ValidationFailed,
)
from ..models import Credential, ProviderIdentity
from .http import HttpResponse, Transport, UrllibTransport

#: GitHub device-flow error codes -> our taxonomy. Verified from the device flow
#: documentation, not inferred.
_DEVICE_ERRORS = {
    "authorization_pending": AuthorizationPending,
    "slow_down": SlowDown,
    "expired_token": TransactionExpired,
    "access_denied": AuthorizationDenied,
    "incorrect_device_code": ValidationFailed,
    "device_flow_disabled": DeviceFlowDisabled,
    "incorrect_client_credentials": ValidationFailed,
    "bad_verification_code": ValidationFailed,
    "bad_refresh_token": RefreshExpired,
}


class GitHubClient:
    def __init__(self, config: Optional[ProviderConfig] = None,
                 transport: Optional[Transport] = None):
        self.config = config or ProviderConfig()
        self.transport = transport or UrllibTransport()

    # ---------------------------------------------------------------- #
    # low level
    # ---------------------------------------------------------------- #
    def _post_form(self, url, fields) -> HttpResponse:
        body = urllib.parse.urlencode(fields).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.config.user_agent,
        }
        try:
            return self.transport.request("POST", url, headers, body)
        except ConnectionError as exc:
            raise ProviderUnavailable(str(exc))

    def _api_get(self, path, token) -> HttpResponse:
        url = path if path.startswith("http") else self.config.api_base + path
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "Authorization": "Bearer %s" % token,
            "User-Agent": self.config.user_agent,
        }
        try:
            response = self.transport.request("GET", url, headers)
        except ConnectionError as exc:
            raise ProviderUnavailable(str(exc))
        self.classify(response)
        return response

    @staticmethod
    def classify(response: HttpResponse):
        """Map a REST response to the taxonomy. Design 03 §3.2.

        The 403 branch is the one that matters: FOUR different conditions share
        that status and only two are retryable. Retrying a permission 403 is
        how an App gets flagged for abuse.
        """
        status = response.status
        if status < 400:
            return
        if status == 401:
            raise CredentialInvalid(response.json().get("message", "bad credentials"))
        if status in (403, 429):
            if "retry-after" in response.headers:
                raise SecondaryRateLimited(
                    "secondary rate limit",
                    retry_after=response.header_int("retry-after", 60))
            if response.header_int("x-ratelimit-remaining", None) == 0:
                raise RateLimited("primary rate limit",
                                  reset_at=response.header_int("x-ratelimit-reset"))
            if "x-github-sso" in response.headers:
                raise SSORequired("organization requires SAML sign-in",
                                  sso=response.headers["x-github-sso"])
            raise PermissionDenied(response.json().get("message", "forbidden"))
        if status == 404:
            # Usually permission, not absence: GitHub returns 404 for private
            # resources you cannot see.
            raise NotFoundOrForbidden("not found or not accessible")
        if status == 422:
            raise ValidationFailed(response.json().get("message", "validation failed"),
                                   errors=response.json().get("errors"))
        if status >= 500:
            raise ProviderUnavailable("github returned %d" % status)
        raise ConnectorError("github returned %d" % status)

    @staticmethod
    def _raise_oauth_error(payload):
        code = payload.get("error")
        if not code:
            return
        exc_class = _DEVICE_ERRORS.get(code, ConnectorError)
        raise exc_class(payload.get("error_description") or code,
                        provider_error=code,
                        error_uri=payload.get("error_uri"))

    # ---------------------------------------------------------------- #
    # device flow
    # ---------------------------------------------------------------- #
    def request_device_code(self, scope: str = "") -> Dict:
        fields = {"client_id": self.config.client_id}
        if scope:
            fields["scope"] = scope
        response = self._post_form(self.config.device_code_url, fields)
        payload = response.json()
        self._raise_oauth_error(payload)
        if response.status >= 400 or "device_code" not in payload:
            raise ProviderUnavailable("device code request failed",
                                      status=response.status)
        return payload

    def poll_for_token(self, device_code: str) -> Credential:
        """One poll. Raises AuthorizationPending/SlowDown for the caller to pace.

        GitHub returns HTTP 200 with an `error` field for the pending states, so
        the body must be inspected -- a status-only check would read
        `authorization_pending` as success.
        """
        response = self._post_form(self.config.access_token_url, {
            "client_id": self.config.client_id,
            "device_code": device_code,
            "grant_type": DEVICE_GRANT_TYPE,
        })
        payload = response.json()
        self._raise_oauth_error(payload)
        if "access_token" not in payload:
            raise ProviderUnavailable("token response had no access_token",
                                      status=response.status)
        return Credential.from_token_response(payload)

    def refresh(self, refresh_token: str) -> Credential:
        """No client_secret. Verified fact F4: refresh requires one UNLESS the
        token was generated by the device flow."""
        response = self._post_form(self.config.access_token_url, {
            "client_id": self.config.client_id,
            "grant_type": REFRESH_GRANT_TYPE,
            "refresh_token": refresh_token,
        })
        payload = response.json()
        self._raise_oauth_error(payload)
        if "access_token" not in payload:
            raise RefreshExpired("refresh did not return an access token")
        return Credential.from_token_response(payload)

    # ---------------------------------------------------------------- #
    # identity
    # ---------------------------------------------------------------- #
    def get_user(self, token: str) -> ProviderIdentity:
        payload = self._api_get("/user", token).json()
        if "id" not in payload:
            raise ProviderUnavailable("/user returned no id")
        return ProviderIdentity(
            account_id=str(payload["id"]),          # numeric, immutable, the identity
            username=payload.get("login", ""),      # mutable, display only
            node_id=payload.get("node_id"),
            display_name=payload.get("name"),
            avatar_url=payload.get("avatar_url"),
            account_type=(payload.get("type") or "User").lower(),
        )
