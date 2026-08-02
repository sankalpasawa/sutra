"""Read-only browser over Claude Code's saved session transcripts.

Sessions live at ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl as JSONL
event logs. We read them; we never write. Viewing costs nothing (no model calls).
Continuing a session happens in the real terminal via `claude --resume`.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

PROJECTS = Path(os.path.expanduser("~/.claude/projects"))


def _text_of(content) -> str:
    """Extract human-readable text from a message.content (str or block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text"):
                parts.append(b["text"])
        return "\n".join(parts)
    return ""


def _is_tool_result(content) -> bool:
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def list_sessions(limit: int = 100) -> List[dict]:
    """Most-recent sessions across all projects. Cheap: reads only the head of each file."""
    if not PROJECTS.exists():
        return []
    files = sorted(PROJECTS.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        title, cwd, branch = "", "", ""
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i > 40:
                        break
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    cwd = cwd or d.get("cwd", "")
                    branch = branch or d.get("gitBranch", "")
                    if not title and d.get("type") == "user":
                        msg = d.get("message", {})
                        if isinstance(msg, dict) and not _is_tool_result(msg.get("content")):
                            t = _text_of(msg.get("content")).strip().replace("\n", " ")
                            if t and not t.startswith("<"):
                                title = t[:90]
        except OSError:
            continue
        out.append({
            "id": f.stem,
            "title": title or "(no prompt)",
            "project": f.parent.name,
            "cwd": cwd,
            "branch": branch,
            "mtime": int(f.stat().st_mtime),
            "size": f.stat().st_size,
        })
    return out


def read_session(session_id: str) -> Optional[Dict]:
    """Parse one session transcript into chat-renderable messages. Read-only."""
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return None  # path-traversal guard
    matches = list(PROJECTS.glob("*/" + session_id + ".jsonl"))
    if not matches:
        return None
    f = matches[0]
    messages, cwd, branch = [], "", ""
    with f.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            cwd = cwd or d.get("cwd", "")
            branch = branch or d.get("gitBranch", "")
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = d.get("message", {})
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if t == "user":
                if _is_tool_result(content):
                    continue  # tool results aren't user turns
                text = _text_of(content).strip()
                if text and not text.startswith("<"):
                    messages.append({"role": "user", "text": text, "ts": d.get("timestamp", "")})
            else:  # assistant
                text = _text_of(content).strip()
                tools = [b.get("name", "") for b in content if isinstance(b, dict) and b.get("type") == "tool_use"] \
                    if isinstance(content, list) else []
                if text or tools:
                    messages.append({"role": "assistant", "text": text, "tools": tools, "ts": d.get("timestamp", "")})
    return {"id": session_id, "cwd": cwd, "branch": branch, "messages": messages}
