# Sutra Compliance Agent

## What This Is

A real-time auditor that runs ALONGSIDE task execution, not after. It checks that every lifecycle phase was followed to the right depth before the next phase begins. Compliance intensity scales with the Depth system (1-5).

## Why It Exists

Previous approach: build first, audit later. Result: 28 FAILs discovered post-hoc. The auditor had no power to prevent violations — only to report them.

New approach: the compliance agent runs as a checkpoint between lifecycle phases. It has the authority to BLOCK the next phase if the current phase's artifacts are missing or insufficient. Compliance intensity is governed by the Depth system — lightweight at Depth 1-2, standard at Depth 3, full audit at Depth 4-5.

## How It Works

```
PHASE 1: OBJECTIVE
  → Agent defines the objective
  → COMPLIANCE AGENT checks:
    ✓ Clear goal statement?
    ✓ Success criteria defined?
    ✓ Depth assigned (1-5)?
  → PASS: proceed to OBSERVE
  → FAIL: block. List what's missing.

PHASE 2: OBSERVE
  → Agent gathers context
  → COMPLIANCE AGENT checks:
    ✓ Relevant context collected?
    ✓ Constraints identified?
    ✓ Depth 1-2: skip (context is implicit)
    ✓ Depth 3+: documented observations?
  → PASS: proceed to SHAPE
  → FAIL: block. List what's missing.

PHASE 3: SHAPE
  → Agent shapes the approach
  → COMPLIANCE AGENT checks:
    ✓ Scope defined?
    ✓ Edge cases identified?
    ✓ Not-in-scope stated?
    ✓ Depth matches problem complexity?
  → PASS: proceed to PLAN
  → FAIL: block. List what's missing.

PHASE 4: PLAN
  → Agent creates execution plan
  → COMPLIANCE AGENT checks:
    ✓ Actionable steps listed?
    ✓ Depth 1-2: inline plan sufficient
    ✓ Depth 3: structured plan required
    ✓ Depth 4-5: detailed plan with dependencies and risk?
  → PASS: proceed to EXECUTE
  → FAIL: block. List what's missing.

PHASE 5: EXECUTE
  → Agent executes the plan
  → COMPLIANCE AGENT checks:
    ✓ Plan steps followed?
    ✓ Depth 4-5: each step verified before next?
  → PASS: proceed to MEASURE
  → FAIL: block. List what's missing.

PHASE 6: MEASURE
  → Agent measures outcomes against success criteria
  → COMPLIANCE AGENT checks:
    ✓ Success criteria evaluated?
    ✓ Depth 1-2: lightweight pass/fail
    ✓ Depth 3+: quantified results?
  → PASS: proceed to LEARN
  → FAIL: block. List what's missing.

PHASE 7: LEARN
  → Agent captures learnings
  → COMPLIANCE AGENT checks:
    ✓ What went well?
    ✓ What surprised?
    ✓ Depth 1-2: skip (no formal learning artifact)
    ✓ Depth 3+: documented learnings?
  → PASS: task complete
  → FAIL: block. List what's missing.
```

## Depth-Based Compliance

The compliance agent scales its checks based on the task's assigned Depth (1-5). Not every task needs full compliance — lightweight tasks should move fast.

| Depth | Level | Compliance Mode | What Gets Checked |
|-------|-------|----------------|-------------------|
| 1 | Surface | **Skip** | No compliance checks. Trust the agent. |
| 2 | Considered | **Lightweight** | OBJECTIVE has goal + criteria. EXECUTE produces output. Other phases: implicit. |
| 3 | Thorough | **Standard** | All 7 phases checked. Artifacts required for OBJECTIVE, SHAPE, PLAN, MEASURE. |
| 4 | Rigorous | **Full audit** | All 7 phases checked with depth. Risk assessment in PLAN. Quantified MEASURE. Cross-impact in LEARN. |
| 5 | Exhaustive | **Full audit + review** | Everything in Depth 4, plus independent review of artifacts before EXECUTE proceeds. |

## What It Checks Per Phase

### OBJECTIVE
- [ ] Clear goal statement (not blank, not generic)
- [ ] Success criteria (measurable, specific)
- [ ] Depth assigned (1-5)
- [ ] Depth 4-5: who requested, why now, stakeholder map

### OBSERVE
- [ ] Depth 1-2: skip (context is implicit)
- [ ] Depth 3: relevant context documented
- [ ] Depth 4-5: constraints, dependencies, and existing state mapped

### SHAPE
- [ ] What we're building (clear scope)
- [ ] Edge cases identified
- [ ] Not-in-scope explicitly stated
- [ ] Depth 4-5: cross-department impact, risk assessment

### PLAN
- [ ] Actionable steps listed
- [ ] Depth 1-2: inline plan sufficient
- [ ] Depth 3: structured plan with steps and acceptance criteria
- [ ] Depth 4-5: dependencies, risk mitigation, rollback plan

### EXECUTE
- [ ] Plan steps followed
- [ ] Depth 4-5: each step verified before proceeding to next

### MEASURE
- [ ] Success criteria evaluated against OBJECTIVE
- [ ] Depth 1-2: simple pass/fail
- [ ] Depth 3: quantified results per criterion
- [ ] Depth 4-5: cross-department verification, regression check

### LEARN
- [ ] Depth 1-2: skip (no formal artifact)
- [ ] Depth 3: what went well, what surprised
- [ ] Depth 4-5: feedback for Sutra, per-department learnings, process improvements

## How to Invoke

The compliance agent is spawned as a sub-agent after each lifecycle phase. It reads the artifact, checks against the requirements for the assigned depth, and returns PASS, SKIP, or FAIL.

```
Agent completes OBJECTIVE phase
  → Orchestrator spawns: Compliance Agent
    → Input: phase artifacts, assigned depth (1-5)
    → Output: PASS (proceed) | SKIP (depth too low for checks) | FAIL (list missing items)
  → If PASS/SKIP: next phase
  → If FAIL: fix, re-check
```

## Authority

The compliance agent can BLOCK but cannot FIX. It reports what's wrong. The feature agent fixes it. This separation prevents the compliance agent from becoming a co-author (which would compromise its independence).

## Evolution

The compliance checks evolve based on LEARN phase feedback:
- If a check consistently passes with no value → remove it (reducing friction)
- If a missing check would have caught a real bug → add it
- Depth thresholds calibrate over time based on the Adaptive Protocol Engine (when built)
- Depth assignments themselves improve as the system learns which tasks truly need Depth 4-5 vs Depth 1-2
