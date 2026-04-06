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
| PROTO-006 | Process Is Default | Constitutional | HARD | Agent receives a task |
| PROTO-007 | Escalate Before Violating | Constitutional | HARD | Cannot complete a required process step |
| PROTO-008 | One Metric Per Feature | Federal | SOFT | Shipping a feature |
| PROTO-009 | Follow the Sprint Sequence | Federal | SOFT | Starting next task after completion |
| PROTO-010 | Narration Is Not Artifact | Constitutional | HARD | Executing a process pipeline |
| PROTO-011 | Version Focus | Constitutional | HARD | File grows unboundedly over time |
| PROTO-012 | Synergy Avoidance | Constitutional | HARD | Proposal to share customers/products between companies |
| PROTO-013 | Decentralized Product Decisions | Constitutional | HARD | Holding co or OS making product decision for client |
| PROTO-014 | Permanent Ownership | Convergent | SOFT | Discussion of selling/sunsetting a company |
| PROTO-015 | Owner Not Operator | Federal | SOFT | Founder spending >50% time operating single company |

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

### PROTO-006: Process Is Default
```
constitutional | [Asawa HUMAN-AI P2] | HARD
trigger: Agent receives a task
check:   Process exists? → follow it. No? → judgment + document gap + feedback to Sutra.
override: "skip the process" / "just do it" / "direct mode"
origin:  HUMAN-AI P2. Process exists because someone learned the hard way.
```

### PROTO-007: Escalate Before Violating
```
constitutional | [Asawa HUMAN-AI P5] | HARD
trigger: Cannot complete required process step
check:   Resolve without skipping? → do it. No? → STOP, ask human. Never write "TBD."
origin:  HUMAN-AI P5. Stopping costs minutes. Shipping wrong costs days.
```

### PROTO-008: One Metric Per Feature
```
federal | [Sutra P3] | SOFT
trigger: Shipping a feature
check:   Metric defined? → ship. No? → define metric first.
origin:  Sutra model. Every action must produce a measurable signal.
```

### PROTO-009: Follow the Sprint Sequence
```
federal | [Sutra P1, P7] | SOFT
trigger: Agent done with task, picking next
check:   Sprint plan exists? → follow its sequence, not instinct. No plan? → ask CEO.
origin:  Maze 2026-04-04/05. Agent skipped HOD sequence, jumped to deploy over PostHog.
```

### PROTO-010: Narration Is Not Artifact
```
constitutional | [Asawa P1, P8] | HARD
trigger: Executing process pipeline (SUTRA mode, feature lifecycle, HOD)
check:   FILE on disk for each stage? → complete. No? → write artifact FIRST. Only files count.
origin:  Maze 2026-04-04. Zero artifacts on disk for 2 features. 28 FAILs on audit.
```

### PROTO-011: Version Focus
```
constitutional | [Asawa founder, Sutra P5] | HARD
trigger: File grows unboundedly (history, versions, archives)
check:   >50 lines of stale history? → split: current-view + history-archive. No? → revisit later.
naming:  current="{NAME}.md" | history="{NAME}-HISTORY.md"
origin:  Founder 2026-04-06 — "Only focus on current versions."
```

### PROTO-012: Synergy Avoidance
```
constitutional | [Asawa governance, Tiny model] | HARD
trigger: Any proposal to share customers, force product collaboration, or merge features between portfolio companies
check:   Are companies being asked to coordinate at the product level? → BLOCK. Sutra OS is the only shared infrastructure.
enforcement: Companies never share customers, product roadmaps, or feature development. Cross-company learning flows through Sutra feedback loops, not direct collaboration.
origin:  Andrew Wilkinson (Tiny): "Synergies make CEOs resentful. Each company is independent."
```

### PROTO-013: Decentralized Product Decisions
```
constitutional | [Asawa governance, CSI model] | HARD
trigger: Asawa or Sutra making a product decision for a client company
check:   Is the holding company or OS deciding WHAT a company should build? → BLOCK. Redirect to company CEO.
enforcement: Asawa provides governance and capital allocation. Sutra provides process and tools. Neither decides product strategy for client companies. Company CEOs (human or AI) make product decisions.
origin:  Mark Leonard (CSI): "Centralization destroys value. Each business keeps its own P&L, culture, and domain expertise."
```

### PROTO-014: Permanent Ownership
```
convergent | [Asawa governance, CSI/Tiny/PE model] | SOFT
trigger: Any discussion of selling, sunsetting, or abandoning a company
check:   Is this a kill-threshold trigger (G14) or an exit discussion? → If G14 pivot, proceed. If exit of successful company, BLOCK.
enforcement: Companies are built to be permanent. Kill-threshold (G14) is about pivoting failed bets, not exiting successful ones. If a company has users and revenue, never sell. Optimize for compounding.
origin:  CSI never sells. Tiny never sells. Permanent Equity: "Build for durability, not exit."
```

### PROTO-015: Owner Not Operator
```
federal | [Asawa governance, Tiny model] | SOFT
trigger: Founder spending >50% of session time operating a single company instead of governing the portfolio
check:   Is the founder acting as company CEO rather than holding company CEO? → Advisory warning.
enforcement: As portfolio grows, founder role shifts from building to allocating. Each company needs its own operator (AI agent configured for that company). Founder sets direction, allocates resources, reviews outcomes.
origin:  Andrew Wilkinson (Tiny): "You must be the owner, not the CEO of each business."
```

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
| 006, 007, 010 | process-gate.sh |
| 008 | ship-metric-check.sh (future) |
| 009 | sprint-sequence-check.sh (future) |
| 011 | Session-start file loading |
| 012, 013 | process-gate.sh |
| 014 | Session-start advisory |
| 015 | Session-start advisory |
