# Goal Tracking Protocol

## Overview

> **NOTE:** This protocol references `os/GOALS.md` and related files that do not exist in the Sutra OS template. Client companies using this protocol must create their own goal file in their repo. Format is their choice — see Phase 1 for options.

Goal tracking connects daily work to the company's objectives. It runs at session start as a quick pulse, goes deeper during weekly planning, and resets quarterly. It does not prescribe a goal format — the company chooses how to express goals. The protocol reads whatever they have and produces alignment scores.

## When It Runs
- Triggered by: `/goals` command, weekly planning, or "goals" keyword in session
- Frequency:
  - **Session start**: Quick check — score summary only (< 1 minute)
  - **Weekly planning**: Deep review — full scorecard with trend analysis
  - **Quarterly**: Full reset — archive old goals, set new ones
- Enforcement: SOFT — runs if goal file exists, silently skips if not

---

## Phase 1: LOAD — Read the Company's Goal File

The company chooses their goal format. The protocol supports all of them:

| Format | Location | Example structure |
|--------|----------|-------------------|
| Sutra default | `os/GOALS.md` | Markdown with OKR blocks |
| YAML | `os/goals.yaml` | Structured key-results |
| Custom | `OKRs.md`, `ROADMAP.md` | Any format with objectives + measures |

**Agent action:**
1. Check `os/GOALS.md` first. If not found, check `os/goals.yaml`. If not found, check for any file with "OKR", "goals", or "objectives" in the name at repo root or `os/`.
2. If no goal file exists anywhere: silently skip. Do not warn unless company is Tier 2+.
3. If found: parse into internal structure:
   - Objective (what we're trying to achieve)
   - Key Results (measurable outcomes, 0.0–1.0 scale)
   - Owner (optional)
   - Due date (optional)

**Example goal file (Sutra default format):**
```markdown
# Goals — Q2 2026

## O1: Ship the core product
- KR1: 100 users onboarded by May 30 [current: 12]
- KR2: NPS > 40 [current: not measured]
- KR3: Zero P0 bugs open [current: 2]

## O2: Build the foundation
- KR1: Test coverage > 70% [current: 41%]
- KR2: Design system adopted across all screens [current: 60%]
```

---

## Phase 2: SCORE — Rate Key Results 0.0–1.0

For each Key Result, derive a numeric score:

**Scoring rules:**
- If KR has a numeric target and current value: `score = current / target` (capped at 1.0)
- If KR is binary (done/not done): `score = 1.0` if done, `0.0` if not
- If KR has no measurable current value: `score = null` — flag as "unmeasured"
- Objective score = average of its KR scores (excluding nulls)

**Output format (internal, passed to Phase 4):**
```
O1: Ship the core product — 0.38
  KR1: users onboarded  0.12  (12/100)
  KR2: NPS > 40         null  (unmeasured)
  KR3: zero P0 bugs     0.0   (2 open)

O2: Build the foundation — 0.55
  KR1: test coverage    0.58  (41/70%)
  KR2: design system    0.60  (60% adopted)
```

**Score interpretation:**
- 0.0–0.3: RED — behind, needs intervention
- 0.3–0.6: YLW — in progress, watch for drift
- 0.6–0.9: GRN — on track
- 1.0: DONE — met or exceeded

---

## Phase 3: ALIGN — Tag Current Task to a Goal

When a task is being routed through input routing, add a `GOAL_ALIGNMENT` field:

```
INPUT: [what the founder said]
TYPE: task
EXISTING HOME: [location]
ROUTE: [protocol]
GOAL_ALIGNMENT: O2-KR1 (test coverage) | impact: +3% toward 70% target
ACTION: [proposed action]
```

**Alignment rules:**
- If the task clearly advances a KR: tag it with the KR reference
- If the task is maintenance or infrastructure: tag as `GOAL: ops`
- If the task has no connection to any goal: tag as `GOAL: none`
- If 5 or more consecutive tasks are tagged `GOAL: none`: flag to founder — this may indicate goal drift or goals that don't reflect actual work

**Flagging format (shown once, not every task):**
```
> GOAL DRIFT FLAG: Last 5 tasks have no goal alignment.
> Options: (a) Update goals to reflect current work, (b) Reprioritize toward goals, (c) Ignore — this sprint is intentionally tactical
> Awaiting founder decision.
```

---

## Phase 4: REPORT — Progress Table with Bars

At session start (quick mode) or weekly planning (full mode):

### Quick Mode (session start)
```
GOALS — Q2 2026
O1: Ship the core product   [==--------] 0.38  YLW
O2: Build the foundation    [=====-----] 0.55  YLW
```

### Full Mode (weekly planning)
```
GOALS — Q2 2026 (deep review)

O1: Ship the core product — 0.38 YLW
  KR1  users onboarded   [==========] 0.12  RED  12 of 100
  KR2  NPS > 40          [??????????] null  --   unmeasured
  KR3  zero P0 bugs      [----------] 0.0   RED  2 open

O2: Build the foundation — 0.55 YLW
  KR1  test coverage     [=====-----] 0.58  YLW  41% of 70%
  KR2  design system     [======----] 0.60  GRN  60% adopted

Trend vs last week: O1 +0.04, O2 +0.12
Unmeasured KRs: 1 (O1-KR2) — consider adding a measurement mechanism
Next milestone: O1 closes May 30 — 51 days away
```

---

## Quarterly Reset

At the start of a new quarter (or when `/goals reset` is called):

1. Read current goal file
2. Score all objectives — final scores
3. Write quarterly retrospective to `os/goal-history/Q{N}-{YEAR}.md`
4. Archive current goal file (rename to include quarter)
5. Prompt founder to define new objectives for the next quarter
6. Do not delete anything — history accumulates

**Retrospective format:**
```markdown
# Goal Retrospective — Q2 2026

## Final Scores
| Objective | Final Score | Assessment |
|-----------|-------------|------------|
| O1: Ship the core product | 0.61 | Partial — users met, NPS missed |
| O2: Build the foundation  | 0.78 | Strong — test coverage exceeded |

## What We Learned
[Agent drafts 3-5 observations from the data — founder edits]

## Carried Forward
- KR2 (NPS): not measured this quarter, carry to Q3
```

---

## Implementation Notes

### When Goal File Does Not Exist
- Tier 1 companies (short engagement): silently skip all phases
- Tier 2-3 companies at session start: silently skip
- Tier 2-3 companies at weekly planning: suggest creating a goal file — one-time prompt, not repeated

**Suggested prompt (shown once):**
```
No goal file found. Goal tracking is available but requires a goal file.
To enable: create os/GOALS.md with your objectives and key results.
Format is flexible — see GOAL-TRACKING.md for examples.
```

### Integration with WEEKLY-PLANNING.md
- Weekly planning calls this protocol's full mode to generate the OKR scorecard
- Goal scores are included in the weekly planning report under "OKR Health"
- If goals are off-track (avg score < 0.3), weekly planning escalates to priority-review mode

### Integration with Input Routing
- Every task that passes through input routing gets a `GOAL_ALIGNMENT` tag (Phase 3)
- This adds < 5 seconds to routing — it is a lookup, not a deep analysis
- The tag appears in the INPUT ROUTING block, not as a separate output

### Skipping Conditions
- No goal file found: skip silently
- Goal file found but empty: skip silently, note in weekly planning
- Quarterly reset: only triggered by `/goals reset` or explicit founder request — not automatic
