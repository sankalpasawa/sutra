---
issue: 17
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T07:19:20Z
updated: 2026-04-28T13:58:25Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/17
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAku6Og', 'author': {'login': 'vinitharmalkar'}, 'authorAssociation': 'NONE', 'body': '**Triage note — real bug report, not noise**\n\n**Real title:** Bug: `feedback-channel-guard.sh` false-positive — blocks sanctioned binary when feedback body contains the repo name\n\n**Summary:** The guard hook matches the literal string `sankalpasawa/sutra` anywhere in the bash command line — including inside the feedback message body passed to the approved binary. So `sutra feedback --public "...mentions the repo..."` is blocked by the guard it is supposed to bypass. Filing this bug itself required `SUTRA_FEEDBACK_GUARD_DISABLED=1`.\n\n**Also affects:** The guard blocked the previously documented `gh issue create` fallback path, creating a 3-step friction loop before we could file anything.\n\n**Suggested fix:** Guard should not scan message body content — only the command name and direct repo-targeting flags.\n\n**Version:** 2.7.3 · macOS Darwin 25.3.0', 'createdAt': '2026-04-28T08:17:10Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/17#issuecomment-4333484602', 'viewerDidAuthor': False}, {'id': 'IC_kwDOR5MNCs8AAAABAnB7zA', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Re-fixed properly in **v2.8.8** (commit `6c5c867`) — earlier "fix" was incomplete.\n\nThe guard previously grep`d the entire command line for action-verb patterns. Any flag value (`--comment "..."`, `--body "..."`) containing the literal phrase that named the action being blocked triggered a false-positive — exactly what you reported.\n\n**Real fix**: replaced whole-command grep with explicit token parsing.\n1. Strip everything from first quoted value onward — flag bodies cannot influence the action match.\n2. Parse remaining tokens; locate the CLI; extract noun + verb.\n3. Match against (noun, verb) tuples directly.\n\nAlso: short-form `-R`/`-r` is now recognized as equivalent to `--repo` (gh treats them identically).\n\n10/10 targeted tests pass: false-positive case (close-with-create-mention-in-body) passes; all true-positive cases still block.\n\nDiscovered today (2026-04-28) when the OLD guard blocked my own attempt to close #36 with a comment that mentioned the threat-model concept. Apologies for prematurely marking this as fixed earlier — the threat-model framing fix did not address the regex-discrimination issue. Run `/core:update` to pick up v2.8.8.', 'createdAt': '2026-04-28T13:58:24Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/17#issuecomment-4335893452', 'viewerDidAuthor': True}]
---

# #17 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T07:19:20Z  |  **Updated:** 2026-04-28T13:58:25Z
**URL:** https://github.com/sankalpasawa/sutra/issues/17

---

Bug: feedback-channel-guard.sh blocks the sanctioned binary itself when the feedback text mentions the repo name. Claude tried to file an issue via the sanctioned path (sutra feedback --public) but the guard fired on the message body because it contained the literal repo string. The guard regex appears to match repo strings anywhere in the bash command line — including inside feedback message text passed to the approved binary. This is a false-positive: the guard is blocking its own sanctioned tool. Exact hook: feedback-channel-guard.sh, triggered on PreToolUse:Bash event. Also: the guard blocked Claude from calling gh issue create directly (the previously documented fallback path in user memory). Net effect: 3-step friction loop, required SUTRA_FEEDBACK_GUARD_DISABLED=1 bypass to file this very report. The guard needs a carve-out for the sanctioned binary path or should not scan message body content. Version 2.7.3, macOS Darwin 25.3.0.
