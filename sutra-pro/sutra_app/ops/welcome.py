"""The first-run welcome (gap package welcome-settings, item 1; the old app's onboarding card, rebuilt on this machine's real readings).

    GET  /api/ops/welcome         {seen, facts: {models, data, egress, autonomy}}      a read, no token (like the other ops reads)
    POST /api/ops/welcome/seen    {seen: true}                                         the owner's "Got it"; needs the token (D81)

Home shows one card until the owner says "Got it". The acknowledgement is stored HERE, in the `meta` table (key `welcome_seen_at`, written
with `INSERT ... ON CONFLICT DO NOTHING`, so the first time stays and a double click is harmless): another browser, a cleared cache or a new
Services over the same database file do not bring the card back. No migration: `meta` is a plain key/value table. "Not now" is the page's
own (this load only) and never reaches the server.

Every fact is a reading, never an illustration:

  models    one row per provider the app can use: `ready`, or the reason it cannot answer and the doctor's one-line fix ("run `claude auth login`").
            Offline (or the stub connector) the one row says that a built-in stub answers and no real model is called.
  data      the data folder, the database's size, the free space and the command that backs it up
  egress    where a prompt goes (only the owner's own CLIs, on a subscription login, an API key is refused) and that credential shapes are scrubbed
  autonomy  what the app does by itself and what it asks (the engine's budget and email mode as the next run would read them)

The answer holds no token, no key and no account name: it goes through the app's redactor like every ops read.
"""
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Request

from sutra_app.ops import api as ops_api
from sutra_app.orchestrator.api.deps import RedactedJSONResponse, require_token, services_of
from sutra_app.orchestrator.db import run_blocking

__all__ = ["build_router", "facts_of", "is_seen", "mark_seen", "META_KEY", "BACKUP_COMMAND"]

log = logging.getLogger(__name__)
META_KEY = "welcome_seen_at"
BACKUP_COMMAND = "sutra-pro backup"
PROVIDERS = ("claude", "codex")
_BLOCKING = ("quota", "cooldown", "breaker")                 # connectors/health.py: a provider that is signed in but not answering now
STUB_WHY = "Offline mode: a built-in stub answers, no real model is called."


def is_seen(services: Any) -> bool:
    row = services.db.conn().execute("SELECT 1 FROM meta WHERE key = ?", (META_KEY,)).fetchone()
    return row is not None


def mark_seen(services: Any) -> None:
    """Store the acknowledgement once (the first time stays)."""
    with services.db.tx() as tx:
        tx.conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (META_KEY, str(tx.now())))


def _checks(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in report.get("checks", ()) if isinstance(c, dict) and isinstance(c.get("id"), str)}


def _ready(entry: dict[str, Any]) -> bool:
    health = entry.get("health") if isinstance(entry.get("health"), dict) else {}
    return (bool(entry.get("installed")) and entry.get("signed_in") is True and entry.get("billing") != "api_key"
            and health.get("state") not in _BLOCKING and health.get("state") not in ("missing", "signed_out"))


def _model_row(name: str, entry: dict[str, Any] | None, check: dict[str, Any] | None) -> dict[str, Any]:
    entry = entry or {}
    row = {"name": name, "state": "ready", "why": "", "fix": ""}
    if _ready(entry):
        return row
    health = entry.get("health") if isinstance(entry.get("health"), dict) else {}
    row["state"] = "blocked" if health.get("state") in _BLOCKING else "not_ready"
    if row["state"] == "blocked":
        row["why"] = str(health.get("reason") or "it is cooling down after an error or a usage limit")
        return row                                          # nothing to fix: it comes back by itself
    said = str(check.get("detail") or "") if check else ""
    row["why"] = said or str(entry.get("detail") or "") or "it cannot answer right now"
    row["fix"] = str(check.get("fix") or "") if check and check.get("status") in ("warn", "fail") else ""
    return row


def _models(services: Any, report: dict[str, Any]) -> list[dict[str, Any]]:
    settings = services.settings
    if settings.offline or settings.connector == "stub":
        return [{"name": "stub", "state": "stub", "why": STUB_WHY, "fix": ""}]
    try:
        status = dict(services.connector.status())
    except Exception:                                                     # noqa: BLE001  (a card must never fail the page)
        log.warning("the welcome could not read the connector status", exc_info=True)
        status = {}
    checks = _checks(report)
    return [_model_row(name, status.get(name), checks.get(name)) for name in PROVIDERS if name in status or name in checks]


def _autonomy(services: Any) -> dict[str, Any]:
    """The engine's budget and email mode as a new run would read them (defaults < engine.json < J2_* environment); None when unreadable."""
    try:
        from sutra_app.engine.spec import EngineSettings, read_settings_file
        file = read_settings_file(services.settings.data_dir / "engine.json") or {}
        effective = EngineSettings.layered(os.environ, file, None, {})
        return {"budget": int(effective.budget), "send_mode": str(effective.send_mode), "asks": True}
    except Exception:                                                     # noqa: BLE001
        log.warning("the welcome could not read the engine settings", exc_info=True)
        return {"budget": None, "send_mode": None, "asks": True}


def facts_of(app: Any, services: Any) -> dict[str, Any]:
    """The four facts. Runs on a worker thread (the doctor's probe and the folder sizes touch the disk and the CLIs)."""
    info = ops_api.collect_info(services)
    report = {} if (services.settings.offline or services.settings.connector == "stub") else ops_api.doctor_answer(app, services)
    return {
        "models": _models(services, report),
        "data": {"dir": info["data_dir"], "db_bytes": info["db_bytes"], "free_bytes": info["free_bytes"], "backup": BACKUP_COMMAND},
        "egress": {"scrub": True, "api_key_refused": True, "only_your_cli": True},
        "autonomy": _autonomy(services),
    }


def _respond(request: Request, content: Any) -> RedactedJSONResponse:
    scrub = getattr(services_of(request).redact, "scrub", None)
    return RedactedJSONResponse(scrub(content) if callable(scrub) else content)


def build_router() -> APIRouter:
    api = APIRouter(prefix="/api/ops", tags=["ops"])

    @api.get("/welcome", summary="Whether the owner has said Got it, and the four first-run facts of this machine")
    async def get_welcome(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        seen = await run_blocking(lambda: is_seen(services))
        if seen:
            return _respond(request, {"seen": True, "facts": None})        # nothing to show: no doctor probe for a card that stays hidden
        facts = await run_blocking(lambda: facts_of(request.app, services))
        return _respond(request, {"seen": False, "facts": facts})

    @api.post("/welcome/seen", summary="The owner's Got it (stored once, in the database)", dependencies=[Depends(require_token)])
    async def post_seen(request: Request) -> RedactedJSONResponse:
        services = services_of(request)
        await run_blocking(lambda: mark_seen(services))
        return _respond(request, {"seen": True})

    return api
