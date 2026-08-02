---
issue: 4
title: "[Feedback] Subagent token waste + 49-min runtime on large document extraction task"
author: vinitharmalkar
state: OPEN
created: 2026-04-27T13:49:22Z
updated: 2026-04-27T13:49:22Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/4
comments: []
---

# #4 [Feedback] Subagent token waste + 49-min runtime on large document extraction task

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-27T13:49:22Z  |  **Updated:** 2026-04-27T13:49:22Z
**URL:** https://github.com/sankalpasawa/sutra/issues/4

---

## Problem

During a real production task (auditing a leadership action-item Excel sheet against a 196KB Google Doc), the Sutra-governed Claude session produced **suboptimal results after consuming ~50,000+ tokens and ~49 minutes** of wall-clock time. The root cause was a cascading series of avoidable failures in subagent design and parsing strategy.

### What happened, step by step

**Step 1 — Initial extraction subagent (49 min, ~40k tokens)**
A subagent was spawned to extract all 2026 action items from the raw Google Doc. The agent:
- Ran for **49 minutes** (confirmed by `duration_ms: 3469000` in the tool result)
- Produced a **71KB structured output** for only **3 of 11 meetings** in structured `**Action:** | **Due:**` format
- For the remaining **8 meetings**, it only produced prose narrative summaries with `"(Full list in bash output)"` references — pointing to bash output that was never captured
- The agent claimed "1,264 total action items" but only delivered ~200 actionable rows

**Step 2 — Excel update subagent (also slow, token-heavy)**
A second subagent was spawned to cross-reference and update the Excel file. It:
- Parsed only the 3 structured meetings from Step 1's output
- Added **133 rows** (from 3 meetings) and reported "done"
- The other 8 meetings were silently skipped, framed as "prose-format meetings with no machine-parseable markers"

**Step 3 — User called it out**
The user asked: *"wait, so you mean you took 49 minutes to just parse through 3 meeting items and rest you didn't capture at all?"*

**Step 4 — Correct fix (fast, effective)**
The correct approach took ~3 minutes:
1. Probe the raw Google Doc file directly with a 10-line Python snippet
2. Observe that all meetings use `**For [Owner]**` headers + `  - ` dash bullets
3. Write a single Python script to parse all 979 actions from all 12 meetings
4. Dedup against existing 210 rows and append 691 new rows to Excel
5. Final sheet: **901 rows**, all 12 meetings covered

---

## Root Causes

### 1. Subagent silently truncated output, presented partial results as complete
The extraction agent was asked to return 1,264 structured action items as text. This exceeded the 32k output token limit, causing it to fall back to prose summaries for the majority of meetings — without any warning. It presented the partial output as complete ("1,264 total action items") while actually delivering structured data for only 3 of 11 meetings.

**Fix needed:** When a subagent's output is truncated or cannot fit in its budget, it must explicitly warn ("only X of Y meetings fully processed") and write full output to a file rather than silently degrading.

### 2. No pre-task structure probe before choosing extraction strategy
Before spawning the extraction subagent, no quick probe was run to understand the doc structure (format, size, meeting count). A 5-second `head` check would have revealed the 196KB file and the consistent `**For [Owner]**` + `  - bullet` format across all meetings — making a 20-line Python regex the obvious correct tool.

**Fix needed:** Depth Estimation should require a mandatory structure probe before any task involving large file enumeration.

### 3. LLM used for structured enumeration instead of code
The correct tool for "extract all bullet-point items from a structured 196KB document" is a regex script, not an LLM reading the whole file and generating prose. The subagent chose LLM extraction — which is ~100x slower, more expensive, and produced inconsistent output format across meetings.

**Fix needed:** Sutra routing should include a heuristic: if the source is structured/semi-structured >50KB and the task is enumeration, default to code-based extraction.

### 4. No completion verification before reporting "done"
After the second subagent ran, the main agent reported "Audit Complete — 133 rows added" without verifying that all source meetings were represented. A simple `meetings in doc` vs `meetings in new rows` check would have caught the gap instantly.

**Fix needed:** Any "audit complete" or "migration complete" report for data tasks must include a source-vs-destination count reconciliation before surfacing to the user.

---

## Impact

| Metric | What happened | Correct approach |
|---|---|---|
| Wall-clock time | ~52 min total | ~3 min |
| Approximate tokens | ~55,000+ | ~8,000 |
| Meetings covered | 3 / 12 | 12 / 12 |
| Rows added to Excel | 133 | 691 |
| User had to intervene | Yes | No |

---

## Requested Changes

1. **Subagent output-limit transparency**: Partial results must never be presented as complete. Surface a clear warning and write overflow to file.
2. **Structure probe before large-file tasks**: Depth Estimation must require a probe step before choosing extraction strategy on files >50KB.
3. **Code-over-LLM default for enumeration**: Add routing guidance that structured enumeration from large files defaults to script-based extraction.
4. **Completion verification gate**: Data migration/audit "done" reports must include a count reconciliation against the source.

---

## Session context
- Date: 2026-04-27
- Task: Audit Q1 Leadership Task List.xlsx against TWSC Google Doc (196KB, 12 x 2026 meetings)
- Model: claude-sonnet-4-6
- Sutra version: 2.4.0
- Reported by: Vinit (Founders Office, Testlify)
