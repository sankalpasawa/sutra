"""LiveClient: the Gmail API through google-api-python-client, with a service account and domain-wide delegation.

Google modules are imported only when a LiveClient is built with the default builders (pipeline step 7), never
at module import, so mock mode and the tests stay stdlib-only (FR-5, FR-6). The only scope is gmail.readonly
(FR-7). Retries are done by gmail_client.with_retry, so every request runs with num_retries=0.
Untested against real Google until the live checklist (plan.md L-1..L-11).
"""
from pathlib import Path

import errors
import policy
from errors import HistoryExpired, MessageGone, PulseError
from gmail_client import METADATA_HEADERS

SCOPES = [errors.SCOPE]


def _import_google():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise PulseError("deps_missing",
                         "Live mode needs the Google libraries. In a virtual env run: "
                         "pip install -r prototypes/pulse/requirements.txt") from None
    return service_account, build


def default_creds_builder(key_path, scopes, subject):
    service_account, _build = _import_google()
    creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=scopes)
    return creds.with_subject(subject)


def default_service_builder(creds):
    _sa, build = _import_google()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _is(exc, class_name: str) -> bool:
    # Matched by name so the real google-auth / googleapiclient classes and test stubs are handled alike.
    return any(c.__name__ == class_name for c in type(exc).__mro__)


# Network failures, matched by class name in the MRO: google.auth.exceptions.TransportError (token refresh),
# httplib2.HttpLib2Error (API calls). socket errors, timeouts and requests' errors are all OSError subclasses.
_NETWORK_CLASSES = ("TransportError", "HttpLib2Error")


def _is_network(exc) -> bool:
    return isinstance(exc, OSError) or any(_is(exc, n) for n in _NETWORK_CLASSES)


def _http_reason(exc) -> str:
    reason = getattr(exc, "reason", "") or ""
    details = getattr(exc, "error_details", None)
    if isinstance(details, list) and details and isinstance(details[0], dict):
        reason = details[0].get("reason") or reason
    return str(reason)


class LiveClient:
    def __init__(self, mailbox: str, key_path: Path, creds_builder=None, service_builder=None):
        if creds_builder is None or service_builder is None:
            _import_google()  # step 7: deps_missing before anything else happens
        self.mailbox = mailbox
        try:
            creds = (creds_builder or default_creds_builder)(key_path, list(SCOPES), mailbox)
        except ValueError:
            # google-auth raises ValueError for missing fields or a PEM it cannot parse; its text may quote the
            # key, so it is dropped (FR-33, R1-6).
            raise policy.key_unreadable(key_path) from None
        self.service = (service_builder or default_service_builder)(creds)

    def _exec(self, request, method: str):
        try:
            return request.execute(num_retries=0)
        except Exception as e:
            if _is_network(e):
                raise errors.TransientError(0, kind="network") from None
            if _is(e, "RefreshError"):
                raise errors.map_refresh_error(str(e), bool(getattr(e, "retryable", False))) from None
            if _is(e, "HttpError"):
                status = int(getattr(getattr(e, "resp", None), "status", 0) or 0)
                mapped = errors.map_http_error(status, _http_reason(e))
                if isinstance(mapped, HistoryExpired) and method == "get_message":
                    raise MessageGone() from None  # deleted between list and get (R1-2)
                if isinstance(mapped, HistoryExpired) and method != "list_history":
                    raise PulseError("internal", f"Unexpected error: Gmail returned HTTP 404 for {method}.") from None
                raise mapped from None
            raise

    def get_profile(self) -> dict:
        return self._exec(self.service.users().getProfile(userId="me"), "get_profile")

    def list_messages(self, query, page_token, max_results):
        kw = {"userId": "me", "maxResults": max_results}
        if query:
            kw["q"] = query
        if page_token:
            kw["pageToken"] = page_token
        return self._exec(self.service.users().messages().list(**kw), "list_messages")

    def get_message(self, msg_id, fmt):
        kw = {"userId": "me", "id": msg_id, "format": fmt}
        if fmt == "metadata":
            kw["metadataHeaders"] = list(METADATA_HEADERS)
        return self._exec(self.service.users().messages().get(**kw), "get_message")

    def list_history(self, start_id, page_token, max_results):
        kw = {"userId": "me", "startHistoryId": start_id, "historyTypes": ["messageAdded"],
              "maxResults": max_results}
        if page_token:
            kw["pageToken"] = page_token
        return self._exec(self.service.users().history().list(**kw), "list_history")
