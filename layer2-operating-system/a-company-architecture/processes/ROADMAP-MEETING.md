# Process: Roadmap Meeting (replaces HOD Meeting)

> Replaces the HOD meeting format. Instead of status updates, this is a **decision meeting** structured around OKRs, impact/effort scoring, and goal-setting.

---

## Format Rule (from EOS L10)

This meeting is IDENTICAL every time. Same order. Same time boxes. Same sections.
Never vary the format. Predictability builds the habit.
If something doesn't fit the format, it goes to the Issues List (Phase 4), not into a new section.

---

## When to Run

- **Weekly** for active companies (part of weekly cadence)
- **Bi-weekly** for holding company (Asawa level)
- **On-demand** when founder requests portfolio review

---

## Structure

### Phase 1: OKR Check (3 min)

Review current OKRs. Score each Key Result 0.0–1.0.

**OKR Format:**
```
OBJECTIVE: [What we're trying to achieve — qualitative]

  KR1: [Measurable outcome] — Score: X.X
  KR2: [Measurable outcome] — Score: X.X
  KR3: [Measurable outcome] — Score: X.X

  Overall: X.X (average)
  Status: ON_TRACK | AT_RISK | OFF_TRACK
```

**Scoring rules:**
- 0.0 = no progress
- 0.3 = started but behind
- 0.5 = on pace
- 0.7 = target (ambitious goals should land here)
- 1.0 = exceeded

**OKR cadence:**
- Quarterly OKRs set at quarter start
- Monthly check-ins score progress
- Weekly roadmap meetings adjust tactics to hit the OKRs

---

### Phase 2: Impact/Effort Matrix (5 min)

Every open item gets scored on two axes:

| Dimension | Scale | What It Measures |
|-----------|-------|-----------------|
| **Impact** | 1–5 | How much this moves the OKR needle |
| **Effort** | 1–5 | Time + tokens + complexity to complete |

**Quadrant routing:**

```
         High Impact
              │
    DO FIRST  │  PLAN CAREFULLY
   (high/low) │  (high/high)
──────────────┼──────────────
    DELEGATE  │  DROP OR DEFER
   (low/low)  │  (low/high)
              │
         Low Impact
```

| Quadrant | Impact | Effort | Action |
|----------|--------|--------|--------|
| **Do First** | 4-5 | 1-2 | Execute this week. No planning needed. |
| **Plan Carefully** | 4-5 | 4-5 | Needs research/design before execution. Schedule it. |
| **Delegate** | 1-3 | 1-2 | Background agent or batch with other small items. |
| **Drop or Defer** | 1-3 | 4-5 | Not worth it now. Move to backlog or delete. |

---

### Phase 3: Goal Setting (5 min)

From the Impact/Effort matrix, select **3-5 goals for the next period** (week or sprint).

**Goal format:**
```
GOAL: [What to achieve]
  OKR Link: [Which KR this serves]
  Impact: X/5
  Effort: X/5
  Owner: Founder | Agent | Both
  Due: [Date]
  Success criteria: [How we know it's done]
```

**Rules:**
- Maximum 5 goals per period (D1: simplicity)
- Each goal must link to an OKR (D8: output-driven)
- At least 1 goal must be a "Do First" quadrant item
- No more than 1 "Plan Carefully" item per period (bandwidth constraint)

---

### Phase 4: Decisions (2 min)

Surface competing priorities (D20). Present as:

```
DECISION: [What needs deciding]
  Option A: [description] — Impact: X, Effort: X
  Option B: [description] — Impact: X, Effort: X
  Recommendation: [A or B]
  Why: [one line]
```

Founder decides. Decision is logged.

---

### Phase 4b: Issues (IDS Process)

Surface issues that aren't decisions but need resolution.

For each issue:
1. IDENTIFY: Name it in one sentence. No storytelling.
2. DISCUSS: Max 2 minutes. What's the root cause? What are the options?
3. SOLVE: Pick one action. Assign an owner. Set a due date.

Rules:
- Issues are solved in the meeting, not deferred to "next time"
- If it can't be solved in 5 minutes, it becomes a task with an owner (goes to Roadmap)
- The Issues List carries over between meetings — unresolved issues stay until solved

---

### Decision Highlighting (mandatory)

Every decision in the Roadmap Card output MUST use rounded-corner box format:

```
  ╭─────────────────────────────────────╮
  │  DECISION: [title]                  │
  │                                     │
  │  Recommendation: [option]           │
  │  Reason: [one sentence]             │
  │                                     │
  │  [1] Option A (recommended)         │
  │  [2] Option B                       │
  │  [3] Option C                       │
  ╰─────────────────────────────────────╯
```

Rules:
- Rounded corners (`╭╮╰╯`) create visual separation — reserved for decisions ONLY
- Recommendation is ALWAYS first inside the box
- Maximum 4 options
- Reason is one sentence, not a paragraph
- Box width: 40 characters (fits any terminal)
- If multiple decisions, each gets its own box with a blank line between
- Decisions are NEVER embedded in tables or running text
- If there are 0 decisions, output: "No decisions needed this period."

---

## Output

The meeting produces a **Roadmap Card** — one artifact per meeting.

**Line budget: 50 lines per section.** If it doesn't fit, use progressive disclosure (headline only, detail on request).

```
══════════════════════════════════════════
  [COMPANY] — Roadmap Meeting
  [Quarter] | [Period] Review | [Date]
══════════════════════════════════════════

  HEADLINE
  X GREEN | X YELLOW | X RED | X decisions needed

  OKR SCORES
  ──────────────────────────────────────
  Charter Name       ▓▓▓▓▓▓░░░░ 0.6  STATUS
  ──────────────────────────────────────
  KR   Description                  Score  Status
  1    [Measurable outcome]         0.X    [icon]
  2    [Measurable outcome]         0.X    [icon]

  THIS PERIOD: SHIPPED
  ──────────────────────────────────────
  ✅ [Item shipped]
  ✅ [Item shipped]

  THIS PERIOD: IN PROGRESS
  ──────────────────────────────────────
  ⏳ [Item] — [blocker if any]

  NEXT PERIOD GOALS
  ──────────────────────────────────────
  | # | Goal | OKR Link | Impact | Effort | Owner | Due |
  |---|------|----------|--------|--------|-------|-----|

  ╭─────────────────────────────────────╮
  │  DECISION: [title]                  │
  │                                     │
  │  Recommendation: [option]           │
  │  Reason: [one sentence]             │
  │                                     │
  │  [1] Option A (recommended)         │
  │  [2] Option B                       │
  ╰─────────────────────────────────────╯

  <!-- If no decisions: "No decisions needed this period." -->

  DEFERRED (moved to backlog)
  ──────────────────────────────────────
  | Item | Impact | Effort | Why Deferred |
  |------|--------|--------|-------------|

══════════════════════════════════════════
```

**Format rules:**
- Double-line (`══`) for document frame only
- Single-line (`──`) for section dividers
- Rounded box (`╭╮╰╯`) for decisions ONLY — makes them visually distinct
- OKR scores use progress bar format: `▓▓▓▓▓▓░░░░ 0.6` (10-char bar, each char = 0.1)
- Headline summarizes the entire meeting in one line
- Shipped before In-Progress before Next (output-first ordering)

---

## How This Differs From HOD Meeting

| HOD Meeting (old) | Roadmap Meeting (new) |
|-------------------|----------------------|
| Status updates ("what happened") | Goal-setting ("what's next and why") |
| Health badges (RED/YELLOW/GREEN) | Impact/Effort scores (quantified) |
| Action items (unlinked to strategy) | Goals linked to OKRs |
| Decisions as open questions | Decisions as scored options with recommendations |
| Backward-looking | Forward-looking |

---

## OKR Protocol

### Setting OKRs (Quarterly)

1. **Start from the company's bet** (from INTAKE.md or company strategy)
2. **Define 1-3 Objectives** — qualitative, ambitious, inspiring
3. **Each Objective gets 2-4 Key Results** — quantitative, measurable, time-bound
4. **Score baseline** — where are we today on each KR?
5. **Set targets** — 0.7 is the expected score for well-set OKRs

### OKR Rules

- **Objectives are qualitative.** "Make DayFlow the best daily reflection app" not "Get 100 users."
- **Key Results are quantitative.** "100 daily active users" not "grow the user base."
- **KRs must be measurable without judgment.** Either we hit the number or we don't.
- **3 is the magic number.** 1-3 Objectives, 2-4 KRs each. More = unfocused.
- **OKRs are not task lists.** "Ship feature X" is a task, not a KR. "Feature X drives 20% engagement increase" is a KR.
- **Score honestly.** 0.7 is good. 1.0 means the goal wasn't ambitious enough.

### OKR Cadence

| Action | When | Who |
|--------|------|-----|
| Set OKRs | Quarter start | Founder + Agent |
| Score OKRs | Monthly | Agent (propose) + Founder (confirm) |
| Adjust tactics | Weekly (Roadmap Meeting) | Founder + Agent |
| Retrospective | Quarter end | Founder |

### OKR Storage

- Company-level OKRs live in `{company}/os/OKRs.md` (or equivalent)
- Holding-level OKRs live in `holding/OKRs.md`
- Historical OKRs archived with scores at quarter end

---

## Connection to Sutra Systems

| System | Connection |
|--------|-----------|
| TASK-LIFECYCLE.md | Goals from Roadmap Meeting become tasks that flow through the lifecycle |
| ESTIMATION-ENGINE.md | Effort scores in the matrix are informed by estimation data |
| SUTRA-KPI.md | V/C/A/U metrics feed into OKR scoring |
| SPEED-CHARTER.md | Speed goals are OKR-trackable |
| ADAPTIVE-PROTOCOL.md | Goal complexity determines protocol depth |
