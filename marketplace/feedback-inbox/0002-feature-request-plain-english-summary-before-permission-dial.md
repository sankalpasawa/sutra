---
issue: 2
title: "Feature request: Plain-English summary before permission dialogs (accessibility for non-technical users)"
author: vinitharmalkar
state: CLOSED
created: 2026-04-24T15:40:35Z
updated: 2026-04-27T21:19:37Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/2
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAhSAcg', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': "Shipped — closing.\n\n**Resolution path (Sutra plugin):**\n- `v1.14.0` (commit eff6b97) — bash permission-prompt plain-English summarizer hook landed (`bash-summary-pretool.sh`, PreToolUse Bash matcher).\n- `v1.14.1` (commit 77e3b90) — feedback-routing-rule, stop-the-bleed for the vinitharmalkar permission-friction pattern.\n- `v1.15.0` (commit d9e72be) — summarizer reframed to outcome-in-product-terms + prompt-scoped firing (so it doesn't fire on every internal sub-call).\n\n**On your install (2.4.0):** the hook is active. You were on 1.12.0 when you filed this and updated to 2.4.0 the same day, so you have all three increments.\n\n**Please verify** on a live permission prompt — the summary should appear above the raw command. If it doesn't fire on a case where it should, please reopen with the command + an indication of what summary you'd have wanted to see (so we can tune the heuristic).\n\n— filed via #2, closed by canonical-feedback-channel cleanup pass (D36)", 'createdAt': '2026-04-27T19:31:09Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/2#issuecomment-4329865330', 'viewerDidAuthor': True}, {'id': 'IC_kwDOR5MNCs8AAAABAh512w', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Hey — thanks for flagging this. Permission prompts now show a plain-English summary above the raw command (e.g., "this will delete 3 files from your downloads folder") so you don\'t have to read shell to decide. Update your plugin and you\'ll see it on the next prompt.', 'createdAt': '2026-04-27T21:19:37Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/2#issuecomment-4330517979', 'viewerDidAuthor': True}]
---

# #2 Feature request: Plain-English summary before permission dialogs (accessibility for non-technical users)

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-24T15:40:35Z  |  **Updated:** 2026-04-27T21:19:37Z
**URL:** https://github.com/sankalpasawa/sutra/issues/2

---

## Problem

As a non-technical user of Claude Code + Sutra, I find permission prompts extremely difficult to understand. When Claude asks for approval, it shows raw bash scripts — `curl`, `python3`, `rm -f`, multi-line heredocs — which are unreadable without a programming background.

## Feature Request

Before displaying any permission dialog, Sutra (or a Sutra hook) should prepend a 1–2 sentence plain-English summary of what the command actually does.

**Example:**
> "This will delete 3 files from your Downloads folder and update a spreadsheet to show which tenders are still open."

The raw command can remain visible below for technical users, but a human-readable summary should always appear first.

## Why This Matters

This would make Claude Code accessible to non-developers and prevent users from blindly approving commands they don't understand.
