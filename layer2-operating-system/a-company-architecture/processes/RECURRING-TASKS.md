# Recurring Tasks Protocol

## Overview

> **NOTE:** This protocol references `os/SCHEDULE.md` and related files that do not exist in the Sutra OS template. Client companies using this protocol must create their own schedule definition in their repo. Format is their choice — see Phase 1 for options.

Recurring tasks are work that happens on a cadence — weekly security reviews, monthly invoicing, biweekly retrospectives. Without a system to surface them, they slip. This protocol checks for overdue recurring items at session start and surfaces them to the founder. It never executes them automatically — that is always a human decision.

## When It Runs
- Triggered by: session start (automatic), `/schedule` command, or "recurring tasks" keyword
- Frequency: Every session start — takes < 30 seconds
- Enforcement: SOFT — flagging only, never blocks

---

## Phase 1: LOAD — Read the Company's Schedule Definition

The company chooses their schedule format. The protocol supports all of them:

| Format | Location | Notes |
|--------|----------|-------|
| Sutra default | `os/SCHEDULE.md` | Markdown with task blocks |
| YAML | `os/schedules.yaml` | Structured with last_run fields |
| Embedded | Section in `TODO.md` | Under a `## Recurring` heading |

**Agent action:**
1. Check `os/SCHEDULE.md` first. If not found, check `os/schedules.yaml`. If not found, check for a `## Recurring` or `## Schedule` section in `TODO.md`.
2. If no schedule definition exists anywhere: silently skip. Do not warn.
3. If found: parse into internal structure:
   - Task name
   - Frequency (daily | weekly | biweekly | monthly | quarterly)
   - Last run date (or "never")
   - Owner (optional)
   - Trigger hint (optional — what to say to start it)

**Example schedule file (Sutra default format):**
```markdown
# Schedule — DayFlow

## Daily
- [ ] Check analytics dashboard | last_run: 2026-04-08 | trigger: /analytics

## Weekly (Monday)
- [ ] Engineering standup review | last_run: 2026-04-07 | trigger: /standup --force
- [ ] Backlog grooming | last_run: 2026-04-01 | trigger: /backlog

## Biweekly
- [ ] Design review | last_run: 2026-03-28 | trigger: /design-review
- [ ] Security audit | last_run: 2026-03-21 | trigger: /security

## Monthly
- [ ] Investor update | last_run: 2026-04-01 | trigger: /investor-update
- [ ] Cost review | last_run: 2026-04-01 | trigger: /costs

## Quarterly
- [ ] OKR reset | last_run: 2026-01-03 | trigger: /goals reset
```

---

## Phase 2: CHECK — Compare Last Run vs Frequency

For each task, determine if it is overdue:

**Overdue calculation:**
| Frequency | Overdue if last_run is older than |
|-----------|----------------------------------|
| daily     | 1 day                            |
| weekly    | 7 days                           |
| biweekly  | 14 days                          |
| monthly   | 30 days                          |
| quarterly | 90 days                          |

**Special cases:**
- `last_run: never` — treat as maximally overdue (always surface first)
- Task with no `last_run` field — treat as never run
- Today's date is known from session context — use it for all comparisons

**Output (internal, passed to Phase 3):**
```
overdue:
  - "Security audit" — biweekly — last run 19 days ago (5 days overdue)
  - "Backlog grooming" — weekly — last run 8 days ago (1 day overdue)
  - "OKR reset" — quarterly — never run

upcoming (due within 3 days):
  - "Design review" — biweekly — last run 12 days ago (due in 2 days)

on track:
  - "Check analytics dashboard" — daily — last run today
  - "Investor update" — monthly — last run 8 days ago
  - "Cost review" — monthly — last run 8 days ago
  - "Engineering standup review" — weekly — last run 2 days ago
```

---

## Phase 3: FLAG — Surface Overdue Items at Session Start

Present overdue and upcoming items to the founder at session start. Format is compact — this is a sidebar, not the main event.

**Flag format (shown at session start, after standup summary if standup ran):**
```
RECURRING TASKS
Overdue (3):
  ! OKR reset           quarterly  never run      /goals reset
  ! Security audit      biweekly   5 days late    /security
  ! Backlog grooming    weekly     1 day late     /backlog

Due soon (1):
  ~ Design review       biweekly   due in 2 days  /design-review
```

**Severity rules:**
- `!` = overdue (past due date)
- `~` = upcoming (due within 3 days)
- Items on track are not shown — no noise

**If nothing is overdue or upcoming:**
```
RECURRING TASKS — all clear
```

**If no schedule file exists:** show nothing. No mention of this protocol.

---

## Phase 4: ROUTE — Surface to Founder, Never Auto-Execute

The protocol's job ends at flagging. It never:
- Runs a recurring task on its own
- Modifies `last_run` without the founder deciding to run the task
- Creates reminders or scheduled jobs outside the session

**When a founder decides to run a recurring task:**
1. They say "run the security audit" or type `/security`
2. The relevant protocol (or skill) executes
3. After completion, update `last_run` in the schedule file to today's date
4. If the task has no associated protocol, run it ad hoc and update `last_run` manually

**Updating last_run:**
```markdown
## Biweekly
- [ ] Security audit | last_run: 2026-04-09 | trigger: /security
```
This is a manual edit — not automated. The founder (or agent on instruction) updates it after confirming the task ran.

---

## Frequency Reference

| Keyword | Interval | Overdue threshold |
|---------|----------|-------------------|
| daily | every day | > 1 day |
| weekly | every 7 days | > 7 days |
| biweekly | every 14 days | > 14 days |
| monthly | every ~30 days | > 30 days |
| quarterly | every ~90 days | > 90 days |

Custom frequencies are supported in YAML format only:
```yaml
- name: "Board meeting prep"
  frequency_days: 45
  last_run: "2026-02-20"
```

---

## Implementation Notes

### When Schedule File Does Not Exist
- Tier 1 companies (short engagement): silently skip all phases
- Tier 2-3 companies: silently skip — no prompt to create a schedule file unless the founder asks

### Integration with DAILY-STANDUP.md
- If both protocols are active, recurring task flags appear after the standup summary
- They do not appear inside the standup report — they are a separate block
- If standup did not run this session, recurring tasks still surface at session start independently

### Keeping last_run Accurate
The protocol is only as useful as the `last_run` data. Two patterns work:
1. **Manual update**: after running a task, edit the schedule file directly
2. **Post-task update**: the relevant protocol (e.g., `/security`) includes a step to update its `last_run` entry

The Sutra OS does not enforce which pattern a company uses — but Tier 2-3 companies are encouraged to adopt the post-task update pattern for accuracy.

### Not Required For
- Tier 1 or short-engagement companies — too much overhead for the relationship length
- Companies with fewer than 3 recurring tasks — TODO.md is sufficient at that scale

### Skipping Conditions
- No schedule file found: skip silently
- Schedule file found but empty: skip silently
- `/schedule` command with `--skip` flag: skip for this session only
