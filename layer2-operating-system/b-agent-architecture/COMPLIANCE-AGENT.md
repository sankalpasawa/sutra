# Sutra Compliance Agent

## What This Is

A real-time auditor that runs ALONGSIDE feature execution, not after. It checks that every process stage was followed to the right depth before the next stage begins.

## Why It Exists

Previous approach: build first, audit later. Result: 28 FAILs discovered post-hoc. The auditor had no power to prevent violations — only to report them.

New approach: the compliance agent runs as a checkpoint between stages. It has the authority to BLOCK the next stage if the current stage's artifacts are missing or insufficient.

## How It Works

```
FEATURE STAGE 1: INTAKE
  → Agent writes INTAKE.md
  → COMPLIANCE AGENT checks:
    ✓ File exists?
    ✓ Has problem statement?
    ✓ Has success criteria?
    ✓ Has "who requested" and "why now"?
  → PASS: proceed to SHAPE
  → FAIL: block. List what's missing.

FEATURE STAGE 2: SHAPE
  → Agent writes SHAPE.md
  → COMPLIANCE AGENT checks:
    ✓ File exists?
    ✓ Has scope definition?
    ✓ Has edge cases?
    ✓ Has "not in scope"?
    ✓ Depth matches problem complexity?
  → PASS: proceed to SPEC
  → FAIL: block. List what's missing.

... (same pattern for each stage)
```

## Depth Matching

The compliance agent doesn't just check "does the artifact exist?" — it checks "is the artifact at the RIGHT DEPTH for this problem?"

| Problem Complexity | INTAKE Depth | SHAPE Depth | SPEC Depth |
|-------------------|-------------|------------|-----------|
| Trivial (1 file, 1 dept) | 3-5 lines | 5-10 lines | File list only |
| Standard (2-5 files, 1-2 depts) | Full template | Full template | Files + acceptance criteria |
| Significant (5+ files, 3+ depts) | Full template + risk assessment | Full template + cross-dept impact | Per-department specs |
| Horizontal (all depts) | Full template + dept routing map | Per-department SHAPE sections | Per-department specs + integration points |

## What It Checks Per Stage

### INTAKE.md
- [ ] Problem statement (not blank, not generic)
- [ ] Who requested (department or person)
- [ ] Why now (what triggered this)
- [ ] Success criteria (measurable, specific)
- [ ] For horizontal features: department routing map

### SHAPE.md
- [ ] What we're building (clear scope)
- [ ] Edge cases identified
- [ ] Not-in-scope explicitly stated
- [ ] For horizontal: per-department impact section
- [ ] For significant+: risk assessment

### SPEC.md
- [ ] Files to modify/create listed
- [ ] Acceptance criteria per file
- [ ] For horizontal: per-department deliverables
- [ ] For significant+: integration points between departments

### VERIFY.md
- [ ] Type-check result
- [ ] Each acceptance criterion verified
- [ ] For horizontal: cross-department verification

### LEARN.md
- [ ] What went well
- [ ] What surprised
- [ ] Feedback for Sutra
- [ ] For horizontal: per-department learnings

## How to Invoke

The compliance agent is spawned as a sub-agent after each stage. It reads the artifact, checks against the requirements, and returns PASS or FAIL with specifics.

```
Agent writes INTAKE.md
  → Orchestrator spawns: Compliance Agent
    → Input: path to INTAKE.md, problem complexity tier
    → Output: PASS (proceed) or FAIL (list missing items)
  → If PASS: next stage
  → If FAIL: fix, re-check
```

## Authority

The compliance agent can BLOCK but cannot FIX. It reports what's wrong. The feature agent fixes it. This separation prevents the compliance agent from becoming a co-author (which would compromise its independence).

## Evolution

The compliance checks evolve based on LEARN.md feedback:
- If a check consistently passes with no value → remove it (reducing friction)
- If a missing check would have caught a real bug → add it
- Depth thresholds calibrate over time based on the Adaptive Protocol Engine (when built)
