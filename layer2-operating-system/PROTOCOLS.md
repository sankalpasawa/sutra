# Sutra — Protocols

Executable rules compiled from Asawa + Sutra principles. Every protocol has: trigger, check, enforcement, origin.

## Protocol Index

| ID | Name | Type | Enf. | Trigger Summary |
|----|------|------|------|-----------------|
| PROTO-001 | Structure Before Creation | Convergent | SOFT | New dir/file at org level |
| PROTO-002 | Wait for Parallel Completion | Constitutional | HARD | Orchestrator writing before agents finish |
| PROTO-003 | Free Tier First | Constitutional | HARD | Selecting a service/provider |
| PROTO-004 | Keys in Env Vars Only | Constitutional | HARD | Configuring API key or secret |
| PROTO-005 | Self-Assess Before Foundational Work | Constitutional | SOFT | Creating/modifying foundational doc |
| PROTO-006 | Process Discipline | Constitutional | HARD | Agent receives task or cannot complete process step |
| PROTO-007 | One Metric Per Feature | Federal | SOFT | Shipping a feature |
| PROTO-008 | Follow the Sprint Sequence | Federal | SOFT | Starting next task after completion |
| PROTO-009 | Narration Is Not Artifact | Constitutional | HARD | Executing a process pipeline |
| PROTO-010 | Version Focus | Constitutional | HARD | File grows unboundedly over time |
| PROTO-011 | Company Independence | Constitutional | HARD | Cross-company synergy or holding co making product decisions |
| PROTO-012 | Ownership Model | Convergent | SOFT | Selling a company or founder operating instead of governing |

Types: **Constitutional** (Asawa-locked, no override) | **Federal** (Sutra, override within bounds) | **Convergent** (both, rule locked, method flexible)

---

## ───── DETAIL: Full definitions ─────

### PROTO-001: Structure Before Creation
```
convergent | [Asawa P3, Sutra P5] | SOFT
trigger: New dir/file at org level
check:   SYSTEM-MAP.md — content has a home? → put it there. No? → document WHY, create, update SYSTEM-MAP.
origin:  Maze onboard 2026-04-04. Agent created shared/ without checking holding/.
```

### PROTO-002: Wait for Parallel Completion
```
constitutional | [Asawa P8] | HARD
trigger: Orchestrator writing synthesis while agents running
check:   ALL agents complete? → proceed. No? → wait. Never substitute own work.
origin:  Maze HOD 2026-04-04. Orchestrator wrote report over 3 running agents — missed 6 bugs.
```

### PROTO-003: Free Tier First
```
constitutional | [Asawa cost, Sutra P5] | HARD
trigger: Selecting service/provider/infra
check:   Free tier meets need? → use it, log upgrade trigger. No? → cheapest, CEO if >$25/mo.
origin:  Founding principle. All companies run at $0/month.
```

### PROTO-004: Keys in Env Vars Only
```
constitutional | [Asawa security] | HARD
trigger: Configuring API key/secret/credential
check:   In env var? → proceed. No? → BLOCK, move to env var.
origin:  Founding principle. No key ever committed to code.
```

### PROTO-005: Self-Assess Before Foundational Work
```
constitutional | [Asawa HUMAN-AI P3] | SOFT
trigger: Creating/modifying foundational doc (DESIGN, ARCHITECTURE, FRAMEWORK…)
check:   .enforcement/research-done marker < 1hr? → proceed. No? → advisory warning.
origin:  HUMAN-AI P3. Foundational work shapes everything downstream.
```

### PROTO-006: Process Discipline
```
constitutional | [Asawa HUMAN-AI P2, P5] | HARD
trigger: Agent receives a task OR cannot complete a required process step
check:   Process exists? → follow it. Cannot follow? → resolve without skipping. Still blocked? → STOP, ask human. Never write "TBD."
override: "skip the process" / "just do it" / "direct mode"
origin:  HUMAN-AI P2+P5. Process exists because someone learned the hard way. Stopping costs minutes; shipping wrong costs days.
```
_Merged from: PROTO-006 (Process Is Default) + PROTO-007 (Escalate Before Violating)_

### PROTO-007: One Metric Per Feature
```
federal | [Sutra P3] | SOFT
trigger: Shipping a feature
check:   Metric defined? → ship. No? → define metric first.
origin:  Sutra model. Every action must produce a measurable signal.
```

### PROTO-008: Follow the Sprint Sequence
```
federal | [Sutra P1, P7] | SOFT
trigger: Agent done with task, picking next
check:   Sprint plan exists? → follow its sequence, not instinct. No plan? → ask CEO.
origin:  Maze 2026-04-04/05. Agent skipped HOD sequence, jumped to deploy over PostHog.
```

### PROTO-009: Narration Is Not Artifact
```
constitutional | [Asawa P1, P8] | HARD
trigger: Executing process pipeline (SUTRA mode, feature lifecycle, HOD)
check:   FILE on disk for each stage? → complete. No? → write artifact FIRST. Only files count.
origin:  Maze 2026-04-04. Zero artifacts on disk for 2 features. 28 FAILs on audit.
```

### PROTO-010: Version Focus
```
constitutional | [Asawa founder, Sutra P5] | HARD
trigger: File grows unboundedly (history, versions, archives)
check:   >50 lines of stale history? → split: current-view + history-archive. No? → revisit later.
naming:  current="{NAME}.md" | history="{NAME}-HISTORY.md"
origin:  Founder 2026-04-06 — "Only focus on current versions."
```

### PROTO-011: Company Independence
```
constitutional | [Asawa governance, Tiny model, CSI model] | HARD
trigger: Proposal to share customers/products between companies OR holding co/OS making product decisions for a client
check:   Cross-company product coordination? → BLOCK. Sutra OS is the only shared infrastructure. Holding co deciding what a company builds? → BLOCK. Redirect to company CEO.
enforcement: Companies never share customers, product roadmaps, or feature development. Cross-company learning flows through Sutra feedback loops only. Asawa provides governance and capital allocation. Sutra provides process and tools. Neither decides product strategy. Company CEOs (human or AI) own product decisions.
origin:  Andrew Wilkinson (Tiny): "Synergies make CEOs resentful." Mark Leonard (CSI): "Centralization destroys value."
```
_Merged from: PROTO-012 (Synergy Avoidance) + PROTO-013 (Decentralized Product Decisions)_

### PROTO-012: Ownership Model
```
convergent | [Asawa governance, CSI/Tiny/PE model] | SOFT
trigger: Discussion of selling/sunsetting a company OR founder spending >50% time operating a single company
check:   Exit discussion for successful company? → BLOCK. Optimize for compounding. Kill-threshold (G14) pivot? → proceed. Founder acting as company CEO instead of holding CEO? → advisory warning.
enforcement: Companies are permanent — never sell a company with users and revenue. Founder role shifts from building to allocating as portfolio grows. Each company needs its own operator (AI agent). Founder sets direction, allocates resources, reviews outcomes.
origin:  CSI never sells. Tiny never sells. Permanent Equity: "Build for durability, not exit." Wilkinson: "You must be the owner, not the CEO of each business."
```
_Merged from: PROTO-014 (Permanent Ownership) + PROTO-015 (Owner Not Operator)_

---

## Protocol Lifecycle

`OBSERVE (2+ occurrences) -> DRAFT (EXPERIMENTAL) -> TEST (2 features) -> REVIEW -> PUBLISH (2+ companies) -> MONITOR -> EVOLVE/RETIRE`

- **Demote if**: 0 fires in 30d, >50% override, >30% false positive
- **Simplicity gate**: Can existing cover it? Fires 1+ per 10 features? Company-level instead? Count >10 = remove one.
- **Target: <= 10 protocols.** Addition requires removal or merger.

## Enforcement Map

| Protocol | Hook |
|----------|------|
| 001 | new-path-detector.sh |
| 002 | agent-completion-check.sh |
| 003 | Onboarding review |
| 004 | Pre-commit grep |
| 005 | self-assessment.sh |
| 006, 009 | process-gate.sh |
| 007 | ship-metric-check.sh (future) |
| 008 | sprint-sequence-check.sh (future) |
| 010 | Session-start file loading |
| 011 | process-gate.sh |
| 012 | Session-start advisory |
