---
name: readability-gate
description: Use before presenting output. Formats for readability — tables over prose, numbers over adjectives, decisions boxed, progress bars for scores.
---

# Readability Gate

Every output passes through a readability check before display. The gate is a BEHAVIOR, applied at output time — not a per-file template.

## Rules

### Status & scores
- Scores with progress bars: `Name ▓▓▓▓▓▓░░░░ 0.6 STATUS`
- Health icons: 🟢 GRN / 🟡 YLW / 🔴 RED
- Tables over paragraphs when 3+ rows of comparable data
- Numbers over adjectives ("12 open PRs" beats "several open PRs")

### Decisions (boxed for visibility)

```
╭───────────────────────────────────────────────╮
│ DECISION: [one-line summary]                  │
│ Recommend: APPROVE / REVISE / DEFER           │
│ Why: [1 sentence]                             │
│ Trade-off: [1 sentence]                       │
│ Verdict: APPROVE  /  REVISE  /  DEFER         │
╰───────────────────────────────────────────────╯
```

### Line budgets
- Daily status ≤25 lines
- Decision board summary ≤15 lines
- Long reports: summary first, detail behind progressive disclosure

### What to avoid
- Walls of prose when a table fits
- "Several" / "some" / "a few" when a count is available
- Multi-paragraph summaries when one sentence + a table work
- Decisions not visually distinct from surrounding narrative

## Self-check

Before submitting output, scan for: redundant prose, missing counts, decisions not visually distinct. Fix before display.
