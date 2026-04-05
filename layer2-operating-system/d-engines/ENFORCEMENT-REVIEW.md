# Enforcement Review Cadence + Adaptive Judgment

## Purpose

Enforcement rules decay without review: hard gates become paper tigers, soft gates mask real risk, and file-count proxies miss the changes that actually break things. This spec defines three review cadences (3-day, weekly, monthly) that keep enforcement rules calibrated, plus an adaptive sensitivity model that replaces the file-count proxy with multi-dimensional scoring. The system self-improves: when a change causes a bug, the affected area gets higher sensitivity; when rules never fire, they get demoted. Asawa-level learnings flow to all companies; company-level learnings stay local.

ENFORCEMENT: HARD -- the review cadence itself is mandatory. Missing a monthly calibration triggers a flag in Daily Pulse.

---

## Review Cadence

### 3-Day Micro-Review (Automated)

**What it does:** Reads hook execution logs, counts blocked vs. allowed actions, overrides, and skipped compliance steps. Outputs a single paragraph appended to DAILY-PULSE.md. Zero human effort.

**Data source:** `.claude/logs/enforcement.jsonl` (see Hook Execution Log Format below).

**Trigger:** Runs every 3 days. Can be triggered by a SessionStart hook that checks `last_micro_review` timestamp in `.claude/state/enforcement-state.json`.

**Logic:**
1. Read all entries from `enforcement.jsonl` since last micro-review
2. Count: `blocked`, `allowed`, `overridden`, `skipped_step` actions
3. Identify the top rule by fire count
4. Identify any override events (these always get surfaced)
5. Append the output paragraph to DAILY-PULSE.md

**Output format (exact):**

```
### Enforcement Micro-Review (YYYY-MM-DD)
Last 3 days: {blocked_count} blocked, {allowed_count} allowed, {override_count} overrides. Top rule: "{hook_name}" fired {count} times. {override_sentence} Compliance score: {score}/100.
```

Where `{override_sentence}` is either "No overrides." or "Override used: {role} overrode {hook_name} on {file} — review in weekly." The compliance score is `(allowed / (allowed + blocked)) * 100`, floored to integer.

**Tier behavior:**
| Tier | Micro-review |
|------|-------------|
| 1 (Personal) | Off. Monthly calibration only. |
| 2 (Product) | On. Automated, appended to Daily Pulse. |
| 3 (Company) | On. Automated, appended to Daily Pulse. |

---

### Weekly Enforcement Review

**When:** Part of the weekly review cadence (same session as /retro).

**Duration:** 5-10 minutes. Structured checklist, not open-ended.

**Checklist (answer each):**

1. **System working?** — Read the last 2 micro-review paragraphs. Are blocked counts stable, rising, or falling?
2. **Rules bypassed?** — List any overrides this week. For each: was the override justified? If yes, the rule may be too strict. If no, the rule is correct and the override was an error.
3. **Hooks too strict?** — Any hooks that blocked legitimate work (false positives)? If >2 false positives this week, flag for demotion review.
4. **Hooks too loose?** — Any incidents this week that SHOULD have been blocked but weren't? If yes, flag for promotion review.
5. **New rule types needed?** — Did any incident reveal a gap in coverage? Draft the rule (don't deploy yet — hold for monthly calibration).
6. **Sensitivity accuracy** — Compare this week's tier assignments against actual outcomes. Record: `{correct_assignments} / {total_assignments}` as accuracy percentage.

**Output:** If any adjustments needed, update ENFORCEMENT.md directly. Log the change in the weekly section of DAILY-PULSE.md:

```
### Enforcement Weekly (YYYY-MM-DD)
Reviewed {n} micro-review periods. Overrides: {count}. False positives: {count}. Accuracy: {pct}%. Changes: {list or "None"}.
```

---

### Monthly Calibration

**When:** First session of the month. Blocking — complete before other work.

**Duration:** 15-20 minutes.

**Calibration Decision Table:**

| Condition | Action |
|-----------|--------|
| Soft gate violated >3 times this month | PROMOTE to hard gate |
| Hard gate with 0 fires in 30 days | DEMOTE to soft gate |
| Hard gate with 0 fires in 60 days | REMOVE (dead rule) |
| Override used >2 times on same rule | Review: rule too strict or users undertrained? |
| New incident revealed uncovered area | ADD new rule (hard by default) |
| Sensitivity accuracy <70% for an area | Recalibrate sensitivity scores for that area |
| Sensitivity accuracy >90% overall | No changes needed — system is calibrated |

**Process:**
1. Pull all `enforcement.jsonl` entries for the past 30 days
2. Aggregate fire counts per hook, per action type
3. Apply the decision table above to each rule
4. For promotions: update ENFORCEMENT.md, change marker from SOFT to HARD
5. For demotions: update ENFORCEMENT.md, change marker from HARD to SOFT
6. Review compliance scores across all companies (Asawa-level view)
7. Deploy updated hooks via Sutra to all client companies
8. Record calibration results:

```
### Enforcement Monthly Calibration (YYYY-MM)
Rules promoted: {list}. Rules demoted: {list}. Rules removed: {list}. Rules added: {list}. Overall accuracy: {pct}%. Companies reviewed: {list with scores}.
```

**Tier behavior:**
| Tier | Monthly calibration |
|------|-------------------|
| 1 (Personal) | Required. Simplified: review fire counts, apply decision table. |
| 2 (Product) | Required. Full calibration including sensitivity recalibration. |
| 3 (Company) | Required. Full calibration + cross-company comparison + dashboard. |

---

## Adaptive Judgment — Sensitivity Scoring

### The Problem with File-Count Proxy

Current enforcement uses change SIZE (number of files touched) as a proxy for risk. This fails because:
- A 1-file change to `auth.ts` is higher risk than a 20-file CSS rename
- A migration file is higher risk than 50 new test files
- Data model changes ripple; UI changes don't

The sensitivity model replaces file count with multi-dimensional scoring.

### The Sensitivity Model

Each file path has a sensitivity score (1-10). The score is computed from five dimensions:

| Dimension | Weight | Score Range | Examples |
|-----------|--------|-------------|----------|
| Area sensitivity | 3x | 1-10 | auth/payment/migration = 9-10, API routes = 6-7, UI components = 3-4, CSS/assets = 1-2 |
| Blast radius | 2x | 1-10 | shared utility imported by 20+ files = 9, leaf component = 2 |
| Incident history | 3x | 0-10 | 0 past incidents = 0, 1 incident = 4, 2 incidents = 7, 3+ incidents = 10 |
| Data sensitivity | 3x | 0-10 | PII handling = 10, financial = 9, credentials/env = 10, public content = 0 |
| Coupling depth | 1x | 1-10 | cross-layer dependency = 8, cross-module = 5, single-file = 1 |

**Composite score formula:**
```
raw = (area * 3 + blast * 2 + incidents * 3 + data * 3 + coupling * 1) / 12
score = clamp(round(raw), 1, 10)
```

### Per-Company Sensitivity Map

**Format:** `sensitivity.jsonl` in each company's `.claude/` directory.

**Entry format:**
```jsonl
{"path": "src/auth/", "score": 9, "base_score": 7, "reason": "auth layer, 2 past incidents", "dimensions": {"area": 9, "blast": 6, "incidents": 7, "data": 8, "coupling": 5}, "updated": "2026-04-05"}
{"path": "src/components/Button.tsx", "score": 2, "base_score": 2, "reason": "leaf UI component", "dimensions": {"area": 2, "blast": 1, "incidents": 0, "data": 0, "coupling": 1}, "updated": "2026-04-05"}
{"path": "supabase/migrations/", "score": 10, "base_score": 10, "reason": "DB migrations, irreversible", "dimensions": {"area": 10, "blast": 9, "incidents": 0, "data": 10, "coupling": 8}, "updated": "2026-04-05"}
```

Fields:
- `path`: file or directory path (directory entries apply to all children unless overridden)
- `score`: current computed score (may be above base_score due to incidents)
- `base_score`: the score without incident history — the floor that scores decay toward
- `reason`: human-readable explanation
- `dimensions`: the raw dimension scores used in computation
- `updated`: last modification date

**How to initialize (auto-seed):**
1. Scan codebase for high-sensitivity patterns:
   - `**/auth/**`, `**/login/**`, `**/session/**` → area: 9, data: 8
   - `**/payment/**`, `**/billing/**`, `**/stripe/**` → area: 9, data: 9
   - `**/migration*/**`, `**/schema/**` → area: 10, data: 10
   - `**/.env*`, `**/credentials*`, `**/secrets/**` → area: 8, data: 10
   - `**/middleware/**`, `**/interceptor/**` → area: 7, blast: 8
   - `**/utils/**`, `**/shared/**`, `**/lib/**` → blast: 7 (widely imported)
2. For each matched path, compute composite score from seeded dimensions
3. Write to `sensitivity.jsonl`
4. Everything not matched starts with score 3 (standard enforcement)

**How it grows:**
- Every bug/incident: increase the `incidents` dimension for affected paths, recompute score
- Every clean month (no incidents for a path): reduce `incidents` dimension by 1 (floor: 0), recompute score
- Score never drops below `base_score` — incident history decays, but inherent sensitivity doesn't

### Sensitivity Score Calculation (Per Change)

For a given change (set of files):

1. Look up each file's sensitivity score from the map. Use directory entries for files without explicit entries (walk up the path tree). Default: 3 if no entry found.
2. Take the **MAX** score across all files touched.
3. Map to enforcement level:

| Score | Level | Enforcement behavior |
|-------|-------|---------------------|
| 1-3 | Low | Soft gates only. No mandatory review steps. Standard commit flow. |
| 4-6 | Standard | Hard gates active. Compliance checklist runs. Normal Sutra mode. |
| 7-9 | High | Hard gates + mandatory self-review before commit. Extended compliance check. Sensitivity reason surfaced to session. |
| 10 | Critical | Hard gates + founder notification. Cannot merge without explicit approval. Change logged in Daily Pulse. |

4. This score feeds directly into the Adaptive Protocol Engine's depth selection (see `ADAPTIVE-PROTOCOL-ENGINE.md`).

---

## Self-Improving Classification

### The Feedback Loop

When a change causes a bug (detected via incident report, /investigate session, or manual flag):

1. **Record the miss:**
   ```jsonl
   {"timestamp": "2026-04-05T15:00:00Z", "type": "incident", "files_changed": ["src/auth/session.ts"], "tier_assigned": "standard", "tier_correct": "high", "incident": "Session tokens not invalidated on password change", "session_id": "abc123"}
   ```
   Location: `.claude/logs/sensitivity-incidents.jsonl`

2. **Update sensitivity.jsonl:**
   - Increase `incidents` dimension by 4 for each affected path (immediate bump)
   - Recompute composite score
   - Update `reason` field to include the incident

3. **Escalation thresholds:**
   - Same area has 2 incidents → sensitivity score locked at minimum 7 (high) for 60 days
   - Same area has 3+ incidents → flag for architectural review in Daily Pulse. This area has a structural problem, not just a process problem.

### Judgment Inheritance

**Two levels of sensitivity rules:**

**Asawa-level (universal):** Rules that apply to ALL companies regardless of context.
- Location: `asawa-holding/holding/SENSITIVITY-RULES.md`
- Examples:
  - "Auth changes are always minimum score 7"
  - "Migration files are always score 10"
  - "Environment files are always score 10"
  - "Files with PII handling are always minimum score 8"
- These cannot be overridden by company-level rules (they set floors, not ceilings)

**Company-level (local):** Rules specific to one company's codebase.
- Location: `{company}/.claude/sensitivity.jsonl`
- Examples:
  - "DayFlow's `recurrence.ts` is fragile — score 8 due to 2 past incidents"
  - "Maze's `feed-algorithm.ts` is score 6 due to high blast radius"
- These stay in the company's sensitivity map and do not propagate

**Inheritance flow during Sutra deploy:**
1. Read `asawa-holding/holding/SENSITIVITY-RULES.md` (universal floors)
2. Read company's `sensitivity.jsonl` (local scores)
3. For each path: `final_score = max(universal_floor, local_score)`
4. Write merged result to company's active sensitivity map

### Accuracy Tracking

**What to track:** For every change, record the tier assigned and whether it was correct.

**Correct means:**
- High-risk classification → the change actually needed careful review (would have caused issues without it, or touched genuinely sensitive code)
- Low-risk classification → the change was actually fine (no incidents, no near-misses)

**Recording format:** Append to `.claude/logs/sensitivity-accuracy.jsonl`:
```jsonl
{"timestamp": "2026-04-05T15:00:00Z", "files": ["src/auth/session.ts"], "score_assigned": 7, "level": "high", "outcome": "correct", "session_id": "abc123"}
{"timestamp": "2026-04-05T15:30:00Z", "files": ["src/components/Card.tsx"], "score_assigned": 3, "level": "low", "outcome": "correct", "session_id": "abc124"}
{"timestamp": "2026-04-05T16:00:00Z", "files": ["src/utils/date.ts"], "score_assigned": 3, "level": "low", "outcome": "incorrect_should_be_high", "session_id": "abc125"}
```

**Surfacing:** Weekly review includes: "Sensitivity scoring accuracy: X% this month ({correct} / {total} changes classified correctly)."

**Targets:**
- >85% accuracy: system is well-calibrated, no action needed
- 70-85% accuracy: review the most-misclassified areas, adjust dimensions
- <70% accuracy: major recalibration needed — run full codebase rescan and reset dimension weights

---

## Hook Execution Log Format

All enforcement data flows from structured logs. Every hook execution writes one entry.

**Location:** `.claude/logs/enforcement.jsonl` per company, and `asawa-holding/.claude/logs/enforcement.jsonl` for holding-level.

**Entry format:**
```jsonl
{"timestamp": "2026-04-05T14:30:00Z", "hook": "enforce-boundaries", "action": "blocked", "file": "sutra/ENFORCEMENT.md", "role": "company-maze", "reason": "file outside company boundary", "sensitivity_score": null, "session_id": "abc123"}
{"timestamp": "2026-04-05T14:31:00Z", "hook": "enforce-boundaries", "action": "allowed", "file": "maze/os/TODO.md", "role": "company-maze", "reason": null, "sensitivity_score": 4, "session_id": "abc123"}
{"timestamp": "2026-04-05T14:32:00Z", "hook": "pre-commit-compliance", "action": "blocked", "file": null, "role": "company-maze", "reason": "METRICS.md not updated", "sensitivity_score": null, "session_id": "abc123"}
{"timestamp": "2026-04-05T14:33:00Z", "hook": "enforce-boundaries", "action": "overridden", "file": "sutra/ENFORCEMENT.md", "role": "founder", "reason": "founder override: cross-company edit needed", "sensitivity_score": 9, "session_id": "abc123"}
{"timestamp": "2026-04-05T14:34:00Z", "hook": "sensitivity-gate", "action": "escalated", "file": "src/auth/session.ts", "role": "company-dayflow", "reason": "score 9 requires extended review", "sensitivity_score": 9, "session_id": "abc124"}
```

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| timestamp | ISO 8601 | Yes | When the hook fired |
| hook | string | Yes | Hook identifier (e.g., `enforce-boundaries`, `pre-commit-compliance`, `sensitivity-gate`) |
| action | enum | Yes | One of: `blocked`, `allowed`, `overridden`, `escalated`, `skipped_step` |
| file | string | No | File path that triggered the hook (null for non-file hooks) |
| role | string | Yes | Active role when hook fired |
| reason | string | No | Why the action was taken (required for `blocked`, `overridden`, `escalated`) |
| sensitivity_score | integer | No | Sensitivity score of the file, if applicable |
| session_id | string | Yes | Session identifier for tracing |

**Retention:** Keep 90 days of logs. Archive older logs to `.claude/logs/archive/`.

---

## The Review Dashboard

**What it shows:**

| Metric | Description | Healthy range |
|--------|-------------|--------------|
| Violations/week | Count of `blocked` actions, trended over 4 weeks | Stable or declining |
| Override frequency | Count of `overridden` actions per week | <2/week |
| Compliance score | `(allowed / (allowed + blocked)) * 100` per company | >90 |
| Time-to-ship impact | Average session duration for high-sensitivity vs low-sensitivity changes | <20% difference |
| Top 5 most-triggered rules | Rules with highest fire count this month | Candidates for review |
| Top 5 never-triggered rules | Rules with 0 fires this month | Candidates for demotion |
| Sensitivity accuracy | Correct classifications / total classifications | >85% |

**Format:** Markdown table generated by a script that reads `enforcement.jsonl`.

**Generation:** Runs as part of the 3-day micro-review (Tier 2+) and monthly calibration (all tiers).

**Output location:** `.claude/reports/enforcement-dashboard.md` — overwritten each generation.

**Example output:**
```markdown
# Enforcement Dashboard — 2026-04-05

## Weekly Trend
| Week | Blocked | Allowed | Overrides | Compliance |
|------|---------|---------|-----------|------------|
| W13  | 4       | 87      | 1         | 96%        |
| W14  | 2       | 93      | 0         | 98%        |

## Top Triggered Rules
| Rule | Fires | Action |
|------|-------|--------|
| enforce-boundaries | 3 | Review: are roles too narrow? |
| pre-commit-compliance | 2 | Expected — metrics enforcement working |

## Never-Triggered Rules
| Rule | Days Silent | Recommendation |
|------|------------|----------------|
| os-version-check | 30 | Demote to soft at next calibration |

## Sensitivity Accuracy: 88% (22/25 correct)
```

---

## Integration Points

| Direction | System | What flows |
|-----------|--------|-----------|
| Feeds into | Adaptive Protocol Engine | Sensitivity scores inform depth selection for each change |
| Feeds into | DAILY-PULSE.md | Micro-review paragraphs, calibration results, incident flags |
| Reads from | `.claude/logs/enforcement.jsonl` | All hook execution data |
| Reads from | Bug reports, /investigate sessions | Incident data for feedback loop |
| Reads from | LEARN.md files | Company-specific learnings that may affect sensitivity |
| Updates | ENFORCEMENT.md | Rule promotions, demotions, additions from calibration |
| Updates | `sensitivity.jsonl` | Score changes from incidents and monthly decay |
| Updates | `SENSITIVITY-RULES.md` (Asawa-level) | Universal floor rules that flow to all companies |

---

## Tier Behavior Summary

| Tier | 3-Day Micro-Review | Weekly Review | Monthly Calibration | Dashboard |
|------|-------------------|---------------|--------------------| ----------|
| 1 (Personal) | Off | Off | Required (simplified) | Not required |
| 2 (Product) | Automated | Required | Required (full) | Generated but optional |
| 3 (Company) | Automated | Required | Required (full + cross-company) | Required |

---

## Implementation Checklist

To deploy this spec:

1. [ ] Create `.claude/logs/` directory structure in each company repo
2. [ ] Update hooks to write `enforcement.jsonl` entries in the format above
3. [ ] Create the auto-seed script for `sensitivity.jsonl` initialization
4. [ ] Add micro-review logic to SessionStart hook (check timestamp, run if >3 days)
5. [ ] Add weekly review checklist to /retro skill
6. [ ] Add monthly calibration to session-start first-of-month check
7. [ ] Create `asawa-holding/holding/SENSITIVITY-RULES.md` with universal floor rules
8. [ ] Create dashboard generation script
9. [ ] Add sensitivity score lookup to pre-commit hooks
10. [ ] Add `sensitivity-incidents.jsonl` and `sensitivity-accuracy.jsonl` logging
