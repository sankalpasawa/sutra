"""What the audit may know about one tool call of a node (MAN-14, D325, D327): the name, the KIND and, for a file, its base name. Never an input: not a command, a query, a URL, a path or
a file's content. `tool_kinds.classify` is not changed; this adds the two kinds of the app's own tools (`sutra`, `github`) on top of its six.

    facts({"name": "Read", "input": {"file_path": "/work/site/index.html"}})  ->  ("Read", "read", "index.html")
    facts({"name": "mcp__sutra__github_repo_get", "input": {"owner": "x"}})  ->  ("mcp__sutra__github_repo_get", "github", "")
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from .tool_kinds import classify

__all__ = ["facts", "KINDS", "NAME_MAX", "TARGET_MAX"]

KINDS = ("read", "edit", "run", "search", "web", "sutra", "github", "other")
NAME_MAX = 60
TARGET_MAX = 80
_PATH_KEYS = ("file_path", "path", "notebook_path")
_NAME_OK = re.compile(r"[^A-Za-z0-9_.:-]+")
_NOT_A_TOOL = frozenset({"StructuredOutput", "PROPOSE"})     # a reply returned as a tool call, and J2's own pseudo-tool for a proposal: neither is something a step did (D394)
_MCP = "mcp__sutra__"                                  # the app's own tool server (`claude.py`: one server for the `sutra` and `github` tools)


def _name(raw: Any) -> str:
    return _NAME_OK.sub("_", str(raw or "")).strip("_")[:NAME_MAX]


def _target(kind: str, tool_input: Any) -> str:
    """The base name of the file a read or an edit is about, and nothing else: a command (`run`), a query (`search`), a URL (`web`) or an app tool's arguments are never kept."""
    if kind not in ("read", "edit") or not isinstance(tool_input, dict):
        return ""
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            base = os.path.basename(value.strip().replace("\\", "/").rstrip("/"))
            return "".join(ch for ch in base if ch.isprintable())[:TARGET_MAX]
    return ""


def _in_git(tool_input: Any) -> bool:
    """True when the call is about a path inside a repository's own `.git` folder (its HEAD, index, COMMIT_EDITMSG): the repository's plumbing, which says nothing the owner can use (D405). Only a path
    with a `.git` component counts; a bare name is never guessed at."""
    if not isinstance(tool_input, dict):
        return False
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and ".git" in value.replace("\\", "/").split("/"):
            return True
    return False


def facts(data: Any, provider: str = "claude") -> Optional[tuple[str, str, str]]:
    """`(name, kind, target)` for a `tool_call` event's data, or None when it is not a tool call worth a line (no name at all, or Claude's own way of returning a reply). Never raises."""
    try:
        if not isinstance(data, dict):
            return None
        raw = data.get("name") or data.get("type")
        name = _name(raw)
        if not name or name in _NOT_A_TOOL or _in_git(data.get("input")):
            return None
        if name.startswith(_MCP):
            kind = "github" if name[len(_MCP):].startswith("github") else "sutra"
        else:
            kind = classify(str(raw), data.get("input"), provider)
        return name, kind, _target(kind, data.get("input"))
    except Exception:                                  # noqa: BLE001  an audit that threw would take a call down
        return None
