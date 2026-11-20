"""The tool-call log of a node's run (MAN-14, D327): `tools.jsonl` in the run folder, one line for each tool call, written by the host as the router reports it and read by the Conductor at
the node's end (`read_log`), which turns it into audit rows. A line is `{"at": seconds, "name", "kind", "target"}`: names and kinds only, a file's base name at most (see
`connectors/tool_audit.py`). It is a small file with a hard limit, written on a best-effort basis: a log that cannot be written never stops a call, and a missing or damaged file is no audit
rows, never an error."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = ["ToolLog", "read_log", "summarize", "TOOLS_FILE", "MAX_LINES", "MAX_READ_BYTES", "MAX_KINDS"]

TOOLS_FILE = "tools.jsonl"
MAX_LINES = 2000                       # the most calls a node's log keeps (the rest are counted in the last line)
MAX_READ_BYTES = 512 * 1024            # the most the server reads of it
MAX_KINDS = 60                         # the most different (name, kind, file) the audit gets for one node
_KINDS = ("read", "edit", "run", "search", "web", "sutra", "github", "other")
log = logging.getLogger(__name__)


class ToolLog:
    """Appends one line for each tool call. It is the router's `on_tool` hook: `log(tag, name, kind, target)`."""

    def __init__(self, path: Path | str, *, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self._clock = clock
        self._lock = threading.Lock()
        self.count = 0
        self._failed = False

    def __call__(self, tag: Any, name: str, kind: str, target: str = "") -> None:
        with self._lock:
            if self._failed:
                return
            self.count += 1
            if self.count > MAX_LINES:                       # the limit: no more lines, so the file stays small
                return
            line = json.dumps({"at": int(self._clock()), "name": str(name), "kind": str(kind), "target": str(target)}, separators=(",", ":"), ensure_ascii=True)
            try:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError as exc:                           # the folder is gone or full: stop trying, never stop the call
                self._failed = True
                log.warning("the tool log %s cannot be written: %s", self.path.name, exc)


def read_log(run_dir: Path | str) -> list[dict[str, Any]]:
    """The valid lines of a run's `tools.jsonl`, at most MAX_LINES; [] for a missing, unreadable or damaged file. A line with a wrong shape or a kind this module does not know is skipped."""
    path = Path(run_dir) / TOOLS_FILE
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_READ_BYTES)
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or row.get("kind") not in _KINDS:
            continue
        rows.append({"name": row["name"][:60], "kind": row["kind"], "target": row["target"][:80] if isinstance(row.get("target"), str) else ""})
        if len(rows) >= MAX_LINES:
            break
    return rows


def summarize(rows: list[dict[str, Any]], limit: int = MAX_KINDS) -> tuple[list[tuple[str, str, str, int]], int]:
    """`([(name, kind, target, times)], left_out)`: the calls grouped by what they were, in the order they first happened, at most `limit` groups; `left_out` is the number of calls in the groups
    that did not fit."""
    groups: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (row["name"], row["kind"], row.get("target", ""))
        groups[key] = groups.get(key, 0) + 1
    ordered = list(groups.items())
    shown = ordered[:limit]
    return [(name, kind, target, times) for (name, kind, target), times in shown], sum(times for _key, times in ordered[limit:])
