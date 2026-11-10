"""The inbox: the tailer of `inbox.jsonl` and the FIFO (engine design 4.5 "Inbox rule", S1-contracts-13).

The server appends one JSON object per line: `{"n": int, "kind": "user"|"override"|"stop"|"setting", "text"?: str, "cmd"?: str,
"decide_for_me"?: bool, "at": iso}`.
`InboxTailer` reads the complete lines that arrived since its last call (a half-written line waits for its newline), checks
each one, puts a batch in `n` order and writes an `inbox.skipped` trace line for what it cannot use (bad JSON, bad shape,
an unknown kind, a repeated `n`). `Inbox` adds the FIFO and the delivery rule:

* lines are delivered one at a time, in `n` order, the head first;
* a `user` line is delivered only while `run.status == "waiting"` (paused, or finished but not yet ended) and when
  `run.user_says` takes it; an `override` line goes to `run.apply_override`;
* a `setting` line (J2 sync 4: `{"kind": "setting", "decide_for_me": bool}`, the Simple view's Decide for me switch) is not an answer: it
  is applied with `run.set_auto` as soon as the host looks, whatever the run is doing and whatever waits ahead of it;
* a head that cannot be delivered now stays the head and writes ONE `inbox.deferred` trace line (a normal path: the `say`
  event of a question is written before the run thread has finished its last steps);
* a `stop` line is handled the moment it is read, ahead of the FIFO, and discards everything queued (and the rest of its
  batch), each with an `inbox.discarded` trace line.

Lines that arrive after `close()` (the host calls it when `run.ended` is about to be written) are never read.
"""
import json
import os
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

__all__ = ["InboxLine", "InboxTailer", "Inbox", "KINDS"]

KINDS = ("user", "override", "stop", "setting")
MAX_LINE_BYTES = 1_000_000
Trace = Callable[[str, dict], Any]


@dataclass(frozen=True)
class InboxLine:
    n: int
    kind: str
    text: Optional[str] = None
    cmd: Optional[str] = None
    at: Optional[str] = None
    decide_for_me: Optional[bool] = None


def _parse(raw: bytes) -> InboxLine:
    """One line as an `InboxLine`; raises ValueError with the reason."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"not JSON: {str(exc)[:80]}") from None
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    n, kind = data.get("n"), data.get("kind")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("n must be an integer from 1")
    if kind not in KINDS:
        raise ValueError(f"unknown kind {str(kind)[:40]!r}")
    text, cmd, at = data.get("text"), data.get("cmd"), data.get("at")
    if kind == "user" and (not isinstance(text, str) or not text.strip()):
        raise ValueError("a user line needs text")
    if kind == "override" and (not isinstance(cmd, str) or not cmd.strip()):
        raise ValueError("an override line needs cmd")
    decide = data.get("decide_for_me")
    if kind == "setting" and not isinstance(decide, bool):
        raise ValueError("a setting line needs decide_for_me, true or false")
    return InboxLine(n=n, kind=kind, text=text if kind == "user" else None, cmd=cmd if kind == "override" else None,
                     at=at if isinstance(at, str) else None, decide_for_me=decide if kind == "setting" else None)


class InboxTailer:
    """Reads the new complete lines of the inbox file. A missing file is an empty inbox."""

    def __init__(self, path, trace: Optional[Trace] = None):
        self.path = os.fspath(path)
        self.trace = trace or (lambda type, data: None)
        self._offset = 0
        self._seen: set[int] = set()

    def read_new(self) -> list[InboxLine]:
        try:
            with open(self.path, "rb") as f:
                size = os.fstat(f.fileno()).st_size
                if size < self._offset:                  # the file was replaced by a shorter one: start again
                    self._offset = 0
                f.seek(self._offset)
                chunk = f.read(max(size - self._offset, 0))
        except OSError:
            return []
        end = chunk.rfind(b"\n")
        if end < 0:                                      # no complete line yet (or a torn one: wait for its newline)
            if len(chunk) > MAX_LINE_BYTES:
                self._offset += len(chunk)
                self.trace("inbox.skipped", {"reason": "line longer than 1 MB without a newline"})
            return []
        self._offset += end + 1
        found: list[InboxLine] = []
        for raw in chunk[:end].split(b"\n"):
            if not raw.strip():
                continue
            try:
                line = _parse(raw)
            except ValueError as exc:
                self.trace("inbox.skipped", {"reason": str(exc), "line": raw[:120].decode("utf-8", "replace")})
                continue
            if line.n in self._seen:
                self.trace("inbox.skipped", {"reason": "repeated n", "n": line.n})
                continue
            self._seen.add(line.n)
            found.append(line)
        return sorted(found, key=lambda line: line.n)


class Inbox:
    def __init__(self, path, trace: Optional[Trace] = None):
        self.trace = trace or (lambda type, data: None)
        self.tailer = InboxTailer(path, self.trace)
        self.fifo: deque[InboxLine] = deque()
        self.closed = False
        self._deferred_n: Optional[int] = None

    def __len__(self) -> int:
        return len(self.fifo)

    def close(self) -> None:
        """Nothing is read after this (the run is over)."""
        self.closed = True

    def poll(self) -> Optional[InboxLine]:
        """Read new lines into the FIFO. Returns the `stop` line when one was read (the FIFO is then empty); else None."""
        if self.closed:
            return None
        batch = self.tailer.read_new()
        for i, line in enumerate(batch):
            if line.kind == "stop":
                for dropped in [*self.fifo, *batch[i + 1:]]:      # the FIFO already holds the lines of this batch before the stop
                    self.trace("inbox.discarded", {"n": dropped.n, "kind": dropped.kind, "by": line.n})
                self.fifo.clear()
                return line
            self.fifo.append(line)
        return None

    def deliver(self, run) -> bool:
        """Try the head of the FIFO against `run`. True when a line was delivered (it is removed); False when the FIFO is
        empty or the head must wait (one `inbox.deferred` trace line per head)."""
        if not self.fifo:
            return False
        for i, line in enumerate(self.fifo):          # a setting jumps the queue: it is not an answer and never waits for the run to stop
            if line.kind == "setting":
                del self.fifo[i]
                run.set_auto(bool(line.decide_for_me))
                return True
        head = self.fifo[0]
        if head.kind == "user":
            taken = run.status == "waiting" and bool(run.user_says(head.text))
        else:
            taken = bool(run.apply_override(head.cmd))
        if taken:
            self.fifo.popleft()
            self._deferred_n = None
            return True
        if self._deferred_n != head.n:
            self._deferred_n = head.n
            self.trace("inbox.deferred", {"n": head.n, "kind": head.kind, "status": run.status})
        return False
