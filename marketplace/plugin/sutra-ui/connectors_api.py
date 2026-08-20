"""Connector endpoints for the panel.

Bridges the panel to marketplace/plugin/connectors/. The panel is a CLIENT of
that module, not a peer: it deals in connector ids and connector state and
never sees a credential (ADR-034). Every route below returns projections that
have already been stripped by the module's own public_dict()/summary().

Endpoints are SYNCHRONOUS `def`, not `async def`, on purpose. The GitHub client
is stdlib urllib and therefore blocking; FastAPI runs a sync endpoint in a
threadpool, so a slow GitHub call cannot stall the event loop and freeze the
whole panel. Declaring these `async` would be the bug that stdlib choice pays
for elsewhere.
"""
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

# The plugin tree ships whole (bundle-runtime.sh rsyncs marketplace/plugin/),
# so connectors/ is a sibling of sutra-ui/ in both dev and the app payload.
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1])
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from connectors.config import ProviderConfig                    # noqa: E402
from connectors.credentials import KeychainCredentialStore, keychain_available  # noqa: E402
from connectors.credentials.store import MemoryCredentialStore  # noqa: E402
from connectors.database import Database                        # noqa: E402
from connectors.errors import ConnectorError                    # noqa: E402
from connectors.permission_service import ConnectorPermissions  # noqa: E402
from connectors.service import ConnectorService                 # noqa: E402

router = APIRouter(prefix="/api", tags=["connectors"])

OPERATOR = "local"
DB_PATH = str(Path.home() / ".sutra" / "connectors.db")

_service = None
_degraded = None


def service():
    """One service per process. Built lazily so importing this module never
    touches the Keychain or the filesystem -- an import that prompts for
    Keychain access on app launch would be its own bug."""
    global _service, _degraded
    if _service is None:
        db = Database(DB_PATH)
        db.migrate()
        if keychain_available():
            store = KeychainCredentialStore()
            _degraded = None
        else:
            # Say so rather than silently losing credentials on restart.
            store = MemoryCredentialStore()
            _degraded = ("No OS keychain on this platform. Credentials will not "
                         "survive a restart.")
        _service = ConnectorService(db, store, config=ProviderConfig.from_env())
    return _service


def permissions(connector_id: str) -> ConnectorPermissions:
    return ConnectorPermissions(service(), OPERATOR, connector_id)


def _fail(exc: ConnectorError):
    """One envelope. The panel switches on user_action, never on the message."""
    status = {"TRANSACTION_NOT_FOUND": 404, "TRANSACTION_EXPIRED": 410,
              "ACCOUNT_MISMATCH": 409, "CREDENTIAL_INVALID": 409,
              "REFRESH_EXPIRED": 409, "RATE_LIMITED": 429,
              "SECONDARY_RATE_LIMITED": 429, "PROVIDER_UNAVAILABLE": 502,
              "DEVICE_FLOW_DISABLED": 500}.get(exc.code, 400)
    raise HTTPException(status_code=status, detail=exc.as_dict())


# ---------------------------------------------------------------- list ---
@router.get("/connectors")
def list_connectors():
    try:
        rows = service().list_connectors(OPERATOR)
    except ConnectorError as exc:
        _fail(exc)
    return {"connectors": rows, "degraded": _degraded,
            "truth_class": "authoritative"}


# ------------------------------------------------------------- connect ---
@router.post("/connectors/github/authorize")
def authorize(label: Optional[str] = None):
    try:
        return service().begin_connect(OPERATOR, label=label)
    except ConnectorError as exc:
        _fail(exc)


@router.get("/connectors/github/authorize/{transaction_id}")
def poll(transaction_id: str):
    try:
        return service().poll_connect(OPERATOR, transaction_id)
    except ConnectorError as exc:
        _fail(exc)


@router.delete("/connectors/github/authorize/{transaction_id}")
def cancel(transaction_id: str):
    try:
        service().cancel_connect(OPERATOR, transaction_id)
    except ConnectorError as exc:
        _fail(exc)
    return {"status": "CANCELLED"}


# -------------------------------------------------------------- detail ---
@router.get("/connectors/github/{connector_id}")
def detail(connector_id: str):
    connector = service().get_connector(OPERATOR, connector_id)
    if connector is None:
        # 404 rather than 403: a 403 confirms the id exists.
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return connector.public_dict()


@router.post("/connectors/github/{connector_id}/validate")
def validate(connector_id: str):
    try:
        return service().validate(OPERATOR, connector_id)
    except ConnectorError as exc:
        _fail(exc)


@router.delete("/connectors/github/{connector_id}")
def disconnect(connector_id: str):
    try:
        return service().disconnect(OPERATOR, connector_id)
    except ConnectorError as exc:
        _fail(exc)


# ----------------------------------------------------------- discovery ---
@router.get("/connectors/github/{connector_id}/repositories")
def repositories(connector_id: str, cursor: Optional[str] = None,
                 refresh: bool = Query(False)):
    try:
        return service().list_repositories(OPERATOR, connector_id,
                                           cursor=cursor, refresh=refresh)
    except ConnectorError as exc:
        _fail(exc)
    except ValueError as exc:                       # InvalidCursor
        raise HTTPException(status_code=400,
                            detail={"code": "INVALID_CURSOR", "message": str(exc)})


@router.get("/connectors/github/{connector_id}/organizations")
def organizations(connector_id: str, refresh: bool = Query(False)):
    try:
        return service().list_organizations(OPERATOR, connector_id, refresh=refresh)
    except ConnectorError as exc:
        _fail(exc)


# --------------------------------------------------------- permissions ---
@router.get("/connectors/github/{connector_id}/permissions")
def connector_permissions(connector_id: str):
    """The P3 capability read model. Read-only: rules are edited in the
    settings files, which is where they can be reviewed in a diff."""
    if service().get_connector(OPERATOR, connector_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    try:
        return permissions(connector_id).summary()
    except ConnectorError as exc:
        _fail(exc)


@router.get("/connectors/github/{connector_id}/events")
def events(connector_id: str, limit: int = Query(50, le=200)):
    if service().get_connector(OPERATOR, connector_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    rows = service().events.list_for_connector(connector_id, limit)
    return {"events": [{"event_type": r["event_type"], "result": r["result"],
                        "resource": r["resource"], "operation": r["operation"],
                        "reason_code": r["reason_code"],
                        "occurred_at": r["occurred_at"]} for r in rows],
            "truth_class": "authoritative"}
