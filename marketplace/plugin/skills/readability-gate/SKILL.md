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

### Task-list tables (added v1.9.2)

Any table whose rows represent **tasks, recommendations, or proposed work** MUST carry `Impact` and `Effort` columns. This is the horizontal version of the Depth-Estimation block (TASK / DEPTH / EFFORT / COST / IMPACT) — the singular practice does not translate to table form on its own, so this rule closes the gap.

**Required columns** (minimum):
```
| # | Area/Task | Impact (who/what changes) | Effort (time, files) |
```

**Encouraged additional columns**: Depth (1-5), Cost (~$X or S/M/L), Severity/Priority score.

**Reshape rule**: if input (from a subagent, codex review, or external tool) presents a task table without Impact/Effort, re-shape before displaying:
- Map `Why it matters` / `Rationale` → Impact
- Map `Cost` (S/M/L/XL) + any time estimate → Effort
- Infer Impact/Effort conservatively if absent; surface the inference explicitly

**Severity alone is insufficient** — it ranks, it doesn't frame. A task with Severity 0.8 but no Impact/Effort tells the founder what to fix first, not what it costs or who benefits.

## Self-check

Before submitting output, scan for:
- redundant prose → cut
- missing counts → add numbers
- decisions not visually distinct → box them
- task-list tables missing Impact/Effort columns → reshape (see Task-list tables rule above)
