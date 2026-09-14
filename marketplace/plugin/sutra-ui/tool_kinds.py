"""What KIND of thing a tool call is -- the one table, for every provider.

WHY. Today every tool call arrives at the screen as one flat `tool` frame, so a
subagent, a shell command, a file edit and a web search look identical. The
frame SET does not change (no old client breaks); the `tool` frame gains four
fields the adapter fills in, and the client draws a different card per `kind`:

    kind    one of KINDS below
    title   the short human label for the card header -- the command, the file
            name, the query
    detail  an optional one-line summary under it (rows changed, matches, exit
            code)
    meta    an optional small dict the card may show ({"path": ...,
            "exit_code": 0, "agent": "explore", ...})

WHY ITS OWN MODULE, and not part of provider_adapters. All three runtimes
(session_runtime, codex_runtime, acp_runtime) classify a tool at the moment they
emit its frame, and all three are imported BY provider_adapters. Putting the
table there would be an import cycle. This file imports nothing local, so every
runtime can use it, provider_adapters re-exports it, and the UI workstream can
reach the same table through an API rather than re-deriving it at paint time --
two copies of this mapping is how one of them goes stale.

TWO RULES THAT OVERRIDE EVERYTHING BELOW
  1. An unknown name falls back to `other` and MUST still render exactly as it
     does today. This table may never be the reason a tool call disappears from
     the screen.
  2. The same classifier runs over STORED history (the `tool_use` blocks in old
     chats), so a chat from three months ago gets the new cards without any
     migration of saved files. That is why names this build no longer offers are
     still in the table.
"""
import os


KINDS = ("subagent", "command", "file_edit", "file_read", "search",
         "web_search", "web_fetch", "plan", "todo", "notebook", "mcp",
         "compaction", "other")

#: Claude tool names -> kind. The names were MEASURED from a live
#: `claude -p ... --output-format stream-json --verbose` system/init frame on
#: 2.1.270 (2026-09-14), not guessed. That build's full tool list:
#: Artifact, Bash, CronCreate, CronDelete, CronList, DesignSync, Edit,
#: EnterWorktree, ExitWorktree, ListAgents, Monitor, NotebookEdit,
#: PushNotification, Read, RemoteTrigger, ReportFindings, ScheduleWakeup,
#: SendMessage, Skill, Task, TaskOutput, TaskStop, ToolSearch, WebFetch,
#: WebSearch, Workflow, Write.
#:
#: `Agent` and `MultiEdit` are kept although this build does not offer them:
#: they appear in older transcripts, and rule 2 above means this classifier has
#: to read history it did not write.
#:
#: NOT MAPPED ON PURPOSE, so they land on `other` and render exactly as today:
#: Artifact, Cron*, DesignSync, EnterWorktree, ExitWorktree, Monitor,
#: PushNotification, RemoteTrigger, ReportFindings, ScheduleWakeup, SendMessage,
#: Skill, ToolSearch, Workflow. None of them is one of the thirteen card shapes,
#: and inventing a kind for each would be the guessing this table exists to stop.
#:
#: NotebookEdit resolves to `notebook`, NOT `file_edit`. The contract table
#: lists it in both rows; the more specific kind exists precisely so a notebook
#: edit can be drawn differently, so the specific one wins. Decided once, here.
CLAUDE_KINDS = {
    "task": "subagent", "agent": "subagent", "taskoutput": "subagent",
    "taskstop": "subagent", "listagents": "subagent",
    "bash": "command", "bashoutput": "command", "killshell": "command",
    "edit": "file_edit", "write": "file_edit", "multiedit": "file_edit",
    "notebookedit": "notebook",
    "read": "file_read",
    "grep": "search", "glob": "search",
    "websearch": "web_search",
    "webfetch": "web_fetch",
    "exitplanmode": "plan",
    "todowrite": "todo",
}

#: Codex `item.type` -> kind. `command_execution` is the ONLY one measured on
#: this build (codex-cli 0.154.0): codex_runtime._TRANSLATED_ITEM_TYPES records
#: that agent_message and command_execution are the only translated types and
#: that nothing else was ever observed on stdout. The rest are here so the card
#: is right the day codex starts emitting them; being wrong about an
#: unobserved type costs nothing, because an unrecognised one already falls back
#: to `other`.
CODEX_KINDS = {
    "command_execution": "command",
    "file_change": "file_edit", "patch_apply": "file_edit",
    "file_read": "file_read",
    "file_search": "search",
    "web_search": "web_search",
    "web_fetch": "web_fetch",
    "plan": "plan", "plan_update": "plan",
    "todo": "todo", "todo_list": "todo",
    "compaction": "compaction", "context_compaction": "compaction",
    "multi_agent": "subagent", "delegation": "subagent", "subagent": "subagent",
}

#: ACP `toolCall.kind` -> kind. These are the ACP protocol's own vocabulary
#: (read / edit / delete / move / search / execute / think / fetch /
#: switch_mode / other), which is exactly what acp_runtime._emit_tool_frame
#: already puts in the frame's `name` field.
ACP_KINDS = {
    "execute": "command",
    "edit": "file_edit", "delete": "file_edit", "move": "file_edit",
    "read": "file_read",
    "search": "search",
    "fetch": "web_fetch",
    "plan": "plan",
    "think": "other",
    "switch_mode": "other",
}

TITLE_MAX = 160


def kind_table():
    """The whole mapping, for an API the UI can read instead of duplicating it."""
    return {"kinds": list(KINDS),
            "claude": dict(CLAUDE_KINDS),
            "codex": dict(CODEX_KINDS),
            "acp": dict(ACP_KINDS)}


def _short(value, limit=TITLE_MAX):
    if not isinstance(value, str):
        return ""
    v = " ".join(value.split())
    return v[:limit] + ("…" if len(v) > limit else "")


def _basename(path):
    """The file name, for a card header. The full path still ships in `meta`, so
    nothing is lost -- a header showing the last 40 characters of a long path is
    the thing that is actually unreadable."""
    if not isinstance(path, str) or not path.strip():
        return ""
    return os.path.basename(path.rstrip("/")) or path


def classify(provider_id, name, tool_input=None, extra=None):
    """One tool call -> {"kind", "title", "detail", "meta"}.

    provider_id  "claude" / "codex" / an ACP provider id ("deepseek",
                 "cursor"). Anything else is read as Claude-shaped.
    name         the Claude tool name, the Codex item type, or the ACP kind --
                 whatever already goes in the frame's `name` field.
    tool_input   the tool's input dict when there is one. Claude has it at
                 phase=start; Codex and ACP mostly do not.
    extra        anything cheap the caller already had: `title` (the fallback
                 label -- pass the `summary` the frame already carries, so a
                 card header and the summary beside it cannot disagree),
                 command, exit_code, matches, lines_added, lines_removed, agent,
                 query, url, path, detail.

    NEVER RAISES. A tool with an unexpected shape must not take a turn down, and
    a classifier that threw would do exactly that. Every failure path lands on
    `other` with an empty title, which renders as today.
    """
    try:
        return _classify(provider_id, name, tool_input, extra)
    except Exception:           # noqa: BLE001 -- see the contract above
        return {"kind": "other", "title": "", "detail": None, "meta": {}}


def _classify(provider_id, name, tool_input, extra):
    raw = (name or "").strip()
    low = raw.lower()
    inp = tool_input if isinstance(tool_input, dict) else {}
    extra = extra if isinstance(extra, dict) else {}

    if provider_id == "codex":
        kind = CODEX_KINDS.get(low, "other")
    elif provider_id in ("deepseek", "cursor"):
        kind = ACP_KINDS.get(low, "other")
        # "fetch WITH A QUERY" is a web search, not a page fetch -- the one
        # place ACP's vocabulary is coarser than the card set.
        if kind == "web_fetch" and (inp.get("query") or extra.get("query")):
            kind = "web_search"
    else:
        # Claude, and anything else Claude-shaped. An `mcp__*` name is an MCP
        # tool whatever else it looks like, so it is tested before the table.
        kind = "mcp" if low.startswith("mcp__") else CLAUDE_KINDS.get(low, "other")

    if kind not in KINDS:
        kind = "other"

    meta = {}
    title = ""

    if kind == "subagent":
        agent = (inp.get("subagent_type") or inp.get("agent_type")
                 or extra.get("agent") or "")
        if agent:
            meta["agent"] = _short(agent, 64)
        desc = inp.get("description")
        title = _short("%s: %s" % (agent, desc) if agent and desc
                       else (desc or agent or ""))
    elif kind == "command":
        cmd = inp.get("command") or extra.get("command") or ""
        if cmd:
            meta["command"] = _short(cmd, 4000)
        title = _short(cmd)
    elif kind in ("file_edit", "file_read", "notebook"):
        path = (inp.get("file_path") or inp.get("notebook_path")
                or inp.get("path") or extra.get("path") or "")
        if path:
            meta["path"] = _short(path, 1024)
        title = _short(_basename(path))
    elif kind == "search":
        pat = inp.get("pattern") or inp.get("query") or extra.get("pattern") or ""
        if pat:
            meta["pattern"] = _short(pat, 512)
        title = _short(pat)
    elif kind == "web_search":
        q = inp.get("query") or extra.get("query") or ""
        if q:
            meta["query"] = _short(q, 512)
        title = _short(q)
    elif kind == "web_fetch":
        url = inp.get("url") or extra.get("url") or ""
        if url:
            meta["url"] = _short(url, 1024)
        title = _short(url)
    elif kind == "mcp":
        # mcp__<server>__<tool>. Both halves are worth showing: the server is
        # what tells the operator WHOSE tool just ran.
        parts = raw.split("__")
        if len(parts) >= 3 and parts[1]:
            meta["server"] = parts[1]
            meta["tool"] = "__".join(parts[2:])
            title = "%s · %s" % (parts[1], meta["tool"])

    if not title:
        # The caller's own summary first (it went through the same
        # session_runtime._tool_summary every frame already uses), then the raw
        # name, so a card is never headerless.
        title = _short(extra.get("title") or raw)

    # ---- detail: ONLY from what the caller already had in hand ---------------
    # Nothing here re-reads a file, re-runs a diff or parses output. A `detail`
    # that costs a syscall does not belong on a frame emitted mid-turn.
    detail = None
    exit_code = extra.get("exit_code")
    if isinstance(exit_code, int):
        meta["exit_code"] = exit_code
        detail = "exit %d" % exit_code
    for key in ("matches", "lines_added", "lines_removed"):
        v = extra.get(key)
        if isinstance(v, int):
            meta[key] = v
    if "lines_added" in meta or "lines_removed" in meta:
        detail = "+%d / -%d" % (meta.get("lines_added", 0),
                                meta.get("lines_removed", 0))
    elif isinstance(meta.get("matches"), int):
        detail = "%d matches" % meta["matches"]
    if extra.get("detail"):
        detail = _short(extra["detail"], 200)

    return {"kind": kind, "title": title, "detail": detail, "meta": meta}
