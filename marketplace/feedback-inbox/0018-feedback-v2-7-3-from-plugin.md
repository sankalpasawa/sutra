---
issue: 18
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T07:20:17Z
updated: 2026-04-28T08:17:20Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/18
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAkmkOg', 'author': {'login': 'tommy29tmar'}, 'authorAssociation': 'NONE', 'body': 'The design looks pointed at the right failure mode: “can resume” is not the same as “knows what it was doing.” I would make the acceptance test explicitly distinguish those two.\n\nA few checks I would add:\n\n- clean stop with `done` sentinel → should not appear in the pending banner\n- blocked/paused sentinel → should appear with the last known goal and exact resume command\n- stream timeout/API error with no sentinel → should appear as `unknown/interrupted`, not be silently treated as resumable\n- two sessions in the same project → banner must show task slug + last action, not just project path\n- stale JSONL tail with no task checkpoint → should degrade to “inspect before resume,” not pretend it has a safe next step\n\nThe checkpoint record probably needs one more field beyond status/resume: `next_action` or `cursor`. Otherwise the user still has to reopen the transcript and reconstruct plan position, which is the expensive part after a context loss.', 'createdAt': '2026-04-28T07:54:35Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/18#issuecomment-4333347898', 'viewerDidAuthor': False}, {'id': 'IC_kwDOR5MNCs8AAAABAku-iQ', 'author': {'login': 'vinitharmalkar'}, 'authorAssociation': 'NONE', 'body': '**Triage note — feature request, not noise**\n\n**Real title:** Feature: Session Resumption UX — `sutra sessions` CLI + SessionStart banner + Stop checkpoint hook\n\n**Summary:** When a user restarts their terminal or has multiple Claude Code sessions, there is no way to know which sessions are resumable, what they were doing, or whether they ended mid-task. Current workaround: ask Claude to scan `~/.claude/projects/*.jsonl` manually — slow and inconsistent.\n\n**Proposed: 3-piece architecture**\n- `session-checkpoint.sh` (Stop hook) — writes status + resume_cmd to `~/.sutra/sessions.jsonl` on every turn end\n- `sutra sessions` CLI — reads sessions.jsonl, shows table of resumable sessions with `claude -r <id>` commands\n- `sessionstart-pending.sh` (SessionStart hook) — banners unfinished sessions at start of every new session, exits silently if nothing pending\n\n**Status detection:** `interrupted` via JSONL API Error pattern; `done/blocked/paused` via `SUTRA_SESSION_STATUS:` sentinel emitted by Claude; `unknown` as catch-all.\n\n**Full spec including edge cases, acceptance criteria, and file list is in the issue body.**\n\n**Version target:** 2.8.x · macOS Darwin 25.3.0', 'createdAt': '2026-04-28T08:17:20Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/18#issuecomment-4333485705', 'viewerDidAuthor': False}]
---

# #18 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T07:20:17Z  |  **Updated:** 2026-04-28T08:17:20Z
**URL:** https://github.com/sankalpasawa/sutra/issues/18

---

Feature Request: Session Resumption UX (3-piece architecture)

Submitted by: Vinit (Testlify, T3 install) | Session: 48102f10 | Date: 2026-04-28

PROBLEM: When a user restarts terminal or has multiple Claude Code sessions open, there is no way to know which sessions are alive/resumable, what each was doing, or whether any ended mid-task. Current workaround requires asking Claude to manually scan ~/.claude/projects/*.jsonl files — ~3 tool calls, inconsistent results, stream-timeout orphans look identical to clean closes at JSONL level.

PROPOSED: Three-piece architecture —

PIECE 1 — session-checkpoint.sh (Stop hook): Fires every Stop event. Reads ~/.claude/depth-registered for task slug. Detects status via: (a) JSONL ends with API Error -> interrupted, (b) Claude emits SUTRA_SESSION_STATUS: done/blocked/paused sentinel -> maps status, (c) else unknown. Appends one JSONL record to ~/.sutra/sessions.jsonl with session_id, project_dir, task_slug, status, reason, ended_at, resume_cmd. Governance block addition needed: Claude emits SUTRA_SESSION_STATUS: done/blocked/paused as last line of each session.

PIECE 2 — sutra sessions CLI: New subcommand. Reads ~/.sutra/sessions.jsonl, filters by date + status, prints formatted table with resume commands. Flags: --all (include completed/unknown), --json (raw JSONL), --project /path. Target: output in under 200ms, pure shell + python3, no network.

PIECE 3 — sessionstart-pending.sh (SessionStart hook): Fires every SessionStart. Counts interrupted/blocked/paused records from last 7 days in sessions.jsonl. If count > 0, emits boxed banner listing unfinished sessions with resume_cmd. If count = 0, exits silently. Target: under 100ms. This is highest-leverage — user doesn't have to ask.

FILES: hooks/session-checkpoint.sh (create), hooks/sessionstart-pending.sh (create), hooks/hooks.json (modify), bin/sutra (add sessions subcommand), scripts/sessions.sh (create), scripts/start.sh (modify), CLAUDE.md managed block (add sentinel rule), tests/unit/test-session-checkpoint.sh (create), tests/unit/test-sessions-cli.sh (create).

EDGE CASES: corrupt session file -> skip + log to sessions-errors.jsonl; same session resumed multiple times -> dedup by session_id show latest; sessions.jsonl unbounded growth -> sutra_retention_cleanup at 90d; terminal closed without Stop -> SessionStart falls back to JSONL orphan scan.

KILL-SWITCHES: SUTRA_SESSION_CHECKPOINT=0 / ~/.sutra-session-checkpoint-disabled and SUTRA_SESSION_PENDING=0 / ~/.sutra-session-pending-disabled independently.

ACCEPTANCE CRITERIA: sutra sessions <200ms, SessionStart banner <100ms, interrupted detection works for stream-timeout orphans, SUTRA_SESSION_STATUS sentinel parsed correctly, kill-switches work independently, --json output schema stable, retention cleanup runs, zero output when nothing pending.

PRIORITY: High. Every user who restarts terminal hits this. SessionStart surface is zero-friction — fires automatically, costs nothing when nothing to show.
