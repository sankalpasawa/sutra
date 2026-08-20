"""Normalised error taxonomy.

Every provider exception is mapped here before it leaves connectors/github/, so
nothing above the provider package ever sees an HTTP status code. The mapping
lives in design/03 §3.2; the two rows that matter most:

  403 is FOUR different conditions (primary rate limit, secondary rate limit,
      SAML SSO, permission) and only two of them are retryable. Blind retry on
      403 is the fastest way to get a GitHub App flagged for abuse.

  404 frequently means PERMISSION, not absence: GitHub returns 404 rather than
      403 for private resources you cannot see. Rendering it as "not found"
      sends users hunting for a typo that isn't there.
"""


class ConnectorError(Exception):
    code = "CONNECTOR_ERROR"
    retryable = False
    #: What the UI should offer. Renderers switch on this, never on the message.
    user_action = "NONE"

    def __init__(self, message="", **detail):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.detail = detail

    def as_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "user_action": self.user_action,
            **self.detail,
        }


class CredentialInvalid(ConnectorError):
    code = "CREDENTIAL_INVALID"
    user_action = "RECONNECT"


class RefreshExpired(ConnectorError):
    code = "REFRESH_EXPIRED"
    user_action = "RECONNECT"


class SSORequired(ConnectorError):
    code = "SSO_REQUIRED"
    user_action = "AUTHORISE_SSO"


class PermissionDenied(ConnectorError):
    code = "PERMISSION_DENIED"
    user_action = "INSTALL_APP"


class NotFoundOrForbidden(ConnectorError):
    """404. Deliberately not called NotFound: it is usually permission."""
    code = "NOT_FOUND_OR_FORBIDDEN"
    user_action = "ADD_REPOSITORY"


class RateLimited(ConnectorError):
    code = "RATE_LIMITED"
    retryable = True
    user_action = "WAIT"


class SecondaryRateLimited(RateLimited):
    code = "SECONDARY_RATE_LIMITED"


class ProviderUnavailable(ConnectorError):
    code = "PROVIDER_UNAVAILABLE"
    retryable = True
    user_action = "WAIT"


class ValidationFailed(ConnectorError):
    code = "VALIDATION_FAILED"


class Conflict(ConnectorError):
    code = "CONFLICT"


# ---- OAuth transaction errors ------------------------------------------ #

class TransactionError(ConnectorError):
    code = "TRANSACTION_ERROR"


class TransactionExpired(TransactionError):
    code = "TRANSACTION_EXPIRED"
    user_action = "RECONNECT"


class TransactionNotFound(TransactionError):
    code = "TRANSACTION_NOT_FOUND"


class TransactionAlreadyRedeemed(TransactionError):
    """A single-use transaction was presented twice. Treated as an attack, not a warning."""
    code = "TRANSACTION_ALREADY_REDEEMED"


class AuthorizationPending(TransactionError):
    """Not an error: the user has not finished authorising yet."""
    code = "AUTHORIZATION_PENDING"
    retryable = True


class SlowDown(TransactionError):
    code = "SLOW_DOWN"
    retryable = True


class AuthorizationDenied(TransactionError):
    code = "AUTHORIZATION_DENIED"


class DeviceFlowDisabled(TransactionError):
    """The app's own configuration is wrong. Surfaces to the developer, not the user."""
    code = "DEVICE_FLOW_DISABLED"


class AccountMismatch(ConnectorError):
    """A reconnect returned a different GitHub account than the connector holds.

    This is not a reconnect. Silently rebinding the row would attach one
    person's history to another person's account.
    """
    code = "ACCOUNT_MISMATCH"
