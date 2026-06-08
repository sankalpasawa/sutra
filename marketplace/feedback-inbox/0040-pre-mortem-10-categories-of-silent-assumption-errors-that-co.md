---
issue: 40
title: "Pre-mortem: 10 categories of silent assumption errors that compound at scale"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T15:18:37Z
updated: 2026-04-28T15:18:37Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/40
comments: []
---

# #40 Pre-mortem: 10 categories of silent assumption errors that compound at scale

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T15:18:37Z  |  **Updated:** 2026-04-28T15:18:37Z
**URL:** https://github.com/sankalpasawa/sutra/issues/40

---

## Context

Triggered by issue #39 (wrong Gmail account used for 2+ hours). Rather than filing one miss at a time reactively, this is a structured pre-mortem of every class of silent assumption failure that follows the same pattern — and gets worse as users, MCPs, and data sources grow.

**The pattern**: Claude receives user instruction with implicit target → maps it to a tool without verification → executes extensively → mismatch discovered only after significant downstream work.

---

## Category 1 — Identity / Account Assumptions
*Assuming an MCP is connected to the account the user named*

- Gmail MCP on wrong account (the actual miss) — 🔴 High
- Drive MCP on different Google account than stated — 🔴 High
- Calendar MCP on wrong account — blocks wrong person's time — 🔴 High
- Slack MCP on wrong workspace — posts to wrong org — 🔴 High
- GitHub MCP on wrong org — pushes to wrong repo — 🔴 High

**Prevention**: Before ANY account operation, run an identity probe (from:me, about(), git config user.email) and confirm it matches the user-stated account. Hard-block if mismatch.

---

## Category 2 — Document / File Targeting
*Writing to the wrong sheet, tab, file, or row*

- 'Update the tracker' — picks stale/wrong sheet ID from memory — 🔴 High
- Row offset errors — stats rows not counted, formatting lands on wrong rows (our second miss this session) — 🟠 Medium
- Append vs overwrite — appends when user expected fresh write — 🟠 Medium
- Wrong tab — writes to Tab A when Tab B was intended — 🟠 Medium

**Prevention**: Before any write, read the target document first. State the plan: 'I will write to tab X, rows Y-Z'.

---

## Category 3 — Memory Staleness
*Acting on remembered facts that have become outdated*

- Stale token path — /tmp/sheets_token.pickle rotated, Claude reuses old path — 🔴 High
- Stale sheet structure — memory says 6 rows but sheet has 15; Claude skips new rows — 🔴 High
- Stale ownership — memory says Taylor owns deal but ownership transferred — 🟠 Medium
- Stale RFP status — memory says In Progress but it was closed — 🟠 Medium
- Stale contact — emails wrong person because memory has outdated contact — 🟠 Medium

**Prevention**: Cross-check memory against current state before acting. Memory older than current session = hint, not fact.

---

## Category 4 — Scope / Intent Mismatch
*Executing broader or narrower action than intended*

- Write when read was intended — user asks 'check if sheet has X', Claude modifies it — 🔴 High
- 'Update the tracker' hits every tab, not just the relevant one — 🔴 High
- Batch delete — 'clean up old emails' deletes more than intended — 🔴 High (destructive)
- 'Send follow-up to RFP contacts' — interpreted too broadly, emails all — 🟠 Medium
- Push to main instead of feature branch — 🔴 High

**Prevention**: Before any write/send/delete, state exact scope. Gate destructive operations behind explicit confirmation.

---

## Category 5 — Silent / False Success
*Tool call returns success but action completed incorrectly*

- 'Updated 23 cells' — correct count but wrong cells (our row offset miss) — 🔴 High
- Gmail search returns 0 in wrong account — Claude infers 'no emails exist' — 🔴 High
- API partial success — batchUpdate formats some rows, fails others, reports success — 🟠 Medium
- Email bounced after Gmail API returns 200 — 🟠 Medium
- Expired token accepted at read, rejected at write — task half-completes — 🟠 Medium

**Prevention**: After every write, re-read a sample and verify. Zero results = 'Is this the right scope?' not 'No data found'.

---

## Category 6 — Cross-Context Data Pollution
*Data from one context bleeds into another*

- Wrong inbox data in right sheet — Namrata data in 'Abhishek' sheet (our compound miss) — 🔴 High
- Search results reused across accounts — Namrata scan used as Abhishek scan — 🔴 High
- Memory from project A applied to project B — 🟠 Medium
- Future multi-user: Abhishek instructions influence Namrata context — 🔴 High (enterprise-critical)

**Prevention**: Tag every result set with its source account. Any cross-account reuse requires explicit re-query.

---

## Category 7 — Date / Time Assumption Errors
*Incorrect temporal context*

- 'Closing today at 12pm EDT' — Claude miscalculates urgency from wrong timezone — 🟠 Medium
- 'Next Monday' interpreted in wrong timezone — 🟡 Low
- Memory from January treated as current in April — 🟠 Medium
- Scheduling in wrong timezone — double-books — 🟠 Medium

**Prevention**: State timezone explicitly at task start for time-sensitive ops. Treat all memory dates as historical.

---

## Category 8 — Permission / Access Assumptions
*Assuming write access without testing*

- Long write operation begun before testing write permission — fails at step 12 of 15 — 🔴 High
- Sharing a private document publicly without confirming intent — 🔴 High (security)
- API quota exhausted mid-task — partial data treated as complete — 🟠 Medium
- Domain-restricted file — Claude assumes cross-user access that does not exist — 🟠 Medium

**Prevention**: Probe write access with a minimal test before any multi-step write. Surface quota limits before bulk operations.

---

## Category 9 — Tool / Config Drift
*Tool behavior changes without Claude knowing*

- MCP reconnects to different account after session break — 🔴 High
- Plugin version drift changes behavior silently — 🟡 Low
- API schema change breaks cell formatting assumptions — 🟡 Low

**Prevention**: Re-probe tool identity at the start of any resumed session. Never assume MCP state persists across breaks.

---

## Category 10 — Ambiguity Resolution Without Asking
*Claude silently disambiguates instead of asking*

- Multiple trackers exist — Claude picks wrong one from memory — 🔴 High
- 'Send the follow-up' — multiple pending, Claude picks one silently — 🔴 High
- Multiple Slack channels named #updates — wrong one chosen — 🟠 Medium
- Personal + work calendar — wrong one checked — 🟠 Medium
- Multiple git branches match intent — wrong one selected — 🟠 Medium

**Prevention**: When multiple targets plausibly match, always ask before acting on high-stakes operations.

---

## The Five Prevention Checks

Every category above is prevented by one of five checks Claude should run before operating:

1. **Identity probe** — Who am I operating as? Does it match what the user said?
2. **Target verification** — What exact file/tab/row/channel? Did I read it first?
3. **Memory freshness** — How old is this memory? Has state likely changed?
4. **Scope declaration** — State exact scope before write. Gate destructive ops explicitly.
5. **Success verification** — After write, re-read a sample. Zero results = wrong scope, not empty data.

These five checks, applied consistently, prevent the original miss and all 45 variants catalogued here.

---
*Filed proactively after issue #39. This is a systematic pre-mortem, not a reactive fix — all failure modes identified before they occur in production.*
