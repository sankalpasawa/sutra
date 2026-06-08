---
issue: 22
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T07:52:26Z
updated: 2026-04-28T08:17:44Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/22
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAkvHjw', 'author': {'login': 'vinitharmalkar'}, 'authorAssociation': 'NONE', 'body': "**Triage note — feature request, not noise**\n\n**Real title:** Feature: Task-Done Alerter — native desktop notification with Snooze/Dismiss when Claude finishes a task\n\n**Summary:** When Claude completes a task and is awaiting the user, Sutra should fire a native desktop notification after a 5-minute grace period. If the user doesn't respond, re-alert every 5 minutes. Zero noise when nothing is pending, zero polling overhead when dismissed.\n\n**The problem:** Claude finishes. User is in Slack or a meeting. They return 30 minutes later — session sat idle the whole time with no signal sent. This is the single most common friction point in agentic workflows.\n\n**How it works:**\n1. Claude emits `SUTRA_SESSION_STATUS: done` (from session resumption feature, issue #18)\n2. Stop hook writes `~/.sutra/pending-ack.json` + spawns `sutra-alerter` daemon\n3. After 5-min grace → macOS notification via `alerter` binary (MIT, ~200KB): title, task slug, session ID, buttons: [Open Session] [Snooze 20m] [Dismiss]\n4. Open Session → brings terminal to front + copies `claude -r <id>` to clipboard\n5. Snooze → writes `snooze_until` timestamp, re-alerts after 20 min\n6. Dismiss → daemon exits cleanly\n\n**Smart suppression:** screen-lock aware (macOS ioreg check), DND-aware, privacy mode (hide task slug), batches multiple pending tasks into one notification.\n\n**CLI:** `sutra pending` (list awaiting tasks), `sutra ack` (dismiss all), `sutra ack --snooze 20`\n\n**Pairs with issue #18** — both write to shared session state via `session_id`. Recommend shipping together.\n\n**Full spec including cross-platform fallbacks, edge cases, acceptance criteria, and file list is in the issue body.**\n\n**Version target:** 2.8.x · macOS Darwin 25.3.0", 'createdAt': '2026-04-28T08:17:44Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/22#issuecomment-4333488015', 'viewerDidAuthor': False}]
---

# #22 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T07:52:26Z  |  **Updated:** 2026-04-28T08:17:44Z
**URL:** https://github.com/sankalpasawa/sutra/issues/22

---

Feature Request: Task-Done Alerter — desktop notification with snooze/dismiss when Claude finishes a task

SUMMARY:
When Claude completes a task and is awaiting user input, Sutra should fire a native desktop notification after a 5-minute grace period. If the user doesn't respond, re-alert every 5 minutes with Snooze 20m and Dismiss options. Zero noise when nothing is pending. Zero polling overhead when dismissed.

THE PROBLEM:
Claude finishes a task. User is in Slack, email, or a meeting. They return 30 minutes later — session has been idle the whole time. No signal was ever sent. This is the single most common friction point in agentic workflows: not knowing when Claude is done without switching back to the terminal to check.

HOW IT WORKS — END TO END:
1. Claude emits SUTRA_SESSION_STATUS: done (or blocked) at end of turn
2. Stop hook fires → task-done-notifier.sh writes ~/.sutra/pending-ack.json + spawns sutra-alerter daemon
3. Daemon wakes every 60s, checks pending-ack.json
4. After 5-min grace period from task end → fires macOS notification via alerter binary (MIT, ~200KB):
   Title: 'Sutra — Task Complete'
   Message: 'Monday meeting Google Doc write · 4 mins ago'
   Subtitle: 'Session 33a9fe88'
   Actions: [Open Session] [Snooze 20m] [Dismiss]
5. Open Session → brings terminal to front + copies resume_cmd to clipboard
   Snooze 20m → writes snooze_until = now+20min to pending-ack.json, re-alerts after
   Dismiss → sets dismissed=true, daemon exits cleanly if no other pending records
   Timeout (user ignores) → re-alerts next 5-min cycle

pending-ack.json schema:
{ session_id, task_slug, status, ended_at, resume_cmd, first_alert_at, snooze_until, dismissed }

MULTIPLE PENDING TASKS:
If 2+ tasks unacknowledged, batch into one notification:
'Sutra — 2 tasks awaiting you: Monday meeting Google Doc (8 mins), Slack bot setup (22 mins)'
Actions: [Review All] [Snooze All 20m] [Dismiss]
Review All runs sutra pending in terminal.

PIECE 1 — task-done-notifier.sh (Stop hook):
Checks SUTRA_SESSION_STATUS: sentinel in last assistant turn. If done or blocked: write pending-ack.json + spawn daemon (idempotent). If unknown/absent: no action.

PIECE 2 — sutra-alerter (background daemon):
Shell + python3 loop. Per record logic: skip if dismissed, skip if snooze_until > now, skip if within 5-min grace period, else fire notification. Exits when all records dismissed. No process stays alive when nothing is pending.

PIECE 3 — sutra pending / sutra ack CLI:
  sutra pending              → table of tasks awaiting input with resume_cmd
  sutra ack                  → dismiss all
  sutra ack --snooze 20      → snooze all 20 minutes
  sutra ack <session_id>     → dismiss specific session

PIECE 4 — lib/notify.sh (cross-platform dispatch):
  macOS primary: alerter binary (interactive buttons, MIT license)
  macOS fallback: osascript display notification (no buttons, Notification Center only)
  Linux: notify-send + zenity for button interactions
  Windows: PowerShell New-BurntToastNotification

PIECE 5 — Smart suppression:
  Screen locked (macOS ioreg check) → queue alert, fire on unlock
  Do Not Disturb active → queue, fire when DND ends
  SUTRA_ALERT_SHOW_TASK=0 → notification shows 'Task complete' without task slug (privacy)
  Rate limit / blocked status → fire immediately, no 5-min grace (user needs to act)
  User actively typing in terminal → suppress this cycle, recheck in 60s
  blocked status (not done) → alert immediately with reason: 'Slack bot setup — needs xoxb- token'

INTEGRATION WITH SESSION RESUMPTION (issue #18):
pending-ack.json and sessions.jsonl share session_id. sutra pending and sutra sessions are two views of the same state — one filtered by acknowledgment, one by resumability. Both surface the same resume_cmd. Daemon can backfill pending-ack.json from sessions.jsonl on startup for sessions that completed before the hook existed.

FILES TO CREATE/MODIFY:
  hooks/task-done-notifier.sh      — Create (Stop hook, writes pending-ack.json, spawns daemon)
  hooks/hooks.json                  — Modify (register Stop hook)
  bin/sutra-alerter                 — Create (background daemon, 60s polling loop)
  scripts/pending.sh                — Create (sutra pending CLI)
  scripts/ack.sh                    — Create (sutra ack CLI)
  scripts/start.sh                  — Modify (init ~/.sutra/pending-ack.json on first run)
  lib/notify.sh                     — Create (cross-platform notification dispatch)
  ARCHITECTURE.yaml                 — Modify (document daemon + pending-ack state file)
  PERMISSIONS.md                    — Modify (document alerter binary + new state files)
  tests/unit/test-alerter-logic.sh  — Create (snooze math, suppress logic, multi-task batching)

KILL-SWITCHES:
  SUTRA_TASK_ALERTS=0 env var
  ~/.sutra-task-alerts-disabled file
  Per-session: sutra ack <session_id>

ACCEPTANCE CRITERIA:
  - Notification fires within 60s of 5-min grace period expiring
  - Snooze writes correct timestamp, re-alerts after exactly snooze duration
  - Daemon exits cleanly (no zombie process) when all records dismissed
  - Fallback to osascript if alerter not installed — zero hard dependency
  - SUTRA_ALERT_SHOW_TASK=0 hides task slug from notification body
  - sutra pending output in under 100ms (file read only)
  - Screen-lock suppression works on macOS (ioreg CGSSessionScreenIsLocked check)
  - Zero notifications fire for sessions with unknown status (no SUTRA_SESSION_STATUS sentinel)
  - Integration: sutra sessions and sutra pending both show same session, same resume_cmd

DEPENDENCY: Pairs with issue #18 (session resumption) — both write to shared session state. Recommend shipping together or designing schemas in coordination. Alerter daemon can be the same process as sessionstart-pending.sh trigger if unified.

PRIORITY: High. This eliminates the most common agentic workflow friction: not knowing when Claude is done. The alerter binary (alerter on macOS) is MIT-licensed and trivially bundled. Core logic is pure shell + python3. No network required.
