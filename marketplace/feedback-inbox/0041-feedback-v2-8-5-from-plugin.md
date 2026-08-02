---
issue: 41
title: "[feedback v2.8.5] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T10:08:56Z
updated: 2026-04-30T10:08:56Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/41
comments: []
---

# #41 [feedback v2.8.5] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T10:08:56Z  |  **Updated:** 2026-04-30T10:08:56Z
**URL:** https://github.com/sankalpasawa/sutra/issues/41

---

## Summary

Proposal for two new Sutra commands — `/core:resume` and `/core:bookmark` — plus matching shell helpers. They turn opaque session UUIDs into semantically titled, fuzzy-searchable, bookmarkable sessions. Built entirely on data Sutra already collects (input-routing blocks).

Fits the brain-layer positioning: Native captures per-session data; Core makes it usable. This is a small feature that demonstrates the abstract positioning concretely on day one.

## Problem

Session resume today requires copy-pasting a 36-character UUID into `claude --resume <uuid>`. Three frictions:

1. **UUIDs carry zero meaning.** `549dc875-cacf-...` says nothing about what the session was about.
2. **The built-in `/resume` picker shows recent sessions but with no titles** — so the user still has to open them blind.
3. **Across terminals, machines, or directories, finding the right session is a manual hunt** through `~/.claude/projects/*/`.

The improvement is small to ship, immediate in user-visible value, and structurally fits Sutra's "brain that makes Native's data legible" story.

---

## What's already true (load-bearing facts)

- Every Sutra-governed turn starts with an input-routing block whose first line is `INPUT: <paraphrase of what the user said>`. That line is **already a session title**, written by Claude on every turn.
- Session JSONL files live at `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`. Format is one JSON object per line; turns are interleaved.
- Sutra already has `~/.sutra/` as its writable user directory + `bin/sutra` dispatcher + `install-shell-helpers` mechanism. All the rails exist.

---

## Architecture — depth-first by component

### 1. Data layer — the session index

**File:** `~/.sutra/sessions/index.jsonl`

One JSONL row per known session. Stored locally, never pushed.

```json
{
  "session_id": "549dc875-cacf-4427-96a3-0372a4511216",
  "project_path": "<HOME>
  "project_dir_encoded": "-Users-vinit",
  "first_input": "run /core:start to initialize Sutra governance in this session",
  "last_input": "Can you create the architecture for /core:resume and brainstorm depth-first?",
  "ts_first": "2026-04-28T14:47:12Z",
  "ts_last": "2026-04-30T15:08:00Z",
  "msg_count": 28,
  "depth_marker": "5",
  "tags": []
}
```

**Why each field:**
- `session_id` — the UUID, primary key.
- `project_path` + `project_dir_encoded` — both stored so display can show the human path while resume can verify the encoded form Claude Code uses.
- `first_input` — title for the picker. Comes from the first input-routing INPUT line. This is what the session was *about* originally.
- `last_input` — context for "what was I doing when I left it?" Useful in the picker when sessions span multiple topics.
- `ts_first` / `ts_last` — sort by recency, render relative ages.
- `msg_count` — quick "depth of conversation" signal.
- `depth_marker` — most recent depth value used (informative, optional).
- `tags` — reserved for future bookmarks (joined to bookmarks file).

**Why JSONL not SQLite:** existing Sutra surface uses JSONL everywhere (metrics-queue, gate-log, hook-fires). One more JSONL is consistent. Performance is fine up to ~10k sessions.

**Why local-only:** the file contains user message text. Cross-machine sync is out of scope for v1. Privacy model matches v2.0 sutra (signals-not-content, opt-in, no central push).

### 2. Bookmarks file

**File:** `~/.sutra/bookmarks.jsonl`

```json
{"name": "sutra-brain", "session_id": "549dc875-...", "project_path": "<HOME> "created_at": "2026-04-30T15:00:00Z"}
{"name": "rfp-bot", "session_id": "a5cfb880-...", "project_path": "<HOME>/rfp", "created_at": "2026-04-25T10:00:00Z"}
```

Names must match `[a-z0-9-]+` (kebab-case). Append-only on creation; on update or delete, rewrite the whole file (small, infrequent operation).

### 3. Indexer — keeping the index fresh

Three triggers:

| Trigger | When | What it does |
|---|---|---|
| `lib/session-index.sh scan` | First-ever `/core:resume` call, or `--rebuild` flag | Walks `~/.claude/projects/*/`, reads first ~50 lines of each JSONL to extract `first_input`, builds index from scratch. |
| `hooks/session-start-index.sh` | SessionStart hook fires | Ensures current session has a row (creates if missing). Captures `first_input` as soon as the first input-routing block lands. |
| `hooks/stop-session-update.sh` | Stop hook fires (every turn ends) | Updates `last_input`, `ts_last`, `msg_count` for current session. O(1) operation — read-update-write of just the current row. |

**Title-extraction logic** (depth-first):

```
1. Read JSONL line by line.
2. For each "user" role message, search content for /^INPUT: (.+)$/.
3. The first match → first_input. The last match → last_input.
4. Fallback if no INPUT line found in entire JSONL:
   a. Take first user message content.
   b. Strip slash-command prefixes, quotes, and known boilerplate.
   c. Truncate to 80 chars.
5. Fallback-of-fallback: "<no title>" (rare — only ancient pre-Sutra sessions).
```

### 4. Slash commands — the in-session surface

#### `/core:resume`

| Invocation | Behavior |
|---|---|
| `/core:resume` (no arg) | Print last 10 sessions from index, sorted by `ts_last` desc. Each row: `[age] title — UUID-short`. End with copy-pasteable resume command for #1. |
| `/core:resume <query>` | Fuzzy match query against `first_input`, `last_input`, and bookmark names. 1 match → print the resume command. 0 matches → show full list. >1 matches → show matched subset. |
| `/core:resume --here` | Same as no-arg but filter to current `project_path`. |
| `/core:resume --last` | Print resume command for most-recent session (semantic alias for `claude -c`). |
| `/core:resume --rebuild` | Force full rescan of `~/.claude/projects/*/` and rebuild index. |

**Output format (no-arg):**

```
🧭 Recent Sutra sessions

  1. [now]      Sutra brain layer brainstorm           549dc875
  2. [3h ago]   Path A instruction manual              5213b5ae
  3. [1d ago]   RFP pipeline diagnosis                 ea5644cb
  4. [3d ago]   Sutra Bot Monday meeting prep          f7349b80

Resume #1:  claude --resume 549dc875-cacf-4427-96a3-0372a4511216
Or shell:   sresume sutra-brain   (if shell helpers installed)

Bookmarks:  sutra-brain → 549dc875   ·   rfp-bot → a5cfb880
```

**Why slash commands cannot relaunch Claude themselves:** they execute inside an already-running session. They can only print. The user pastes or types the resume command after exiting. This is a hard constraint of the Claude Code architecture, not a design choice.

#### `/core:bookmark`

| Invocation | Behavior |
|---|---|
| `/core:bookmark <name>` | Save current session UUID under `<name>`. Validates kebab-case. Refuses if name exists unless `--force`. |
| `/core:bookmark` (no arg) | List all bookmarks with their titles from the index. |
| `/core:bookmark --remove <name>` | Delete bookmark. |
| `/core:bookmark --rename <old> <new>` | Rename. |

**Output (creation):**

```
✓ Bookmarked current session as 'sutra-brain'
  → 549dc875-cacf-4427-96a3-0372a4511216
  Resume later:  sresume sutra-brain
```

#### `/core:sessions` (optional power-user view)

Same data as `/core:resume` but with filters: `--project <path>`, `--since <duration>`, `--depth <n>`, `--limit <n>`. Fits later, not v1.

### 5. Shell helpers — the *real* fix to the friction

The slash commands solve discovery and bookmarking. The shell helpers solve the actual relaunch.

**Installed via** `sutra install-shell-helpers` (already a Sutra mechanism). Adds to `~/.zshrc` / `~/.bashrc`:

```bash
sresume() {
  if [ -z "$1" ]; then
    # No-arg: show picker
    if command -v fzf >/dev/null; then
      local choice
      choice=$(jq -r '. | "\(.session_id)\t\(.first_input // "<untitled>")"' ~/.sutra/sessions/index.jsonl \
        | sort -r | head -50 | fzf --with-nth=2 --delimiter=$'\t')
      [ -n "$choice" ] && claude --resume "$(echo "$choice" | cut -f1)"
    else
      sutra resume --last  # fallback
    fi
  elif [ "$1" = "--last" ]; then
    claude -c
  else
    # Fuzzy match query
    local id
    id=$(sutra resume "$1" --print-id-only)
    [ -n "$id" ] && claude --resume "$id"
  fi
}

sbookmarks() { sutra bookmark; }
```

**Net result:** to resume any past session by partial title:

```bash
$ sresume brain
# launches claude --resume 549dc875-... with the matched session
```

No copy-paste, no UUIDs.

### 6. `bin/sutra` dispatcher additions

```
sutra resume [<query>] [--here|--last|--rebuild|--print-id-only]
sutra bookmark [<name>] [--remove|--rename|--list]
sutra sessions [--project|--since|--depth|--limit]
```

Slash commands (`/core:resume`, `/core:bookmark`) thin-wrap these.

---

## Depth-first edge cases

### A. Old sessions with no input-routing blocks

Sessions created before Sutra was active. Title fallback hierarchy already specified above. These sessions will appear with truncated first-message text or `<no title>`.

### B. Bookmark points to deleted session

Detect at display time: row missing from index OR JSONL no longer at expected path → render bookmark grayed-out with `(session no longer exists)`. Provide `sutra bookmark --prune` to remove dead bookmarks.

### C. Cross-directory resume

`claude --resume <uuid>` works from any cwd — Claude Code reads the session by UUID, not by current directory. So users can resume a session created in `/proj-a` from anywhere. Confirmed worth verifying with the Anthropic team but not blocking design.

### D. Duplicate bookmark names

Refuse with helpful error: `bookmark 'sutra-brain' already exists → 5213b5ae. Use --force to overwrite, or --rename.`

### E. Index corruption

`sutra resume --rebuild` regenerates from `~/.claude/projects/*/` ground truth. Any malformed row in `index.jsonl` is logged and skipped, not fatal.

### F. Performance at scale

10k sessions = 10k JSONL rows in index ≈ ~3 MB. Read-all-then-sort is fine. If users hit pain, switch to SQLite later — but premature for v1.

### G. Privacy / leakage

Session JSONLs contain everything the user typed. `index.jsonl` extracts only the `INPUT:` paraphrase line, which is **already a sanitized summary** Claude wrote during the session. Still: store local-only, scrub paths via existing `lib/privacy-sanitize.sh` before writing to index, never push to `sutra-data` or any remote.

### H. Multi-machine sync

Out of scope for v1. If users want cross-machine: copy `~/.sutra/sessions/index.jsonl` + `~/.sutra/bookmarks.jsonl` manually. v2 could ship `sutra sessions sync --to <machine>` over SSH if demand emerges.

### I. Session title staleness

`first_input` is set once and frozen. `last_input` updates on each Stop. Both can drift from "what this session is now about." Acceptable v1 behavior — the user can rebookmark with a new explicit name if needed.

### J. Concurrent writes

Two Claude sessions in the same project both writing to `index.jsonl` on Stop hooks. Resolve via `flock` on a sidecar lock file: `~/.sutra/sessions/index.jsonl.lock`. Standard sutra discipline.

---

## Implementation sketch (for the team — not a sprint plan)

| Component | New file | Lines (rough) |
|---|---|---|
| Index reader/writer | `lib/session-index.sh` | ~150 |
| SessionStart hook | `hooks/session-start-index.sh` | ~40 |
| Stop hook | `hooks/stop-session-update.sh` | ~50 |
| Resume subcommand | `scripts/resume.sh` | ~120 |
| Bookmark subcommand | `scripts/bookmark.sh` | ~90 |
| Slash command def | `commands/resume.md`, `commands/bookmark.md` | ~30 |
| Shell helpers | append to `scripts/install-shell-helpers.sh` | ~40 |
| Tests | `tests/unit/test-session-index.sh`, `tests/unit/test-bookmark.sh` | ~200 |

Total: ~720 LoC for v1. Realistic for one focused engineering pass.

---

## Open questions for the team

1. **Slash command naming**: `/core:resume` matches the existing `/core:*` family. Confirm or override.
2. **Shell helper namespace**: `sresume` / `sbookmarks` short and zsh-friendly, but conflicts with any user's existing aliases. Alternative: `sutra-resume` (verbose but namespaced).
3. **Should bookmarks survive `claude plugin uninstall`?** Argument for yes (user data, lives in `~/.sutra/`, not plugin cache). Argument for no (clean uninstall principle). Recommend yes — bookmarks are user content, not plugin state.
4. **Should `/core:resume` show sessions from ALL projects by default, or only the current project?** Recommend: all projects, with `[project-name]` rendered next to each row, and `--here` to filter. Cross-project visibility is the actual win over `claude -c`.
5. **`/core:resume <num>` selection by row number?** I.e. `/core:resume 2` resumes #2 from the most recent listing. Adds state (the last-shown list). Probably yes — common UX pattern. Track in `~/.sutra/sessions/last-listing.jsonl`.
6. **Title editing**: should `/core:bookmark <name> --title "Custom title"` allow overriding the auto-extracted title? Recommend: defer to v2.

---

## Why this is small AND strategic

It's tactically small: ~720 LoC, ~1 engineering week, no new dependencies, fits cleanly in existing Sutra surfaces.

It's strategically valuable because **it's the first feature where users feel "Core knows things Native can't."** Native sees one project; Core sees them all. Native captures hook fires; Core remembers what those fires were *about*. The brain-layer story stops being abstract the moment a user types `sresume brain` and lands back where they were.

Build this before the OS engines if it helps prove the positioning to early adopters. The data plumbing it builds (`~/.sutra/sessions/`, hooks for SessionStart + Stop) is the same plumbing Coverage / Estimation / Adaptive Protocol will need.

---

*Submitted 2026-04-30 from a Claude Code session running sutra@2.9.0. Architecture is depth-first design only — implementation, sequencing, and prioritization are Sutra team decisions.*
