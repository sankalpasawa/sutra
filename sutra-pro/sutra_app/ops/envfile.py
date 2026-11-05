"""The `.env` template and its safe creation (`sutra-pro config init`, gaps G03/G09).

    path = create(settings.env_file, generate_override_key=True)      # a new file, mode 0600; FileExistsError when there is one

Only two kinds of names are read from the `.env` file: the owner override key (`J2_OVERRIDE_KEY`, by the server) and the five
`J2_SMTP_*` names (by the engine, for live email). The `SUTRA_*` names are read from the process environment only; the template
lists them as comments so the owner has one place that names them all.
"""
import os
from sutra_app import oslayer
import secrets
from pathlib import Path

from sutra_app.config import ENV_NAMES, OVERRIDE_KEY_NAME
from sutra_app.engine.paths import SMTP_VARS

__all__ = ["render_template", "create", "new_override_key", "mode_problem", "SMTP_VARS", "SUTRA_NAMES"]

# the SUTRA_* names worth listing: the token is made fresh at every launch and the env-file location is not read from the file
SUTRA_NAMES = tuple(name for field, name in ENV_NAMES.items() if field not in ("token", "env_file"))
_HINTS = {
    "SUTRA_DATA_DIR": "where the database, run folders and logs live (default: ./data in a checkout, ~/.sutra-pro installed)",
    "SUTRA_HOST": "loopback only: 127.0.0.1 or localhost",
    "SUTRA_PORT": "an exact port (otherwise the first free one from 8780 to 8799)",
    "SUTRA_CONNECTOR": "auto | claude | codex | stub",
    "SUTRA_ENGINE": "process | fake",
    "SUTRA_OFFLINE": "1: no model calls (stub connector, engine mock mode)",
    "SUTRA_CHAT_TIMEOUT": "seconds one chat turn may take",
    "SUTRA_CHAT_ATTEMPTS": "tries per chat turn, 1 to 5",
    "SUTRA_MAX_RUNS": "teams running at the same time",
    "SUTRA_MAX_LIVE": "most live processes (at least SUTRA_MAX_RUNS)",
    "SUTRA_WATCH_MS": "how often a run's event file is read",
    "SUTRA_LIVE": "1: allow the tests that call the real CLIs",
}


def new_override_key() -> str:
    return secrets.token_urlsafe(24)


def render_template(*, override_key: str | None = None) -> str:
    """The file text. With `override_key` the `J2_OVERRIDE_KEY` line is live; every other line is a comment."""
    key_line = f"{OVERRIDE_KEY_NAME}={override_key}" if override_key else f"# {OVERRIDE_KEY_NAME}="
    smtp = {"J2_SMTP_HOST": "smtp.example.com", "J2_SMTP_PORT": "587", "J2_SMTP_USER": "you@example.com",
            "J2_SMTP_PASSWORD": "", "J2_SMTP_FROM": "you@example.com"}
    lines = [
        "# Sutra Pro environment file. It holds secrets: keep it mode 0600 (`sutra-pro doctor` checks).",
        "# One NAME=value per line. A variable set in the real environment wins over this file.",
        "# Only the J2_OVERRIDE_KEY and J2_SMTP_* lines are read from here.",
        "",
        "# Owner override key: the chat accepts the owner overrides (budget +N, ship, drop) only with it.",
        "# Choose a long random value, or run `sutra-pro config init --generate-override-key` on a new file.",
        key_line,
        "",
        "# Live email (only when the locked setting send_mode is live: `sutra-pro config set send_mode live`).",
        "# All five are needed; the port is the STARTTLS port.",
    ]
    lines += [f"# {name}={smtp[name]}" for name in SMTP_VARS]
    lines += ["", "# The SUTRA_* names below are read from the process environment only (not from this file); they are listed here as a reference."]
    for name in SUTRA_NAMES:
        hint = _HINTS.get(name, "")
        lines.append(f"# {name}=" + (f"    # {hint}" if hint else ""))
    return "\n".join(lines) + "\n"


def create(path: str | os.PathLike[str], *, generate_override_key: bool = False) -> Path:
    """Write a new `.env` at `path` (mode 0600 from the first byte). Raises `FileExistsError` when the file is there already: an
    existing file is never overwritten, and a link is never followed."""
    target = Path(path)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    text = render_template(override_key=new_override_key() if generate_override_key else None)
    fd = os.open(target, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    return target


def mode_problem(path: str | os.PathLike[str]) -> str | None:
    """None when the file is private (no group or other bits); else a sentence naming the mode."""
    try:
        mode = Path(path).stat().st_mode & 0o777
    except OSError:
        return None
    if mode & 0o077:
        return f"mode is {mode:03o}, others can read it"
    return None
