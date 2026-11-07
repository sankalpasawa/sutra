"""What the automatic update check remembers (gap package autoupdate): the owner's setting and the last result, both in the `meta` table.

    get_auto(services) -> (on, chosen)          key `update_auto`: "1" or "0". Absent means the default, ON, and `chosen` is False.
    set_auto(services, on)                      the owner's switch in Settings -> About (PUT /api/ops/update-setting)
    get_last(services) -> dict | None           key `update_last`: {at, state, version, message}; never raises (a value that is not that reads as None)
    set_last(services, state, version, message) written by the server after every update-plan, and by the desktop app as it downloads and verifies
                                                (POST /api/ops/update-status): the one line the About group shows under "Last check"

No migration: `meta` is a plain key/value table (like `welcome_seen_at`). The default is ON because the only thing that ever acts on it is the desktop
app's own timer; the command line and a browser-only start never check by themselves whatever this says.

What is stored is always cleaned first: the message loses control characters and is cut at MAX_MESSAGE, the version is kept only when it has the shape of
one of ours, the state is one of STATES. The page escapes it again when it draws it.
"""
import json
import re
from typing import Any

__all__ = ["get_auto", "set_auto", "get_last", "set_last", "clean_message", "clean_version", "AUTO_KEY", "LAST_KEY", "STATES", "MAX_MESSAGE"]

AUTO_KEY = "update_auto"
LAST_KEY = "update_last"
MAX_MESSAGE = 240
STATES = ("up_to_date", "available", "error", "downloading", "ready", "failed", "tell_only", "installing")
_NUM = r"(?:0|[1-9][0-9]{0,8})"                       # the same 9-digit limit as ops/update_check.py
_VERSION = re.compile(rf"{_NUM}\.{_NUM}\.{_NUM}(?:-beta\.{_NUM})?")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]+")


def clean_message(text: Any) -> str:
    """One line of plain text: control characters (and line breaks) become a space, runs of spaces one, at most MAX_MESSAGE characters."""
    if not isinstance(text, str):
        return ""
    return re.sub(r" {2,}", " ", _CONTROL.sub(" ", text)).strip()[:MAX_MESSAGE]


def clean_version(text: Any) -> str | None:
    return text if isinstance(text, str) and _VERSION.fullmatch(text) else None


def get_auto(services: Any) -> tuple[bool, bool]:
    """(on, chosen). Never raises: an unreadable store is the default."""
    try:
        row = services.db.conn().execute("SELECT value FROM meta WHERE key = ?", (AUTO_KEY,)).fetchone()
    except Exception:                                                              # noqa: BLE001  (a setting that cannot be read is the default)
        return True, False
    if row is None or row["value"] not in ("0", "1"):
        return True, False
    return row["value"] == "1", True


def _put(services: Any, key: str, value: str) -> None:
    with services.db.tx() as tx:
        tx.conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def set_auto(services: Any, on: bool) -> None:
    _put(services, AUTO_KEY, "1" if on else "0")


def get_last(services: Any) -> dict[str, Any] | None:
    try:
        row = services.db.conn().execute("SELECT value FROM meta WHERE key = ?", (LAST_KEY,)).fetchone()
        found = json.loads(row["value"]) if row is not None else None
    except Exception:                                                              # noqa: BLE001
        return None
    if not isinstance(found, dict) or found.get("state") not in STATES:
        return None
    at = found.get("at")
    return {"at": float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else None, "state": found["state"],
            "version": clean_version(found.get("version")), "message": clean_message(found.get("message"))}


def set_last(services: Any, state: str, version: str | None, message: str) -> dict[str, Any]:
    """Store the cleaned record and return it. A state that is not one of STATES is a ValueError (the route checks it first)."""
    if state not in STATES:
        raise ValueError(f"unknown update state {state!r}")
    record = {"at": float(services.clock.now()), "state": state, "version": clean_version(version), "message": clean_message(message)}
    _put(services, LAST_KEY, json.dumps(record, separators=(",", ":")))
    return record
