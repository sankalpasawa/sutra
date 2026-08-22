"""Read-only browser over Claude Code's saved session transcripts.

Sessions live at ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl as JSONL
event logs. Mostly read-only; the write path (append_title/relocate) is the one
exception, operator-granted, and it only appends Claude's own record types or
MOVES files, never rewrites a conversation. Viewing costs nothing (no model calls).
Continuing a session happens in the real terminal via `claude --resume`.
"""
import json
import os
import re
import time
import shutil
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


def list_sessions(limit: int = 100, offset: int = 0) -> List[dict]:
    """Most-recent sessions across all projects, newest first.

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

    PAGINATION. `offset` walks further back in the same mtime-sorted order, so the
    panel can fetch history a page at a time as the operator scrolls rather than
    parsing every transcript on disk at boot -- title parsing is the expensive
    part and only the requested slice pays for it. The full glob+stat+sort is
    cheap (stat-only) and is what makes offsets stable within one call; across
    calls a session bumped to the top by a new write can shift the window by one,
    which the client dedups by id. A short page (fewer than `limit`) is how the
    client knows it has reached the end.
    """
    if not PROJECTS.exists():
        return []
    files = sorted(PROJECTS.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    offset = max(0, offset)
    out = []
    for f in files[offset:offset + limit]:
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


def head_meta(session_id: str) -> Dict[str, str]:
    """{title, cwd} for ONE session -- same precedence as list_sessions
    (custom-title > ai-title > first user message). Read-only, fails soft to
    blanks. The activity endpoint calls this only for the handful of sessions
    that are currently active, so it never scans the whole projects dir.
    """
    p = resolve_path(session_id)
    if p is None:
        return {"title": "", "cwd": ""}
    first_msg = cwd = custom_title = ai_title = ""
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                head = i <= 40
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
                    if not first_msg and d.get("type") == "user":
                        msg = d.get("message", {})
                        if isinstance(msg, dict) and not _is_tool_result(msg.get("content")):
                            t = _strip_injected(_text_of(msg.get("content")))
                            t = t.strip().replace("\n", " ")
                            if t and not t.startswith("<"):
                                first_msg = t[:90]
    except OSError:
        return {"title": "", "cwd": cwd}
    title = custom_title or ai_title or first_msg or "(no prompt)"
    return {"title": title[:90], "cwd": cwd}


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


# ------------------------------------------------------------ write path -----
# Sutra MAY write to and delete Claude's transcripts (operator-granted). The
# rules: RENAME appends the same custom-title record Claude itself writes (so a
# rename here also shows in Claude); ARCHIVE/DELETE MOVE the file out of
# ~/.claude/projects rather than unlinking, so the */*.jsonl glob stops listing
# it while it stays on disk and recoverable.
SUTRA_STORE = Path(os.path.expanduser("~/.sutra-ui"))


def _safe_id(session_id: str) -> bool:
    return not ("/" in session_id or "\\" in session_id or ".." in session_id)


def resolve_path(session_id: str) -> Optional[Path]:
    if not _safe_id(session_id):
        return None
    matches = list(PROJECTS.glob("*/" + session_id + ".jsonl"))
    return matches[0] if matches else None


def append_title(session_id: str, title: str) -> bool:
    """Append a custom-title record -- byte-identical to Claude's own rename."""
    p = resolve_path(session_id)
    if p is None:
        return False
    title = (title or "").replace("\n", " ").strip()[:200]
    if not title:
        return False
    rec = {"type": "custom-title", "customTitle": title, "sessionId": session_id}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return True


def relocate(session_id: str, kind: str) -> Optional[Dict]:
    """Move a transcript to ~/.sutra-ui/{archive,trash}/<project>/, recoverably."""
    if kind not in ("archive", "trash"):
        return None
    p = resolve_path(session_id)
    if p is None:
        return None
    dest_dir = SUTRA_STORE / kind / p.parent.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / p.name
    orig = str(p)
    shutil.move(orig, str(dest))
    dest.with_name(dest.name + ".orig.json").write_text(
        json.dumps({"original": orig, "session_id": session_id,
                    "moved_at": int(time.time())}), encoding="utf-8")
    return {"moved_to": str(dest), "original": orig}


_TOOL_INPUT_KEYS = ("command", "file_path", "path", "pattern", "query", "url",
                    "prompt", "notebook_path", "description")
_RESULT_CAP = 8000   # per tool result, chars — bound the payload, keep the useful head


def _tool_input_summary(name, inp):
    """A concise one-liner for a tool call's input -- the command / path / pattern,
    the part a human actually reads. Falls back to compact JSON."""
    if not isinstance(inp, dict):
        return (str(inp)[:400] if inp else "")
    for k in _TOOL_INPUT_KEYS:
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return v[:600]
    try:
        return json.dumps(inp)[:600]
    except (TypeError, ValueError):
        return str(inp)[:600]


def _result_text(content) -> str:
    """The human-readable text of a tool_result.content (str or block list)."""
    if isinstance(content, str):
        return content[:_RESULT_CAP]
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text" and b.get("text"):
                    parts.append(str(b["text"]))
                elif b.get("type") == "image":
                    parts.append("[image]")
        return ("\n".join(parts))[:_RESULT_CAP]
    return ""


def _parse_transcript(f) -> Dict:
    """Parse ONE transcript file into chat-renderable messages. Read-only.

    Shared by read_session (a top-level <session-id>.jsonl) and read_agent (a
    subagents/**/agent-*.jsonl). A subagent record is the SAME shape as a session
    record -- type user|assistant, message.content str-or-blocks, tool_use blocks,
    verified on disk: agent files carry agentId/entrypoint/isSidechain and are
    otherwise identical -- so one parser guarantees an agent turn and a session
    turn can never disagree about how the same record renders.

    CAPTURES THE AGENTIC OUTPUT. An assistant record's tool_use blocks carry the
    INPUT (the command/path/pattern); the matching tool_result -- a user-role record
    that arrives later, keyed by tool_use_id -- carries the OUTPUT. Both used to be
    dropped (only tool NAMES survived), so the panel could show that an agent ran
    Bash but never what it ran or what came back. Now each assistant message gets a
    `calls` list of {id, name, input, output, is_error}; `tools` (names) is kept for
    back-compat with the rail count and the older render path.
    """
    messages, cwd, branch = [], "", ""
    results = {}   # tool_use_id -> {output, is_error}
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
                # A user record that IS a tool_result is not a turn -- but it carries
                # the OUTPUT of a tool the agent ran. Capture it, keyed by id.
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            results[b.get("tool_use_id")] = {
                                "output": _result_text(b.get("content")),
                                "is_error": bool(b.get("is_error"))}
                if _is_tool_result(content):
                    continue
                text = _text_of(content).strip()
                if text and not text.startswith("<"):
                    messages.append({"role": "user", "text": text, "ts": d.get("timestamp", "")})
            else:  # assistant
                text = _text_of(content).strip()
                calls = []
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            calls.append({"id": b.get("id"), "name": b.get("name", ""),
                                          "input": _tool_input_summary(b.get("name"), b.get("input"))})
                if text or calls:
                    messages.append({"role": "assistant", "text": text,
                                     "tools": [c["name"] for c in calls],   # back-compat
                                     "calls": calls, "ts": d.get("timestamp", "")})
    # The result follows the call, so attach after the whole file is read.
    for m in messages:
        for c in m.get("calls", ()):
            r = results.get(c.get("id"))
            if r:
                c["output"] = r["output"]
                c["is_error"] = r["is_error"]
    return {"cwd": cwd, "branch": branch, "messages": messages}


def read_session(session_id: str) -> Optional[Dict]:
    """Parse one session transcript into chat-renderable messages. Read-only."""
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        return None  # path-traversal guard
    matches = list(PROJECTS.glob("*/" + session_id + ".jsonl"))
    if not matches:
        return None
    # Single source of truth: read_session and read_agent parse identically, so
    # an agent turn and a session turn can never disagree about one record.
    return {"id": session_id, **_parse_transcript(matches[0])}


# --------------------------------------------------------------- subagents ---
# A subagent transcript lives at <project>/<parent-session>/subagents/**/agent-*.jsonl
# -- confirmed on disk, workflow fan-outs nest under subagents/workflows/<wf>/.
# index() already folds their mtimes onto the parent and sets agents_live; this
# makes the files themselves readable.
def _subagents_root(parent_sid: str):
    """The parent session's subagents dir, or None.

    parent_sid is guarded for traversal and only ever placed INSIDE a glob
    pattern, never joined onto a path, so it cannot walk out of ~/.claude/projects.
    """
    if "/" in parent_sid or "\\" in parent_sid or ".." in parent_sid:
        return None
    hits = list(PROJECTS.glob("*/" + parent_sid + "/subagents"))
    return hits[0] if hits else None


def _norm120(s: str) -> str:
    """Whitespace-collapsed prefix, for matching an agent to the Task that spawned it."""
    return " ".join((s or "").split())[:120]


def _parent_tasks(parent_sid: str) -> List[dict]:
    """The Task/Agent tool_use calls in the PARENT transcript, each carrying the
    clean `description` (3-5 word title) and `subagent_type` the caller gave it.

    Read-only. Returns [] when the parent file is gone or the spawning turns were
    compacted away -- in which case the agent falls back to a derived title.
    """
    if "/" in parent_sid or "\\" in parent_sid or ".." in parent_sid:
        return []
    matches = list(PROJECTS.glob("*/" + parent_sid + ".jsonl"))
    if not matches:
        return []
    tasks = []
    try:
        with matches[0].open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") != "assistant":
                    continue
                content = (d.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if (isinstance(b, dict) and b.get("type") == "tool_use"
                            and b.get("name") in ("Task", "Agent")):
                        inp = b.get("input") or {}
                        prompt = (inp.get("prompt") or "").strip()
                        if prompt:
                            tasks.append({
                                "key": _norm120(prompt),
                                "description": (inp.get("description") or "").strip(),
                                "subagent_type": (inp.get("subagent_type") or "").strip(),
                            })
    except OSError:
        return []
    return tasks


def _agent_title_fallback(text: str) -> str:
    """A concise title from the agent's own prompt, when no parent Task described it.

    Prefer a structured marker (FEATURE:/TASK:/SCOPE:/GOAL:), else the first line
    that is not generic role boilerplate, else the first line. Capped for a card.
    """
    t = text or ""
    m = re.search(r'(?im)^\s*(?:FEATURE|TASK|SCOPE|GOAL|OBJECTIVE|SUMMARY)\s*[:\-]\s*(.+)$', t)
    if m:
        return m.group(1).strip()[:72]
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    for ln in lines:
        if not ln.lower().startswith(("you are ", "you're ", "repo:", "repo :", "you will ")):
            return ln[:72]
    return (lines[0][:72] if lines else "subagent")


def list_agents(parent_sid: str) -> List[dict]:
    """Every subagent under one session, enriched for a readable list. Read-only,
    newest first, fails to [].

    Per agent: {id, title, agent_type, label, steps, tools, turns, mtime, running}.
      - title      clean short name: the parent Task's `description` when the
                   spawning turn is still on disk, else derived from the prompt.
      - agent_type the Task's `subagent_type` (e.g. general-purpose), or "".
      - steps      assistant messages -- the real work count (a "1 turn" agent may
                   have taken 30 steps).
      - tools      distinct tool names it used (first 8).
      - label      the full first prompt, kept for a hover tooltip.
      - running    transcript liveness, the same signal index() uses.
    """
    root = _subagents_root(parent_sid)
    if root is None:
        return []
    tasks = _parent_tasks(parent_sid)
    out = []
    for f in sorted(root.glob("**/agent-*.jsonl"),
                    key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            st = f.stat()
        except OSError:
            continue
        msgs = _parse_transcript(f)["messages"]
        first_user = next((m["text"] for m in msgs if m["role"] == "user"), "")
        key = _norm120(first_user)
        match = None
        for t in tasks:
            k = t["key"]
            if k and (k == key or (len(key) >= 40 and (k.startswith(key[:80]) or key.startswith(k[:80])))):
                match = t
                break
        title = (match["description"] if (match and match["description"])
                 else _agent_title_fallback(first_user)) or f.stem
        tools = []
        for m in msgs:
            for tn in (m.get("tools") or []):
                if tn and tn not in tools:
                    tools.append(tn)
        out.append({
            "id": f.stem,                 # agent-<hex>: no slashes, URL-safe path param
            "title": title[:80],
            "agent_type": (match or {}).get("subagent_type", ""),
            "label": (first_user.strip().replace("\n", " ") or f.stem)[:200],
            "steps": sum(1 for m in msgs if m["role"] == "assistant"),
            "tools": tools[:8],
            "turns": sum(1 for m in msgs if m["role"] == "user"),
            "mtime": int(st.st_mtime),
            "running": liveness(st.st_mtime) == "active",
        })
    return out


def read_agent(parent_sid: str, agent_id: str) -> Optional[Dict]:
    """One subagent transcript, parsed exactly like read_session. Read-only.

    CONFINEMENT: agent_id is matched by STEM against files actually found under the
    parent's subagents dir -- it is never joined onto a path -- and the resolved
    file is re-checked to sit under that dir, so neither `..` nor a symlink can
    point the read outside <project>/<parent>/subagents/.
    """
    if "/" in agent_id or "\\" in agent_id or ".." in agent_id:
        return None
    root = _subagents_root(parent_sid)
    if root is None:
        return None
    root_r = os.path.realpath(root)
    for f in root.glob("**/agent-*.jsonl"):
        if f.stem != agent_id:
            continue
        if not os.path.realpath(f).startswith(root_r + os.sep):
            continue              # a symlink pointing out of the subagents dir
        return {"id": agent_id, "parent": parent_sid, **_parse_transcript(f)}
    return None
