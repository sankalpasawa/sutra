"""Egress scrub and audit row for every prompt that leaves for a CLI (absorb design 2.4, D109; ported from the old `switch_egress.py`).

Credential SHAPES (and, when a `Redactor` is given, the app's known secret VALUES) are matched in the outgoing text. Two modes:

  replace   ChatPort and the orchestrator's JSON calls: each match becomes `[redacted:<shape>]`
  observe   ModelPort (J2's agents): the text is returned byte-identical; only the audit row is written (J2's prompts are not ours to edit)

The audit row (`<data>/connectors/egress.jsonl`, append only, 0600) holds time, session, provider, mode, byte count and shape names with
counts. Never a payload, never a match. A write failure never stops a call; it is logged and the row is returned with `log_error`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from sutra_app import oslayer

__all__ = ["SHAPES", "Egress", "scan", "scrubbed"]

log = logging.getLogger(__name__)
MAX_ROW_BYTES = 8192
_PEM_BODY = r".{0,20000}?"                                    # bounded: many BEGIN lines and no END cannot go quadratic

# What an assignment's value may hold: letters, digits and the symbols a password or a key carries, never a bracket, a quote or a space, so
# `password = hash(password)` and a quoted sentence are not mistaken for a value.
_VALUE = r"['\"]?[A-Za-z0-9._~\-/+!@#$%^&*=:?]{12,}['\"]?"
_NOT_PART_OF_A_WORD = r"(?<![A-Za-z0-9])"                      # `OPENAI_API_KEY=` counts (an underscore is not a letter); `mypassword=` does not
_AFTER_NAME = r"['\"]?\s*[=:]\s*"                              # `name=`, `name: ` and the JSON or dict form `"name": `

SHAPES: list[tuple[str, "re.Pattern[str]", bool]] = [        # (name, pattern, keep the prefix group)
    ("openai-key", re.compile(r"sk-[A-Za-z0-9_-]{8,}"), False),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), False),                     # ghp (personal), gho (OAuth: what `gh auth token` prints), ghu, ghs, ghr
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), False),
    ("slack-token", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), False),
    ("aws-key-id", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}"), False),           # AKIA long-lived, ASIA temporary (STS)
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"), False),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), False),
    ("pem-private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----" + _PEM_BODY + r"-----END [A-Z ]*PRIVATE KEY(?: BLOCK)?-----", re.DOTALL), False),
    ("stripe-key", re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"), False),
    ("slack-webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{10,}"), False),
    ("discord-webhook", re.compile(r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]{10,}"), False),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{30,}"), False),
    ("gitlab-token", re.compile(r"glpat-[A-Za-z0-9_-]{20,}"), False),
    ("npm-token", re.compile(_NOT_PART_OF_A_WORD + r"npm_[A-Za-z0-9]{30,}"), False),
    ("huggingface-token", re.compile(_NOT_PART_OF_A_WORD + r"hf_[A-Za-z0-9]{30,}"), False),
    ("sendgrid-key", re.compile(_NOT_PART_OF_A_WORD + r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"), False),
    # `Basic <base64 of user:password>`: the word "basic" is common, so the value must look like base64 (a digit, + or /, or = padding)
    ("basic-auth", re.compile(r"\b[Bb]asic\s+(?:(?=[A-Za-z0-9+/]*[0-9+/])[A-Za-z0-9+/]{16,}={0,2}|[A-Za-z0-9+/]{16,}={1,2})"), False),
    ("db-uri-credentials", re.compile(r"(?i)\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://)[^\s/@]*:[^\s]*@(?=[^\s@/]+)"), True),
    ("private-key-env", re.compile(
        r"(?i)" + _NOT_PART_OF_A_WORD + r"((?:api[_-]?key|secret[_-]?(?:access[_-]?)?key|client[_-]?secret|(?:access|auth|refresh)[_-]?token"
        r"|private[_-]?key|password|passwd|passphrase)" + _AFTER_NAME + r")" + _VALUE), True),
    # a bare `token` or `secret` is also an ordinary word: its value must hold a digit, as a real token does (`token: refresh it daily` stays)
    ("private-key-env", re.compile(r"(?i)" + _NOT_PART_OF_A_WORD + r"((?:token|secret)" + _AFTER_NAME + r")(?=['\"]?[A-Za-z0-9._~\-/+!@#$%^&*=:?]*[0-9])" + _VALUE), True),
]


def scan(text: str, *, replace: bool = False) -> tuple[str, dict[str, int]]:
    """`(text, {shape: count})`. With `replace` False the text comes back unchanged."""
    counts: dict[str, int] = {}
    for name, pattern, keep in SHAPES:
        if replace:
            text, n = pattern.subn((r"\1" if keep else "") + f"[redacted:{name}]", text)
        else:
            n = sum(1 for _ in pattern.finditer(text))
        if n:
            counts[name] = counts.get(name, 0) + n                    # a shape may have more than one pattern
    return text, counts


def scrubbed(text: str, redact: Optional[Callable[[str], str]] = None) -> str:
    """`text` with the app's secret values (through `redact`, the app's `Redactor`, when given) and every credential shape replaced. What the
    owner types is put through this where it enters (a chat line, a task, a team answer, a schedule), so the stored line, the line a model gets
    and the files of a run are one and the same text and no secret ever lands in a store."""
    return scan(redact(text) if redact is not None else text, replace=True)[0]


class Egress:
    def __init__(self, path: "str | os.PathLike[str]", redactor: Any = None) -> None:
        self.path = Path(path)
        self.redactor = redactor
        self._lock = threading.Lock()

    def check(self, text: str, *, session: Optional[str], provider: str, replace: bool, system: str = "") -> str:
        """The text to send (scrubbed when `replace`), after writing the audit row."""
        counts: dict[str, int] = {}
        out = text
        if self.redactor is not None:
            values = self.redactor.secrets()
            hits = sum(out.count(v) for v in values)
            if hits:
                counts["secret-value"] = hits
                if replace:
                    for v in values:
                        out = out.replace(v, "[redacted:secret-value]")
        out, shapes = scan(out, replace=replace)
        counts.update(shapes)
        self._record({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "session": session or "-", "provider": provider,
                      "mode": "replace" if replace else "observe", "bytes": len((system + text).encode("utf-8")), "shapes": counts})
        return out if replace else text

    def _record(self, row: dict) -> None:
        line = json.dumps(row, sort_keys=True) + "\n"
        if len(line.encode("utf-8")) > MAX_ROW_BYTES:
            line = json.dumps({"time": row["time"], "log_error": "row too large, not written"}) + "\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self.path, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    try:
                        os.fchmod(fd, 0o600)
                    except (OSError, AttributeError):
                        pass
                    os.write(fd, line.encode("utf-8"))
                finally:
                    os.close(fd)
        except OSError:
            log.warning("could not write the egress audit row", exc_info=True)

    def rows(self, limit: int = 50) -> list[dict]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        except OSError:
            return []
        return [json.loads(x) for x in lines if x.strip()]
