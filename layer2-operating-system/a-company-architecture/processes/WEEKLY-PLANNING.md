# Weekly Planning Protocol

## Overview
Every Monday (or first session of the week), the organization conducts a comprehensive planning session. This reviews the previous week, sets priorities for the coming week, resolves cross-practice dependencies, and ensures all practices are aligned.

## When It Runs
- Triggered by: Monday standup, `/strategy` command, or "weekly planning" keyword
- Frequency: Once per week (Monday)
- Duration: 10-15 minutes
- Output: `org/standup/{date}-weekly.md`

---

## Phase 1: Last Week Review (10 minutes)

### Step 1: OKR Scorecard
Review each practice's OKRs from the previous week. Score each KR as:
- **Hit** (100%): KR fully achieved
- **Partial** (50-99%): Progress made but not complete
- **Missed** (0-49%): Little or no progress
- **Blocked**: Could not progress due to dependency

```markdown
## Last Week OKR Scorecard

### Product
| KR | Target | Actual | Status |
|----|--------|--------|--------|
| {KR description} | {target} | {actual} | Hit/Partial/Missed |

### Design
| KR | Target | Actual | Status |
|----|--------|--------|--------|

### Engineering
| KR | Target | Actual | Status |
|----|--------|--------|--------|

{... all practices}

### Org-Wide Score
- KRs Hit: {count}/{total} ({percent}%)
- KRs Partial: {count}
- KRs Missed: {count}
- KRs Blocked: {count}
```

### Step 2: What Shipped
List everything that actually shipped last week:
- Features completed
- Bugs fixed
- Infrastructure improvements
- Documentation updates
- Design system additions

### Step 3: What Didn't Ship (and why)
For every planned item that didn't ship:
- What was it?
- Why didn't it ship? (scope creep, blocked, deprioritized, harder than expected)
- Is it still a priority? If yes, what sprint?
- What do we learn from this?

### Step 4: Retrospective Questions
- What went well this week? (keep doing)
- What didn't go well? (stop doing or fix)
- What should we try next week? (start doing)
- Any process improvements needed?

---

## Phase 2: This Week Planning (10 minutes)

### Step 1: Update Practice OKRs
Each practice updates their Weekly OKRs section in their PRACTICE.md:
- Roll over incomplete KRs (if still relevant)
- Add new KRs for this week's priorities
- Ensure KRs are specific and measurable
- Date-stamp the OKRs with the current week

### Step 2: Priority Stack Ranking
Create a single, ordered list of all work items across all practices:

```markdown
## This Week's Priority Stack

| Rank | Item | Practice | Type | Effort | Dependencies |
|------|------|-----------|------|--------|-------------|
| 1 | {item} | {dept} | P0-Feature/Bug/Debt | {hours} | {none or dept} |
| 2 | {item} | {dept} | P1-Feature | {hours} | {dept} |
| 3 | {item} | {dept} | P1-Feature | {hours} | {none} |
| ... | | | | | |
```

### Priority Stack Rules
1. P0 bugs and security issues always rank first
2. Cross-practice blockers rank second
3. Features in progress rank above new features (finish what you started)
4. Tech debt ranks proportionally (20% of capacity)
5. Design debt ranks with tech debt
6. New features rank by RICE score

### Step 3: Cross-Practice Dependencies
Identify all work items that require multiple practices:

```markdown
## Cross-Practice Dependencies

| Item | Needs From | Needs To | Sequence | Status |
|------|-----------|---------|----------|--------|
| {feature} | Design spec | Engineering impl | Design first | {status} |
| {feature} | Engineering API | Data events | Eng first | {status} |
| {feature} | Content copy | Design layout | Parallel | {status} |
```

For each dependency:
1. Identify the sequence (what must happen first?)
2. Set deadlines for each handoff
3. Assign an owner for tracking (usually Operations)
4. Flag any that are at risk

### Step 4: Capacity Check
Verify planned work fits within capacity:
- How many hours of work are planned?
- How many hours are realistically available?
- Buffer for unplanned work (20% of capacity)
- If over-capacity: cut lowest-ranked items
- If under-capacity: pull from backlog

### Step 5: Roadmap Update
Update the product roadmap based on:
- What shipped last week (move to "Shipped")
- What's in progress (update estimates)
- What's planned this week (move to "In Progress")
- What got deprioritized (move to "Backlog" with reason)

---

## Phase 3: Alignment Check

### Founder Direction
- Any new direction from the founder this week?
- Any taste decisions needed?
- Any strategic pivots?

### Practice Alignment
- Is every practice clear on their top priority?
- Are there any disagreements on prioritization?
- Does every practice have what they need to execute?

### Risk Register
| Risk | Likelihood | Impact | Mitigation | Owner |
|------|-----------|--------|-----------|-------|
| {risk} | H/M/L | H/M/L | {strategy} | {dept} |

---

## Output: Weekly Plan Document

Write to `org/standup/{date}-weekly.md`:

```markdown
# Weekly Plan — {YYYY-MM-DD}

## Last Week Score: {X}% OKRs Hit

### What Shipped
- {item 1}
- {item 2}

### What Missed
- {item 1} — reason: {why}

### Retro
- Keep: {what worked}
- Stop: {what didn't}
- Start: {what to try}

## This Week's Focus
{One sentence describing the week's theme}

## Priority Stack
| Rank | Item | Practice | Effort | Status |
|------|------|-----------|--------|--------|
| 1 | {item} | {dept} | {hours} | Not Started |
| 2 | {item} | {dept} | {hours} | Not Started |

## Dependencies
| Handoff | From | To | Deadline | Status |
|---------|------|-----|---------|--------|
| {what} | {dept} | {dept} | {date} | Pending |

## Risks
- {risk 1}

## Decisions Needed
- {decision 1}

## Practice OKRs This Week
{Summary of each practice's top OKR}
```

---

## Process Improvement Tracking

Maintain a running list of process improvements identified during weekly planning:

| Date Identified | Improvement | Status | Impact |
|----------------|------------|--------|--------|
| {date} | {description} | Proposed/Active/Done | {H/M/L} |

Review this list monthly. Implement high-impact improvements within 2 weeks.
