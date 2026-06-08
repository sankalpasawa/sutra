---
issue: 27
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T08:32:34Z
updated: 2026-04-28T14:04:34Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/27
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnFPGg', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Closing as duplicate of #26 (identical body, filed 14s apart). Tracking the silent-UserPromptSubmit-hook UX issue at #26.', 'createdAt': '2026-04-28T14:04:32Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/27#issuecomment-4335947546', 'viewerDidAuthor': True}]
---

# #27 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T08:32:34Z  |  **Updated:** 2026-04-28T14:04:34Z
**URL:** https://github.com/sankalpasawa/sutra/issues/27

---

Bug: sutra-feedback-routing-rule hook silently injected via UserPromptSubmit blocks assistant filing mid-session without user awareness. Hook  
  fires on every message and prevents assistant from using any filing path including the sanctioned sutra feedback binary. Contradicts prior session behavior where filing worked. Contradicts documented /core:feedback --public usage. User  
  has no visibility that behavior changed. If intentional post-incident policy, must be surfaced explicitly not silently injected. Filed 2026-04-28 Sutra 2.7.3
