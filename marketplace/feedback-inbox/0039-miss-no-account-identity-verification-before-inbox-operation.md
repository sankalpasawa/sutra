---
issue: 39
title: "MISS: No account identity verification before inbox operations \u2014 parsed wrong Gmail account for 2+ hours"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T15:15:13Z
updated: 2026-04-28T15:15:13Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/39
comments: []
---

# #39 MISS: No account identity verification before inbox operations — parsed wrong Gmail account for 2+ hours

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T15:15:13Z  |  **Updated:** 2026-04-28T15:15:13Z
**URL:** https://github.com/sankalpasawa/sutra/issues/39

---

## Governance Miss: Wrong Gmail account used for extended inbox task

**Version:** 2.8.5
**Severity:** High — caused significant wasted work and incorrect outputs

### What happened

User asked Claude to parse `abhishek@testlify.com` inbox for action items and unsubscribe candidates. Claude used the `mcp__gmail__` tool without first verifying which Google account it was connected to.

After ~2 hours of work including:
- 23 Gmail searches
- ~1,030 email results fetched
- 2 Google Sheets created with "Abhishek Inbox" labels
- Action items and unsubscribe list populated

...the user noticed all results were from **Namrata Kamdar** (`namrata@testlify.com`). A simple `from:me` search at task start would have caught this in seconds.

Both `mcp__gmail__` and `mcp__gmail-namrata__` turn out to be connected to the same Namrata account. No MCP for Abhishek's inbox was configured.

### Root cause

No account identity verification step before operating on a user-specified inbox. Claude assumed MCP naming mapped to the user's stated account without checking.

### What Sutra's governance should have caught

The input routing block identified this as an "inbox task" but did not surface account identity verification as a required pre-check. A rule like:

> When a user specifies an email account by address (e.g. "check abhishek@testlify.com"), verify MCP identity matches before proceeding — run `from:me` or equivalent, confirm with user, then proceed.

would have prevented this entirely.

### Recommendation

Add a governance pre-check for inbox tasks: verify MCP account identity matches the user-specified address before any search or read operation.

---
*Filed automatically via curl fallback (Sutra feedback binary requires interactive confirmation)*
