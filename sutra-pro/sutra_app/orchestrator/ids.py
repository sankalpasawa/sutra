"""Ids and time (orchestrator 3.1): `Clock`, `IdFactory` and the patterns of the ids the server hands out.

    task      tsk_<12 hex>                      session   cs_<12 hex> (the org chat is the fixed `cs_org`)
    run       j2-YYYYMMDD-HHMMSS-<4 hex>        request   req-<message id>
    change    chg-NNNN (4 digits or more, the library's ChangeId)

Chart node ids, function node ids, step ids and atom ids are the library's (`slug_id`, `function_node_id`, `step_node_id`,
`function_atom_id`). Times in the database are epoch seconds; the wire shows ISO-8601 with a Z (`iso_z`).
Nothing here reads the real clock except `SystemClock`, so tests inject `testing.FakeClock` and `testing.FakeIds`.
"""
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Protocol

from sutra_app.engine.spec import DEPT_ID_RE, RUN_ID_RE
from sutra_app.library.types import CHANGE_ID_RE

__all__ = [
    "Clock", "SystemClock", "IdFactory", "ORG_SESSION_ID", "ROOT_NODE_ID", "TASK_ID_RE", "SESSION_ID_RE", "REQUEST_ID_RE",
    "URL_ID_RE", "DEPT_ID_RE", "RUN_ID_RE", "is_task_id", "is_session_id", "is_request_id", "is_run_id", "is_url_id",
    "is_dept_id", "iso_z", "parse_iso_z",
]

ORG_SESSION_ID = "cs_org"
ROOT_NODE_ID = "root"
TASK_ID_RE = re.compile(r"tsk_[0-9a-f]{12}")
SESSION_ID_RE = re.compile(r"cs_[0-9a-f]{12}|cs_org")
REQUEST_ID_RE = re.compile(r"req-[0-9]{1,12}")
URL_ID_RE = re.compile(r"[A-Za-z0-9_.:\-]{1,120}")       # every id in a URL path or query (design 6.1)
_ISO_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def is_task_id(value: object) -> bool:
    return isinstance(value, str) and TASK_ID_RE.fullmatch(value) is not None


def is_session_id(value: object) -> bool:
    return isinstance(value, str) and SESSION_ID_RE.fullmatch(value) is not None


def is_request_id(value: object) -> bool:
    return isinstance(value, str) and REQUEST_ID_RE.fullmatch(value) is not None


def is_run_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(RUN_ID_RE, value) is not None


def is_dept_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(DEPT_ID_RE, value) is not None


def is_url_id(value: object) -> bool:
    return isinstance(value, str) and URL_ID_RE.fullmatch(value) is not None


def iso_z(ts: float | int) -> str:
    """Epoch seconds as `2026-11-04T10:00:06Z` (UTC, whole seconds)."""
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_z(text: str) -> int:
    """The inverse of `iso_z`: epoch seconds of `2026-11-04T10:00:06Z`. Anything else is a ValueError."""
    if not isinstance(text, str) or not _ISO_RE.fullmatch(text):
        raise ValueError(f"not an ISO-8601 UTC time like 2026-11-04T10:00:06Z: {str(text)[:40]!r}")
    return int(datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


class Clock(Protocol):
    """The one source of time. `now()` is whole epoch seconds (what the database stores)."""

    def time(self) -> float: ...

    def now(self) -> int: ...


class SystemClock:
    def time(self) -> float:
        return time.time()

    def now(self) -> int:
        return int(time.time())


class IdFactory:
    """Makes the ids the server assigns. Random parts come from `secrets` unless a `token_hex` callable is given."""

    def __init__(self, clock: Clock | None = None, *, token_hex=secrets.token_hex) -> None:
        self._clock = clock or SystemClock()
        self._hex = token_hex

    def task_id(self) -> str:
        return f"tsk_{self._hex(6)}"

    def session_id(self) -> str:
        return f"cs_{self._hex(6)}"

    def run_id(self) -> str:
        """`j2-YYYYMMDD-HHMMSS-<4 hex>` (UTC). The caller retries on a collision (the folder is made with exist_ok=False)."""
        moment = datetime.fromtimestamp(int(self._clock.now()), timezone.utc)
        return f"j2-{moment:%Y%m%d-%H%M%S}-{self._hex(2)}"

    @staticmethod
    def request_id(message_id: int) -> str:
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id < 1:
            raise ValueError("a request id needs the owner's message id, a whole number from 1")
        return f"req-{message_id}"

    @staticmethod
    def change_id(seq: int) -> str:
        """`chg-0002` for seq 2 (the library's ChangeId: at least 4 digits)."""
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
            raise ValueError("a change id needs the row's seq, a whole number from 1")
        text = f"chg-{seq:04d}"
        if not CHANGE_ID_RE.fullmatch(text):
            raise ValueError(f"seq {seq} does not make a change id")
        return text
