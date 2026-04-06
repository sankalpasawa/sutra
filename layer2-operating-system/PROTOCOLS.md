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
| PROTO-013 | Sutra Version Deploy | Federal | SOFT | New Sutra version released |
| PROTO-014 | Sutra Version Check | Federal | SOFT | Client company session starts |
| PROTO-015 | Verify Before Commit | Constitutional | HARD | Any commit to a company repo |
| PROTO-016 | Root Cause on Founder Correction | Constitutional | HARD | Founder points out a miss |

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

### PROTO-013: Sutra Version Deploy
```
federal | [Sutra P9, D22] | SOFT
trigger: New Sutra version released OR company needs OS deploy/update
check:   Company OS matches Sutra source 100%? → done. Any mismatch? → deploy.

Deployment is BINARY. Either the OS is fully deployed or it's not.
There is no "partial deploy" or "Depth 2 deploy." You don't install
60% of an operating system.

THE PROCESS:

  1. SUTRA OS EXISTS (source of truth in sutra/)
  2. CUSTOMIZE for the company (company-specific config)
  3. DEPLOY 100% (every file, every line, every reference)
  4. VERIFY 100% (content matches, not just file exists)

STEP 1: GENERATE EXPECTED STATE

  Read the Sutra source and generate the FULL expected state for
  this company. Not "what changed since last version" — what the
  company SHOULD look like right now if deployed perfectly.

  Expected state includes:
    CLAUDE.md:
      [ ] "Sutra OS Version: v{current}" — exact version string
      [ ] Session start instructions — match current Sutra template
      [ ] Depth assessment block with cost as % of $200 plan
      [ ] Version check protocol (PROTO-014) — reads ../sutra/CURRENT-VERSION.md
      [ ] Input routing section — current format
      [ ] All terminology current ("Depth" not "Level" or "Gear")

    os/engines/:
      [ ] ADAPTIVE-PROTOCOL.md — byte-identical to Sutra source (minus company customization)
      [ ] ESTIMATION-ENGINE.md — byte-identical to Sutra source
      [ ] estimation-log.jsonl — exists (content is company-specific, don't overwrite)

    os/:
      [ ] SUTRA-CONFIG.md — version matches, lifecycle phases match,
          depth range matches, terminology current
      [ ] METRICS.md — exists with correct format
      [ ] OKRs.md — exists with correct format
      [ ] feedback-to-sutra/ — directory exists
      [ ] feedback-from-sutra/ — directory exists

    .claude/:
      [ ] hooks/enforce-boundaries.sh — exists, executable, exit 2 on violation
      [ ] settings.json — hook registered

STEP 2: COMPARE TO ACTUAL STATE

  Read EVERY file listed above in the company.
  Compare CONTENT, not just existence.

  For each file, check:
    - Does it exist? (L1)
    - Does the version string match? (L2)
    - Does the terminology match? ("Depth" not "Level") (L2)
    - Do the lifecycle phases match? (L2)
    - Does the depth range match the company's tier? (L2)
    - Are references to other OS files current? (L2)

  Output a diff report:
    MATCH:    file exists AND content is current
    OUTDATED: file exists BUT content references old version/terminology
    MISSING:  file does not exist
    EXTRA:    file exists in company but not in expected state (leave alone)

STEP 3: DEPLOY (fix every mismatch)

  For each OUTDATED or MISSING item:
    - Update the file to match expected state
    - Preserve company-specific content (architecture, design, TODO)
    - Replace ONLY the Sutra-managed sections

  WHAT IS SUTRA-MANAGED (update freely):
    - Version strings
    - Session start instructions
    - Depth assessment format
    - Version check protocol
    - Input routing format
    - Engine files (ADAPTIVE-PROTOCOL.md, ESTIMATION-ENGINE.md)
    - SUTRA-CONFIG.md lifecycle and depth sections
    - Hook files

  WHAT IS COMPANY-MANAGED (never touch):
    - Architecture sections in CLAUDE.md
    - Design principles
    - Key files / important files sections
    - TODO.md content
    - estimation-log.jsonl entries (company data)
    - feedback-to-sutra/ content
    - Company-specific workflows

  Commit: "deploy: Sutra OS v{ver} — full state sync"

STEP 4: VERIFY (content, not existence)

  Re-run Step 2 after deploy. Every item must be MATCH.
  If any OUTDATED remains, the deploy failed. Fix and re-verify.

  Binary outcome: DEPLOYED (100% match) or NOT DEPLOYED.

  Then confirm in a live session:
    - Start a session in the company directory
    - Does the version check fire?
    - Give a task — does depth assessment appear?
    - If yes: DEPLOYED
    - If no: instructions unclear, rewrite and re-deploy

POST-DEPLOY (ongoing, not part of deploy):

  These happen AFTER deployment, during normal company sessions:

  ADOPTION SCORECARD (after 5 sessions):
    - Depth compliance: what % of tasks show depth blocks?
    - Triage compliance: what % log triage after completion?
    - Estimation compliance: what % have estimate vs actual?
    - Target: > 80% on all. Below 80% = rewrite instructions.

  MECHANICAL ENFORCEMENT (only if adoption < 80% after rewrite):
    - Add hooks that remind or block
    - Last resort — hooks add friction

  GRADUATION (for experimental features):
    - Used correctly in 5+ tasks > ADDITIVE
    - Used in 2+ companies > STABLE
    - Can become required

  DEPRECATION (when retiring old features):
    - 2-version notice minimum
    - Migration path documented
    - Audit: no company depends on it
    - Remove from expected state

REFERENCES:
  Ansible/Puppet — desired state convergence (declare, compare, converge)
  Salesforce — readiness scoring before upgrade
  Stripe — version pinning with explicit upgrade
  Kubernetes — feature graduation
  Accenture — adoption scorecards

TRIGGER: SUTRA-CONFIG.md found with "Level 1-4" after v1.7 deploy.
         File existed (L1 pass) but content was wrong (L2 fail).
         Incremental deploy missed it. Full state sync would catch it.
SOURCE: customer feedback (DayFlow CEO session 2026-04-06)
GRADE: I
times_used: 2
```

### PROTO-014: Sutra Version Check (Client-Side)
```
federal | [Sutra P3, D22] | SOFT
trigger: Client company session starts
check:   Sutra version current? > proceed. Outdated? > notify founder.
reference: Stripe API version headers — client pinned until explicit upgrade.

PROCESS (built into every client CLAUDE.md):

1. On session start, read ../sutra/CURRENT-VERSION.md line 3
2. Compare to "Sutra OS Version" in own CLAUDE.md
3. If versions match > proceed normally
4. If Sutra is newer:

   a. SHOW: "Sutra update available: v{new} (you're on v{current})"
   b. READ changelog. Summarize in 1-2 lines.
   c. CLASSIFY relevance:
      "Affects you: [list]"
      "Does not affect you: [list]"
      "BREAKING changes: [if any, with migration notes]"
   d. ASK (do NOT auto-update):
      "Want to update? [summary of what changes]"
   e. If yes > apply per PROTO-013 classification. For BREAKING,
      show migration notes before applying. Commit and push.
   f. If no > proceed with current version. Do not ask again
      this session. Check again next session.
   g. If 3+ sessions ignore same update > note once:
      "v{new} available for 3 sessions. No action needed."
      Do not escalate further. Inform, never nag.

WHY PULL NOT PUSH (D22):
  Like Stripe: client stays pinned until they choose to move.
  Mid-sprint companies should not be forced to adopt new process.

ENFORCEMENT: SOFT — check runs, founder can ignore. No blocking.

origin: Adaptive Protocol v3 deploy 2026-04-06. Informed by
        Stripe (version pinning), Salesforce (upgrade center).
times_used: 0 (deployed to DayFlow)
```

### PROTO-015: Verify Before Commit
```
constitutional | [Asawa D11, P3] | HARD
trigger: Any commit to a company repo
check:   Tests pass AND typecheck clean? → commit. Either fails? → fix first.

PROCESS:
  Before every git commit in a company repo:
    1. If tests exist: run them (npm test / jest)
    2. If typecheck exists: run it (npx tsc --noEmit)
    3. Both pass → commit
    4. Either fails → fix, then re-run, then commit
    5. NEVER skip because "it's just docs" — verify anyway

  The assumption "this change is safe" is the exact assumption
  that causes regressions. The test suite catches assumptions.

origin: 2026-04-06. Removed Operating Modes from DayFlow SUTRA-CONFIG.md.
        Did not run tests before committing. Founder asked "why didn't you
        run it?" Change was safe (142/142 pass) but verification was skipped.
        The miss was behavioral, not technical.
```

### PROTO-016: Root Cause on Founder Correction
```
constitutional | [Asawa D11, P3] | HARD
trigger: Founder points out something was missed or done wrong
check:   Root cause identified AND systemic fix applied? → continue. Not yet? → stop and fix.

PROCESS:
  When the founder corrects a mistake or points out a miss:

    1. STOP current work immediately
    2. ACKNOWLEDGE the specific miss (not generic "you're right")
    3. ROOT CAUSE: Why did this happen systemically?
       Not "I forgot" — what process gap allowed the forget?
    4. FIX THE INSTANCE: do the thing that was missed (run the test,
       check the file, verify the content)
    5. FIX THE SYSTEM: create or update a protocol/memory/hook so
       this class of miss cannot recur
       - If it's a repeated behavior: save as feedback memory
       - If it's a process gap: add to a protocol
       - If it's critical: add a hook
    6. RESUME work

  The founder should never have to point out the same class of
  miss twice. The first correction creates the prevention.

  NEVER:
    - Say "you're right" and continue without fixing
    - Treat it as a one-time mistake without systemic analysis
    - Fix only the instance without fixing the process
    - Wait until asked to do the root cause analysis

origin: 2026-04-06. Multiple instances during session where founder
        pointed out misses (tests not run, SUTRA-CONFIG.md outdated,
        modes feature still present, feedback not implemented).
        Each required founder to push for the systemic fix.
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
| 006, 009 | process-gate.sh |
| 007 | ship-metric-check.sh (future) |
| 008 | sprint-sequence-check.sh (future) |
| 010 | Session-start file loading |
| 011 | process-gate.sh |
| 012 | Session-start advisory |
| 013 | Manual (CEO of Asawa/Sutra runs after version bump) |
| 014 | Client CLAUDE.md session start instructions |
