"""What KIND of thing a tool call is, for the fold of a settled turn (absorb design 2.2 rule 7; ported from the old `tool_kinds.py`).

Six kinds: read, edit, run, search, web, other. An unknown name is `other` and still shows (the table may never be the reason a call
disappears). `classify` never raises. The same table classifies stored history, so older chats fold the same way.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

__all__ = ["KINDS", "classify", "title_of", "describe", "CLAUDE_KINDS", "CODEX_KINDS", "LIVE_TEXT_MAX"]

KINDS = ("read", "edit", "run", "search", "web", "other")
TITLE_MAX = 160
LIVE_TEXT_MAX = 200                  # the longest title or target a live tool line carries (D210)

CLAUDE_KINDS = {
    "bash": "run", "bashoutput": "run", "killshell": "run",
    "edit": "edit", "write": "edit", "multiedit": "edit", "notebookedit": "edit",
    "read": "read", "grep": "search", "glob": "search", "websearch": "web", "webfetch": "web",
}
CODEX_KINDS = {
    "command_execution": "run", "file_change": "edit", "patch_apply": "edit", "file_read": "read", "file_search": "search",
    "web_search": "web", "web_fetch": "web",
}


def classify(name: Optional[str], tool_input: Any = None, provider: str = "claude") -> str:
    try:
        low = (name or "").strip().lower()
        table = CODEX_KINDS if provider == "codex" else CLAUDE_KINDS
        return table.get(low, "other")
    except Exception:           # noqa: BLE001  a classifier that threw would take a turn down
        return "other"


def _short(value: Any, limit: int = TITLE_MAX) -> str:
    if not isinstance(value, str):
        return ""
    flat = " ".join(value.split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def title_of(name: Optional[str], tool_input: Any = None) -> str:
    """The short label of a card: the command, the file name, the query."""
    try:
        inp = tool_input if isinstance(tool_input, dict) else {}
        for key in ("command", "query", "url", "pattern"):
            if inp.get(key):
                return _short(inp[key])
        for key in ("file_path", "path", "notebook_path"):
            if inp.get(key):
                return os.path.basename(str(inp[key]).rstrip("/")) or _short(inp[key])
        return _short(name)
    except Exception:           # noqa: BLE001
        return ""


_SHELL_WRAPPER = re.compile(r"^(?:/[\w./+-]*/)?(?:ba|z|da|k|fi)?sh\s+-[a-z]*c\s+(.+)$", re.DOTALL)
_VERBS = {"read": "Reading", "edit": "Editing", "run": "Running", "search": "Searching", "web": "Fetching"}


def _unwrap_command(command: str) -> str:
    """`/bin/zsh -lc "sed -n 1,5p a.txt"` -> `sed -n 1,5p a.txt`: the shell wrapper Codex puts around a command is not what the person asked for."""
    found = _SHELL_WRAPPER.match(command.strip())
    if found is None:
        return command
    inner = found.group(1).strip()
    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "\"'":
        inner = inner[1:-1]
    return inner


def _relative(path: str, folder: str) -> str:
    """`path` as the turn's folder sees it: relative when it lies inside it, else the last component (the work root and the home directory never leave).
    No file system is touched except `realpath` of the two strings, which is how the connectors name the folder."""
    raw = str(path).strip()
    if not raw:
        return ""
    if not os.path.isabs(raw):
        norm = os.path.normpath(raw)
        return os.path.basename(norm) if norm.startswith("..") else norm.replace(os.sep, "/")
    if folder:
        for base, target in ((os.path.normpath(folder), os.path.normpath(raw)), (os.path.realpath(folder), os.path.realpath(raw))):
            try:
                if os.path.commonpath([base, target]) == base and target != base:
                    return os.path.relpath(target, base).replace(os.sep, "/")
            except ValueError:
                continue
    return os.path.basename(raw.rstrip("/\\")) or raw[:1]


def describe(name: Optional[str], tool_input: Any = None, folder: str = "", provider: str = "claude") -> tuple[str, str, str]:
    """`(kind, title, target)` of one tool call for the live tool line (D210). `target` is what the call is about (a path inside the turn's `folder`
    relative to it, a basename outside it, a command, a search pattern, a URL); `title` is a short sentence over it ("Reading src/a.py"). Both are cut to
    `LIVE_TEXT_MAX`; the caller redacts them. Raw input, tool output and the folder itself are never part of the result. Never raises."""
    try:
        kind = classify(name, tool_input, provider)
        inp = tool_input if isinstance(tool_input, dict) else {}
        target = ""
        for key in ("file_path", "path", "notebook_path"):
            if isinstance(inp.get(key), str) and inp[key].strip():
                target = _relative(inp[key], folder)
                break
        if not target:
            for key in ("command", "pattern", "query", "url"):
                if isinstance(inp.get(key), str) and inp[key].strip():
                    target = " ".join((_unwrap_command(inp[key]) if key == "command" else inp[key]).split())
                    break
        target = target[:LIVE_TEXT_MAX]
        label = str(name or "").strip()
        if name and low_name(name) in ("write",):
            verb = "Writing"
        else:
            verb = _VERBS.get(kind)
        title = f"{verb} {target}".strip() if verb and target else (f"Using {label}" if label else "Using a tool")
        return kind, title[:LIVE_TEXT_MAX], target
    except Exception:           # noqa: BLE001
        return "other", "Using a tool", ""


def low_name(name: Any) -> str:
    return str(name or "").strip().lower()
