# Sutra — Protocols

## What This Is

The convergence layer. Principles (abstract beliefs) from Asawa and Sutra are compiled here into **executable protocols** — concrete rules that agents and humans follow.

Every protocol has: a trigger, a check, an action, an enforcement level, and an origin story.

## Authority

Protocols are owned by **Sutra** (the operating system). But some are locked by **Asawa** (the holding company) — meaning Sutra can define HOW to comply but cannot weaken the rule.

## Protocol Types

| Type | Source | Company Can Override? |
|------|--------|----------------------|
| **Constitutional** | Asawa principle → Sutra protocol | No. Rule is locked. Method may be flexible. |
| **Federal** | Sutra principle → Sutra protocol | Yes, within bounds. |
| **Convergent** | Both Asawa + Sutra → single protocol | Rule locked, method flexible. |

---

## The Protocols

### PROTO-001: Structure Before Creation

```yaml
id: PROTO-001
name: Structure Before Creation
type: convergent
source:
  - Asawa P3 (self-assessment before foundational work)
  - Sutra P5 (start simple, earn complexity)
trigger: Agent is about to create a new directory or file at the organizational level (asawa-inc/)
check: Read SYSTEM-MAP.md. Does this content already have a home in an existing directory?
if_yes: Put it there. Don't create a new structure.
if_no: Document WHY existing structures don't fit. Then create. Update SYSTEM-MAP.md immediately.
enforcement: SOFT (hook warns on new paths under asawa-inc/)
origin: "Maze onboarding 2026-04-04. Agent created asawa-inc/shared/ without checking that holding/ already served the same purpose. Violated P3 and P5. shared/ was later merged back into holding/."
```

---

### PROTO-002: Wait for Parallel Completion

```yaml
id: PROTO-002
name: Wait for Parallel Completion
type: constitutional
source:
  - Asawa P8 (never bypass a running process)
trigger: Orchestrator has delegated work to parallel agents and is about to write synthesis/output
check: Are ALL delegated agents complete?
if_yes: Read ALL agent outputs. Reference them in synthesis. Proceed.
if_no: Wait. Do not proceed. Do not substitute own work. Do not write partial synthesis.
enforcement: HARD (block Write if pending agents exist)
origin: "Maze HOD meeting 2026-04-04. Three department agents were running in parallel. Orchestrator wrote the full report itself while agents were still working, rendering their analysis pointless. Agents found 6 bugs and 2 health downgrades the orchestrator missed."
```

---

### PROTO-003: Free Tier First

```yaml
id: PROTO-003
name: Free Tier First
type: constitutional
source:
  - Asawa cost policy (don't waste money)
  - Sutra P5 (start simple, earn complexity)
trigger: Agent is selecting a service, provider, or infrastructure component
check: Does a free tier exist that meets the current requirement?
if_yes: Use the free tier. Document the paid upgrade trigger in METRICS.md.
if_no: Use the cheapest option. Document the cost in METRICS.md. Get CEO approval if >$25/month.
enforcement: HARD (review at onboarding; METRICS.md must show $0 or justified costs)
origin: "Asawa founding principle. All three companies (DayFlow, PPR, Maze) run on $0/month."
```

---

### PROTO-004: Keys in Env Vars Only

```yaml
id: PROTO-004
name: Keys in Env Vars Only
type: constitutional
source:
  - Asawa security policy
trigger: Agent is configuring an API key, secret, or credential
check: Is the key stored in an environment variable (not in code, not in client bundle)?
if_yes: Proceed.
if_no: BLOCK. Move key to env var. Use platform-specific mechanism (Vercel env, Supabase dashboard).
enforcement: HARD (grep for hardcoded keys in pre-commit)
origin: "Asawa founding principle. No key has ever been committed to code."
```

---

### PROTO-005: Self-Assess Before Foundational Work

```yaml
id: PROTO-005
name: Self-Assess Before Foundational Work
type: constitutional
source:
  - Asawa HUMAN-AI Principle 3
trigger: Agent is about to create or modify a foundational document (DESIGN, ARCHITECTURE, FRAMEWORK, PROCESS, INTERACTION, ENFORCEMENT, CHARTER, PRINCIPLES, PROTOCOLS)
check: Has the agent researched best practices? Does a .enforcement/research-done marker exist (< 1 hour old)?
if_yes: Proceed.
if_no: Display advisory. Agent can proceed but the warning is in context.
enforcement: SOFT (self-assessment.sh warns, doesn't block)
origin: "Asawa HUMAN-AI-INTERACTION.md Principle 3. Foundational work shapes everything downstream."
```

---

### PROTO-006: Process Is Default

```yaml
id: PROTO-006
name: Process Is Default
type: constitutional
source:
  - Asawa HUMAN-AI Principle 2
trigger: Agent receives a task from the human
check: Does a defined process exist for this type of work? (Feature lifecycle, incident response, onboarding, etc.)
if_yes: Follow the process. "Fix this bug" means "follow the debugging process to fix this bug."
if_no: Use judgment. Document the gap. Send feedback to Sutra so the process can be created.
override: Human says "skip the process," "just do it," "bypass Sutra," "direct mode," "no process needed"
enforcement: HARD (process-gate.sh blocks code edits without SHAPE.md for Standard+ tier changes)
origin: "Asawa HUMAN-AI-INTERACTION.md Principle 2. Process exists because someone learned something the hard way."
```

---

### PROTO-007: Escalate Before Violating

```yaml
id: PROTO-007
name: Escalate Before Violating
type: constitutional
source:
  - Asawa HUMAN-AI Principle 5
trigger: Agent cannot complete a required process step (missing info, conflicting requirements, blocker)
check: Can the agent resolve the blocker without skipping the step?
if_yes: Resolve it, then continue.
if_no: STOP. Ask the human. Do not skip the step. Do not write "TBD" and move on.
enforcement: HARD (process-gate.sh blocks progress without required artifacts)
origin: "Asawa HUMAN-AI-INTERACTION.md Principle 5. Stopping costs minutes. Shipping wrong costs days."
```

---

### PROTO-008: One Metric Per Feature

```yaml
id: PROTO-008
name: One Metric Per Feature
type: federal
source:
  - Sutra P3 (feedback loops determine health)
trigger: Agent is shipping a feature
check: Is there at least one measurable metric defined for this feature? (In METRICS.md, TODO.md, or the feature spec)
if_yes: Proceed with ship.
if_no: Define the metric before shipping. "What does success look like for this feature?"
enforcement: SOFT (advisory at ship time)
origin: "Sutra operating model. Every action must produce a measurable signal."
```

---

### PROTO-009: Follow the Sprint Sequence

```yaml
id: PROTO-009
name: Follow the Sprint Sequence
type: federal
source:
  - Sutra P1 (make work visible — the sprint plan IS the visible work)
  - Sutra P7 (decisions need an owner — the plan owner decided the sequence)
trigger: Agent completes a task and is about to start the next one
check: Does an active sprint plan exist? (HOD meeting, TODO.md sprint, or any sequenced plan). If yes, what is the NEXT item in the designed sequence?
if_yes: Start that item. Not what feels right. Not what's fastest. What the plan says.
if_no: Ask the CEO what's next. Do not self-select.
enforcement: SOFT (post-commit reminder: "Sprint says next: {item}")
origin: "Maze session 2026-04-04/05. Agent completed INIT-0 blockers and jumped to deploy instead of following the HOD sprint sequence. Day 2-3 (PostHog) was skipped. Agent's momentum overrode the designed sequence."
```

---

### PROTO-010: Narration Is Not Artifact

```yaml
id: PROTO-010
name: Narration Is Not Artifact
type: constitutional
source:
  - Asawa P1 (make work visible — if not written to a file, it doesn't exist)
  - Asawa P8 (never bypass a running process — narrating a step is not completing it)
trigger: Agent is executing a process pipeline (SUTRA mode, feature lifecycle, HOD meeting)
check: For each process stage completed, does a FILE exist on disk? (Not a message in chat. Not a line in a commit message. A file.)
if_yes: Stage is complete. Proceed to next.
if_no: Stage is NOT complete. Write the artifact FIRST. Then proceed.
enforcement: HARD (process-gate should check for stage artifacts before allowing code edits)
origin: "Maze session 2026-04-04. Two features shipped with SUTRA mode declared in commit messages but zero artifacts on disk. Independent auditors scored 28 FAILs. Founder: 'It was theater.' The pipeline was described verbally in chat but never executed as files. Chat is ephemeral — only files count."
```

---

## How Protocols Evolve

1. **Bottom-up**: A company discovers a gap (like the shared/ incident) → logs it → Sutra evaluates → if valid, creates a new protocol
2. **Top-down**: Sutra identifies a pattern across companies → creates a protocol proactively
3. **Incident-driven**: A violation happens → root cause analysis → new protocol prevents recurrence

Every protocol records its origin. This is the institutional memory of why rules exist.

## How Protocols Map to Enforcement

| Protocol | Hook | Gate Type |
|----------|------|-----------|
| PROTO-001 | (future: new-path-detector.sh) | SOFT |
| PROTO-002 | (future: agent-completion-check.sh) | HARD |
| PROTO-003 | Reviewed at onboarding | HARD (process) |
| PROTO-004 | Pre-commit grep | HARD |
| PROTO-005 | self-assessment.sh | SOFT |
| PROTO-006 | process-gate.sh | HARD |
| PROTO-007 | process-gate.sh | HARD |
| PROTO-008 | (future: ship-metric-check.sh) | SOFT |
| PROTO-009 | (future: sprint-sequence-check.sh) | SOFT |
| PROTO-010 | process-gate.sh (extend to check artifacts) | HARD |
