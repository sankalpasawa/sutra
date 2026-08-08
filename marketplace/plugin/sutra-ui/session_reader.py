"""Read-only browser over Claude Code's saved session transcripts.

Sessions live at ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl as JSONL
event logs. We read them; we never write. Viewing costs nothing (no model calls).
Continuing a session happens in the real terminal via `claude --resume`.
"""
import json
import os
import time
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


# Sutra PREPENDS a routing preamble to the operator's message before sending it
# (panel.html builds it and joins with "\n\n" before the real text). The title of
# a session is taken from its first user message, so every conversation started
# from the panel was titled with Sutra's own bookkeeping instead of what the
# operator typed -- measured: 17 of 120 sessions read "PLACEMENT: unresolved --
# no department could be resolved for this turn." in the rail.
#
# Split on the FIRST blank line and keep the remainder, which is exactly how the
# preamble is joined. A message that is ONLY the preamble (no text after it) keeps
# the preamble rather than becoming blank -- an empty title is worse than an ugly
# one, because it names nothing at all.
_INJECTED_PREFIXES = ("PLACEMENT:",)


def _strip_injected(text: str) -> str:
    t = (text or "").lstrip()
    if not t.startswith(_INJECTED_PREFIXES):
        return text or ""
    _, sep, rest = t.partition("\n\n")
    rest = rest.strip()
    return rest if sep and rest else t


def list_sessions(limit: int = 100) -> List[dict]:
    """Most-recent sessions across all projects.

    THE TITLE HONOURS WHAT YOU SET IN CLAUDE. Claude appends two kinds of title
    record to the transcript -- `custom-title` (you renamed it) and `ai-title`
    (Claude auto-named it) -- and Sutra ignored both, so a conversation you had
    deliberately titled still showed its raw first prompt here. Now the precedence
    is: a title you set > the AI title > the first user message. The first two are
    quotations of records Claude actually wrote, not anything Sutra invents.

    Cost: the head fields (cwd, branch, first-message fallback) still come from the
    first ~40 lines, but a rename can be appended ANYWHERE in a long session, so
    the title records are scanned across the whole file. The `in line` gate keeps
    that from json-parsing the big assistant/attachment lines -- measured ~165ms
    for 97MB across every transcript on disk, and this runs at boot and on a new
    session appearing, not on a timer.
    """
    if not PROJECTS.exists():
        return []
    files = sorted(PROJECTS.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        first_msg, cwd, branch = "", "", ""
        custom_title = ai_title = ""
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    head = i <= 40
                    # LAST title record wins: a rename overwrites an earlier one.
                    titley = "customTitle" in line or "aiTitle" in line
                    if not head and not titley:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if titley:
                        if d.get("type") == "custom-title" and isinstance(d.get("customTitle"), str):
                            custom_title = d["customTitle"].strip() or custom_title
                        elif d.get("type") == "ai-title" and isinstance(d.get("aiTitle"), str):
                            ai_title = d["aiTitle"].strip() or ai_title
                    if head:
                        cwd = cwd or d.get("cwd", "")
                        branch = branch or d.get("gitBranch", "")
                        if not first_msg and d.get("type") == "user":
                            msg = d.get("message", {})
                            if isinstance(msg, dict) and not _is_tool_result(msg.get("content")):
                                t = _strip_injected(_text_of(msg.get("content")))
                                t = t.strip().replace("\n", " ")
                                if t and not t.startswith("<"):
                                    first_msg = t[:90]
        except OSError:
            continue
        # A title you set is verbatim -- NOT run through _strip_injected, which is
        # only for the machine preamble on a first message.
        title = custom_title or ai_title or first_msg or "(no prompt)"
        out.append({
            "id": f.stem,
            "title": title[:90],
            # Stated so the UI could badge a renamed session if it wanted; also
            # what the test uses to know a title is a legitimate on-disk record.
            "title_source": ("custom" if custom_title else
                             "ai" if ai_title else
                             "prompt" if first_msg else "none"),
            "project": f.parent.name,
            "cwd": cwd,
            "branch": branch,
            "mtime": int(f.stat().st_mtime),
            "size": f.stat().st_size,
        })
    return out


# How recently a transcript must have been written to count as each state. These
# are about the FILE, which is the only evidence there is: Claude appends a line
# per event, so "was written 4 seconds ago" is as close to "someone is typing in
# it right now" as anything outside Claude can honestly get.
ACTIVE_S = 45          # a turn in flight, or one that just landed
IDLE_S = 30 * 60       # the conversation is open but nothing is happening


def liveness(mtime: float, now: Optional[float] = None) -> str:
    """active | idle | stale, from the transcript's last write.

    Deliberately three states and not a boolean: "not active" covers both a chat
    someone is sitting in between messages and one abandoned last Tuesday, and
    collapsing them would make the rail claim the second is as current as the first.
    """
    age = (time.time() if now is None else now) - float(mtime or 0)
    if age <= ACTIVE_S:
        return "active"
    if age <= IDLE_S:
        return "idle"
    return "stale"


def index() -> Dict[str, Dict]:
    """{session_id: {mtime, size, project}} for every transcript on disk.

    STAT ONLY -- no file is opened. This is what the watcher polls, so it has to
    stay cheap enough to run every second or two against a projects directory
    with hundreds of transcripts in it; parsing titles here would make the poll
    cost scale with history rather than with change.
    """
    out: Dict[str, Dict] = {}
    if not PROJECTS.exists():
        return out
    for f in PROJECTS.glob("*/*.jsonl"):
        try:
            st = f.stat()
        except OSError:
            continue          # deleted between glob and stat: simply not there
        out[f.stem] = {"mtime": int(st.st_mtime), "size": st.st_size,
                       "project": f.parent.name}
    # SUBAGENTS. The glob above is exactly one directory deep, so it never saw
    # <project>/<session-id>/subagents/**/agent-*.jsonl -- the bulk of transcript
    # files on a machine that runs fan-outs. Liveness was therefore the PARENT
    # file's mtime alone, so a session with agents writing while the parent was
    # silent read as idle and then stale precisely when the machine was busiest.
    #
    # The parent id is NOT parents[1]/[2] -- workflow-nested agents sit deeper and
    # that returns the literal "subagents". Index from the right instead. Still
    # stat-only, so the poll cost stays flat in history size. agent-*.jsonl only,
    # or workflow journal.jsonl bookkeeping files get counted as agents.
    for f in PROJECTS.glob("*/*/subagents/**/agent-*.jsonl"):
        parts = f.parts
        try:
            i = len(parts) - 1 - parts[::-1].index("subagents")
        except ValueError:
            continue
        rec = out.get(parts[i - 1])
        if rec is None:
            continue          # an agent whose parent transcript is not on disk
        try:
            st = f.stat()
        except OSError:
            continue
        rec["mtime"] = max(rec["mtime"], int(st.st_mtime))
        rec["agents_bytes"] = rec.get("agents_bytes", 0) + st.st_size
        if liveness(st.st_mtime) == "active":
            rec["agents_live"] = rec.get("agents_live", 0) + 1
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
