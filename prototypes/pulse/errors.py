"""Error codes, exit codes and the pure mappers from live Google error shapes to Pulse errors.

Every expected failure is a PulseError(code, message). The CLI maps code -> exit code via EXIT.
TransientError (429 / 5xx / network) is retried by gmail_client.with_retry. HistoryExpired (404 on history.list)
triggers the full-list fallback and is never an exit code. MessageGone (404 on messages.get) makes the caller
skip that message and count it.
"""

EXIT = {
    "ok": 0,
    "internal": 1,
    "usage": 2, "config_missing": 2, "config_invalid": 2, "rules_invalid": 2, "deps_missing": 2,
    "wrong_domain": 3, "not_allowlisted": 3, "mailbox_mismatch": 3, "audit_unavailable": 3, "unsafe_path": 3,
    "key_missing": 4, "key_unreadable": 4, "unauthorized_client": 4, "invalid_grant": 4, "access_denied": 4,
    "rate_limited": 5, "server_error": 5, "network_error": 5,
}

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

DELEGATION_HELP = (
    "In the Google Admin console go to Security > Access and data control > API controls > "
    "Domain-wide delegation, add the service account's client ID, and grant only the scope " + SCOPE + "."
)


class PulseError(Exception):
    """An expected failure with a stable code. The message is shown to the user and never holds secrets."""

    def __init__(self, code: str, message: str):
        if code not in EXIT:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = EXIT[code]


class TransientError(Exception):
    """429 or 5xx from Google, or a network failure (kind="network", status 0); retried with backoff."""

    def __init__(self, status: int, kind: str = "http"):
        super().__init__(f"HTTP {status}" if kind == "http" else kind)
        self.status = status
        self.kind = kind


class HistoryExpired(Exception):
    """history.list returned 404: the saved historyId is too old. Caller falls back to a full list."""


class MessageGone(Exception):
    """messages.get returned 404: the message was deleted after it was listed. Caller skips and counts it."""


def map_refresh_error(text: str) -> PulseError:
    """Map a token-endpoint error (google.auth.exceptions.RefreshError text) to a PulseError.

    Unknown shapes fail closed as unauthorized_client. The strings are unverified until a key exists (A-2, L-5).
    """
    low = (text or "").lower()
    if "invalid_grant" in low:
        return PulseError(
            "invalid_grant",
            "Google refused a token for this mailbox (invalid_grant). The mailbox may be outside the domain, "
            "suspended or deleted, or this machine's clock may be wrong.",
        )
    if "unauthorized_client" in low:
        return PulseError(
            "unauthorized_client",
            "Google refused a token for this service account (unauthorized_client). " + DELEGATION_HELP,
        )
    return PulseError(
        "unauthorized_client",
        "Google refused a token for this service account (could not get a token). " + DELEGATION_HELP,
    )


RATE_LIMIT_403 = ("rateLimitExceeded", "userRateLimitExceeded")


def map_http_error(status: int, reason: str = ""):
    """Map an HTTP status from the Gmail API. Returns (does not raise) the exception to raise."""
    reason = reason or "no reason given"
    if status == 403 and reason in RATE_LIMIT_403:
        return TransientError(429)  # Gmail reports per-user / per-project rate limits as 403 (R1-4)
    if status == 403 and reason == "dailyLimitExceeded":
        return PulseError("rate_limited",
                          "Gmail's daily usage limit for this project is used up (HTTP 403, dailyLimitExceeded). "
                          "Try again tomorrow.")
    if status == 403:
        return PulseError(
            "access_denied",
            f"Gmail refused access (HTTP 403, {reason}). Enable the Gmail API in the GCP project, "
            "and check that no Workspace policy blocks API access for this mailbox.",
        )
    if status == 404:
        return HistoryExpired()
    if status == 429 or 500 <= status <= 599:
        return TransientError(status)
    return PulseError("internal", f"Unexpected error: Gmail returned HTTP {status} ({reason}).")
