---
issue: 24
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T08:19:59Z
updated: 2026-04-28T08:19:59Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/24
comments: []
---

# #24 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T08:19:59Z  |  **Updated:** 2026-04-28T08:19:59Z
**URL:** https://github.com/sankalpasawa/sutra/issues/24

---

Suggestion: Rename the feedback/issue tracker from 'Issues' to 'Tickets'

The current GitHub Issues page is being used for a mix of: bug reports, feature requests, positive feedback, suggestions, UX observations, and general thoughts. The word 'Issues' carries a negative connotation — it implies something is broken. Users with positive feedback or neutral suggestions may self-censor or feel their submission doesn't belong.

Renaming the tracker surface (or at minimum the language used in docs, README, and /core:feedback output) from 'Issues' to 'Tickets' would:
- Lower the barrier for positive/neutral feedback (not everything is an 'issue')
- Better reflect the actual range of submissions (bugs, features, ideas, praise, UX notes)
- Align with how tools like Linear, Jira, and Notion refer to their work items

Practical options (GitHub does not allow renaming 'Issues' natively, but these achieve the same effect):
1. Add a CONTRIBUTING.md that calls them 'tickets' and explains all types are welcome
2. Use GitHub Issue templates labelled 'Bug', 'Feature', 'Feedback', 'Suggestion' so users self-select type on creation
3. Update /core:feedback --public output text from 'issue opened' to 'ticket opened'
4. Update README 'report bugs' language to 'submit a ticket'

This is especially relevant now that the /core:feedback binary is the primary channel — the confirmation message currently says 'issue opened on sankalpasawa/sutra' which reinforces the negative framing even for positive feedback.

Priority: Low effort, high signal. Mostly a docs + template change.
