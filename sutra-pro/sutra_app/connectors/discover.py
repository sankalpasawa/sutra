"""Where the Claude and Codex CLIs are, for an app opened from Finder (GAP-providers; the old app's providers.py `_KNOWN_BIN_DIRS`,
`_known_bin_dirs`, `claude_desktop_installed` and `_bin_for`).

A Mac app opened from Finder gets launchd's PATH (/usr/bin:/bin:/usr/sbin:/sbin), so a CLI installed through nvm, Volta, pnpm, mise, asdf,
fnm, yarn or bun reads "not installed" although the owner runs it in Terminal every day. This module looks where those installers put the
command. It never runs the owner's shell or its startup files (the old login-shell harvest is NOT taken: it executes .zshrc and waits up
to 25 s), it runs no CLI, and it installs nothing (D34).

    known_dirs(home, environ)             the folders installers use, in order; every ~/.nvm/versions/node/*/bin, newest version first
    find_cli(name, *, stored, path, home, environ) -> Found(exe, folder, source)
                                          the owner's chosen file (bins.py) while it is still an executable file, else the first `name`
                                          on PATH, else the first known folder that holds an executable `name`. source: stored | path |
                                          known | none (then `exe` is the bare name, as before)
    augment_path(path, folders)           PATH with the folders appended, each once: never prepended, so the owner's own order wins
    claude_desktop_installed(home, isdir) /Applications/Claude.app or ~/Applications/Claude.app is there
    explain_missing(provider, desktop, default)   the Desktop sentence (errors.DESKTOP_ONLY) for Claude when Claude Desktop is installed,
                                          else `default`, the PATH wording each surface already had
    connector_config(data_dir, ...)       the ConnectorConfig of the running app: full paths of both CLIs, a child PATH that holds the
                                          folders they were found in (a `#!/usr/bin/env node` shim needs its node beside it), and the
                                          Desktop flag. The factory and the doctor use it when no config is handed in (tests hand one in)
    use_cli(router, provider, stored)     the running router follows a new choice at once: the connector's executable and PATH change,
                                          what was cached about the old file is forgotten, and `connector.health` goes out

POSIX only: on Windows the installer's PATH is used as it is (`connector_config` gives the defaults, plus the file the owner chose in Settings).
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Optional

from sutra_app import oslayer

from .bins import BinStore, is_executable_file
from .errors import DESKTOP_ONLY
from .models import ConnectorConfig

__all__ = ["Found", "KNOWN_DIRS", "SYSTEM_DIRS", "DESKTOP_APPS", "known_dirs", "find_cli", "augment_path", "claude_desktop_installed", "explain_missing",
           "connector_config", "use_cli"]

# Locations the vendors and the version managers document, not a wishlist; a folder only joins PATH when it EXISTS and holds the command.
SYSTEM_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")          # Homebrew (Apple silicon, Intel) and npm -g on Intel
KNOWN_DIRS = (
    "~/.local/bin",                                  # Claude Code's native installer
    "~/.claude/local",                               # Claude Code's older local installer
    *SYSTEM_DIRS,
    "~/.npm-global/bin",                             # the documented npm prefix
    "~/.yarn/bin", "~/.config/yarn/global/node_modules/.bin",
    "~/.bun/bin", "~/.volta/bin", "~/.deno/bin",
    "~/Library/pnpm", "~/.local/share/pnpm",         # pnpm on macOS and on Linux
    "~/.local/share/mise/shims", "~/.asdf/shims", "~/.nodenv/shims", "~/.n/bin",
    "~/.fnm/aliases/default/bin", "~/Library/Application Support/fnm/aliases/default/bin",
)
# Folders an installer variable names, when the app happens to have it (a terminal start; Finder gives none of them).
_VAR_DIRS = (("VOLTA_HOME", "bin"), ("PNPM_HOME", ""), ("BUN_INSTALL", "bin"), ("ASDF_DATA_DIR", "shims"), ("MISE_DATA_DIR", "shims"),
             ("FNM_DIR", "aliases/default/bin"), ("N_PREFIX", "bin"))
DESKTOP_APPS = ("/Applications/Claude.app", "~/Applications/Claude.app")
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class Found:
    exe: str                                          # the full path, or the bare name when nothing was found
    folder: Optional[str]                             # the folder to add to the child's PATH (None: on PATH already, or not found)
    source: Literal["stored", "path", "known", "none"]


def _home_path(home: str, entry: str) -> str:
    return home + entry[1:] if entry.startswith("~") else entry


def _nvm_dirs(root: str) -> list[str]:
    """Every installed node version's bin folder, newest version first (nvm chooses one in .zshrc, which Finder never reads)."""
    versions = os.path.join(root, "versions", "node")
    try:
        names = os.listdir(versions)
    except OSError:
        return []

    def rank(name: str) -> tuple:
        found = _VERSION.fullmatch(name)
        return (1, *(int(g) for g in found.groups())) if found else (0, 0, 0, 0)

    return [os.path.join(versions, name, "bin") for name in sorted(names, key=rank, reverse=True)]


def known_dirs(home: str, environ: Mapping[str, str]) -> list[str]:
    out: list[str] = []
    for name, sub in _VAR_DIRS:
        value = environ.get(name)
        if value and os.path.isabs(value):
            out.append(os.path.join(value, sub) if sub else value)
    out += [_home_path(home, entry) for entry in KNOWN_DIRS]
    out += _nvm_dirs(environ.get("NVM_DIR") or os.path.join(home, ".nvm"))
    seen: set[str] = set()
    return [d for d in out if not (d in seen or seen.add(d))]


def find_cli(name: str, *, stored: Optional[str], path: str, home: str, environ: Mapping[str, str],
             is_exe: Callable[[str], bool] = is_executable_file) -> Found:
    if isinstance(stored, str) and stored and is_exe(stored):          # a stored path that has vanished is ignored, not honoured
        return Found(exe=stored, folder=os.path.dirname(stored), source="stored")
    on_path = shutil.which(name, path=path or None) if path else None
    if on_path:
        return Found(exe=os.path.abspath(on_path), folder=None, source="path")
    for folder in known_dirs(home, environ):
        candidate = os.path.join(folder, name)
        if is_exe(candidate):
            return Found(exe=candidate, folder=folder, source="known")
    return Found(exe=name, folder=None, source="none")


def augment_path(path: str, folders: Iterable[Optional[str]]) -> str:
    parts = [p for p in (path or "").split(os.pathsep) if p]
    for folder in folders:
        if folder and folder not in parts:
            parts.append(folder)
    return os.pathsep.join(parts)


def claude_desktop_installed(home: str, isdir: Callable[[str], bool] = os.path.isdir) -> bool:
    return any(isdir(_home_path(home, p)) for p in DESKTOP_APPS)


def explain_missing(provider: str, desktop: bool, default: str) -> str:
    return DESKTOP_ONLY if provider == "claude" and desktop else default


def _home_of(environ: Mapping[str, str], home: Optional[str]) -> str:
    return home or environ.get("HOME") or os.path.expanduser("~")


def connector_config(data_dir: Path, *, environ: Optional[Mapping[str, str]] = None, home: Optional[str] = None,
                     isdir: Callable[[str], bool] = os.path.isdir, **fields: Any) -> ConnectorConfig:
    """The running app's ConnectorConfig. `fields` are other ConnectorConfig fields (work_root, python) passed through unchanged."""
    if oslayer.IS_WINDOWS:
        # No folder discovery on Windows (the installer's PATH is used), but the file the owner chose in Settings is still theirs to keep: it is read
        # here exactly as on a Mac, or the choice the page confirmed ("Using that file.") would be forgotten at the next start.
        chosen = {f"{name}_exe": path for name, path in BinStore(Path(data_dir)).load().items()}
        return ConnectorConfig(data_dir=data_dir, **{**chosen, **fields})
    env = os.environ if environ is None else environ
    home_dir = _home_of(env, home)
    stored = BinStore(Path(data_dir)).load()
    path = env.get("PATH", "")
    found = {name: find_cli(name, stored=stored.get(name), path=path, home=home_dir, environ=env) for name in ("claude", "codex")}
    folders = [f.folder for f in found.values()]
    extra = {"PATH": augment_path(path, folders)} if any(folders) else {}
    return ConnectorConfig(data_dir=data_dir, claude_exe=found["claude"].exe, codex_exe=found["codex"].exe, extra_env=extra,
                           claude_desktop=claude_desktop_installed(home_dir, isdir), **fields)


def use_cli(router: Any, provider: str, stored: Optional[str], *, environ: Optional[Mapping[str, str]] = None,
            home: Optional[str] = None) -> Found:
    """Point the running connector of `provider` at `stored` (the owner's new choice) or, with None, at what discovery finds."""
    connector = router.connectors[provider]
    env = os.environ if environ is None else environ
    path = env.get("PATH", "")
    found = find_cli(provider, stored=stored, path=path, home=_home_of(env, home), environ=env)
    cfg = connector.cfg
    extra = dict(cfg.extra_env)
    if found.folder:
        extra["PATH"] = augment_path(extra.get("PATH", path), [found.folder])
    connector.cfg = cfg.model_copy(update={f"{provider}_exe": found.exe, "extra_env": extra})
    connector.forget_cli()
    router.health.forget_installed(provider)
    router.health.forget_auth(provider)
    state = router.health.state(provider)
    router._emit("connector.health", {"provider": provider, "state": state.state, "until": state.until, "reason": state.reason})
    return found
