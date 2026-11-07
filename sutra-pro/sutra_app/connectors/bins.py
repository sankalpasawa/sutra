"""The CLI file the owner chose in Settings, per provider (GAP-providers; the old app's providers.py `set_provider_bin` and `_bin_for`).

    <data>/connectors/bins.json     {"version": 1, "bins": {"claude": "/full/path/to/claude", "codex": "..."}}   mode 0600, atomic

An environment variable is a useless escape hatch for an app opened from Finder, so the choice is a file the Settings page writes.
`set(provider, path)` checks the path when it is written: a full path (a leading ~ is the owner's home folder) to a regular file that can
be run and is named as the provider's command (claude, codex; with .exe or .cmd on Windows). Anything else is refused with the reason
(InvalidRequestError, a 422), because storing it would turn "cannot find it" into "found it and it will not run", a worse error further
from the mistake. The name is the name of the path as chosen, not of its target: an nvm, Volta or native-installer command is a link to a
file with another name. `load()` gives only paths that are still executable files: a stored path that has since vanished is ignored, not
honoured, so a CLI installed elsewhere afterwards is found again. Nothing here runs the file.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import ValidationError

from sutra_app import oslayer

from .base import write_private_file
from .errors import InvalidRequestError
from .models import M

__all__ = ["BinStore", "BinsFile", "BINS_FILE", "CHOOSABLE", "check_path", "is_executable_file"]

log = logging.getLogger("sutra_app.connectors.bins")

BINS_FILE = "bins.json"
CHOOSABLE = ("claude", "codex")
MAX_PATH = 1024
_NAMES = {"claude": "Claude", "codex": "Codex"}


class BinsFile(M):
    version: Literal[1] = 1
    bins: dict[Literal["claude", "codex"], str] = {}


def is_executable_file(path: str) -> bool:
    """A regular file (a link to one counts) that this user may run."""
    try:
        return os.path.isfile(path) and os.access(path, os.X_OK)
    except (OSError, ValueError):
        return False


def _allowed_names(provider: str) -> set[str]:
    return {provider, f"{provider}.exe", f"{provider}.cmd"} if oslayer.IS_WINDOWS else {provider}


def _named_as_its_command(provider: str, path: str) -> bool:
    """A full path whose last part is the provider's command: the part of `check_path` that needs no file on disk. The file is not trusted
    to have come from `set` (a restored or copied data folder, a hand edit), so `stored` asks this of every entry it reads."""
    return os.path.isabs(path) and os.path.basename(os.path.normpath(path)) in _allowed_names(provider)


def check_path(provider: str, raw: str, *, home: Optional[str] = None) -> str:
    """The full path of the chosen file, or InvalidRequestError with the sentence the owner reads."""
    if provider not in CHOOSABLE:
        raise InvalidRequestError(f"{provider} has no command-line file to choose")
    name = _NAMES[provider]
    text = raw.strip() if isinstance(raw, str) else ""
    if not text or len(text) > MAX_PATH or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise InvalidRequestError(f"Write the full path of the {provider} command, as `which {provider}` prints it in Terminal")
    if text == "~" or text.startswith("~/"):
        text = (home or os.path.expanduser("~")) + text[1:]
    if not os.path.isabs(text):
        raise InvalidRequestError(f"Write the full path, starting with / (or ~ for your home folder), as `which {provider}` prints it")
    full = os.path.normpath(text)
    if os.path.basename(full) not in _allowed_names(provider):
        raise InvalidRequestError(f"Choose the file named {provider}: {os.path.basename(full)} is not the {name} command")
    if not os.path.lexists(full):
        raise InvalidRequestError(f"There is no file at {full}")
    if os.path.isdir(full):
        raise InvalidRequestError(f"{full} is a folder, not the {provider} command")
    if not is_executable_file(full):
        raise InvalidRequestError(f"{full} cannot be run: it is not a file this account may run")
    return full


class BinStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "connectors" / BINS_FILE
        self._lock = threading.Lock()

    def stored(self) -> dict[str, str]:
        """What the file holds ({} when there is none or it does not read); a path may have vanished since. An entry that is not named as its
        provider's command is left out, as `check_path` would have refused it: the file runs as the model CLI, so it is never taken on trust."""
        try:
            found = dict(BinsFile.model_validate(json.loads(self.path.read_text(encoding="utf-8"))).bins)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, ValidationError) as exc:
            log.warning("the CLI path file %s is not used (%s)", self.path, type(exc).__name__)
            return {}
        kept = {provider: path for provider, path in found.items() if _named_as_its_command(provider, path)}
        if len(kept) != len(found):
            log.warning("the CLI path file %s names a path that is not its provider's command; that entry is not used", self.path)
        return kept

    def load(self) -> dict[str, str]:
        """The stored paths that are still executable files."""
        return {provider: path for provider, path in self.stored().items() if is_executable_file(path)}

    def set(self, provider: str, path: Optional[str], *, home: Optional[str] = None) -> Optional[str]:
        """Store the checked path for `provider`, or forget the choice when `path` is None or empty. Returns what is stored."""
        chosen = check_path(provider, path, home=home) if isinstance(path, str) and path.strip() else None
        if provider not in CHOOSABLE:
            raise InvalidRequestError(f"{provider} has no command-line file to choose")
        with self._lock:
            bins = self.stored()
            if chosen is None:
                bins.pop(provider, None)
            else:
                bins[provider] = chosen
            body = BinsFile(bins=bins).model_dump_json(indent=2)                 # type: ignore[arg-type]
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self.path.parent / f".{self.path.name}.{uuid.uuid4().hex[:8]}.tmp"
            try:
                write_private_file(tmp, body)
                oslayer.replace(tmp, self.path)
            finally:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
        return chosen
