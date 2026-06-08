---
issue: 25
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: CLOSED
created: 2026-04-28T08:26:50Z
updated: 2026-04-28T13:58:17Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/25
comments: [{'id': 'IC_kwDOR5MNCs8AAAABAnB4HQ', 'author': {'login': 'sankalpasawa'}, 'authorAssociation': 'OWNER', 'body': 'Both bugs resolved.\n\n**Bug 1 — ghost issues on cancellation**: fixed in earlier version (v2.6.x). The confirmation gate (`read -r CONFIRM`) now precedes the public-post call. Cancellations no longer leak ghost public issues.\n\n**Bug 2 — generic title for all issues**: fixed in **v2.8.6** (commit `8b915ff`). Title now derives from the first non-blank, non-frontmatter, non-redacted line of the body, capped at 80 chars: `[v${PLUGIN_VERSION}] <derived line>`. Falls back to legacy generic only when body has no usable line.\n\nThis means your reports going forward will be triageable by title — your inbox of #16-#34 was indeed completely undifferentiated until today, exactly as you described. Thanks for the clear repro and reasoning.\n\nRun `/core:update` to pick up v2.8.6+.', 'createdAt': '2026-04-28T13:58:16Z', 'includesCreatedEdit': False, 'isMinimized': False, 'minimizedReason': '', 'reactionGroups': [], 'url': 'https://github.com/sankalpasawa/sutra/issues/25#issuecomment-4335892509', 'viewerDidAuthor': True}]
---

# #25 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** CLOSED  |  **Labels:** —
**Created:** 2026-04-28T08:26:50Z  |  **Updated:** 2026-04-28T13:58:17Z
**URL:** https://github.com/sankalpasawa/sutra/issues/25

---

Bug: sutra feedback --public creates ghost issues on cancellation AND uses generic title for all issues

## Two bugs, one filing

---

### Bug 1 — Ghost issue created even when user cancels (SEVERITY: HIGH)

REPRODUCTION:
  sutra feedback --public 'some content'
  binary shows confirmation prompt
  user types anything other than 'yes' (or non-interactive shell provides no input)
  binary prints: 'public post cancelled — feedback kept local only'
  BUT a GitHub issue is still created

EVIDENCE:
Today (2026-04-28) we filed 3 intentional feature requests. The issue list shows 8 issues created today. The extra 5 are ghosts from cancelled or non-interactive invocations where the binary returned 'cancelled' but still called the GitHub API.

EXPECTED: If user does not confirm with 'yes', NO issue is created. The GitHub API call must happen AFTER confirmation is received, not before.

ROOT CAUSE (hypothesis): The binary likely calls gh issue create to stage the issue body, then asks for confirmation and either closes or leaves it open. The confirmation gate must move to BEFORE the gh call, not after.

---

### Bug 2 — All issues get generic title '[feedback vX.Y.Z] from plugin' (SEVERITY: MEDIUM)

REPRODUCTION:
  echo 'yes' | sutra feedback --public 'Feature: My Amazing Feature with full body...'
  issue created with title: '[feedback v2.7.3] from plugin'
  body contains the full content correctly

EXPECTED: Binary should derive title from first non-empty line of feedback body:
  - First line starts with 'Feature:' or 'Bug:' or 'Feedback:' — use that line as title
  - Otherwise use first line truncated to 80 chars
  - '[feedback vX.Y.Z] from plugin' as fallback ONLY when body is empty

IMPACT: With generic titles, the issue list is completely untriageable. All 8 of today's issues look identical. Maintainer must open each one individually to understand what it is.

---

## Reproduction evidence (today's session, 2026-04-28)

3 intentional filings produced 8 issues total. 5 ghosts. All 8 with generic titles.

Issues filed today by category:
  Ghost (cancelled attempts): 5 issues
  Content-bearing but generic title: 3 issues (Approval Visibility Layer, Cognitive Checkpoints, Dynamic Model Switching)
  Total: 8 issues, 0 with meaningful titles

---

## Fix checklist

  Move gh issue create call to AFTER 'yes' confirmation received
  Parse first line of feedback body as issue title
  Add --title flag override: sutra feedback --public --title 'My Title' 'body'
  Validate: non-interactive shell with no 'yes' input means local-only, no issue
  Add cleanup helper: sutra feedback --cleanup-ghosts to list and close generic-titled issues from this install_id

---

Filed: 2026-04-28 · Sutra 2.7.3 · Reported by Vinit (Testlify Founders Office)
