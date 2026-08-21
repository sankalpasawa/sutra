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

from connectors.credentials import KeychainCredentialStore, keychain_available  # noqa: E402
from connectors.credentials.store import MemoryCredentialStore  # noqa: E402
from connectors.database import Database                        # noqa: E402
from connectors.errors import ConnectorError                    # noqa: E402
from connectors.permission_service import ConnectorPermissions  # noqa: E402
from connectors.registry import (                               # noqa: E402
    build_service, get_spec, provider_ids, secret_available,
)

router = APIRouter(prefix="/api", tags=["connectors"])

OPERATOR = "local"
SUTRA_DIR = Path.home() / ".sutra"
DB_PATH = str(SUTRA_DIR / "connectors.db")
ERROR_LOG = SUTRA_DIR / "panel-errors.log"

#: One Database for the whole process; one service PER PROVIDER over it. They
#: share the file, and Database keeps a connection per thread.
_db = None
_store = None
_services = {}
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


def _foundation():
    """The shared database and credential store."""
    global _db, _store, _degraded
    if _db is None:
        _db = Database(DB_PATH)
        _db.migrate()
    if _store is None:
        if keychain_available():
            _store = KeychainCredentialStore()
            _degraded = None
        else:
            # Say so rather than silently losing credentials on restart.
            _store = MemoryCredentialStore()
            _degraded = ("No OS keychain on this platform. Credentials will not "
                         "survive a restart.")
    return _db, _store


def service(provider: str = "github"):
    """One service per provider, REBUILT if the shared connection goes bad.

    A failed construction is never cached, so the next request retries instead
    of inheriting a permanent None.
    """
    global _db, _services
    if provider not in provider_ids():
        raise HTTPException(status_code=404,
                            detail={"code": "UNKNOWN_PROVIDER", "provider": provider})
    existing = _services.get(provider)
    if existing is not None:
        try:
            existing.db.execute("SELECT 1").fetchone()
            return existing
        except (sqlite3.Error, AttributeError) as exc:
            _log_unexpected("service.healthcheck", exc)
            try:
                existing.db.close()
            except Exception:
                pass
            _services.clear()
            _db = None
    db, store = _foundation()
    built = build_service(provider, db, store)
    _services[provider] = built
    return built


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


def permissions(provider: str, connector_id: str) -> ConnectorPermissions:
    return ConnectorPermissions(service(provider), OPERATOR, connector_id)


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
    """Every connector across every provider."""
    rows = []
    for pid in provider_ids():
        for row in service(pid).list_connectors(OPERATOR):
            rows.append(dict(row, provider=pid))
    return {"connectors": rows, "degraded": _degraded,
            "truth_class": "authoritative"}


# NOT /api/providers: org_api.py already owns that path for AI CLI providers
# (Claude, Codex, Gemini) and its router is registered first, so a route there
# is silently shadowed rather than rejected. One segment under /connectors
# cannot collide with /connectors/{provider}/{connector_id}, which is two.
@router.get("/connectors/providers")
@guarded("connector_providers")
def connector_providers():
    """Tile data. Includes providers with NO connector, which is the whole
    point of a tile view: an unconnected provider still needs somewhere to be
    shown, and no connector row exists to render it from."""
    db, store = _foundation()
    out = []
    for pid in provider_ids():
        spec = get_spec(pid)
        connectors = service(pid).list_connectors(OPERATOR)
        ready = secret_available(spec)
        out.append({
            "provider": spec.provider,
            "display_name": spec.display_name,
            "tagline": spec.tagline,
            "auth_mode": spec.auth_mode,
            "caveat": spec.caveat,
            "connectable": ready,
            "blocked_reason": None if ready else
                "No client secret on this machine. Add "
                "SUTRA_%s_CLIENT_SECRET to ~/.sutra/provider-secrets.env "
                "(mode 600)." % spec.provider.upper(),
            "connectors": connectors,
            "connected": len(connectors),
            "needs_attention": sum(
                1 for c in connectors if c["status"] == "REAUTH_REQUIRED"),
        })
    return {"providers": out, "degraded": _degraded, "truth_class": "authoritative"}


# ------------------------------------------------------------- connect ---
@router.post("/connectors/{provider}/authorize")
@guarded("authorize")
def authorize(provider: str, label: Optional[str] = None):
    try:
        return service(provider).begin_connect(OPERATOR, label=label)
    except ConnectorError as exc:
        _fail(exc)


@router.get("/connectors/{provider}/authorize/{transaction_id}")
@guarded("poll")
def poll(provider: str, transaction_id: str):
    try:
        return service(provider).poll_connect(OPERATOR, transaction_id)
    except ConnectorError as exc:
        _fail(exc)


@router.delete("/connectors/{provider}/authorize/{transaction_id}")
@guarded("cancel")
def cancel(provider: str, transaction_id: str):
    try:
        service(provider).cancel_connect(OPERATOR, transaction_id)
    except ConnectorError as exc:
        _fail(exc)
    return {"status": "CANCELLED"}


# -------------------------------------------------------------- detail ---
@router.get("/connectors/{provider}/{connector_id}")
@guarded("detail")
def detail(provider: str, connector_id: str):
    connector = service(provider).get_connector(OPERATOR, connector_id)
    if connector is None:
        # 404 rather than 403: a 403 confirms the id exists.
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return connector.public_dict()


@router.post("/connectors/{provider}/{connector_id}/validate")
@guarded("validate")
def validate(provider: str, connector_id: str):
    try:
        return service(provider).validate(OPERATOR, connector_id)
    except ConnectorError as exc:
        _fail(exc)


@router.delete("/connectors/{provider}/{connector_id}")
@guarded("disconnect")
def disconnect(provider: str, connector_id: str):
    try:
        return service(provider).disconnect(OPERATOR, connector_id)
    except ConnectorError as exc:
        _fail(exc)


# ----------------------------------------------------------- discovery ---
@router.get("/connectors/{provider}/{connector_id}/repositories")
@guarded("repositories")
def repositories(provider: str, connector_id: str, cursor: Optional[str] = None,
                 refresh: bool = Query(False)):
    try:
        return service(provider).list_repositories(OPERATOR, connector_id,
                                           cursor=cursor, refresh=refresh)
    except ConnectorError as exc:
        _fail(exc)
    except ValueError as exc:                       # InvalidCursor
        raise HTTPException(status_code=400,
                            detail={"code": "INVALID_CURSOR", "message": str(exc)})


@router.get("/connectors/{provider}/{connector_id}/organizations")
@guarded("organizations")
def organizations(provider: str, connector_id: str, refresh: bool = Query(False)):
    try:
        return service(provider).list_organizations(OPERATOR, connector_id, refresh=refresh)
    except ConnectorError as exc:
        _fail(exc)


# --------------------------------------------------------- permissions ---
@router.get("/connectors/{provider}/{connector_id}/permissions")
@guarded("connector_permissions")
def connector_permissions(provider: str, connector_id: str):
    """The P3 capability read model. Read-only: rules are edited in the
    settings files, which is where they can be reviewed in a diff."""
    if service(provider).get_connector(OPERATOR, connector_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    try:
        return permissions(provider, connector_id).summary()
    except ConnectorError as exc:
        _fail(exc)


@router.get("/connectors/{provider}/{connector_id}/events")
@guarded("events")
def events(provider: str, connector_id: str, limit: int = Query(50, le=200)):
    if service(provider).get_connector(OPERATOR, connector_id) is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    rows = service(provider).events.list_for_connector(connector_id, limit)
    return {"events": [{"event_type": r["event_type"], "result": r["result"],
                        "resource": r["resource"], "operation": r["operation"],
                        "reason_code": r["reason_code"],
                        "occurred_at": r["occurred_at"]} for r in rows],
            "truth_class": "authoritative"}
