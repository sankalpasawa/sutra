# Sutra -- Coverage Engine

> Tracks whether a session followed the full Sutra process. Like code coverage, but for the operating system itself.

**Version**: 1.0
**Date**: 2026-04-09
**Depends on**: COMPLIANCE-AGENT.md, ADAPTIVE-PROTOCOL.md, MEASUREMENT-PROTOCOL.md

---

## Why This Exists

A company can be "on Sutra" but only using 30% of it. Without instrumentation, the founder has no way to know. The Coverage Engine makes process adherence visible -- per task, per session, per company.

## How It Works

```
TASK STARTS
    |
    v
[1] Expected Checklist generated (based on assigned depth)
    |
    v
[2] As each step fires, it logs to coverage-log.jsonl
    |
    v
[3] At task end (or on demand), Coverage Report compares expected vs actual
    |
    v
[4] Gaps surfaced: "SHAPE phase skipped", "No estimation table", "LEARN phase missing"
```

---

## The Expected Checklist

Every task gets an expected checklist based on its depth. This is the source of truth for "what should have happened."

### Depth 1: Direct

| # | Step | Required | Method ID |
|---|------|----------|-----------|
| 1 | Input routing block | YES | INPUT-ROUTING |
| 2 | Depth assessment | YES | ENGINE-ADAPTIVE |
| 3 | Execute | YES | PHASE-EXECUTE |
| 4 | Triage log | YES | TRIAGE-LOG |

**Expected coverage: 4 steps**

### Depth 2: Think Then Do

| # | Step | Required | Method ID |
|---|------|----------|-----------|
| 1 | Input routing block | YES | INPUT-ROUTING |
| 2 | Depth assessment | YES | ENGINE-ADAPTIVE |
| 3 | Estimation table | YES | ENGINE-ESTIMATION |
| 4 | Objective (goal + criteria) | YES | PHASE-OBJECTIVE |
| 5 | Execute | YES | PHASE-EXECUTE |
| 6 | Verify (build/render check) | YES | VERIFY-BASIC |
| 7 | Triage log | YES | TRIAGE-LOG |

**Expected coverage: 7 steps**

### Depth 3: Research Then Plan Then Do

| # | Step | Required | Method ID |
|---|------|----------|-----------|
| 1 | Input routing block | YES | INPUT-ROUTING |
| 2 | Depth assessment (full scoring) | YES | ENGINE-ADAPTIVE |
| 3 | Pre-scoring gates check | YES | GATE-PRESCORING |
| 4 | Estimation table (Impact/Confidence/Cost/Time) | YES | ENGINE-ESTIMATION |
| 5 | OBJECTIVE: goal + success criteria + depth | YES | PHASE-OBJECTIVE |
| 6 | OBSERVE: context documented | YES | PHASE-OBSERVE |
| 7 | Research gate (3-5 bullets prior art) | YES | GATE-RESEARCH |
| 8 | SHAPE: scope + edge cases + not-in-scope | YES | PHASE-SHAPE |
| 9 | PLAN: structured plan with steps + acceptance criteria | YES | PHASE-PLAN |
| 10 | EXECUTE: plan steps followed | YES | PHASE-EXECUTE |
| 11 | Verify (test output or grep evidence) | YES | VERIFY-EVIDENCE |
| 12 | MEASURE: quantified results per criterion | YES | PHASE-MEASURE |
| 13 | LEARN: what went well, what surprised | YES | PHASE-LEARN |
| 14 | Triage log | YES | TRIAGE-LOG |

**Expected coverage: 14 steps**

### Depth 4: Architect Then Research Then Plan Then Do

| # | Step | Required | Method ID |
|---|------|----------|-----------|
| 1 | Input routing block | YES | INPUT-ROUTING |
| 2 | Depth assessment (full scoring) | YES | ENGINE-ADAPTIVE |
| 3 | Pre-scoring gates check | YES | GATE-PRESCORING |
| 4 | Estimation table (full) | YES | ENGINE-ESTIMATION |
| 5 | OBJECTIVE: goal + criteria + depth + stakeholder map | YES | PHASE-OBJECTIVE |
| 6 | OBSERVE: constraints, dependencies, existing state mapped | YES | PHASE-OBSERVE |
| 7 | Research gate (full scan) | YES | GATE-RESEARCH |
| 8 | SHAPE: scope + edge cases + not-in-scope + cross-practice impact | YES | PHASE-SHAPE |
| 9 | HLD gate (architecture document) | YES | GATE-HLD |
| 10 | ADR gate (architecture decision record for irreversible choices) | CONDITIONAL | GATE-ADR |
| 11 | PLAN: dependencies + risk mitigation + rollback plan | YES | PHASE-PLAN |
| 12 | Parallelization gate (Bernstein independence test) | CONDITIONAL | GATE-PARALLEL |
| 13 | EXECUTE: each step verified before next | YES | PHASE-EXECUTE |
| 14 | Verify (test + deployment verification + rollback plan) | YES | VERIFY-STAGED |
| 15 | MEASURE: cross-practice verification + regression check | YES | PHASE-MEASURE |
| 16 | Finding resolution gate | YES | GATE-FINDINGS |
| 17 | LEARN: feedback for Sutra + per-practice learnings + process improvements | YES | PHASE-LEARN |
| 18 | Retrospective gate | YES | GATE-RETRO |
| 19 | Triage log | YES | TRIAGE-LOG |

**Expected coverage: 19 steps (17-19 if conditionals don't apply)**

### Depth 5: Full Cascade

All of Depth 4, plus:

| # | Step | Required | Method ID |
|---|------|----------|-----------|
| 20 | Domain expert consultation | YES | EXPERT-CONSULT |
| 21 | Market research | YES | RESEARCH-MARKET |
| 22 | Independent review before EXECUTE | YES | REVIEW-INDEPENDENT |
| 23 | Multi-stage verification | YES | VERIFY-MULTISTAGE |
| 24 | Full retrospective document | YES | RETRO-FULL |

**Expected coverage: 24 steps**

---

## Coverage Log Format

Each session writes to `os/coverage-log.jsonl` in the company's directory. One line per method fire.

```jsonl
{"task": "Add content moderation", "depth": 3, "method": "INPUT-ROUTING", "ts": "2026-04-09T14:30:05Z", "evidence": "routing block output"}
{"task": "Add content moderation", "depth": 3, "method": "ENGINE-ADAPTIVE", "ts": "2026-04-09T14:30:08Z", "evidence": "depth=3, gate=none, type=Complex"}
{"task": "Add content moderation", "depth": 3, "method": "ENGINE-ESTIMATION", "ts": "2026-04-09T14:30:15Z", "evidence": "table: 2h, 5 files, $0.80"}
{"task": "Add content moderation", "depth": 3, "method": "PHASE-OBJECTIVE", "ts": "2026-04-09T14:30:20Z", "evidence": "goal: moderate user content, criteria: 3 rules"}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| task | YES | Task name (matches depth block TASK field) |
| depth | YES | Assigned depth (1-5) |
| method | YES | Method ID from the checklist above |
| ts | YES | ISO timestamp |
| evidence | YES | One-line proof that the step actually happened (not just claimed) |
| skipped_reason | NO | If method was intentionally skipped, why |
| override | NO | If founder overrode a gate, logged here |

---

## Coverage Report

Generated at task end, session end, or on demand. Reads `os/coverage-log.jsonl`, compares against the expected checklist for the depth, outputs the gap.

### Report Format

```
SUTRA COVERAGE: [company] / [task]
Depth: [N] | Expected: [X] steps | Fired: [Y] steps | Coverage: [Y/X]%
------------------------------------------------------------

COMPLETED:
  [check] INPUT-ROUTING          14:30:05  "routing block output"
  [check] ENGINE-ADAPTIVE        14:30:08  "depth=3, gate=none"
  [check] ENGINE-ESTIMATION      14:30:15  "2h, 5 files, $0.80"
  [check] PHASE-OBJECTIVE        14:30:20  "goal defined, 3 criteria"
  [check] PHASE-OBSERVE          14:30:45  "context documented"
  [check] GATE-RESEARCH          14:31:10  "5 bullets prior art"
  [check] PHASE-SHAPE            14:32:00  "scope + 3 edge cases"
  [check] PHASE-PLAN             14:33:00  "7 steps, acceptance criteria"
  [check] PHASE-EXECUTE          14:45:00  "plan followed"
  [check] VERIFY-EVIDENCE        14:46:00  "12/12 tests pass"

MISSED:
  [x] PHASE-MEASURE    -- No quantified results against success criteria
  [x] PHASE-LEARN      -- No learnings captured
  [x] TRIAGE-LOG       -- No triage block output

SKIPPED (with reason):
  [skip] GATE-PRESCORING  -- "no sensitive domain triggers"

SUMMARY:
  Hit:     10/14 (71%)
  Missed:   3/14 (21%)  << CONCERN
  Skipped:  1/14 (7%)

PROCESS GAPS:
  - MEASURE phase was skipped entirely. Task shipped without verifying
    success criteria. This is the #1 source of rework.
  - No LEARN phase means the system cannot improve depth routing
    for similar tasks.
  - Missing triage log breaks the calibration feedback loop.
```

---

## How to Instrument

The coverage log is written by the LLM during execution. This is NOT a passive hook -- the LLM actively logs each step as it performs it.

### Behavioral instruction (added to company CLAUDE.md):

```
## Coverage Logging (Sutra Coverage Engine)

After performing each Sutra process step, append one line to `os/coverage-log.jsonl`:

{"task": "[current task]", "depth": [N], "method": "[METHOD-ID]", "ts": "[ISO timestamp]", "evidence": "[one-line proof]"}

Method IDs match the expected checklist in COVERAGE-ENGINE.md for your assigned depth.
If you intentionally skip a step, log it with skipped_reason instead of evidence.
At task completion, output the Coverage Report comparing your log to the expected checklist.
```

### What counts as "evidence"

| Method | Acceptable Evidence | NOT Acceptable |
|--------|-------------------|----------------|
| INPUT-ROUTING | "routing block output with TYPE + ROUTE" | "did input routing" |
| ENGINE-ADAPTIVE | "depth=3, gate=none, type=Complicated, scores=[...]" | "assessed depth" |
| ENGINE-ESTIMATION | "2h, 5 files, $0.80, confidence=75%" | "estimated" |
| PHASE-OBJECTIVE | "goal: [specific], criteria: [N items]" | "defined objective" |
| PHASE-OBSERVE | "read [N] files, identified [constraints]" | "gathered context" |
| GATE-RESEARCH | "[N] bullets of prior art documented" | "researched" |
| PHASE-SHAPE | "scope: [X], edge cases: [N], not-in-scope: [Y]" | "shaped approach" |
| PHASE-PLAN | "[N] steps with acceptance criteria" | "made a plan" |
| PHASE-EXECUTE | "plan steps [list] followed, [N] files changed" | "executed" |
| VERIFY-* | "[N] tests pass" or "build exit 0" or "screenshot confirms" | "verified" |
| PHASE-MEASURE | "criteria [X]: PASS, criteria [Y]: PASS" | "measured" |
| PHASE-LEARN | "surprised by [X], would change [Y]" | "learned" |
| TRIAGE-LOG | "depth_selected=3, depth_correct=3, class=correct" | "triaged" |

**Rule: If your evidence could describe any task, it's not evidence. It must be specific to THIS task.**

---

## Aggregation: Session-Level Coverage

At session end, aggregate all task coverage into one session report:

```
SESSION COVERAGE: DayFlow (2026-04-09)
Tasks: 4 | Avg Coverage: 82%
-------------------------------------------
Task 1: "Fix button color"      D1  4/4   100%
Task 2: "Add moderation"        D3  10/14  71%  << gaps
Task 3: "Update copy"           D1  4/4   100%
Task 4: "SDK integration"       D2  7/7   100%

SESSION GAPS:
  - PHASE-MEASURE skipped in 1/4 tasks (Task 2)
  - PHASE-LEARN skipped in 1/4 tasks (Task 2)

PATTERN: Depth 3 tasks skip tail phases (MEASURE, LEARN). 
         This is a common failure mode -- fatigue after EXECUTE.
```

## Aggregation: Company-Level Coverage (Rolling 30 Days)

```
COMPANY COVERAGE: DayFlow (30-day rolling)
Sessions: 12 | Tasks: 47 | Avg Coverage: 78%
-------------------------------------------
Method                  Fire Rate    Concern?
INPUT-ROUTING           47/47 100%
ENGINE-ADAPTIVE         47/47 100%
ENGINE-ESTIMATION       38/43  88%   (D2+ only)
PHASE-OBJECTIVE         43/43 100%   (D2+ only)
PHASE-OBSERVE           18/22  82%   (D3+ only)
GATE-RESEARCH           15/22  68%   << LOW
PHASE-SHAPE             20/22  91%   (D3+ only)
PHASE-PLAN              21/22  95%   (D3+ only)
PHASE-EXECUTE           47/47 100%
VERIFY-*                40/47  85%
PHASE-MEASURE           12/22  55%   << CONCERN
PHASE-LEARN             8/22   36%   << CRITICAL
TRIAGE-LOG              30/47  64%   << LOW

TOP GAPS:
  1. PHASE-LEARN fires only 36% of the time at D3+.
     Impact: Depth calibration cannot improve without learning data.
  2. PHASE-MEASURE fires only 55% at D3+.
     Impact: Tasks ship without verifying success criteria.
  3. GATE-RESEARCH fires 68% at D3+.
     Impact: 32% of complex tasks skip prior art research.
```

---

## Enforcement

### SOFT enforcement (v1.0):
- Coverage report is generated and shown. No blocking.
- Founder sees gaps and can act on them.

### Future HARD enforcement:
- Coverage below 80% at assigned depth triggers a warning.
- Coverage below 60% blocks session checkpoint (forces retroactive completion).
- Specific methods (VERIFY, MEASURE) can be individually HARD-gated.

---

## Integration

| Direction | System | What Flows |
|-----------|--------|------------|
| **Writes to** | os/coverage-log.jsonl | Per-method fire events |
| **Reads from** | ADAPTIVE-PROTOCOL.md | Expected checklist per depth |
| **Reads from** | COMPLIANCE-AGENT.md | Gate definitions |
| **Feeds into** | Session Checkpoint | Coverage % as checkpoint field |
| **Feeds into** | SUTRA-KPI.md | A (Accuracy) metric — compliance component |
| **Feeds into** | Daily Pulse | Per-company coverage in portfolio view |
| **Queried by** | Founder | On-demand via /sutra-coverage or at session end |

---

## Operationalization

### 1. Measurement mechanism
Per-task coverage % (Y/X × 100); per-session avg coverage; rolling 30-day company avg; per-method fire rate. Source: `os/coverage-log.jsonl` (per company, written by LLM during execution). Aggregated to ANALYTICS-PULSE coverage panel.

### 2. Adoption mechanism
Behavioral instruction in every company's CLAUDE.md (LLM actively logs per-method fires). Plugin doesn't enforce — coverage is observed, not blocked, in v1.0 SOFT mode. Method IDs match the expected checklist in this engine for the assigned depth.

### 3. Monitoring / escalation
Coverage report at task end (on demand). Session-level rollup at session end. Company-level monthly rolling 30-day. Method fire rate <70% on any required method → CONCERN flag in pulse (Sutra-OS reviews); <40% → CRITICAL (founder notification + remediation plan). Cross-company gap pattern (e.g., PHASE-LEARN <40% across multiple companies) → engine v2 instruction redesign.

### 4. Iteration trigger
HARD enforcement upgrade per §"Future HARD": when method fire rate stabilizes >85% under SOFT for 90 days, that method becomes individually HARD-gated (block on absence). Coverage <80% at assigned depth: warn-mode rolls out fleet-wide. Coverage <60% on a session: block checkpoint (forces retroactive completion). Triggers per-method, not all-at-once.

### 5. DRI
CEO of Sutra (engine + checklist authorship). Per-company operator (LLM behavioral compliance). Analytics dept (rollup pulse + cross-company pattern detection).

### 6. Decommission criteria
When coverage stabilizes ≥95% across all companies for 90 consecutive days, engine retires from active observation → SOFT sensor only, embedded in PROTO-000 6th criterion (continuous compliance is the new norm). If Sutra restructures process model (merging phases or eliminating gates), checklist regenerated and v1 archived to `sutra/archive/`.

## Origin

v1.0 (2026-04-09): Founded on the insight that a company can be "on Sutra" but only exercising a fraction of the process. The 7-phase lifecycle with depth-modulated gates provides a concrete, checkable surface area. Coverage tracking makes adherence visible and improvable.

Analogues: code coverage (Istanbul/nyc), test coverage, audit trail compliance. No known prior art for "operating system coverage" in AI-mediated workflows.
