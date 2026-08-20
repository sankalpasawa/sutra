"""Domain types.

The Credential class is the security-critical one. Its properties are not
conveniences -- each corresponds to a real way tokens escape:

  __repr__/__str__/__format__ redact   an f-string in a log line
  not JSON-serialisable                a token attached to a response model
  no __dict__ exposure via asdict()    a debug dump
"""
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if moment else None


def parse_iso(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class ConnectorStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    DISCONNECTED = "DISCONNECTED"


class StatusReason(str, Enum):
    REVOKED = "REVOKED"
    SSO_REQUIRED = "SSO_REQUIRED"
    SCOPE_INSUFFICIENT = "SCOPE_INSUFFICIENT"
    REFRESH_EXPIRED = "REFRESH_EXPIRED"
    ORG_ACCESS_REMOVED = "ORG_ACCESS_REMOVED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class TransactionStatus(str, Enum):
    CREATED = "CREATED"
    AUTHORIZATION_STARTED = "AUTHORIZATION_STARTED"
    CALLBACK_RECEIVED = "CALLBACK_RECEIVED"      # web_pkce only; kept so both strategies share one FSM
    CODE_EXCHANGED = "CODE_EXCHANGED"
    CONNECTOR_CREATED = "CONNECTOR_CREATED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


#: The only transitions the FSM permits. Anything else raises.
LEGAL_TRANSITIONS = {
    TransactionStatus.CREATED: {
        TransactionStatus.AUTHORIZATION_STARTED, TransactionStatus.CANCELLED,
        TransactionStatus.FAILED, TransactionStatus.EXPIRED},
    TransactionStatus.AUTHORIZATION_STARTED: {
        TransactionStatus.CALLBACK_RECEIVED, TransactionStatus.CODE_EXCHANGED,
        TransactionStatus.CANCELLED, TransactionStatus.FAILED,
        TransactionStatus.EXPIRED, TransactionStatus.REJECTED},
    TransactionStatus.CALLBACK_RECEIVED: {
        TransactionStatus.CODE_EXCHANGED, TransactionStatus.FAILED, TransactionStatus.EXPIRED},
    TransactionStatus.CODE_EXCHANGED: {
        TransactionStatus.CONNECTOR_CREATED, TransactionStatus.FAILED},
    TransactionStatus.CONNECTOR_CREATED: {TransactionStatus.COMPLETED},
    TransactionStatus.COMPLETED: set(),
    TransactionStatus.EXPIRED: set(),
    TransactionStatus.CANCELLED: set(),
    TransactionStatus.FAILED: set(),
    TransactionStatus.REJECTED: set(),
}

TERMINAL_STATUSES = frozenset({
    TransactionStatus.COMPLETED, TransactionStatus.EXPIRED,
    TransactionStatus.CANCELLED, TransactionStatus.FAILED, TransactionStatus.REJECTED,
})

_REDACTED = "<Credential redacted>"


class Credential:
    """A provider credential. Never logged, never serialised, never returned.

    Deliberately NOT a dataclass: a dataclass gets a __repr__ that prints its
    fields, and dataclasses.asdict() would walk it straight into a JSON body.
    """

    __slots__ = ("access_token", "refresh_token", "access_expires_at",
                 "refresh_expires_at", "token_type", "credential_type")

    def __init__(self, access_token, refresh_token=None, access_expires_at=None,
                 refresh_expires_at=None, token_type="bearer",
                 credential_type="user_to_server"):
        if not access_token:
            raise ValueError("access_token is required")
        object.__setattr__(self, "access_token", access_token)
        object.__setattr__(self, "refresh_token", refresh_token)
        object.__setattr__(self, "access_expires_at", access_expires_at)
        object.__setattr__(self, "refresh_expires_at", refresh_expires_at)
        object.__setattr__(self, "token_type", token_type)
        object.__setattr__(self, "credential_type", credential_type)

    # -- redaction -------------------------------------------------------
    def __repr__(self):
        return _REDACTED

    __str__ = __repr__

    def __format__(self, spec):
        return _REDACTED

    def __reduce__(self):
        raise TypeError("Credential is not picklable; it must not leave the process")

    # -- expiry ----------------------------------------------------------
    def is_expired(self, skew_seconds=60, now=None) -> bool:
        if self.access_expires_at is None:
            return False
        now = now or utcnow()
        return now >= self.access_expires_at - timedelta(seconds=skew_seconds)

    def refresh_expired(self, now=None) -> bool:
        if self.refresh_expires_at is None:
            return self.refresh_token is None
        return (now or utcnow()) >= self.refresh_expires_at

    # -- storage form ----------------------------------------------------
    def to_secret_json(self) -> Dict[str, Any]:
        """The ONLY way to get the material out, and it exists solely so the
        CredentialStore can hand it to the OS keychain. Nothing else may call it."""
        return {
            "v": 1,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "access_expires_at": iso(self.access_expires_at),
            "refresh_expires_at": iso(self.refresh_expires_at),
            "token_type": self.token_type,
            "credential_type": self.credential_type,
        }

    @classmethod
    def from_secret_json(cls, data: Dict[str, Any]) -> "Credential":
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            access_expires_at=parse_iso(data.get("access_expires_at")),
            refresh_expires_at=parse_iso(data.get("refresh_expires_at")),
            token_type=data.get("token_type", "bearer"),
            credential_type=data.get("credential_type", "user_to_server"),
        )

    @classmethod
    def from_token_response(cls, payload: Dict[str, Any], now=None) -> "Credential":
        now = now or utcnow()
        expires_in = payload.get("expires_in")
        refresh_expires_in = payload.get("refresh_token_expires_in")
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            access_expires_at=now + timedelta(seconds=int(expires_in)) if expires_in else None,
            refresh_expires_at=(now + timedelta(seconds=int(refresh_expires_in))
                                if refresh_expires_in else None),
            token_type=payload.get("token_type", "bearer"),
        )


@dataclass
class ProviderIdentity:
    """Identity as the provider reports it.

    account_id is GitHub's numeric user id and is the ONLY value permitted in a
    unique key. username is mutable: a rename must not orphan a connector, and a
    released username reassigned to someone else must not rebind one.
    """
    account_id: str
    username: str
    node_id: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    account_type: str = "user"


@dataclass
class Installation:
    """One GitHub App installation reachable by a connector.

    permissions and repository_selection are the org owner's decisions, not
    ours. They are an upstream ceiling GitHub enforces regardless of our bugs.
    """
    installation_id: int
    account_login: str
    account_id: int
    account_type: str                     # 'Organization' | 'User'
    repository_selection: str             # 'all' | 'selected'
    permissions: Dict[str, str] = field(default_factory=dict)
    suspended: bool = False
    sso_required: bool = False

    def public_dict(self):
        return {
            "id": self.installation_id,
            "account": self.account_login,
            "account_type": self.account_type,
            "repository_selection": self.repository_selection,
            "permissions": dict(self.permissions),
            "suspended": self.suspended,
        }


@dataclass
class Repository:
    repo_id: str
    full_name: str
    owner: str
    name: str
    visibility: str
    default_branch: str
    archived: bool = False
    user_permission: str = "read"
    installation_id: Optional[int] = None
    app_permissions: Dict[str, str] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    access: str = "ok"                    # ok | sso_required | suspended

    def public_dict(self):
        return {
            "id": self.repo_id,
            "full_name": self.full_name,
            "visibility": self.visibility,
            "default_branch": self.default_branch,
            "archived": self.archived,
            "user_permission": self.user_permission,
            "installation_id": self.installation_id,
            "app_permissions": dict(self.app_permissions),
            "capabilities": list(self.capabilities),
            "access": self.access,
        }


@dataclass
class Organization:
    org_id: str
    login: str
    avatar_url: Optional[str] = None
    installation: Optional[Installation] = None
    access: str = "not_installed"         # ok | not_installed | sso_required | suspended

    def public_dict(self):
        return {
            "id": self.org_id,
            "login": self.login,
            "avatar_url": self.avatar_url,
            "installation": self.installation.public_dict() if self.installation else None,
            "access": self.access,
        }


@dataclass
class Connector:
    id: str
    operator_id: str
    provider: str
    provider_account_id: str
    provider_username: str
    status: ConnectorStatus = ConnectorStatus.PENDING
    status_reason: Optional[str] = None
    provider_account_node: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    account_type: str = "user"
    label: Optional[str] = None
    api_base: str = "https://api.github.com"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None

    def public_dict(self) -> Dict[str, Any]:
        """What may cross the API boundary. No scopes, no installation ids, no secrets."""
        return {
            "id": self.id,
            "provider": self.provider,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "account": {
                "id": self.provider_account_id,
                "username": self.provider_username,
                "display_name": self.display_name,
                "avatar_url": self.avatar_url,
            },
            "label": self.label,
            "created_at": iso(self.created_at),
            "last_used_at": iso(self.last_used_at),
        }


@dataclass
class OAuthTransaction:
    id: str
    operator_id: str
    provider: str
    strategy: str
    status: TransactionStatus
    created_at: datetime
    expires_at: datetime
    state_hash: Optional[str] = None
    device_code_enc: Optional[bytes] = None
    code_verifier_enc: Optional[bytes] = None
    redirect_uri: Optional[str] = None
    reconnect_of: Optional[str] = None
    connector_id: Optional[str] = None
    failure_code: Optional[str] = None
    completed_at: Optional[datetime] = None
    poll_interval: int = 5
    label: Optional[str] = None

    def is_expired(self, now=None) -> bool:
        return (now or utcnow()) >= self.expires_at

    def public_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.id,
            "status": self.status.value,
            "strategy": self.strategy,
            "expires_at": iso(self.expires_at),
            "connector_id": self.connector_id,
            "failure_code": self.failure_code,
        }
