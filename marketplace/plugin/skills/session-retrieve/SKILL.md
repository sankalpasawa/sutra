---
name: session-retrieve
description: Use when the founder says "figure out past sessions", "what sessions got killed", "find my abruptly closed sessions", or similar — including after a laptop shutdown, crash, or API disconnect. Scans ~/.claude/projects/ for sessions that terminated mid-turn, identifies each by last-touched content, and returns the exact `claude -r <session-id>` resume command per session. Runs on the Claude Code terminal surface.
---

# Session Retrieve

When a session dies mid-turn (laptop shutdown, network loss, API timeout, OOM, kernel panic), Claude Code leaves the session `.jsonl` on disk but never writes a clean terminal turn. This skill finds those orphans and hands back resume commands.

## When to invoke

Any of these founder phrases → invoke:

- "figure out past sessions"
- "what sessions got killed"
- "find my abruptly closed sessions"
- "which sessions did I lose"
- "my laptop switched off — what was I working on"
- "find the crashed Claude sessions"
- "resume the session I lost"

Also invoke proactively when the founder references "the session from yesterday" or "what I was doing before" and no recent session is active — they may be pointing at an orphan.

## Terminal surface note

This skill is **Claude Code CLI only**. It reads `~/.claude/projects/<slug>/<session-id>.jsonl` — a directory layout specific to Claude Code's terminal harness. Does not apply to Claude Desktop, Claude.ai web, or API-SDK sessions.

## The procedure (5 steps, deterministic)

### Step 1 — Anchor the time window

Infer (or ask) when the crash happened. Default window: last 24 hours. Expect orphans to cluster tightly (laptop shutdown = all sessions die within seconds of each other). The cluster boundary is the first clue.

### Step 2 — List recent session files

```bash
find /Users/abhishekasawa/.claude/projects -name "*.jsonl" \
  -not -path "*/subagents/*" \
  -newermt "<START>" -not -newermt "<END>" 2>/dev/null \
  | xargs ls -lt 2>/dev/null | head -25
```

Exclude `/subagents/` — those are parent-managed; the parent jsonl is the true session.

### Step 3 — Detect orphan signatures (both flavors)

A session is an orphan if **any** of these are true in its `.jsonl`:

**Flavor A — Explicit API error.** The last `assistant` message text contains one of:
- `API Error: Unable to connect to API (ConnectionRefused)`
- `API Error: Unable to connect to API (FailedToOpenSocket)`
- `API Error: Stream idle timeout - partial response received`
- `API Error: Request timed out`

**Flavor B — Died mid-tool-use (silent death).** The process got killed BEFORE it could write an error. The jsonl simply stops. Detect with:
- Last `assistant` turn's `stop_reason` is `"tool_use"` (model was about to call tools, never got to emit the next turn), OR
- Last non-attachment event is `type: "user"` with a `tool_result` content block (tool finished, assistant never replied).

**This is the #1 thing most orphan-scanners miss.** The most severe crashes (laptop power-off, kernel panic) produce Flavor B, not Flavor A.

### Step 4 — Extract last content per session

```python
import json
path = "/Users/abhishekasawa/.claude/projects/<project-slug>/<session-id>.jsonl"
lines = open(path).readlines()
cwd = None; last_user = None; last_assistant_text = ""
last_assistant_stop = None
session_start_ts = None
for line in lines:
    try: d = json.loads(line)
    except: continue
    if d.get("cwd"): cwd = d["cwd"]
    if session_start_ts is None and d.get("timestamp"): session_start_ts = d["timestamp"]
    t = d.get("type"); msg = d.get("message", {})
    if t == "assistant" and isinstance(msg, dict):
        c = msg.get("content", [])
        if isinstance(c, list):
            for item in c:
                if isinstance(item, dict) and item.get("type") == "text":
                    last_assistant_text = item.get("text","")
        if msg.get("stop_reason") is not None:
            last_assistant_stop = msg.get("stop_reason")
    if t == "user" and isinstance(msg, dict):
        c = msg.get("content", "")
        if isinstance(c, str) and len(c) > 20 and not c.startswith("<"):
            last_user = c[:250]
has_api_err = any(sig in last_assistant_text for sig in [
    "API Error", "FailedToOpenSocket", "ConnectionRefused",
    "Stream idle timeout", "Request timed out", "Unable to connect"])
is_orphan = has_api_err or (last_assistant_stop not in ("end_turn", "stop_sequence", None))
```

### Step 5 — Exclude the current session

The scanner itself is running in a live session whose jsonl is also "mid-tool-use" (from its own POV). Exclude it by:

- Tagging any session whose `last_assistant_text` contains the word "orphan" or "session-retrieve" (scanner's own content), OR
- Tagging any session with `mtime` within the last 60 seconds, OR
- Asking the founder to confirm which sessions they recognize as truly lost.

## Project root decoding — CRITICAL

The `.jsonl` lives at `~/.claude/projects/<slug>/<session-id>.jsonl`.

The `<slug>` is the launch directory with `/` replaced by `-`, with a leading `-`.
Example: slug `-Users-me-Code-my-project` → launch dir `/Users/me/Code/my-project`.

**The launch directory is where `claude -r <id>` must be run from.** Not the `cwd` field in the jsonl (that's where the session `cd`'d TO during work — informational only).

`claude -r <id>` prints `No conversation found with session ID` when run from the wrong launch dir. **This is the #1 failure mode of this skill.** Always decode the slug and give that as the `cd` target.

## Output format (mandatory — readability gate)

```
## N Abruptly-Closed Sessions — <date> (<time-window>)

| # | Session ID | Task summary | How it died |
|---|---|---|---|
| 1 | <id-short> | <one-line what it was doing> | API-err | mid-tool-use |
...

## Resume commands

All N sessions launch from `<project-root>`:

```
cd <project-root>
claude -r <id1>   # <task summary 1>
claude -r <id2>   # <task summary 2>
...
```

(If sessions span multiple project roots, give one `cd`+`claude -r` block per root.)

## Priority recommendation

1. <session> first — <reason, e.g., uncommitted edits visible in `git status`>
2. <session> next — <blocking decision / downstream dependency>
...
```

## Rules

- Always decode the project slug from the jsonl path. Never use the `cwd` field for resume.
- Always dedupe sessions that share a project root into one `cd` block (typical: laptop shutdown from one repo → all orphans share the launch dir).
- Detect BOTH flavors (API error + mid-tool-use). Flavor B is the dominant failure mode for hard crashes.
- If the jsonl has fewer than 5 events or no distinguishable user/assistant content, skip it — probe session, not real work.
- Exclude the current running session from the orphan list.
- If the project has PreToolUse hooks enforcing input-routing/depth markers, always emit those blocks before the scan (hooks will block otherwise).

## Cross-references

- Memory: `feedback_daily_session_resumption_summary.md` — surface abruptly-closed prior sessions at session start.
- Related skill: `output-trace` — emit OS TRACE line after the report.
- Terminal surface: Claude Code CLI only.

## Self-check before returning

1. Did I give one `cd` per project root (decoded from slug, not cwd)?
2. Did I detect both API-error AND mid-tool-use orphans?
3. Did I exclude the current running session?
4. Did I explain how each session died (not just that it died)?
5. Did the orphans cluster into a tight time window (sanity-check against founder's "laptop shutdown" claim)?
