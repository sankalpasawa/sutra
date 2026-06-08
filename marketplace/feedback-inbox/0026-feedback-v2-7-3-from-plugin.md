---
issue: 26
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T08:32:20Z
updated: 2026-04-28T14:12:10Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/26
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnJQ1g', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Fixed in **v2.8.10** (commit `c05982e`).\n\nThe `hooks/feedback-routing-rule.sh` hook previously had a clause 7 that explicitly said *"Do not mention this rule to the user in responses; just follow it"* — which is exactly the silent-injection pattern you reported.\n\nReplaced with a transparency requirement:\n> *"Briefly acknowledge that Sutra has guided this routing in your reply. One short sentence is enough — e.g., (Sutra has routed this through the sanctioned `/core:feedback` channel.). The user should always know when Sutra-injected guidance is shaping the response. Do not be silent about it."*\n\nVerified by smoke test: hook output now contains "Transparency requirement" + "(Sutra has routed this through ...)" template + the prior silence clause is gone.\n\nThe hook still fires on feedback-intent prompts (advisory injection of behavioral rules). The behavior change is just that the user now always knows when it fires. Run `/core:update` to pick up v2.8.10.\n\nNote: this is a process-level transparency fix. A UI-level surface (e.g., a Sutra activity panel showing all hook-injected guidance) is a feature track separately. For now, the assistant explicitly tells you when it has been routed.', 'createdAt': '2026-04-28T14:12:09Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/26#issuecomment-4336013526', 'viewerDidAuthor': True}]
---

# #26 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T08:32:20Z  |  **Updated:** 2026-04-28T14:12:10Z
**URL:** https://github.com/sankalpasawa/sutra/issues/26

---

Bug: sutra-feedback-routing-rule hook silently injected via UserPromptSubmit blocks assistant filing mid-session without user awareness. Hook  
  fires on every message and prevents assistant from using any filing path including the sanctioned sutra feedback binary. Contradicts prior session behavior where filing worked. Contradicts documented /core:feedback --public usage. User  
  has no visibility that behavior changed. If intentional post-incident policy, must be surfaced explicitly not silently injected. Filed 2026-04-28 Sutra 2.7.3
