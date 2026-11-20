"""What the computer has allowed (multi-agent nodes, MAN-15; D295, guardrails 5.2): checked BEFORE a node starts, explained in plain steps for that system, the right settings page opened, checked again.

    needs = probe(folder, write=True)             # [] when nothing is in the way; else one `Need` for each thing the owner must allow
    steps = explain(need)                         # plain steps for this system
    open_settings(need)                           # opens the page; True when it could

Sutra changes no setting of the computer, asks for no administrator password and never works around a refusal. The probe only LOOKS: it lists the folder (read) or makes and removes one empty file of
its own name in it (write; never inside `.git`); a permission error is a need. One adapter for each system: macOS (Files & Folders, Full Disk Access), Windows (Controlled folder access, running as
administrator, long paths), and one that asks for nothing. A plan that never names a protected folder shows nothing. Tests use fake adapters and a monkeypatched platform: no real system dialog.
"""
from __future__ import annotations

import errno
import os
import secrets
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sutra_app import oslayer

__all__ = ["Need", "Adapter", "MacAdapter", "WindowsAdapter", "NoAdapter", "adapter_for", "probe", "explain", "open_settings", "is_permission_failure", "ITEMS"]

ITEMS = ("files_folders", "full_disk", "controlled_folder", "elevated", "long_paths", "unknown")
_PROTECTED_MAC = ("Desktop", "Documents", "Downloads")        # the folders macOS asks about (Files & Folders)


@dataclass(frozen=True)
class Need:
    """One thing the owner has to allow. `item` is one of `ITEMS`, `level` is `read` or `write` (what the step wanted to do), `label` names the folder or the setting in plain words."""

    item: str
    level: str = "read"
    label: str = ""


class Adapter(Protocol):
    name: str

    def probe(self, folder: Path | None, *, write: bool) -> list[Need]: ...
    def explain(self, need: Need) -> list[str]: ...
    def open_settings(self, need: Need) -> bool: ...


NEEDS_PERMISSION = "needs_system_permission"     # the outcome prefix the engine host writes when the computer refused a file (engine/host/loop.py `permission_outcome`)


def is_permission_failure(error: BaseException | str) -> bool:
    """True for a refusal of the computer: a real PermissionError (or an OSError with EPERM or EACCES), or an outcome that STARTS with the word the engine host writes for one. The words of a node
    are never matched: a hand-off or a model that says "permission denied" is not a permission need (m5)."""
    if isinstance(error, PermissionError):
        return True
    if isinstance(error, OSError):
        return error.errno in (errno.EPERM, errno.EACCES)
    return isinstance(error, str) and error.startswith(NEEDS_PERMISSION)


def _can_list(folder: Path) -> bool:
    try:
        next(iter(os.scandir(folder)), None)
        return True
    except PermissionError:
        return False
    except OSError:
        return True                                           # a folder that is not there, or another trouble: not a permission need


def _can_write(folder: Path) -> bool:
    """Make one empty file of our own name and remove it. Never inside `.git`; a name no project file has; nothing is left behind."""
    if ".git" in folder.parts:
        return True
    probe_file = folder / f".sutra-probe-{secrets.token_hex(6)}"
    try:
        fd = os.open(probe_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | oslayer.O_BINARY, 0o600)
        os.close(fd)
    except PermissionError:
        return False
    except OSError:
        return True
    try:
        os.unlink(probe_file)
    except OSError:
        pass
    return True


class MacAdapter:
    name = "macos"

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or Path.home()

    def _protected(self, folder: Path) -> str:
        for name in _PROTECTED_MAC:
            base = self.home / name
            try:
                folder.resolve().relative_to(base.resolve())
                return name
            except (ValueError, OSError):
                continue
        return ""

    def probe(self, folder: Path | None, *, write: bool) -> list[Need]:
        if folder is None:
            return []
        name = self._protected(Path(folder))
        if not name:                                          # a plan that never names a protected folder shows nothing
            return []
        level = "write" if write else "read"
        if not _can_list(Path(folder)):
            return [Need("files_folders", level, name)]
        if write and not _can_write(Path(folder)):
            return [Need("files_folders", "write", name)]
        return []

    def explain(self, need: Need) -> list[str]:
        where = need.label or "that folder"
        if need.item == "full_disk":
            return ["Open System Settings, then Privacy & Security, then Full Disk Access.", "Turn on Sutra Pro in the list.", "Come back here and press Check again."]
        return ["Open System Settings, then Privacy & Security, then Files & Folders.", f"Find Sutra Pro and turn on {where}.",
                "Come back here and press Check again.", "Nothing starts until you do, and Sutra changes no setting for you."]

    def open_settings(self, need: Need) -> bool:
        pane = "Privacy_AllFiles" if need.item == "full_disk" else "Privacy_FilesAndFolders"
        try:
            return subprocess.run(["open", f"x-apple.systempreferences:com.apple.preference.security?{pane}"], capture_output=True, timeout=10, check=False).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False


class WindowsAdapter:
    name = "windows"

    def probe(self, folder: Path | None, *, write: bool) -> list[Need]:
        found: list[Need] = []
        if oslayer.is_elevated():
            found.append(Need("elevated", "write" if write else "read", "administrator rights"))
        if folder is None:
            return found
        path = Path(folder)
        if len(str(path)) > 240 and not oslayer.long_paths_enabled():
            found.append(Need("long_paths", "read", "long file names"))
        if not _can_list(path):
            found.append(Need("controlled_folder", "read", path.name or str(path)))
        elif write and not _can_write(path):
            found.append(Need("controlled_folder", "write", path.name or str(path)))
        return found

    def explain(self, need: Need) -> list[str]:
        if need.item == "elevated":
            return ["Sutra is running as administrator. Close it and open it again the usual way (not as administrator).", "Then ask again."]
        if need.item == "long_paths":
            return ["Windows is set to refuse long file names, and this folder has one.", "Move the work to a folder with a shorter path, or ask the person who looks after this computer to allow long paths.", "Then press Check again."]
        return ["Open Windows Security, then Virus & threat protection, then Ransomware protection.", "Open Manage Controlled folder access, then Allow an app through Controlled folder access.",
                "Add Sutra Pro and the programs it runs, `claude` and `codex`, then come back here and press Check again.", "Nothing starts until you do, and Sutra changes no setting for you."]

    def open_settings(self, need: Need) -> bool:
        try:
            start = getattr(os, "startfile", None)
            if start is None:
                return False
            start("windowsdefender://ransomwareprotection")
            return True
        except OSError:
            return False


class NoAdapter:
    name = "none"

    def probe(self, folder: Path | None, *, write: bool) -> list[Need]:
        return []

    def explain(self, need: Need) -> list[str]:
        return ["Allow Sutra to use that folder in your computer's settings, then press Check again."]

    def open_settings(self, need: Need) -> bool:
        return False


def adapter_for(platform: str | None = None) -> Adapter:
    """The adapter of a system (`sys.platform` by default): `darwin` macOS, `win32` Windows, anything else asks for nothing."""
    name = platform if platform is not None else sys.platform
    return MacAdapter() if name == "darwin" else WindowsAdapter() if name == "win32" else NoAdapter()


def probe(folder: str | os.PathLike[str] | None, *, write: bool, adapter: Adapter | None = None) -> list[Need]:
    return (adapter or adapter_for()).probe(Path(folder) if folder else None, write=write)


def explain(need: Need, adapter: Adapter | None = None) -> list[str]:
    return list((adapter or adapter_for()).explain(need))


def open_settings(need: Need, adapter: Adapter | None = None) -> bool:
    return bool((adapter or adapter_for()).open_settings(need))
