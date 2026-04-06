# Sutra — KPI Measurement System

> Every Sutra version must improve at least one metric without regressing others beyond threshold.
> D31: "Speed of building improved, complexity down, accuracy up, cost down."

---

## The Four Metrics

### V — Velocity (Time-to-Ship)

**Definition**: Wall-clock time from OBSERVE phase initiation to MEASURE phase completion, per feature unit.

**Formula**:
```
V = Σ(duration_actual_min) / N
V_level = Σ(duration_actual_min | thoroughness = L) / N_L
```

**Unit**: minutes per feature, segmented by thoroughness level.

**Normalization**: Velocity is reported per-level to prevent composition bias. A version that takes on more Level 4 tasks will naturally show higher V_overall — level-segmented reporting isolates genuine efficiency gains from task-mix shifts.

**Statistical method**: Arithmetic mean per level. When N > 20 per level, report trimmed mean (5th-95th percentile) to exclude outliers from cascading scope changes.

---

### C — Cognitive Load (System Complexity)

**Definition**: Composite index measuring the total cognitive surface area of the governance system — the amount a new session must internalize to operate correctly.

**Formula**:
```
C = F × W_avg / P

Where:
  F     = total governance file count (sutra/ + holding/ markdown files)
  W_avg = total_words / F  (average words per governance file)
  P     = active protocol count (layer2-operating-system/ files)
```

**Unit**: Dimensionless composite index. Lower is better.

**Interpretation**: C rises when files or verbosity increase without proportional protocol consolidation. C decreases when protocols absorb more responsibility per unit (higher P) or when docs are compressed (lower W_avg). The metric penalizes documentation sprawl and rewards abstraction density.

**Contraction trigger (D30)**: If C increases >10% version-over-version, a mandatory simplification cycle fires before the next version ships.

---

### A — Accuracy (Estimation + Compliance)

**Definition**: Dual-axis metric combining estimation calibration (how closely pre-task estimates match post-task actuals) and principle compliance (D27 regression test pass rate).

**Formula**:
```
A_estimation = EWMA(accuracy_tokens_pct, α=0.3)

  EWMA_t = α × x_t + (1 - α) × EWMA_{t-1}

A_compliance = principle_tests_passed / principle_tests_run

A = 0.7 × A_estimation + 0.3 × A_compliance
```

**Unit**: Percentage (0-100%). Higher is better.

**Statistical method**: Exponentially Weighted Moving Average (EWMA) with α=0.3 for estimation accuracy. EWMA weights recent performance more heavily, reflecting calibration improvement within a session while smoothing noise. The 0.7/0.3 weighting reflects that estimation accuracy is measured continuously (every task) while compliance is event-driven (violations only).

**Supplementary statistics**: Report arithmetic mean, median, and standard deviation alongside EWMA for transparency. High σ indicates inconsistent estimation — a calibration problem distinct from low mean accuracy.

---

### U — Unit Cost (Tokens and Dollars per Feature)

**Definition**: Total computational resource expenditure per feature shipped.

**Formula**:
```
U_tokens = Σ(tokens_total_actual) / N
U_cost   = Σ(cost_usd_actual) / N
```

**Unit**: Tokens per feature, USD per feature.

**Normalization**: Like velocity, report per-level to prevent composition effects. A version handling more Level 4 tasks will naturally show higher U — level-segmented reporting isolates efficiency from task mix.

**Cost model**: Based on ESTIMATION-LOG.jsonl `cost_usd` field, which uses the pricing model active at measurement time. When model pricing changes, annotate the version boundary.

---

## Baseline Record — Sutra v1.3.1

> Detailed baseline data (dashboard, per-metric breakdown, observations) moved to [SUTRA-KPI-HISTORY.md](SUTRA-KPI-HISTORY.md). (PROTO-011)

**Summary**: 2026-04-05, N=11 tasks, first calibration session (4 research, 4 build, 2 implementation, 1 migration).

---

## Version Comparison Protocol

### When to Measure

A KPI snapshot is taken at every Sutra version bump (minor or patch). The measurement window is the full set of ESTIMATION-LOG.jsonl entries between version tags.

### Comparison Format

```
═══════════════════════════════════════════════════════════════════
  SUTRA KPI — v{NEW} vs v{OLD}
═══════════════════════════════════════════════════════════════════

  V (Velocity):       XX min/feature (Level 2)   [↑↓→ vs v{OLD}]
  C (Cognitive Load): XX composite index          [↑↓→ vs v{OLD}]
  A (Accuracy):       XX% EWMA                    [↑↓→ vs v{OLD}]
  U (Unit Cost):      XXK tokens ($X.XX)          [↑↓→ vs v{OLD}]

  VERDICT: {PASS | FAIL | REVIEW}
═══════════════════════════════════════════════════════════════════
```

### Pass/Fail Criteria

| Condition | Verdict |
|-----------|---------|
| ≥1 metric improved, 0 regressed beyond threshold | **PASS** |
| ≥1 metric improved, ≥1 regressed but within threshold | **PASS** (with annotation) |
| 0 metrics improved | **FAIL** — version adds overhead without value |
| ≥1 metric regressed beyond threshold, none improved | **FAIL** — version is net negative |
| Ambiguous (mixed signals, composition effects) | **REVIEW** — founder judgment required (D19) |

### Regression Threshold

A metric has **regressed** if it worsens by more than 5% relative to the previous version baseline:

```
regression_test(metric_old, metric_new):
  if metric is V or C or U:  // lower is better
    regressed = (metric_new - metric_old) / metric_old > 0.05
  if metric is A:             // higher is better
    regressed = (metric_old - metric_new) / metric_old > 0.05
```

### Composition Adjustment

When comparing versions with different task-mix distributions (e.g., v1.3.1 had 36% research, v1.4 has 60% implementation), apply level-segmented comparison. Only compare Level-2-to-Level-2 and Level-3-to-Level-3 velocities. Aggregate comparison is reported but flagged as potentially confounded.

---

## Metric Collection Automation

### Data Flow

```
TASK (any company)
  │
  ├─ PLAN phase    → ESTIMATION-LOG.jsonl (estimates)
  │
  ├─ MEASURE phase → ESTIMATION-LOG.jsonl (actuals + accuracy)
  │
  └─ LEARN         → Category calibration updates
        │
        ▼
  VERSION BUMP → KPI snapshot generated from ESTIMATION-LOG.jsonl
        │
        ▼
  SUTRA-KPI.md → Baseline record appended, comparison rendered
```

### Required Fields (from ESTIMATION-LOG.jsonl)

| Field | Used by | Required |
|-------|---------|----------|
| `actuals.duration_min` | V | Yes |
| `actuals.tokens_total` | U | Yes |
| `actuals.cost_usd` | U | Yes |
| `accuracy.tokens_pct` | A | Yes |
| `thoroughness_level` | V, U (normalization) | Yes |
| `category` | A (calibration tracking) | Yes |

### Cognitive Load Measurement

C is measured by filesystem scan at version bump time:

```bash
F = find sutra/ holding/ -name "*.md" | wc -l
W = find sutra/ holding/ -name "*.md" -exec wc -w {} + | tail -1
P = find sutra/layer2-operating-system/ -name "*.md" | wc -l
C = F * (W / F) / P
```

---

## Historical Baselines

> For full version-over-version history, see [SUTRA-KPI-HISTORY.md](SUTRA-KPI-HISTORY.md). (PROTO-011: Version Focus)

**Current baseline**: v1.3.1 (2026-04-05) — V=24.7/23.0, C=4621, A=89.6% EWMA, U=47.5K/$1.47, N=11
