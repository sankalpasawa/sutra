"""The working folder (GAP3-workdir): the one folder of the owner's own files that a chat may read.

    <data>/connectors/workdir.json     {"version": 1, "path": "/full/path/of/the/folder"}      mode 0600, atomic

Until now every chat ran its CLI in a private empty folder, so the model could not see a single file of the owner. The owner now chooses ONE
folder in Settings; a chat turn (a direct chat, a team's chat, and the org chat agent) then runs the CLI with that folder as the child's working
directory (claude.py, codex.py). The owner also says what the team may do there: `read` (read-only file tools) or `edit` (the same, plus changing
files and looking at git; no other command). The project's own instructions (CLAUDE.md, AGENTS.md) at the top of the folder go to the model with
the folder's name (`instructions_of`). A department's document or website run of the engine is not touched: it never asks this store.

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

__all__ = ["WorkFolder", "WorkdirFile", "Folder", "WORKDIR_FILE", "MAX_PATH", "PREVIEW_MAX", "check_folder", "preview_of", "grounding_text",
           "instructions_of", "READ_TOOLS", "EDIT_TOOLS", "GIT_READ", "GIT_DENY", "DOT_GIT_DENY", "NO_FOLDER_TEXT", "TEAM_EDIT_TEXT", "TEAM_READ_TEXT",
           "ACCESS", "INSTRUCTION_FILES", "INSTRUCTIONS_MAX"]

log = logging.getLogger("sutra_app.connectors.workdir")

WORKDIR_FILE = "workdir.json"
MAX_PATH = 1024
PREVIEW_MAX = 60               # names shown in the preview
SCAN_MAX = 20_000              # entries looked at before the count stops (a huge folder must not stall the page)
NAME_CHARS = 120
READ_TOOLS = ("Read", "Glob", "Grep", "LS")        # the claude tools a chat gets with a folder: all read-only
EDIT_TOOLS = ("Edit", "MultiEdit", "Write")        # added when the owner lets the team change files in the folder (access "edit")
GIT_READ = ("Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)")      # the only commands a team may run, with "edit"
GIT_DENY = ("Bash(git*--output*)", "Bash(git*--no-index*)", "Bash(git*--ext-diff*)", "Bash(git*--textconv*)", "Bash(git*-c *)", "Bash(git*--exec-path*)")
DOT_GIT_DENY = ("Edit(.git)", "Edit(.git/**)", "Edit(**/.git/**)")    # Edit rules also bind MultiEdit and Write: the repository's own state is not the team's to write
ACCESS = ("read", "edit")
INSTRUCTION_FILES = ("CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md")      # the project's own instructions, the first one that exists is read
INSTRUCTIONS_MAX = 12_000          # characters of them given to the model (a longer file is cut with a note)

NO_FOLDER_TEXT = ("No working folder is set, so you cannot see any of the owner's files. When the owner asks about their files, a project or a "
                  "folder, say so and tell them to choose one in Settings, under Connectors, in Working folder.")

# What the TEAM of an engine run may do in the folder (D135), added to the grounding of every agent whose own tools do not change files. The first
# is for a run of an output whose builders change files when the owner chose "read and change"; the second when the same run meets "read only".
TEAM_EDIT_TEXT = ("The owner allowed changes to this folder (Settings, under Working folder). In this run the team's builders can create and change "
                  "files there and look at git status, diff, log and show; nobody commits or runs anything else. Plan and judge as a team that CAN change "
                  "the folder: when the request is to update, implement, fix, change or add something, the change is made in the folder (the plan names "
                  "the files to change), not only described. Never write that the folder is read-only: for this run it is not.")
TEAM_READ_TEXT = ("The owner chose read only for this folder (Settings, under Working folder), so nobody on this team can create, change or delete a "
                  "file in it. When the request asks for a change, say so plainly: the report gives the exact edits (file by file, what to change) and "
                  "tells the owner to allow changes in Settings, under Working folder, and ask again.")


class WorkdirFile(M):
    version: Literal[1] = 1
    path: str
    access: Literal["read", "edit"] = "read"       # a file written before the owner could choose stays read-only


class Folder(str):
    """The folder of one chat turn: the path itself (every place that compares or joins it sees a plain string) that also says whether THIS call may
    change files in it. The connectors read `.edit` when they choose the tools; nothing else needs to know.

    `team` is what the grounding says about the team the call belongs to (D135), for the engine's runs only: `edit` (this run's builders can change
    files here and the owner allowed it), `read` (the run is built to change files but the owner chose read only: nobody can), or `` (nothing is
    said about a team: a direct chat, the org agent, an output whose builders only read). It changes the words of `grounding_text`, never the tools.

    `git` says the call may run the four git reads (status, diff, log, show) without being able to change a file (Audit of a run whose builders change
    files, D135); a call that may edit has them anyway. The claude connector adds Bash restricted to those reads and the same deny list as for an edit."""

    edit: bool = False
    team: str = ""
    git: bool = False

    def __new__(cls, path: str, edit: bool = False, team: str = "", git: bool = False) -> "Folder":
        found = super().__new__(cls, path)
        found.edit = bool(edit)
        found.team = team if team in ("edit", "read") else ""
        found.git = bool(git)
        return found


def _inside(path: str, parent: str) -> bool:
    """`path` is `parent` or lies below it. Spelled alike first (normcase folds the case on Windows only); then the folders themselves are compared,
    because macOS's default file system ignores case (and Unicode form) while `normcase` there changes nothing, and realpath does not repair a
    spelling: `<data>` typed in another case is still `<data>` on disk. Some folder from `path` up to the top is `parent` itself, or it is not inside."""
    a, b = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(parent))
    if a == b or a.startswith(b.rstrip("\\/") + os.sep):
        return True
    here = path
    while True:
        try:
            if os.path.samefile(here, parent):
                return True
        except OSError:                                    # `parent` is not there (nothing to be inside of) or this level cannot be read: go on up
            pass
        up = os.path.dirname(here)
        if up == here:
            return False
        here = up


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
    if any(_inside(folder, real) for folder in own):         # a folder that holds Sutra's own folders (the home folder) would let the file tools read them
        raise InvalidRequestError("That folder holds Sutra's own data folder, and the model could read it from there. Choose a folder inside it, "
                                  "for example the folder of your project")
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


def instructions_of(folder: str) -> tuple[str, str]:
    """`(file name, text)` of the project's own instructions (CLAUDE.md, then .claude/CLAUDE.md, then AGENTS.md) at the top of the folder, cut to
    INSTRUCTIONS_MAX characters; `("", "")` when there is none or it cannot be read. A file that is a link out of the folder is not read: the folder's
    own words are what the owner put there, not what a link leads to."""
    root = os.path.realpath(folder)
    for name in INSTRUCTION_FILES:
        path = os.path.join(root, *name.split("/"))
        try:
            if os.path.islink(path) or not os.path.isfile(path) or not _inside(os.path.realpath(path), root):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(INSTRUCTIONS_MAX + 1)
        except OSError:
            continue
        text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32).strip()
        if not text:
            continue
        return name, (text[:INSTRUCTIONS_MAX] + "\n(the rest of this file is cut; read it with your file tools)") if len(text) > INSTRUCTIONS_MAX else text
    return "", ""


def grounding_text(folder: Optional[str], edit: Optional[bool] = None, team: Optional[str] = None) -> str:
    """What a chat model is told about the folder: where it is, what its tools can do, and the project's own instructions; or that none is set and
    how to set one. The one source of the words (chat_ground.py puts it in every direct chat's system text; the router adds it to the org agent's
    calls and to every agent call of the engine). `edit` and `team` default to the folder's own marks (a `Folder` the router read from the store).

    A call whose own tools only read may belong to a team that can change files (Identity plans, the builders write): then the text says what the TEAM
    may do (`team` `edit`), or that the owner chose read only so nobody can (`team` `read`), and not only what this agent's own tools do. Saying only
    "they are read-only" made a planner write the folder's limit into the charter of a run whose owner had allowed changes (D135)."""
    if not folder:
        return NO_FOLDER_TEXT
    allowed = bool(getattr(folder, "edit", False)) if edit is None else edit
    crew = getattr(folder, "team", "") if team is None else team
    git = bool(getattr(folder, "git", False)) and not allowed
    shown = folder if len(folder) <= 300 else folder[:299] + "…"
    look = "You can look at the owner's files there with your file tools (read, list and search)"
    if allowed:
        tools = ("You work in the owner's project like a developer at their desk. You can read, list and search the files there, and you can create and change "
                 "files with your file tools. You can look at the project's git state (status, diff, log, show) but you cannot run anything else and you cannot "
                 "commit: the owner does that. Paths are relative to that folder.")
    elif crew == "edit":
        tools = (look + (" and at the project's git state (status, diff, log, show), so you can check what was changed" if git else "") +
                 ". Your own tools do not change files, because you plan and check the work and the builders do the changing: that is not a limit of this "
                 "run. " + TEAM_EDIT_TEXT + " Paths are relative to that folder.")
    elif git:
        tools = (look + " and at the project's git state (status, diff, log, show). They are read-only: you cannot create, change or delete a file, and you "
                 "can run only those git reads." + (" " + TEAM_READ_TEXT if crew == "read" else "") + " Paths are relative to that folder.")
    else:
        tools = (look + ". They are read-only: you cannot create, change or "
                 "delete a file, and you cannot run a command." + (" " + TEAM_READ_TEXT if crew == "read" else "") + " Paths are relative to that folder.")
    text = (f"Working folder: {shown}\n{tools} When the owner mentions their files, a project, an app or a folder, look there first, starting with "
            "a listing of the folder itself, and say which files you read" + (" and which you changed." if allowed else "."))
    name, body = instructions_of(folder)
    if body:
        text += (f"\n\nThe project's own instructions ({name}); follow them as you would in any session in this folder:\n"
                 f"<project-instructions>\n{body}\n</project-instructions>")
    return text


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

    def stored_access(self) -> str:
        """`edit` or `read`: what the owner let the team do in the stored folder (`read` when none is stored or the file is older than the choice)."""
        try:
            return WorkdirFile.model_validate(json.loads(self.path.read_text(encoding="utf-8"))).access
        except (OSError, ValueError, ValidationError):
            return "read"

    def get(self) -> Optional[str]:
        """The folder a chat turn uses now: the stored one while it is still a usable folder, else None."""
        found = self.stored()
        return found if found is not None and self.problem(found) is None else None

    def grant(self) -> Optional[Folder]:
        """`get()` with the access the owner chose: what the connectors run a chat turn in."""
        found = self.get()
        return None if found is None else Folder(found, edit=self.stored_access() == "edit")

    def preview(self) -> Optional[dict]:
        found = self.get()
        return None if found is None else preview_of(found)

    # ---- writes ----------------------------------------------------------------------------------------------------------------
    def set(self, raw: Any, *, home: Optional[str] = None, access: str = "edit") -> str:
        """Store the checked folder; returns what is stored. Raises InvalidRequestError (with the reason) and writes nothing."""
        if access not in ACCESS:
            raise InvalidRequestError("Choose read only, or read and change")
        chosen = check_folder(raw, data_dir=self.data_dir, work_root=self.work_root, home=home)
        self._write(WorkdirFile(path=chosen, access=access).model_dump_json(indent=2))
        return chosen

    def set_access(self, access: str) -> str:
        """Change what the team may do in the folder already chosen; InvalidRequestError when none is chosen."""
        found = self.stored()
        if found is None:
            raise InvalidRequestError("Choose a working folder first")
        return self.set(found, access=access)

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
