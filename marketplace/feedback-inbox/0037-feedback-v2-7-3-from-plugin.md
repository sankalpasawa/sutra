---
issue: 37
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T12:01:02Z
updated: 2026-04-28T14:00:08Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/37
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnCuww', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Closing — body contains only the privacy redactor output marker (the `<HOME>/.<HIGH-ENTROPY>.md` placeholder) with no actionable content. The privacy-sanitize layer appears to have stripped the entire body.\n\nThis points at a separate issue worth tracking: **the redactor over-redacts when the entire input matches a high-entropy or path pattern**. We have signal that this happens for two distinct content classes:\n- Path-only or single-line bodies that look entirely like paths\n- Dollar-figure content (`$0.14`, `$5,000`) being pre-corrupted by zsh `$0` expansion before redaction even sees them, then matching high-entropy patterns\n\nBoth are tracked separately for redactor-tuning. If you can re-file the actual content (please paste from your local manual capture at `~/.sutra/feedback/manual/<timestamp>.md`), happy to address whatever you intended to report.', 'createdAt': '2026-04-28T14:00:07Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/37#issuecomment-4335906499', 'viewerDidAuthor': True}]
---

# #37 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T12:01:02Z  |  **Updated:** 2026-04-28T14:00:08Z
**URL:** https://github.com/sankalpasawa/sutra/issues/37

---

<HOME>/.<HIGH-ENTROPY>.md
