"""The working folder (GAP3-workdir): the one folder of the owner's own files that a chat may read.

    <data>/connectors/workdir.json     {"version": 1, "path": "/full/path/of/the/folder"}      mode 0600, atomic

Until now every chat ran its CLI in a private empty folder, so the model could not see a single file of the owner. The owner now chooses ONE
folder in Settings; a chat turn (a direct chat, and the org chat agent) then runs the CLI with that folder as the child's working directory and
read-only file tools (claude.py, codex.py). The engine's department runs are not touched: they never ask this store.

`WorkFolder.set(path)` checks the path when it is written: absolute (a leading ~ is the owner's home folder), existing, a folder, readable, then
resolved with realpath (a link to a folder is stored as the folder it leads to, so what the owner sees is what the CLI gets). It refuses the
filesystem root, the app's own data folder and the app's work root, and anything inside them: the model must never be able to read the app's
database, its launch token or other chats' state. A refused path writes nothing and says why (InvalidRequestError, a 422).

`get()` is read on EVERY chat turn, so a change applies to the next message; it gives the stored folder only while it is still a readable folder
outside the app's own folders (a folder that has since vanished is ignored, not honoured, so a chat never starts a CLI in a missing directory).
`preview()` is what the model will be able to see at the top: the names of the folder's entries (folders first, at most 60, with the total),
never a file's contents; an entry that cannot be read is skipped. Nothing here runs a process or reads a file's contents.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import ValidationError

from sutra_app import oslayer

from .base import write_private_file
from .errors import InvalidRequestError
from .models import M

__all__ = ["WorkFolder", "WorkdirFile", "WORKDIR_FILE", "MAX_PATH", "PREVIEW_MAX", "check_folder", "preview_of", "grounding_text",
           "READ_TOOLS", "NO_FOLDER_TEXT"]

log = logging.getLogger("sutra_app.connectors.workdir")

WORKDIR_FILE = "workdir.json"
MAX_PATH = 1024
PREVIEW_MAX = 60               # names shown in the preview
SCAN_MAX = 20_000              # entries looked at before the count stops (a huge folder must not stall the page)
NAME_CHARS = 120
READ_TOOLS = ("Read", "Glob", "Grep", "LS")        # the claude tools a chat gets with a folder: all read-only

NO_FOLDER_TEXT = ("No working folder is set, so you cannot see any of the owner's files. When the owner asks about their files, a project or a "
                  "folder, say so and tell them to choose one in Settings, under Connectors, in Working folder.")


class WorkdirFile(M):
    version: Literal[1] = 1
    path: str


def _inside(path: str, parent: str) -> bool:
    """`path` is `parent` or lies below it (case-insensitive where the file system is: Windows, and macOS by default)."""
    a, b = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(parent))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _is_root(path: str) -> bool:
    return os.path.dirname(path) == path


def check_folder(raw: Any, *, data_dir: "str | Path", work_root: "str | Path | None" = None, home: Optional[str] = None) -> str:
    """The resolved full path of the chosen folder, or InvalidRequestError with the sentence the owner reads."""
    text = raw.strip() if isinstance(raw, str) else ""
    if not text or len(text) > MAX_PATH or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise InvalidRequestError("Write the full path of the folder, for example ~/Documents/my-project")
    if text == "~" or text.startswith("~/") or (oslayer.IS_WINDOWS and text.startswith("~\\")):
        text = (home or os.path.expanduser("~")) + text[1:]
    if not os.path.isabs(text):
        raise InvalidRequestError("Write the full path, starting with / (or ~ for your home folder)")
    if not os.path.lexists(text):
        raise InvalidRequestError(f"There is no folder at {text}")
    real = os.path.realpath(text)
    if not os.path.isdir(real):
        raise InvalidRequestError(f"{text} is a file, not a folder")
    if _is_root(real):
        raise InvalidRequestError("Choose a folder of your own, not the top of the whole disk")
    own = [os.path.realpath(str(data_dir))] + ([os.path.realpath(str(work_root))] if work_root is not None else [])
    if any(_inside(real, folder) for folder in own):
        raise InvalidRequestError("That folder belongs to Sutra itself (its data and chat state). Choose a folder of your own")
    if not os.access(real, os.R_OK | os.X_OK):
        raise InvalidRequestError(f"{real} cannot be read by this account")
    return real


def _clean_name(name: str) -> str:
    return "".join("?" if ord(c) < 32 or ord(c) == 127 else c for c in name)[:NAME_CHARS]


def preview_of(path: str, *, limit: int = PREVIEW_MAX) -> dict:
    """The top of the folder as the model will see it: `{entries: [{name, kind}], total, shown, capped, readable}`. Names only, folders first
    and then by name; an entry that cannot be read is skipped and not counted."""
    found: list[tuple[bool, str, str]] = []
    capped = False
    try:
        with os.scandir(path) as it:
            for entry in it:
                if len(found) >= SCAN_MAX:
                    capped = True
                    break
                try:
                    is_dir = entry.is_dir()
                    entry.stat()                   # an entry that cannot be read (a dead link, no rights) is skipped
                except OSError:
                    continue
                found.append((not is_dir, entry.name.casefold(), entry.name))      # (is a file, sort key, name): folders sort first
    except OSError:
        return {"entries": [], "total": 0, "shown": 0, "capped": False, "readable": False}
    found.sort()
    shown = [{"name": _clean_name(name), "kind": "file" if is_file else "dir"} for is_file, _, name in found[:limit]]
    return {"entries": shown, "total": len(found), "shown": len(shown), "capped": capped, "readable": True}


def grounding_text(folder: Optional[str]) -> str:
    """What a chat model is told about the folder: where it is and that its file tools are read-only, or that none is set and how to set one.
    The one source of the words (chat_ground.py puts it in every direct chat's system text; the router adds it to the org agent's calls)."""
    if not folder:
        return NO_FOLDER_TEXT
    shown = folder if len(folder) <= 300 else folder[:299] + "…"
    return (f"Working folder: {shown}\n"
            "You can look at the owner's files there with your file tools (read, list and search). They are read-only: you cannot create, change or "
            "delete a file, and you cannot run a command. Paths are relative to that folder. When the owner mentions their files, a project or a folder, "
            "look there first, starting with a listing of the folder itself, and say which files you read.")


class WorkFolder:
    """The store: one small file next to the connector policy. Safe to call from any thread; every read goes to the file."""

    def __init__(self, data_dir: "str | Path", work_root: "str | Path | None" = None) -> None:
        self.data_dir = Path(data_dir)
        self.work_root = Path(work_root) if work_root is not None else None
        self.path = self.data_dir / "connectors" / WORKDIR_FILE
        self._lock = threading.Lock()

    # ---- reads -----------------------------------------------------------------------------------------------------------------
    def stored(self) -> Optional[str]:
        """What the file holds (None when there is none or it does not read); the folder may have vanished since."""
        try:
            return WorkdirFile.model_validate(json.loads(self.path.read_text(encoding="utf-8"))).path
        except FileNotFoundError:
            return None
        except (OSError, ValueError, ValidationError) as exc:
            log.warning("the working folder file %s is not used (%s)", self.path, type(exc).__name__)
            return None

    def problem(self, stored: Optional[str] = None) -> Optional[str]:
        """Why the stored folder cannot be used now, in words; None when it can (or none is stored)."""
        found = self.stored() if stored is None else stored
        if found is None:
            return None
        try:
            check_folder(found, data_dir=self.data_dir, work_root=self.work_root)
        except InvalidRequestError as exc:
            return exc.user_message()
        return None

    def get(self) -> Optional[str]:
        """The folder a chat turn uses now: the stored one while it is still a usable folder, else None."""
        found = self.stored()
        return found if found is not None and self.problem(found) is None else None

    def preview(self) -> Optional[dict]:
        found = self.get()
        return None if found is None else preview_of(found)

    # ---- writes ----------------------------------------------------------------------------------------------------------------
    def set(self, raw: Any, *, home: Optional[str] = None) -> str:
        """Store the checked folder; returns what is stored. Raises InvalidRequestError (with the reason) and writes nothing."""
        chosen = check_folder(raw, data_dir=self.data_dir, work_root=self.work_root, home=home)
        self._write(WorkdirFile(path=chosen).model_dump_json(indent=2))
        return chosen

    def clear(self) -> None:
        """Forget the choice; chats go back to the private empty folder."""
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    def _write(self, body: str) -> None:
        with self._lock:
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
