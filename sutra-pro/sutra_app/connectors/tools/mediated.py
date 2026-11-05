"""Claude-held Gmail, Google Drive and Slack: shown, not implemented (connectors design 3.9, CD16, plugin ADR-035).

These connections live inside Claude; Sutra can only look at them, and looking costs a probe: `claude mcp list` contacts every
connector Claude holds and rewrites Claude's own cache. So:

- `snapshot()` reads the last answer and starts nothing; `refresh()` is the manual check, at most once per `min_interval_s`
  (60 s) and single-flight (callers that arrive while one runs share its answer; one that arrives inside the interval gets
  `RefreshTooSoon`, which the API maps to 429).
- `status` is `added` (a `claude.ai ` row names the connector), `not_added` (ONLY when at least one `claude.ai ` row was parsed,
  which proves the server list arrived) or `unknown` (every other path: not asked yet, no CLI, timeout, error, empty output).
  Offline, `claude mcp list` prints "No MCP servers configured." and exits 0, the same as having none: absence of rows is
  never evidence of absence of a connection.
- A row's probe result ("Connected", "Needs authentication") is attributed to Claude's last check in the note, never stated as
  the connector's state: it can change several times an hour while nothing changed.
- No account is shown: `account_known` is always false. The Claude account is never offered in its place.
- The child: fixed argv, `stdin` closed, a fresh empty working directory (the CLI reads `.mcp.json` from its cwd) and the
  project's environment allowlist.

The 2.1.308 output format was not captured (the command mutates Claude state); the parser is built on the hand-written sample.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict

from ..env import child_env
from ..errors import ConnectorError
from ..process import Command, ProcessRunner

__all__ = ["MediatedItem", "MediatedReport", "MediatedConnectors", "RefreshTooSoon", "parse_claude_mcp_list", "KNOWN", "MIN_INTERVAL_S"]

MIN_INTERVAL_S = 60.0
CHECK_TIMEOUT_S = 45.0
# id -> (display name, words that identify the row)
KNOWN: dict[str, tuple[str, tuple[str, ...]]] = {
    "gmail": ("Gmail", ("gmail",)),
    "drive": ("Google Drive", ("drive",)),
    "slack": ("Slack", ("slack",)),
}
_ROW = re.compile(r"^claude\.ai\s+(?P<name>[^:]+?)\s*:\s*(?P<rest>.*)$")
_MARKS = re.compile(r"^[\s✔✓✗✘!•·-]+")


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediatedItem(_Closed):
    name: str
    via: Literal["claude"] = "claude"
    status: Literal["added", "not_added", "unknown"]
    observed_at: Optional[float]
    note: str


class MediatedReport(_Closed):
    truth_class: Literal["observed"] = "observed"
    account_known: Literal[False] = False
    items: list[MediatedItem]


class RefreshTooSoon(RuntimeError):
    """A refresh came inside the interval; `retry_after_s` says how long to wait."""

    def __init__(self, retry_after_s: float) -> None:
        super().__init__(f"Claude's connectors were checked a moment ago: wait {retry_after_s:.0f} s before asking again")
        self.retry_after_s = retry_after_s


def parse_claude_mcp_list(text: str) -> tuple[bool, dict[str, str]]:
    """-> (proof, rows). `proof` is true when at least one line starts with `claude.ai ` (the server list arrived); `rows` maps a
    known connector id to its probe text ("" when the row has none). Anything else, such as local servers, only counts for neither."""
    proof = False
    rows: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("claude.ai "):
            continue
        proof = True                                           # proof of fetch is decoupled from the strict row pattern
        m = _ROW.match(line)
        name = (m.group("name") if m else line[len("claude.ai "):].split(":")[0]).lower()
        for key, (_, words) in KNOWN.items():
            if key not in rows and any(w in name for w in words):
                rest = m.group("rest") if m else ""
                probe = rest.rsplit(" - ", 1)[1] if " - " in rest else ""
                rows[key] = _MARKS.sub("", probe).strip()
    return proof, rows


def _added_note(probe: str) -> str:
    if not probe:
        return "Added in Claude. Its last check result could not be read."
    return f"Added in Claude. Claude's last check reported: {probe[:120]}."


class MediatedConnectors:
    """The three shown-only connectors. `runner` needs `run(cmd, on_line=, timeout_s=) -> ExitInfo` (default: ProcessRunner)."""

    def __init__(self, cfg: Any, *, runner: Optional[ProcessRunner] = None, clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic, min_interval_s: float = MIN_INTERVAL_S,
                 timeout_s: float = CHECK_TIMEOUT_S) -> None:
        self.cfg = cfg
        self._runner = runner or ProcessRunner()
        self._clock, self._mono = clock, monotonic
        self._min_interval = min_interval_s
        self._timeout = timeout_s
        self._lock = threading.Lock()
        self._flight: Optional["_Flight"] = None
        self._last_start: Optional[float] = None
        self._report = self._unknown("Not checked yet. Refresh asks Claude, which probes every connector it holds.", None)

    # ---- reading ---------------------------------------------------------------------------------------------------------------
    def snapshot(self) -> dict:
        """The last answer; starts nothing."""
        with self._lock:
            return self._report.model_dump()

    def refresh(self) -> dict:
        """Ask Claude now. Raises RefreshTooSoon inside the interval; concurrent callers share one run."""
        with self._lock:
            if self._flight is not None:
                flight, leader = self._flight, False
            else:
                if self._last_start is not None and self._mono() - self._last_start < self._min_interval:
                    raise RefreshTooSoon(self._min_interval - (self._mono() - self._last_start))
                flight = self._flight = _Flight()
                self._last_start = self._mono()
                leader = True
        if not leader:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            return flight.result
        try:
            report = self._check()
            with self._lock:
                self._report = report
            flight.result = report.model_dump()
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            with self._lock:
                self._flight = None
            flight.done.set()
        return flight.result

    # ---- the check -------------------------------------------------------------------------------------------------------------
    def _unknown(self, note: str, observed_at: Optional[float]) -> MediatedReport:
        return MediatedReport(items=[MediatedItem(name=n, status="unknown", observed_at=observed_at, note=note) for n, _ in KNOWN.values()])

    def _check(self) -> MediatedReport:
        now = self._clock()
        work = Path(tempfile.mkdtemp(prefix="sutra-mediated-"))
        lines: list[str] = []
        try:
            cmd = Command(argv=(str(self.cfg.claude_exe), "mcp", "list"), cwd=str(work), env=child_env("claude", self.cfg.extra_env),
                          stdin_text=None, provider="claude")
            info = self._runner.run(cmd, on_line=lines.append, timeout_s=self._timeout)
        except ConnectorError as exc:
            reason = "Claude is not installed on this Mac" if exc.code == "cli_missing" else f"Claude could not be started ({exc.code})"
            return self._unknown(f"Status unknown: {reason}.", now)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if info.reason != "exit":
            return self._unknown("Status unknown: Claude did not answer in time.", now)
        if info.returncode != 0:
            return self._unknown(f"Status unknown: Claude's connector check failed (exit {info.returncode}).", now)
        proof, rows = parse_claude_mcp_list("\n".join(lines))
        if not proof:
            return self._unknown("Status unknown: Claude listed no connectors (offline, signed out, or none added: it looks the same).", now)
        items = []
        for key, (name, _) in KNOWN.items():
            if key in rows:
                items.append(MediatedItem(name=name, status="added", observed_at=now, note=_added_note(rows[key])))
            else:
                items.append(MediatedItem(name=name, status="not_added", observed_at=now,
                                          note="Not added in Claude. Add it in Claude's connector directory."))
        return MediatedReport(items=items)


class _Flight:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: Optional[dict] = None
        self.error: Optional[BaseException] = None
