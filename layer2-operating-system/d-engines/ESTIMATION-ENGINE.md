# Sutra — Task Estimation Engine

ENFORCEMENT: HARD (Tier 2+), SOFT (Tier 1)

## Purpose

The Estimation Engine generates a structured cost/impact/confidence/time table before every task — engineering, PRD, design, research, onboarding, or any other work type — so the founder and the system can make informed commit-or-defer decisions. It runs at task pickup, captures actuals at task completion, and feeds accuracy data back into itself and the Adaptive Protocol Engine. Over time it self-calibrates: bad predictors lose weight, good ones gain it, and confidence scores converge on real-world delivery rates.

---

## The Estimation Table

Generated once per task at pickup. The `Actual` and `Accuracy` columns are filled post-task.

```
TASK: {task-slug}
DATE: {YYYY-MM-DD}
TIER: {1|2|3}
WORK-TYPE: {engineering|prd|design|research|onboarding|ops}

| Dimension              | Estimate                              | Actual | Accuracy |
|------------------------|---------------------------------------|--------|----------|
| **Impact**             |                                       |        |          |
| — Security             | HIGH — closes open RLS gap            | —      | —        |
| — User P&L             | +$200/mo retention, -3% churn         | —      | —        |
| — Tech debt            | REDUCES — removes 5 TODOs             | —      | —        |
| — Unblocks             | 2 downstream tasks                    | —      | —        |
| — Strategic alignment  | P0 — on critical path for launch      | —      | —        |
| **Confidence**         |                                       |        |          |
| — Error-free delivery  | 70%                                   | —      | —        |
| — Scope creep risk     | LOW — well-defined boundary           | —      | —        |
| — Unknown unknowns     | MEDIUM — new API, untested            | —      | —        |
| **Cost**               |                                       |        |          |
| — Tokens (→ $)         | ~18K tokens (~$0.27 Opus)             | —      | —        |
| — Files touched        | 4-6 files                             | —      | —        |
| — External/API spend   | $0 (within free tier)                 | —      | —        |
| — Infra delta          | +$0/mo                                | —      | —        |
| **Time**               |                                       |        |          |
| — Build time           | 25-40 min                             | —      | —        |
| — Review cycles        | 1 cycle                               | —      | —        |
| — Total wall-clock     | ~1 hour                               | —      | —        |

GATE: PASS | FLAGGED ({reason})
OVERRIDE: {none | founder-approved}
```

**Dimensions adapt to work type.** For a PRD, "Files touched" becomes "Sections drafted." For research, "Build time" becomes "Research time." The four top-level dimensions (Impact, Confidence, Cost, Time) are fixed. Sub-metrics flex.

---

## How Estimates Are Generated

### Step 1: Read Inputs

The engine reads three input categories:

| Input | Source | What It Provides |
|-------|--------|-----------------|
| Task description | TODO.md, INTAKE.md, or verbal task | Scope, intent, success criteria |
| Codebase context | File tree, recent git log, architecture docs | Files likely touched, coupling risk, test coverage |
| Historical data | ESTIMATION-LOG.jsonl (if exists) | Past tasks of similar type, their estimates vs actuals |

### Step 2: Apply Heuristics

#### Token Estimation Heuristics

```
Base formula:
  estimated_tokens = files_touched × avg_tokens_per_file × edit_ratio

Where:
  files_touched     = count of files the task will read + modify
  avg_tokens_per_file:
    - TypeScript/JS component:  ~800 tokens
    - Config file:              ~200 tokens
    - Markdown doc:             ~500 tokens
    - SQL migration:            ~300 tokens
    - Full-page rewrite:        ~1500 tokens
  edit_ratio:
    - Read-only (context):      0.3  (model reads but doesn't output)
    - Modify existing:          0.6  (reads + partial output)
    - Create new:               1.0  (full output)
    - Delete/refactor:          0.4  (reads + targeted output)

Conversation overhead multiplier:
  - Simple/clear task:          1.2x  (minimal back-and-forth)
  - Ambiguous task:             1.8x  (clarification rounds)
  - Research-heavy task:        2.5x  (exploration + synthesis)

Final: estimated_tokens × overhead_multiplier = total_tokens
```

#### Model Pricing Table

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Typical ratio (in:out) |
|-------|----------------------|------------------------|----------------------|
| Opus  | $15.00               | $75.00                 | 3:1                  |
| Sonnet | $3.00               | $15.00                 | 3:1                  |
| Haiku | $0.25                | $1.25                  | 4:1                  |

```
Dollar estimate:
  input_tokens  = total_tokens × (ratio_in / (ratio_in + ratio_out))
  output_tokens = total_tokens × (ratio_out / (ratio_in + ratio_out))
  cost = (input_tokens × input_rate) + (output_tokens × output_rate)

Example (18K tokens on Opus, 3:1 ratio):
  input  = 13,500 × $15.00/1M = $0.20
  output = 4,500  × $75.00/1M = $0.34
  total  = $0.54
```

Update these rates when Anthropic changes pricing. Store in `SUTRA-CONFIG.md` under `model_pricing`.

### Step 3: Score Confidence

Confidence is not a gut feeling. It is computed from three signals:

| Signal | How to Measure | Weight |
|--------|---------------|--------|
| Historical similarity | Count past tasks in ESTIMATION-LOG.jsonl with matching `work_type` and overlapping `files_touched`. More matches = higher confidence. 0 matches = floor of 40%. | 0.4 |
| Domain maturity | Has this area of the codebase been touched 5+ times? Does it have tests? Mature = +15%, immature = -15%. | 0.3 |
| Scope clarity | Does the task have explicit success criteria? YES = +10%. Ambiguous language ("explore", "investigate", "maybe") = -10%. | 0.3 |

```
confidence = (similarity_score × 0.4) + (maturity_score × 0.3) + (clarity_score × 0.3)
Clamp to [20%, 95%]. Nothing is 100% — unknown unknowns always exist.
```

#### Calibration Target

"If we say 70%, do 70% of those tasks ship error-free?"

Track this with a calibration table updated weekly:

| Predicted Confidence | Tasks at This Level | Actually Error-Free | Calibration |
|---------------------|--------------------|--------------------|-------------|
| 80-90%              | 12                 | 10 (83%)           | GOOD        |
| 60-70%              | 8                  | 4 (50%)            | OVERCONFIDENT — recalibrate |
| 40-50%              | 3                  | 2 (67%)            | UNDERCONFIDENT — recalibrate |

If calibration drifts more than 15 percentage points from predicted, apply a correction factor to future estimates in that band.

### Step 4: Output

Write the estimation table (format above) to the task's working directory or inline in the session. For GSD workflows, the table is appended to the phase's PLAN.md. For ad-hoc tasks, it is printed in the session before work begins.

---

## Post-Task Feedback

After every task completion, capture actuals in structured JSONL format. One file per company: `ESTIMATION-LOG.jsonl` in the company's `os/` directory.

### JSONL Record Format

```json
{
  "task_id": "maze-rls-rewrite",
  "date": "2026-04-05",
  "work_type": "engineering",
  "tier": 2,
  "estimate": {
    "impact": {
      "security": "HIGH",
      "user_pnl": "+$200/mo",
      "tech_debt": "REDUCES",
      "unblocks": 2,
      "strategic": "P0"
    },
    "confidence": {
      "error_free": 0.70,
      "scope_creep": "LOW",
      "unknown_unknowns": "MEDIUM"
    },
    "cost": {
      "tokens": 18000,
      "dollars": 0.54,
      "files_touched": 5,
      "external_spend": 0,
      "infra_delta": 0
    },
    "time": {
      "build_minutes": 32,
      "review_cycles": 1,
      "wall_clock_minutes": 60
    }
  },
  "actual": {
    "impact": {
      "security": "HIGH",
      "user_pnl": "TBD-post-launch",
      "tech_debt": "REDUCES",
      "unblocks": 2,
      "strategic": "P0"
    },
    "confidence": {
      "error_free": true,
      "scope_creep": false,
      "surprises": "none"
    },
    "cost": {
      "tokens": 22400,
      "dollars": 0.67,
      "files_touched": 7,
      "external_spend": 0,
      "infra_delta": 0
    },
    "time": {
      "build_minutes": 45,
      "review_cycles": 1,
      "wall_clock_minutes": 75
    }
  },
  "accuracy": {
    "tokens": 0.80,
    "dollars": 0.81,
    "files": 0.71,
    "time": 0.80,
    "confidence_calibrated": true
  },
  "gate_triggered": false,
  "notes": "Underestimated files — forgot migration file and test file."
}
```

### Capture Procedure

1. At task completion, the engine reads the original estimate from the session.
2. It prompts for actuals: actual tokens (from session metadata if available), actual files changed (from `git diff --stat`), actual time (session duration or founder input).
3. It computes per-dimension accuracy: `accuracy = 1 - abs(estimate - actual) / max(estimate, actual)`.
4. It appends the JSONL record to `ESTIMATION-LOG.jsonl`.
5. For Tier 1: this step is prompted but not enforced (founder can skip). For Tier 2+: this step is required before the task is marked complete.

---

## Accuracy Tracking

### Rolling Metrics

Maintain a rolling window (last 20 tasks per company) for each dimension:

| Metric | Formula | Target |
|--------|---------|--------|
| Token accuracy | mean(token_accuracy across last 20) | > 0.70 |
| File count accuracy | mean(files_accuracy across last 20) | > 0.75 |
| Time accuracy | mean(time_accuracy across last 20) | > 0.65 |
| Confidence calibration | abs(predicted_band - actual_success_rate) | < 15pp |
| Cost accuracy | mean(dollar_accuracy across last 20) | > 0.70 |

### Surfacing in Weekly Reviews

In the weekly review (or weekly check-in for Tier 2), include an Estimation Health section:

```
## Estimation Health (week of {date})
Tasks estimated: 8
Tasks with actuals captured: 7

| Dimension   | Accuracy | Trend     | Action Needed         |
|-------------|----------|-----------|-----------------------|
| Tokens      | 74%      | improving | None                  |
| Files       | 68%      | flat      | Review file heuristics|
| Time        | 61%      | declining | Add overhead buffer   |
| Confidence  | 82% cal  | stable    | None                  |
| Cost ($)    | 73%      | improving | None                  |
```

### What "Good Calibration" Looks Like

- Token/cost accuracy consistently above 70% over a 4-week window.
- Confidence calibration within 15 percentage points (if we predict 70% confidence, between 55% and 85% of those tasks actually ship clean).
- No single dimension below 50% accuracy for more than 2 consecutive weeks (triggers heuristic review).
- Time estimates within 1.5x of actuals on average (time is the hardest to estimate — wider tolerance).

---

## Cost Thresholds and Gates

### Default Thresholds

| Condition | Gate Type | Action |
|-----------|-----------|--------|
| Token cost > $5 | ALERT | Print warning. Founder must acknowledge before proceeding. |
| Files touched > 50 | ALERT | Print warning. Suggest breaking into smaller tasks. |
| Confidence < 40% | GATE | Recommend research phase first. Founder can override. |
| Wall-clock > 4 hours | ALERT | Print warning. Suggest checkpointing plan. |
| External spend > $0 | INFO | Log to METRICS.md. No block (PROTO-003 handles this). |

### Founder Configuration

Thresholds are configurable per company in `SUTRA-CONFIG.md`:

```yaml
estimation_engine:
  enabled: true
  thresholds:
    max_token_cost_dollars: 5
    max_files_touched: 50
    min_confidence_percent: 40
    max_wall_clock_hours: 4
  model_pricing:
    opus_input_per_1m: 15.00
    opus_output_per_1m: 75.00
    sonnet_input_per_1m: 3.00
    sonnet_output_per_1m: 15.00
    haiku_input_per_1m: 0.25
    haiku_output_per_1m: 1.25
  default_model: opus
  capture_actuals: required    # required | optional | disabled
  accuracy_window: 20          # rolling window size for accuracy tracking
```

Tier 1 companies default to `capture_actuals: optional`. Tier 2+ default to `required`.

---

## Integration Points

### Pre-Task (generates estimate)

**Trigger**: When a task is picked up — via GSD (`/gsd:plan-phase`, `/gsd:execute-phase`), manual TODO.md selection, or verbal task assignment.

**Procedure**:
1. Read task description and scope.
2. Scan codebase: identify likely files touched (from task description keywords matched against file tree).
3. Query ESTIMATION-LOG.jsonl for similar past tasks (match on `work_type` + overlapping file paths).
4. Apply token, confidence, and time heuristics.
5. Generate the estimation table.
6. Evaluate against thresholds. If any gate triggers, surface it before proceeding.
7. Print the table in the session. For GSD, append to PLAN.md.

### Post-Task (captures actuals)

**Trigger**: Task completion — feature shipped, document written, research concluded.

**Procedure**:
1. Collect actuals: `git diff --stat` for files, session token count if available, elapsed time.
2. Compute accuracy per dimension.
3. Append JSONL record to ESTIMATION-LOG.jsonl.
4. If any accuracy metric falls below 50%, flag for heuristic review in next weekly review.

### Feeds Into: Adaptive Protocol Engine

The estimation table's cost and confidence dimensions inform the Adaptive Protocol Engine's depth selection:

| Estimation Signal | Protocol Engine Response |
|-------------------|------------------------|
| Cost < $0.50 and confidence > 80% | Lightweight process (skip full lifecycle, minimal review) |
| Cost > $2 or confidence < 50% | Full process (specs, review, QA) |
| Confidence < 40% | Recommend research phase before committing |
| Files > 20 | Require TECH-SPEC.md before implementation |

The Adaptive Protocol Engine reads the estimation table — it does not re-derive these values.

### Validated By: Effectiveness Agent

After task completion, the Effectiveness Agent evaluates whether the estimate was useful:

| Effectiveness Check | What It Asks |
|--------------------|-------------|
| Estimate accuracy | Were the numbers close enough to be decision-useful? |
| Gate value | Did any triggered gate prevent a bad outcome? |
| Gate friction | Did any triggered gate slow down a task that didn't need slowing? |
| Overhead cost | How much time did estimation itself add? Was it worth it? |

If the Effectiveness Agent consistently reports that estimation adds no value for a task category (10 consecutive tasks), it can recommend disabling estimation for that category. The founder decides.

---

## Tier Behavior

| Tier | Estimation Depth | Actuals Capture | Gates | Accuracy Review |
|------|-----------------|-----------------|-------|-----------------|
| **Tier 1 (Personal)** | Generate table. Print inline. No artifact file required. | Optional — prompted but not enforced. | SOFT — warnings only, never block. | Monthly glance, no formal review. |
| **Tier 2 (Product)** | Generate table. Append to PLAN.md or feature directory. | Required — task not complete until actuals logged. | HARD on confidence < 40%. ALERT on cost/files. | Weekly in check-in. |
| **Tier 3 (Company)** | Generate table. Write to dedicated ESTIMATE.md per task. Cross-referenced in PLAN.md. | Required — automated collection from git + session metadata. | HARD on all thresholds. Override requires written justification. | Weekly with trend analysis. Monthly calibration review. |

Tier 1 keeps estimation lightweight — the table is still generated (the thinking matters) but the overhead is minimal. No files to write, no gates that block, no mandatory actuals capture.

Tier 3 adds rigor — every estimate is a file on disk (PROTO-010 compliance), every gate requires justification to override, and accuracy is reviewed both weekly and monthly.

---

## Enforcement

ENFORCEMENT: HARD (Tier 2+), SOFT (Tier 1).

| Rule | Tier 1 | Tier 2 | Tier 3 |
|------|--------|--------|--------|
| Estimation table generated before task starts | SOFT — prompted, not required | HARD — task cannot begin without estimate | HARD — estimate must be written to file |
| Actuals captured after task completes | SOFT — skip allowed | HARD — task not marked complete without actuals | HARD — automated capture + manual review |
| Gates respected | SOFT — warnings only | HARD — confidence gate blocks, cost/files alert | HARD — all gates block, override requires justification |
| ESTIMATION-LOG.jsonl maintained | SOFT — best effort | HARD — append required | HARD — append required + weekly integrity check |
| Accuracy reviewed | No requirement | Weekly in check-in | Weekly + monthly calibration |

Violations follow the standard Sutra violation handling (see ENFORCEMENT.md): BLOCK for hard enforcement, FLAG for soft enforcement.


---

## Calibration Data (from Evolution Cycles 1-18)

### Time Estimation Multipliers (proven across 2 companies)

Raw estimates consistently over-predict. Apply these multipliers:

| Task Category | Multiplier | Based On |
|--------------|-----------|----------|
| Config change (vercel.json, env vars) | 0.3x | Cycle 1: 10min est → 5min actual |
| Routing/navigation (new routes, links) | 0.4x | Cycle 2: 35min → 15min |
| UI feature (new component + page) | 0.45x | Cycle 3: 45min → 20min |
| Security/auth (edge functions, JWT) | 0.8x | Cycle 4: 30min → 25min |
| Content creation (privacy policy, docs) | 0.8x | Cycle 5: 10min → 12min |
| Cross-cutting (analytics, logging) | 0.75x | Cycle 6: 20min → 18min |
| Bug fix (one-line root cause) | 0.3x | Cycle 7: 5min → 3min |
| Test writing | 0.8x | Cycle 8: 25min → 20min |

### File Count Heuristics

| Pattern | File Count |
|---------|-----------|
| New React Native screen | 3 (screen + navigator + linking) |
| New Next.js page with OG | 3 (page + OG image + optional client component) |
| New API route | 1-2 (route + optional types) |
| New component | 1 (component file only) |
| Cross-cutting feature (analytics, logging) | 3-5 (lib + integrations across files) |

### Confidence Calibration

From 18 cycles: when we estimate 60-75% confidence, actual success rate is 100%.
The model is systematically under-confident for familiar patterns.
Adjust: if the pattern has been done before in this codebase, add +20% to confidence.
