# Sutra KPI — Historical Baselines

> Historical KPI data. For current metrics and measurement protocol, see [SUTRA-KPI.md](SUTRA-KPI.md).
> Split per PROTO-011 (Version Focus) — sessions load SUTRA-KPI.md only.

---

## Version Baseline Table

| Version | Date | V (L2) | V (L3) | C | A (EWMA) | A (mean) | U (tokens) | U ($) | N | Verdict |
|---------|------|--------|--------|---|----------|----------|------------|-------|---|---------|
| v1.3.1 | 2026-04-05 | 24.7 | 23.0 | 4,621 | 89.6% | 77.6% | 47.5K | $1.47 | 11 | BASE |

---

## v1.3.1 Detailed Baseline Data

**Measurement date**: 2026-04-05
**Data source**: ESTIMATION-LOG.jsonl (11 task records, single calibration session)
**Session context**: First calibration session — 4 research, 4 build, 2 implementation, 1 migration

### Dashboard

```
═══════════════════════════════════════════════════════════════════
  SUTRA KPI BASELINE — v1.3.1
═══════════════════════════════════════════════════════════════════

  V (Velocity):       23.9 min/feature (overall)           [BASE]
                      24.7 min/feature (Level 2, n=6)      [BASE]
                      23.0 min/feature (Level 3, n=5)      [BASE]

  C (Cognitive Load): 4,621 composite index                [BASE]
                      136 files | 1,393 avg words | 41 protocols

  A (Accuracy):       78% mean | 90% EWMA | 86% median    [BASE]
                      σ = 0.233 (high variance — calibrating)

  U (Unit Cost):      47.5K tokens/feature ($1.47)         [BASE]
                      522K total tokens | $16.22 total (11 features)

═══════════════════════════════════════════════════════════════════
```

### Detailed Data

| Metric | Value | Method | N | Notes |
|--------|-------|--------|---|-------|
| V_overall | 23.9 min | Arithmetic mean | 11 | Range: 12-45 min |
| V_level2 | 24.7 min | Arithmetic mean | 6 | Includes 2 outliers (45, 40 min) from first-occurrence Android/migration tasks |
| V_level3 | 23.0 min | Arithmetic mean | 5 | Research + build tasks, lower variance |
| C | 4,621 | F × W_avg / P | — | 136 files, 189,445 words, 41 protocols |
| A_mean | 77.6% | Arithmetic mean | 11 | Bimodal: early tasks ~40-60%, late tasks ~100% |
| A_ewma | 89.6% | EWMA (α=0.3) | 11 | Recency-weighted; reflects within-session calibration |
| A_median | 86% | Median | 11 | Robust to outliers |
| A_σ | 23.3% | Sample std dev | 11 | High — expected for first calibration session |
| U_tokens | 47,455 | Total/N | 11 | Range: 20K-73K |
| U_cost | $1.47 | Total/N | 11 | Range: $0.60-$2.28 |

### Observations

1. **Accuracy is bimodal.** The first 6 tasks (first-occurrence category) averaged 65.8% accuracy. The last 3 tasks (calibrated category) hit 100%. This is the estimation engine's learning curve — expected behavior per D23.

2. **Level 2 velocity is inflated by outliers.** Tasks 5 and 6 (Android visual fixes, LayoutAnimation migration) took 45 and 40 minutes respectively — 2-3x their estimates. Excluding these, Level 2 average drops to 15.0 min. These represent uncalibrated task categories (Android UI, API migration).

3. **Cognitive Load baseline is high.** 136 governance files averaging 1,393 words each is substantial. D30 (expansion then contraction) suggests a simplification cycle is warranted before v1.4.

4. **Unit cost is reasonable.** $1.47 per feature at current model pricing. The 47.5K tokens/feature includes both input and output tokens across research, build, and implementation task types.
