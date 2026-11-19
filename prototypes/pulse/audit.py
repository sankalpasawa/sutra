"""Append-only audit log: <STATE_DIR>/audit.jsonl, 0600, one JSON line per invocation, flock per write.

Opened and lock-tested before any Google call (FR-28). A symlink at the log path is refused (O_NOFOLLOW).
Rows only ever hold the 11 schema fields below; never mail fields, key contents or tokens (FR-33).
"""
import fcntl
import getpass
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from errors import PulseError

FIELDS = ("ts", "os_user", "mode", "command", "mailbox", "query", "rules_file", "reason", "count", "purged",
          "result")
LOCK_WAIT_S = 5.0


def os_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return str(os.getuid())


def build_row(**fields) -> dict:
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError(f"audit row: unknown fields {sorted(unknown)}")
    row = {k: fields.get(k) for k in FIELDS}
    if row["ts"] is None:
        row["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if row["os_user"] is None:
        row["os_user"] = os_user()
    return row


class AuditLog:
    def __init__(self, state_dir):
        self.path = Path(state_dir) / "audit.jsonl"
        self.fd = None
        try:
            os.makedirs(state_dir, mode=0o700, exist_ok=True)
            self.fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            os.fchmod(self.fd, 0o600)
            self._lock()
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        except (OSError, PulseError):
            self.close()
            raise self._unavailable() from None

    def _unavailable(self) -> PulseError:
        return PulseError("audit_unavailable",
                          f"The audit log at {self.path} cannot be opened, locked or written (a symlink is refused). "
                          "Nothing was read.")

    def _lock(self) -> None:
        # Another Pulse run may hold the lock for one write; wait briefly instead of failing (NFR-6).
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise PulseError("audit_unavailable", "lock timeout")
                time.sleep(0.02)

    def write(self, row: dict) -> None:
        if set(row) != set(FIELDS):
            raise ValueError("audit row must have exactly the schema fields")
        data = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self._lock()
            try:
                if os.write(self.fd, data) != len(data):
                    raise OSError("short write")
            finally:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except (OSError, PulseError):
            raise self._unavailable() from None

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
