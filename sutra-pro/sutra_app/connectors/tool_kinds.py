"""What KIND of thing a tool call is, for the fold of a settled turn (absorb design 2.2 rule 7; ported from the old `tool_kinds.py`).

Six kinds: read, edit, run, search, web, other. An unknown name is `other` and still shows (the table may never be the reason a call
disappears). `classify` never raises. The same table classifies stored history, so older chats fold the same way.
"""
from __future__ import annotations

import os
from typing import Any, Optional

__all__ = ["KINDS", "classify", "title_of", "CLAUDE_KINDS", "CODEX_KINDS"]

KINDS = ("read", "edit", "run", "search", "web", "other")
TITLE_MAX = 160

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
