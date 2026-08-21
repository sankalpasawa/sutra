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
import functools
import logging
import sqlite3
import sys
import traceback
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
SUTRA_DIR = Path.home() / ".sutra"
DB_PATH = str(SUTRA_DIR / "connectors.db")
ERROR_LOG = SUTRA_DIR / "panel-errors.log"

_service = None
_degraded = None

log = logging.getLogger("sutra.connectors")


def _log_unexpected(where: str, exc: BaseException) -> str:
    """Write the traceback somewhere a human can actually reach it.

    Electron buffers the backend's stderr IN MEMORY and only surfaces it if the
    process exits, so an unhandled exception in a request leaves no trace
    anywhere: the panel shows an opaque 500 and the reason is unreachable
    without killing the app. This function is the fix for that, and it is why
    every endpoint below catches Exception rather than only ConnectorError.
    """
    detail = traceback.format_exc()
    try:
        SUTRA_DIR.mkdir(mode=0o700, exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as handle:
            handle.write("\n=== %s: %s: %s\n%s" % (where, type(exc).__name__, exc, detail))
    except OSError:
        pass                                    # never fail a request over logging
    log.exception("connectors: %s failed", where)
    return "%s: %s" % (type(exc).__name__, exc)


def _build_service():
    db = Database(DB_PATH)
    db.migrate()
    global _degraded
    if keychain_available():
        store = KeychainCredentialStore()
        _degraded = None
    else:
        # Say so rather than silently losing credentials on restart.
        store = MemoryCredentialStore()
        _degraded = ("No OS keychain on this platform. Credentials will not "
                     "survive a restart.")
    return ConnectorService(db, store, config=ProviderConfig.from_env())


def service():
    """One service per process, REBUILT if its connection has gone bad.

    The previous version cached a module global holding a live SQLite
    connection for the life of the process. A connection that broke could never
    recover, so the only cure was quitting the whole app -- which is what
    happened in practice. Now a dead handle is detected and replaced, and a
    FAILED construction is never cached, so the next request retries instead of
    inheriting a permanent None.
    """
    global _service
    if _service is not None:
        try:
            _service.db.execute("SELECT 1").fetchone()
            return _service
        except (sqlite3.Error, AttributeError) as exc:
            _log_unexpected("service.healthcheck", exc)
            try:
                _service.db.close()
            except Exception:
                pass
            _service = None
    _service = _build_service()
    return _service


def guarded(where):
    """Every endpoint returns a STRUCTURED error, never a bare 500.

    An opaque 500 tells the operator only that something is wrong; the panel
    cannot switch on it and the reason is not written down anywhere. A 500 with
    a code, a message and a log path is a thing a person can act on.
    """
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except HTTPException:
                raise
            except ConnectorError as exc:
                _fail(exc)
            except Exception as exc:
                message = _log_unexpected(where, exc)
                raise HTTPException(status_code=500, detail={
                    "code": "PANEL_INTERNAL_ERROR",
                    "message": message,
                    "where": where,
                    "log": str(ERROR_LOG),
                    "user_action": "NONE",
                    "retryable": True,
                })
        return wrapper
    return decorate


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
@guarded("list_connectors")
def list_connectors():
    try:
        rows = service().list_connectors(OPERATOR)
    except ConnectorError as exc:
        _fail(exc)
    return {"connectors": rows, "degraded": _degraded,
            "truth_class": "authoritative"}


# ------------------------------------------------------------- connect ---
@router.post("/connectors/github/authorize")
@guarded("authorize")
def authorize(label: Optional[str] = None):
    try:
        return service().begin_connect(OPERATOR, label=label)
    except ConnectorError as exc:
        _fail(exc)


@router.get("/connectors/github/authorize/{transaction_id}")
@guarded("poll")
def poll(transaction_id: str):
    try:
        return service().poll_connect(OPERATOR, transaction_id)
    except ConnectorError as exc:
        _fail(exc)


@router.delete("/connectors/github/authorize/{transaction_id}")
@guarded("cancel")
def cancel(transaction_id: str):
    try:
        service().cancel_connect(OPERATOR, transaction_id)
    except ConnectorError as exc:
        _fail(exc)
    return {"status": "CANCELLED"}


# -------------------------------------------------------------- detail ---
@router.get("/connectors/github/{connector_id}")
@guarded("detail")
def detail(connector_id: str):
    connector = service().get_connector(OPERATOR, connector_id)
    if connector is None:
        # 404 rather than 403: a 403 confirms the id exists.
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return connector.public_dict()


@router.post("/connectors/github/{connector_id}/validate")
@guarded("validate")
def validate(connector_id: str):
    try:
        return service().validate(OPERATOR, connector_id)
    except ConnectorError as exc:
        _fail(exc)


@router.delete("/connectors/github/{connector_id}")
@guarded("disconnect")
def disconnect(connector_id: str):
    try:
        return service().disconnect(OPERATOR, connector_id)
    except ConnectorError as exc:
        _fail(exc)


# ----------------------------------------------------------- discovery ---
@router.get("/connectors/github/{connector_id}/repositories")
@guarded("repositories")
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
@guarded("organizations")
def organizations(connector_id: str, refresh: bool = Query(False)):
    try:
        return service().list_organizations(OPERATOR, connector_id, refresh=refresh)
    except ConnectorError as exc:
        _fail(exc)


# --------------------------------------------------------- permissions ---
@router.get("/connectors/github/{connector_id}/permissions")
@guarded("connector_permissions")
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
@guarded("events")
def events(connector_id: str, limit: int = Query(50, le=200)):
    if service().get_connector(OPERATOR, connector_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    rows = service().events.list_for_connector(connector_id, limit)
    return {"events": [{"event_type": r["event_type"], "result": r["result"],
                        "resource": r["resource"], "operation": r["operation"],
                        "reason_code": r["reason_code"],
                        "occurred_at": r["occurred_at"]} for r in rows],
            "truth_class": "authoritative"}
