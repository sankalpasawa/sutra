---
name: sessions
description: Unified Claude Code session tool — dashboard of every session (last instruction, last reply, idle time, blocker), interactive fuzzy picker to resume sessions, bookmark management, and daily-refresh scheduler. Default subcommand is `dash` when invoked from chat (no tty). Subcommands — `dash` (markdown report + chat summary), `pick` (fzf/numbered picker, then resumes), `list [N]`, `resume <id-or-bookmark>`, `last` (claude -c), `bookmark <name> [id]`, `unbookmark <name>`, `schedule install/uninstall/status`. Common flags — `--here` (current cwd only), `--top N` (chat-view rows, default 15), `--no-write`.
---

# sessions — unified session management skill

Single surface for everything you do with Claude Code session transcripts:
see what's running, see what's blocked, jump back into one, bookmark
important ones, and schedule a daily refresh.

## Relation to session-retrieve

`session-retrieve` is a **diagnostic** skill — it finds crashed/orphaned
sessions after a laptop shutdown or API timeout. `sessions` is the
**day-to-day** tool — dashboard, picker, bookmarks, schedule. They are
complementary; invoke `session-retrieve` for crash forensics and `sessions`
for normal session navigation.

## Architectural home

This skill ships as:

- `skills/sessions/SKILL.md` — this invocation guide (company catalog layer)
- `scripts/sessions.py` — the Python implementation (~700 LOC, stdlib only)

The script is a standalone CLI; it does not import Sutra internals.
Users installing this skill via `~/.claude/skills/sessions/` should
symlink or copy `sessions.py` adjacent to `SKILL.md`.

## When to invoke

Invoke when the user:

- Types `/sessions` or `/sessions <subcommand>` (any form)
- Asks "show me all my sessions", "which sessions are blocked / stale / waiting on me"
- Asks "what was the last thing in session X" or "help me get back into the session about Y"
- Wants to bookmark a session, resume by name, or check what's idle
- Wants to set up a daily auto-refresh of the dashboard

## Terminal surface

Claude Code CLI only. Reads `~/.claude/projects/<slug>/*.jsonl` — the
transcript layout specific to Claude Code's terminal harness.

## How to invoke the script

```bash
SKILL_DIR="${SUTRA_SKILL_BASE:-$HOME/.claude/skills}/sessions"
python3 "$SKILL_DIR/sessions.py" <subcommand> [args...]
```

If the user provided no subcommand, default to `dash` when stdout is not
a tty (chat context), or `pick` when stdout is a tty (terminal context).
The script itself applies this smart default when called with no args.

## Subcommands

| Subcommand | What it does |
|---|---|
| `dash` | Scan all sessions → write `~/session-dashboard.md` → print chat-view summary (flagged table + most-recent N) |
| `pick [QUERY]` | Fuzzy-pick a session and resume it (fzf if installed; numbered fallback) |
| `list [N]` | Flat list of recent sessions — age, 8-char id, title, bookmark name if any |
| `resume <id-or-name>` | Direct resume by id-prefix or bookmark name → `claude --resume <uuid>` |
| `last` | Resume most recent session → `claude -c` |
| `bookmark <name> [id]` | Save a name→session-id mapping (id defaults to most recent) |
| `unbookmark <name>` | Remove a bookmark |
| `schedule install` | macOS: install daily 08:00 launchd job; Linux: print cron line |
| `schedule uninstall` | Remove the launchd job |
| `schedule status` | Report whether the daily job is loaded |

Common flags (applied where relevant):
- `--here` — restrict to sessions started in the current cwd
- `--top N` — cap chat-view rows (default 15)
- `--no-write` — print only, don't write the markdown report file
- `--output PATH` — override the default `~/session-dashboard.md` path

## Blocker heuristics

The script infers a blocker tag from transcript content (no structured
field exists in Claude Code transcripts):

| Tag | Detection rule |
|---|---|
| `rate-limit` | An assistant message has `error: rate_limit` |
| `api-error <status>` | Message has `isApiErrorMessage: true` |
| `perm-denied` | Last reply matches `permission(s) denied / denied the tool` |
| `needs-input` | Last reply matches `waiting on / blocked on / can you provide` |
| `open-question` | Last non-empty reply line ends with `?` |
| `error` | Last reply mentions `traceback` or `exception` |
| `stale` | >7 days idle, no other tag |
| `—` | No blocker detected |

## Bookmarks

Stored at `~/.sutra/bookmarks.jsonl` — compatible with the legacy
`sresume` format:

```json
{"name": "my-session", "session_id": "de74268b-...", "created_at": "2026-05-05T..."}
```

The `resume` subcommand resolves names first, then falls back to
id-prefix matching. The `pick` subcommand appends `[bookmark-name]` to
the picker row when the session is bookmarked.

## Title extraction

Titles are pulled from the first non-bootstrap `INPUT:` line (Sutra
discipline) in the transcript, falling back to the first substantive
user message. Bootstrap noise (Sutra activation, `/core:start`, etc.) is
skipped via:

```
BOOTSTRAP_RE = /core:(start|status|update|sbom|permissions|uninstall|depth-check)
              | ^Run /core:
              | activate Sutra | initialize Sutra
```

This produces meaningful titles even in sessions that open with Sutra
governance hooks.

## Smart default

When called with no subcommand:

- `stdout.isatty()` → `pick` (interactive terminal — show the fuzzy picker)
- not tty → `dash` (chat context — render the dashboard)

This means `/sessions` from a slash command always renders the dashboard,
while `sessions` in a terminal opens the interactive picker.

## Daily refresh

`schedule install` writes a macOS launchd plist to
`~/Library/LaunchAgents/com.user.claude-sessions-dashboard.plist` that
fires at 08:00 daily, regenerates `~/session-dashboard.md`, and logs to
`~/Library/Logs/claude-sessions-dashboard.log`.

`schedule uninstall` removes the plist and unloads the job.

On Linux, `schedule install` prints a `crontab` line instead.

## Portability

- No hardcoded usernames — all paths via `Path.home()`
- No external dependencies beyond Python stdlib
- Cross-platform script; launchd installer is Darwin-only (Linux gets cron line)
- The skill works whether `sresume` is installed or not (sresume bookmarks are reused if present)

## Output delivered to user

After running, surface:

1. The script's stdout verbatim — it's already markdown-formatted with tables
2. For `dash`: confirm the report file path (`~/session-dashboard.md`)
3. For `pick`: the resume happens via `os.execvp("claude", ["claude", "--resume", uuid])` — confirm the handoff
4. For `bookmark` / `unbookmark` / `schedule`: pass through the one-line confirmation

## Self-check before returning

1. Did I call the right subcommand given the user's phrasing?
2. For `dash` — did I surface the flagged sessions prominently (those are the ones needing action)?
3. For `resume` — is the session id fully resolved (bookmark name → full uuid)?
4. Did I include the full report path so the user can open it?
