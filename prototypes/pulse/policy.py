"""Mailbox, domain, allowlist, reason and key-file checks. All run before any Google call.

Messages hold paths and mailbox addresses only, never file contents (FR-33).
"""
import json
import os
import re
import stat
from pathlib import Path

from errors import PulseError

MAILBOX_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+$")
REASON_MIN, REASON_MAX = 10, 500


def normalise_mailbox(raw: str) -> str:
    """Trim and lowercase; raise ValueError if the format is wrong (argparse turns it into usage)."""
    m = (raw or "").strip().lower()
    if not MAILBOX_RE.match(m):
        raise ValueError("--mailbox must look like name@domain, using only letters, digits and . _ % + -")
    return m


def check_reason(raw: str) -> str:
    r = (raw or "").strip()
    if not REASON_MIN <= len(r) <= REASON_MAX:
        raise ValueError(f"--reason must be {REASON_MIN} to {REASON_MAX} characters, saying why this mailbox is read")
    return r


def check_domain(mailbox: str, domain: str) -> None:
    if not domain or mailbox.rsplit("@", 1)[-1] != domain:
        raise PulseError("wrong_domain",
                         f"Refused: {mailbox} is not in the configured domain {domain or '(none)'}. Nothing was read.")


def load_allowlist(path) -> frozenset:
    if path is None:
        return frozenset()
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return frozenset()
    out = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            out.add(line)
    return frozenset(out)


def check_allowlist(mailbox: str, path) -> None:
    if mailbox not in load_allowlist(path):
        raise PulseError("not_allowlisted",
                         f"Refused: {mailbox} is not in the allowlist {path or '(not set)'} "
                         "(a missing or unreadable allowlist refuses every mailbox). Nothing was read.")


KEY_FIELDS = ("client_email", "private_key", "token_uri")  # google-auth requires all three (R1-6)


def key_unreadable(path) -> PulseError:
    return PulseError("key_unreadable",
                      f"The key file at {path} is not a readable service-account JSON key. Check PULSE_SA_KEY_PATH.")


def check_key_file(path) -> list:
    """Raise key_missing / key_unreadable; return warnings (for example loose permissions)."""
    p = Path(path)
    if not p.exists():
        raise PulseError("key_missing", f"No key file at {p}. Check PULSE_SA_KEY_PATH.")
    unreadable = key_unreadable(p)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        raise unreadable from None
    ok = (isinstance(data, dict) and data.get("type") == "service_account"
          and all(isinstance(data.get(k), str) and data.get(k) for k in KEY_FIELDS))
    del data
    if not ok:
        raise unreadable
    warnings = []
    mode = stat.S_IMODE(os.stat(p).st_mode)
    if mode & 0o044:
        warnings.append(f"Warning: the key file {p} is readable by group or others. Run: chmod 600 {p}")
    return warnings
