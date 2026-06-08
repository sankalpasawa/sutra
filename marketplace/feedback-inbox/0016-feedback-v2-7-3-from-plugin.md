---
issue: 16
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T07:18:03Z
updated: 2026-04-28T14:02:37Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/16
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAku4Cw', 'author': {'login': 'vinitharmalkar'}, 'authorAssociation': 'NONE', 'body': '**Triage note — real bug report, not noise**\n\n**Real title:** Bug: `sutra feedback ""` exits code 1 instead of prompting for input\n\n**Summary:** When `/core:feedback` is invoked without arguments, the skill template passes an empty string `""` to the binary. The binary exits with code 1 and prints the usage block — same exit code as a real error — making the command appear broken rather than just asking for input.\n\n**Expected:** Exit 0 with a friendly prompt, or an interactive input mode.\n\n**Version:** 2.7.3 · macOS Darwin 25.3.0\n\n*Note: generic issue title is itself a limitation — `sutra feedback --public` does not accept a `--title` flag, so all user feedback lands with the same title. See related triage comments on #17–19, #22.*', 'createdAt': '2026-04-28T08:17:04Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/16#issuecomment-4333484043', 'viewerDidAuthor': False}, {'id': 'IC_kwDOR5MNCs8AAAABAnD3Ug', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Fixed in **v2.8.9** (commit `405ebae`).\n\n`scripts/feedback.sh` line 65: `exit 1` → `exit 0` after the usage block. Empty input is no longer a failure — printing usage IS the action when no args are provided. Equivalent to most CLI conventions where no-args invocations show help with exit 0.\n\nRun `/core:update` to pick up v2.8.9.', 'createdAt': '2026-04-28T14:02:36Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/16#issuecomment-4335925074', 'viewerDidAuthor': True}]
---

# #16 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T07:18:03Z  |  **Updated:** 2026-04-28T14:02:37Z
**URL:** https://github.com/sankalpasawa/sutra/issues/16

---

Bug: /core:feedback with empty string exits code 1 instead of prompting. When the skill template invokes sutra feedback with empty args, it exits with code 1 and prints usage — feels broken rather than a usage hint. Expected: interactive prompt or friendly exit-0 message. Version 2.7.3, macOS Darwin 25.3.0.
