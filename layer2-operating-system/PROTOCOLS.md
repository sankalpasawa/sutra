# Sutra — Protocols

Executable rules compiled from Asawa + Sutra principles. Every protocol has: trigger, check, enforcement, origin.

<!-- GEN:PROTOCOL-INDEX:START -->
## Protocol Index

> WARNING: GENERATED section — source of truth is `sutra/state/system.yaml`.
> Hand-edits below the INDEX table may be overwritten on next reconcile.
> Regenerate: `node sutra/package/bin/gen-protocols-md.mjs`
>
> Prose sections below the INDEX are historical record. RETIRED/ABSORBED
> protocols are marked inline but not deleted — they document what once
> shipped and why the system moved past them.

_Last reconciled from system.yaml: **2026-04-18** · 22 protocols total + 2 hand-added (PROTO-024, PROTO-025) — system.yaml backfill TODO_

| ID | Name | yaml_status | enforcement | mechanism | test | last_updated |
|----|------|-------------|-------------|-----------|------|--------------|
| PROTO-000 | Every Change Must Ship With Implementation | ACTIVE | SOFT | validate.mjs inverse coverage + test runner (current); doct… | — | 2026-04-18 |
| PROTO-004 | Keys in Env Vars Only | ACTIVE | HARD | holding/hooks/dispatcher-pretool.sh Check 5 (PreToolUse exi… | sutra/package/tests/test-d28-routing-gate.sh | 2026-04-18 |
| PROTO-006 | Process Discipline | ACTIVE | SOFT | CLAUDE.md + dispatcher routing check | — | 2026-04-18 |
| PROTO-009 | Narration Is Not Artifact | ACTIVE | SOFT | dispatcher-pretool.sh | — | 2026-04-18 |
| PROTO-013 | Sutra Version Deploy | ACTIVE | SOFT | D27 depth-5 gate (current); compiler upgrades this in Phase… | — | 2026-04-18 |
| PROTO-014 | Sutra Version Check (Client-Side) | ACTIVE | SOFT | CLAUDE.md session-start check + .claude/sutra-version manif… | — | 2026-04-18 |
| PROTO-015 | Verify Before Commit | ACTIVE | SOFT | agent behavior + estimation-enforcement.sh (current); pre-c… | — | 2026-04-18 |
| PROTO-017 | Policy-to-Implementation Coverage | ACTIVE | SOFT | validate.mjs inverse coverage check (current); reconciler/d… | — | 2026-04-18 |
| PROTO-001 | Structure Before Creation | RETIRED | — | — | — | 2026-04-18 |
| PROTO-002 | Wait for Parallel Completion | RETIRED | — | — | — | 2026-04-18 |
| PROTO-003 | Free Tier First | RETIRED | — | — | — | 2026-04-18 |
| PROTO-005 | Self-Assess Before Foundational Work | RETIRED | — | — | — | 2026-04-18 |
| PROTO-007 | One Metric Per Feature | RETIRED | — | — | — | 2026-04-18 |
| PROTO-008 | Follow the Sprint Sequence | RETIRED | — | — | — | 2026-04-18 |
| PROTO-010 | Version Focus | RETIRED | — | — | — | 2026-04-18 |
| PROTO-011 | Company Independence | RETIRED | — | — | — | 2026-04-18 |
| PROTO-012 | Ownership Model | RETIRED | — | — | — | 2026-04-18 |
| PROTO-016 | Root Cause on Founder Correction | RETIRED | — | — | — | 2026-04-18 |
| PROTO-018 | Auto-Propagation on Version Bump | RETIRED | — | — | — | 2026-04-18 |
| PROTO-019 | Codex Directive Enforcement | ACTIVE | HARD | sutra/marketplace/plugin/hooks/codex-directive-{detect,gate}.sh | sutra/marketplace/plugin/tests/unit/test-codex-directive-*.sh + integration/test-codex-directive-e2e.sh | 2026-04-23 |
| PROTO-020 | Plugin Identity Capture | ACTIVE | SOFT | lib/identity.sh | sutra/marketplace/plugin/tests/unit/test-identity… | 2026-04-18 |
| PROTO-021 | BUILD-LAYER Declaration | ACTIVE | HARD-ON-CODE / SOFT-ON-DOCS | holding/hooks/build-layer-check.sh (PreToolUse Edit\|Write) | holding/hooks/tests/test-build-layer-check.sh | 2026-04-18 |
| PROTO-022 | Completion Status Protocol | ACTIVE | SOFT | sutra/marketplace/plugin/hooks/completion-protocol-check.sh (PostToolUse Task) | sutra/marketplace/plugin/tests/unit/test-completion-protocol.sh | 2026-04-24 |
| PROTO-023 | Centralized Config (`sutra-config`) | ACTIVE | FOUNDATION (read-surface) | bin/sutra-config | sutra/marketplace/plugin/tests/unit/test-sutra-config.sh | 2026-04-24 |
| PROTO-024 | Client→Team Feedback Fan-in (V1) | ACTIVE | SOFT | scripts/feedback.sh + lib/privacy-sanitize.sh | sutra/marketplace/plugin/tests/unit/test-feedback.sh | 2026-04-27 |
| PROTO-025 | Structural-Move Authorization (extends PROTO-021) | ACTIVE | HARD-ON-CODE | holding/hooks/structural-move-check.sh | holding/hooks/structural-move-check.test.sh | 2026-04-27 |

**Status legend**: ACTIVE = shipped and enforced per mechanism · RETIRED = removed, see `reason` in system.yaml · ABSORBED = folded into another protocol (see pointer below)

**Enforcement legend**: HARD = blocking hook (exit 2 on violation) · SOFT = advisory / agent-behavior
<!-- GEN:PROTOCOL-INDEX:END -->

---

## ───── DETAIL: Full definitions ─────

### PROTO-000: Every Change Must Ship With Implementation
```
constitutional | [Asawa P0, P9, D11] | HARD
trigger: Any change that affects how companies operate
check:   6-part rule satisfied? → ship. Any part missing? → mark EXPERIMENTAL.

This is the meta-protocol. It governs everything below.
A change without implementation is prose, not process.

APPLIES TO ALL CHANGE TYPES:

  1. New/changed PROTOCOL       → 6-part rule below
  2. New/changed PRINCIPLE      → must flow downstream (verify-recursive-flow.sh)
  3. New/changed DIRECTION      → must encode TRIGGER/CHECK/ENFORCEMENT
  4. ENGINE UPDATE              → must deploy to companies, content verified
  5. LIFECYCLE CHANGE           → must update SUTRA-CONFIG in companies
  6. NEW FOUNDING DOCTRINE      → must cascade Doctrine > Asawa > Sutra > Companies
  7. MANIFEST CHANGE            → must re-verify all companies against new manifest
  8. HOOK CHANGE                → must re-test, re-register, re-deploy

THE 6-PART RULE (for every change type):

  1. DEFINED:      written in the right file
  2. CONNECTED:    linked to every existing file that references or
                   is referenced by this change. Scan the architecture.
                   New feature? What existing processes use it?
                   New principle? What existing protocols embody it?
                   New engine? What existing files should read from it?
  3. IMPLEMENTED:  mechanism exists (hook / instruction / manifest / memory)
  4. TESTED:       evidence the mechanism works
  5. DEPLOYED:     mechanism active in affected companies
  6. OPERATIONALIZED: 6-section ops plan present (measurement, adoption,
                   monitoring, iteration trigger, DRI, decommission). Enforced
                   for L0-L2 artifacts per D30 + OPERATIONALIZATION charter.
                   See sutra/os/charters/OPERATIONALIZATION.md + 
                   holding/OPERATIONALIZATION-STANDARD.md.

  If any part is missing → mark EXPERIMENTAL, schedule implementation.

  STEP 2 (CONNECTED) is the one that gets skipped. Building forward
  is natural. Connecting backward to existing architecture requires
  scanning the full system. Run: grep for related terms across all
  layers. Any file that touches this domain must reference the change.

WHAT SHIFTS ON CHANGE:

  When anything above changes, the manifest (MANIFEST-v{version}.md)
  must be updated. The manifest IS the expected state. If the manifest
  doesn't reflect the change, the change doesn't exist from a
  deployment perspective.

  Deployment is always verified against the manifest. Binary:
  company matches manifest = DEPLOYED. Any mismatch = NOT DEPLOYED.

PROTOCOL STATUS LABELS:

  SHIPPED:       all 4 parts satisfied
  PARTIAL:       words + mechanism exist, test or deploy incomplete
  EXPERIMENTAL:  words exist, mechanism/test/deploy incomplete
  PROSE:         words only, no mechanism at all

origin: 2026-04-06. Session created 7 protocols, most without
        implementation. Founder: "is it actually implemented?"
        Audit: 11 of 17 protocols had gaps. Root cause: no rule
        requiring implementation alongside documentation.
```

### PROTO-001: Structure Before Creation [RETIRED]
_yaml status: retired — absorbed into reconciler invariant I-6 (no orphan files). See `sutra/state/system.yaml`._
```
convergent | [Asawa P3, Sutra P5] | SOFT
trigger: New dir/file at org level
check:   SYSTEM-MAP.md — content has a home? → put it there. No? → document WHY, create, update SYSTEM-MAP.
origin:  Maze onboard 2026-04-04. Agent created shared/ without checking holding/.
```

### PROTO-002: Wait for Parallel Completion [RETIRED]
_yaml status: retired — agent-execution concern, not a system invariant. Handled by TaskCreate/TaskGet in runtime._
```
constitutional | [Asawa P8] | HARD
implements: P8 (holding/PRINCIPLES.md)
trigger: Orchestrator writing synthesis while agents running
check:   ALL agents complete? → proceed. No? → wait. Never substitute own work.
enforcement: agent-completion-check.sh (PostToolUse) + depth-5 hard gate
origin:  Maze HOD 2026-04-04. Orchestrator wrote report over 3 running agents — missed 6 bugs.
         Dharmik SEO audit 2026-04-07. Orchestrator compiled before 4 agents returned — incomplete JS analysis.
```

### PROTO-003: Free Tier First [RETIRED]
_yaml status: retired — business heuristic, not a runtime invariant (codex: "business heuristics should not be in kernel")._
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

### PROTO-005: Self-Assess Before Foundational Work [RETIRED]
_yaml status: retired — subsumed by depth system (D2, D26). Depth 5 already requires self-assessment._
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
override: "skip the process" / "just do it" / "skip depth assessment"
origin:  HUMAN-AI P2+P5. Process exists because someone learned the hard way. Stopping costs minutes; shipping wrong costs days.
```
_Merged from: PROTO-006 (Process Is Default) + PROTO-007 (Escalate Before Violating)_

### PROTO-007: One Metric Per Feature [RETIRED]
_yaml status: retired — product discipline, moves to IDEA-SHAPING.md (Phase 5). Not a runtime invariant._
```
federal | [Sutra P3] | SOFT
trigger: Shipping a feature
check:   Metric defined? → ship. No? → define metric first.
origin:  Sutra model. Every action must produce a measurable signal.
```

### PROTO-008: Follow the Sprint Sequence [RETIRED]
_yaml status: retired — project-management protocol, not OS enforcement. v1 is deploy/verify/upgrade, not PM._
```
federal | [Sutra P1, P7] | SOFT
trigger: Agent done with task, picking next
check:   Sprint plan exists? → follow its sequence, not instinct. No plan? → ask CEO.
origin:  Maze 2026-04-04/05. Agent skipped HOD sequence, jumped to deploy over PostHog.
```

### PROTO-009: Narration Is Not Artifact
```
constitutional | [Asawa P1, P8] | HARD
trigger: Executing process pipeline (Depth 3+, feature lifecycle, HOD)
check:   FILE on disk for each stage? → complete. No? → write artifact FIRST. Only files count.
origin:  Maze 2026-04-04. Zero artifacts on disk for 2 features. 28 FAILs on audit.
```

### PROTO-010: Version Focus [RETIRED]
_yaml status: retired — subsumed by PROTO-013 (Sutra Version Deploy) + PROTO-014 (Client-Side Version Check)._
```
constitutional | [Asawa founder, Sutra P5] | HARD
trigger: File grows unboundedly (history, versions, archives)
check:   >50 lines of stale history? → split: current-view + history-archive. No? → revisit later.
naming:  current="{NAME}.md" | history="{NAME}-HISTORY.md"
origin:  Founder 2026-04-06 — "Only focus on current versions."
```

### PROTO-011: Company Independence [RETIRED]
_yaml status: retired — absorbed by boundary hook (R4 fail-closed) + tier model. Mechanism is live; separate protocol isn't needed._
```
constitutional | [Asawa governance, Tiny model, CSI model] | HARD
trigger: Proposal to share customers/products between companies OR holding co/OS making product decisions for a client
check:   Cross-company product coordination? → BLOCK. Sutra OS is the only shared infrastructure. Holding co deciding what a company builds? → BLOCK. Redirect to company CEO.
enforcement: Companies never share customers, product roadmaps, or feature development. Cross-company learning flows through Sutra feedback loops only. Asawa provides governance and capital allocation. Sutra provides process and tools. Neither decides product strategy. Company CEOs (human or AI) own product decisions.
origin:  Andrew Wilkinson (Tiny): "Synergies make CEOs resentful." Mark Leonard (CSI): "Centralization destroys value."
```
_Merged from: PROTO-012 (Synergy Avoidance) + PROTO-013 (Decentralized Product Decisions)_

### PROTO-012: Ownership Model [RETIRED]
_yaml status: retired — business doctrine, moves to holding/ governance. Not portable Sutra canon._
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
  Use judgment based on the task's depth assessment:

  Depth 1 (doc-only, no code touched):
    Quick grep: does any code reference what you changed?
    If no references → commit. No test run needed.
    If references exist → run affected tests only.

  Depth 2 (1-3 files, known pattern):
    Typecheck: npx tsc --noEmit
    Skip full test suite unless changed files have tests.

  Depth 3+ (cross-file, risky, or unfamiliar):
    Full typecheck + full test suite.
    Both pass → commit. Either fails → fix first.

  The goal is proportional verification, not ritual verification.
  Burning 30 seconds of tokens to confirm a README change is safe
  is overtriage. But NEVER assume — check if code references exist.

origin: 2026-04-06. Removed Operating Modes from DayFlow SUTRA-CONFIG.md.
        Did not run tests before committing. Founder asked "why didn't you
        run it?" Change was safe (142/142 pass) but verification was skipped.
        The miss was behavioral, not technical.
```

### PROTO-016: Root Cause on Founder Correction [RETIRED]
_yaml status: retired — absorbed into D11 (Fix the Process). Single source for that rule._
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
        stale mode references present, feedback not implemented).
        Each required founder to push for the systemic fix.
```

---

## Protocol Lifecycle

`OBSERVE (2+ occurrences) -> DRAFT (EXPERIMENTAL) -> TEST (2 features) -> REVIEW -> PUBLISH (2+ companies) -> MONITOR -> EVOLVE/RETIRE`

- **Demote if**: 0 fires in 30d, >50% override, >30% false positive
- **Simplicity gate**: Can existing cover it? Fires 1+ per 10 features? Company-level instead? Count >10 = remove one.
- **Target: <= 10 protocols.** Addition requires removal or merger.

## Enforcement Map

| Protocol | Mechanism | Where | Status |
|----------|-----------|-------|--------|
| 000 | memory entry | all sessions | ACTIVE |
| 001 | dispatcher-pretool.sh check 4 | Asawa | ACTIVE |
| 002 | agent-completion-check.sh | Asawa (PostToolUse) | ACTIVE |
| 003 | onboarding review | CLIENT-ONBOARDING.md | ACTIVE (manual) |
| 004 | dispatcher check 5 (secret pattern grep) | Asawa + DayFlow | ACTIVE |
| 005 | dispatcher check 6 (foundational doc reminder) | Asawa + DayFlow | ACTIVE |
| 006 | dispatcher check 7 + depth system | Asawa + DayFlow | ACTIVE |
| 007 | MEASURE phase in task lifecycle | all sessions | ACTIVE |
| 008 | depth assessment sequence | all sessions | ACTIVE |
| 009 | dispatcher check 8 (artifact reminder) | Asawa + DayFlow | ACTIVE |
| 010 | CLAUDE.md session start | all companies | ACTIVE |
| 011 | enforce-boundaries.sh | all companies (exit 2) | ACTIVE |
| 012 | advisory in session start | CLAUDE.md | ACTIVE |
| 013 | verify-os-deploy.sh + manual | holding/hooks/ | ACTIVE |
| 014 | CLAUDE.md instruction | all companies | ACTIVE |
| 015 | memory entry | all sessions | ACTIVE |
| 016 | memory entry | all sessions | ACTIVE |
| 017 | policy-coverage-gate.sh (PreToolUse) + verify-policy-coverage.sh (scan) | Sutra + holding/hooks | ACTIVE |
| 018 | upgrade-clients.sh (triggered on CURRENT-VERSION.md bump) | holding/hooks | ACTIVE |

---

## PROTO-017: Policy-to-Implementation Coverage
```
constitutional | [PROTO-000 operationalized] | HARD
trigger: Any edit to a Sutra policy file (PROTOCOLS.md, MANIFEST-*.md,
         CLIENT-ONBOARDING.md, ENFORCEMENT.md, d-engines/*.md,
         templates/SUTRA-CONFIG*.md)
check:   Does the change satisfy PROTO-000's 6-part rule — DEFINED,
         CONNECTED, IMPLEMENTED, TESTED, DEPLOYED?
enforce: Two legs, surfacing + verification.
         (1) policy-coverage-gate.sh fires as PreToolUse on Edit/Write,
             warns loudly when a policy file is being edited.
         (2) verify-policy-coverage.sh generates/refreshes
             POLICY-COVERAGE.md ledger — every written commitment mapped
             to its executable artifact and its deployed clients. Rows
             without both are DRIFT.
origin:  Billu onboarding revealed declared-but-not-installed hooks (RC4)
         and manifest silent on 95% of shipping hooks. The drift class
         keeps recurring because nothing gates policy-without-propagation.

THE CONTRACT:
  Every written Sutra commitment has three rows:
    1. policy    (where it's declared)
    2. enforcer  (the script/hook/gate that executes it)
    3. clients   (where it's installed and active)
  If any row is blank, the commitment does not exist operationally.

EXEMPT: POLICY_EXEMPT=1 bypass + logged reason in POLICY-EXEMPTIONS.md.
        Exemptions are reviewed weekly.
```

## PROTO-018: Auto-Propagation on Version Bump [RETIRED]
_yaml status: retired — Phase 0 D-7. Post-commit trigger disabled 2026-04-15. Phase 2 compiler replaces the mechanism._
```
federal | [closes the recurrence loop] | HARD
trigger: CURRENT-VERSION.md line 3 changes (new Sutra version published).
check:   Every client in the registry verified against the new manifest.
enforce: upgrade-clients.sh walks the client registry, runs
         verify-os-deploy.sh against each, and for any client below
         the new manifest it:
           - copies updated engine files from sutra/layer2-operating-system/d-engines/
           - rewrites client SUTRA-VERSION.md to the new version
           - installs any newly-required hooks per tier
           - registers hooks in .claude/settings.json
         After propagation, re-runs verify and reports per-client score.
origin:  Version drift (Maze/PPR on v1.7 while Sutra ships v1.8) kept
         recurring because PROTO-013 described the upgrade path but no
         mechanism executed it. Propagation is now mechanical, not
         documentary.

THE CONTRACT:
  Version bump in Sutra → clients reorganize to match, automatically.
  No drift window. No manual audit. If a client can't upgrade, the
  script reports why and leaves the old version in place; it does not
  half-upgrade.
```

## PROTO-019: Codex Directive Enforcement [ACTIVE]
_yaml status: active — directive-triggered. Replaces the v1 request/verify design that Codex itself FAILED (12 findings, 2026-04-15 review). Un-absorbed from Phase 3 doctor — directive enforcement is a distinct capability from diff reconciliation. Shipped 2026-04-23 post Codex-converged design (session 019dbad9-871a-7b03-8343-badbb44f087f)._

```
constitutional | [every Sutra-enabled instance] | HARD

trigger: UserPromptSubmit — founder says "use codex to review X", "codex
         should check Y", "run codex", "consult codex", "/codex review",
         or any phrase where an imperative verb + "codex" co-occur in
         the prompt (negation-aware, code-block-stripped).

check:   When a directive is detected, does a codex verdict artifact
         exist in .enforcement/codex-reviews/ whose DIRECTIVE-ID
         matches the pending marker and whose CODEX-VERDICT is PASS
         or ADVISORY?

enforce: Two hooks, both L0 (shipped via Sutra plugin).
  (1) codex-directive-detect.sh (UserPromptSubmit)
        Regex phrase detection with code-block stripping, negation
        suppression (don't|do not|without|shouldn't|can't|won't|no-need).
        On match: writes .claude/codex-directive-pending with
        DIRECTIVE-ID (epoch), TS, and matched-phrase excerpt.
        Single-slot marker — latest directive supersedes earlier
        unresolved ones.
  (2) codex-directive-gate.sh (PreToolUse on Edit|Write|MultiEdit and
        destructive Bash — git commit, git push, git reset --hard, rm -rf)
        If marker present and no matching verdict: exit 2 (BLOCK) with
        instructions to run /codex review. Verdict must echo
        DIRECTIVE-ID: N so the gate can pair it to the current directive
        (prevents old-verdict-clears-new-directive bug).
        If matching verdict is PASS|ADVISORY: clear marker, allow.
        If matching verdict is FAIL|CHANGES-REQUIRED: block, surface
        findings, keep marker.

override: CODEX_DIRECTIVE_ACK=1 CODEX_DIRECTIVE_REASON="<why>" <tool>
         Clears marker + appends audit row to
         .enforcement/codex-reviews/gate-log.jsonl.

kill-switch: CODEX_DIRECTIVE_DISABLED=1 env var, OR
             touch ~/.codex-directive-disabled

verdict contract: codex verdict files MUST contain two lines:
  DIRECTIVE-ID: <matching epoch from marker>
  CODEX-VERDICT: PASS | FAIL | CHANGES-REQUIRED | ADVISORY

origin:  Founder direction 2026-04-15 — "For anything of Asawa, Sutra,
         or any change I am doing right now, ensure that the review is
         done by the Codex as well." Re-scoped 2026-04-23: not blanket
         pre-review of every change, but enforcement of the explicit
         "use codex" directive whenever founder issues it. Design
         converged with Codex consult 2026-04-23 (5-question review,
         CHANGES-REQUIRED → all changes adopted: regex hardening,
         atomic writes, DIRECTIVE-ID pairing, gate-only-on-destructive-Bash).
         Ships via Sutra plugin (L0) — reaches every Sutra-enabled
         instance on next upgrade-clients.sh run.

THE CONTRACT:
  When founder says "use codex to review X", that directive is
  honored — not acknowledged and forgotten. Claude cannot proceed
  past the next Edit/Write/commit without either a matching Codex
  verdict or an explicit logged override.
```

### PROTO-019 v1 (deprecated)
The pre-2026-04-23 design used a two-phase request/verify model driven by
commit-time gating. Codex review of that implementation (2026-04-15) found
12 blocking findings including stale-PENDING state, pathspec injection on
`$SCOPE`, advisory-only behavior masquerading as enforcement, and logic
that created a fresh PENDING marker on every invocation. The old script
remains at `holding/hooks/codex-review-gate.sh` (archived, unregistered
from .claude/settings.json) and `sutra/marketplace/plugin/hooks/codex-review-gate.sh`
(pending removal next plugin minor). v2 replaces the entire mechanism.

## PROTO-020: Plugin Identity Capture [PENDING — design at holding/research/2026-04-22-sutra-identity-capture-v17-design.md]

Reserved. Design-stage only; not enforced until founder sign-off on §18 checkpoints A-G. See research doc for scope.

## PROTO-021: BUILD-LAYER Declaration
_yaml status: active — SOFT on research/docs, HARD on code paths (holding/hooks/**, holding/departments/**, sutra/marketplace/plugin/**, sutra/os/charters/**). Shipped 2026-04-23 post Codex adversarial review (session 019db709-bddc-77f0-8823-9b5e7aad0a96)._

```
constitutional | [every Asawa/Sutra build routes through a layer decision] | HARD-on-code / SOFT-on-docs

trigger: Any Edit or Write to a non-whitelisted path. Whitelist: .claude/,
         .enforcement/, checkpoints, TODO.md, hook-log.jsonl, .lock, memory
         files under ~/.claude/projects/.../memory/, git operations.

check:   Did the author emit a BUILD-LAYER block for the current turn before
         the first enforced-path Edit/Write? Block format (fourth block
         alongside Input Routing + Depth + Estimation):

           BUILD-LAYER: L0 | L1 | L2
           ACTIVATION-SCOPE: fleet | cohort:<name> | single-instance:<name>
           TARGET-PATH: <absolute path>
           PROMOTION:
             SOURCE: founder | sutra-forge | client-feedback
             TARGET-PATH: (if L1) <path in sutra/marketplace/plugin/>
             BY:          (if L1) <YYYY-MM-DD>
             OWNER:       (if L1) <durable role>
             ACCEPTANCE-CRITERIA: (if L1) [checklist]
             STALE-DISPOSITION:   (if L1) auto-promote-PR | demote-to-L2

         Layers:
           L0 PLUGIN    — ships via plugin, reaches every instance
           L1 STAGING   — authoring instance now + promotion deadline to L0
           L2 INSTANCE  — instance-local forever (doctrine, company-specific)

         Default aspiration is L0; picking L1 requires promotion contract;
         picking L2 requires REASON field (one-line specificity claim).

enforce: holding/hooks/build-layer-check.sh fires as PreToolUse on Edit|Write.
         Enforcement bifurcated per founder + Codex decision 2026-04-23:
           (a) HARD on authored code paths — exit 2 blocks the tool call
               when declaration missing. Paths:
                 - holding/hooks/**
                 - holding/departments/**
                 - sutra/marketplace/plugin/**
                 - sutra/os/charters/**
           (b) SOFT on research/docs and elsewhere — stderr advisory,
               never blocks.
         Marker `.claude/build-layer-registered` persists within a turn;
         cleared by holding/hooks/reset-turn-markers.sh on UserPromptSubmit.
         Override: BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>' <tool>.
         Override writes audit row to .enforcement/build-layer-ledger.jsonl
         with event=override.
         Ledger schema at .enforcement/build-layer-ledger.jsonl:
           { ts, session_id, task_slug, layer, scope, target_path,
             promotion: {source, target_path, by, owner,
                         acceptance_criteria, stale_disposition},
             reason, outcome, promoted_ts }
         Session-end review appended by holding/hooks/dispatcher-stop.sh
         reports per-session L0/L1/L2 counts + stale-L1 items past
         promote-by date.

origin:  Founder direction 2026-04-23 — "every block in the ecosystem should
         be built via the Core Sutra Plugin, not around it." Ecosystem
         diagram at holding/designs/sutra-ecosystem-diagram.md observed
         drift: ~14 capabilities in holding/ are L0-candidates by
         mechanism universality but had no named moment to route them
         into the plugin. Absorbed founder amendment "decommission the
         package, everything via Sutra plugin" (package archived 2026-04-23
         in commits deb81ac + ce20a73 + a5b7cbb). Codex adversarial review
         (SHIP-WITH-AMENDMENTS verdict) surfaced: ACTIVATION-SCOPE missing
         axis (adopted), L1 graveyard risk (addressed via OWNER +
         ACCEPTANCE + STALE-DISPOSITION), advisory-only fatigue
         (addressed via HARD-on-code bifurcation), declaration block cost
         (acceptable — compresses via D9 at ≥10 samples + ≥80% accuracy
         per category).

THE CONTRACT:
  Every enforced build declares its layer before the first Edit/Write.
  L0 ships via plugin. L1 carries a promotion contract (owner + deadline
  + acceptance + stale disposition). L2 carries a specificity reason.
  Misfiled L0 candidates in holding/ become visible at session end and
  weekly promotion-debt review.

EXEMPT: BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>' for single-call
        bypass. Research docs (holding/research/**) SOFT-enforced only.
        Test and design-doc sessions may use the override liberally;
        code-producing sessions should not.

RELATES:
  Composes with D28 (per-turn routing/depth enforcement — shares marker
  lifecycle). Composes with D30a (every L0/L1 artifact ships with
  Operationalization section). Honors D29 (plugin is bare "Sutra", no
  Asawa strings in plugin-facing files). Honors D31 (Sutra owns
  authoring authority; PROMOTION.SOURCE=client-feedback is a nomination,
  not a direct commit). Honors D33 (plugin remains the only cross-
  firewall channel). Design doc: holding/research/2026-04-23-build-layer-
  protocol-design.md (§15 Codex review synthesis).
```

## PROTO-022: Completion Status Protocol [ACTIVE]
_yaml status: active — SOFT enforcement (subagent footer scan warns, does not block). Shipped 2026-04-24 from gstack-patterns-review codex consult (session 019dbc14-ace9-7323-a796-693d943200c9) top-2 ROI recommendation._

```
constitutional | [every skill/hook/subagent emits a normalized terminal state] | SOFT

trigger: End-of-output for any Sutra-plugin-produced text (skill output,
         subagent return, hook-emitted banner, commit summary).

check:   Does the output end with exactly one of four normalized
         terminal state lines?

           STATUS: DONE
           STATUS: DONE_WITH_CONCERNS
           STATUS: BLOCKED
           STATUS: NEEDS_CONTEXT

         For BLOCKED or NEEDS_CONTEXT, the STATUS line is followed by an
         escalation block:

           STATUS: BLOCKED
           REASON: <1-2 sentences — why stopped>
           ATTEMPTED: <what was tried>
           RECOMMENDATION: <next step for founder>

enforce: sutra/marketplace/plugin/hooks/completion-protocol-check.sh runs
         as PostToolUse on Task (subagent returns). SOFT enforcement:
         missing STATUS line → warning to stderr + audit row in
         .enforcement/completion-protocol.jsonl, NOT blocking. Override
         with COMPLETION_PROTOCOL_ACK=1 COMPLETION_PROTOCOL_ACK_REASON=...

states:
  DONE                 — all steps completed, evidence attached.
  DONE_WITH_CONCERNS   — shipped, but flag something the consumer should know.
  BLOCKED              — cannot proceed; external dependency or unresolvable
                         conflict. Must include REASON + ATTEMPTED + RECOMMENDATION.
  NEEDS_CONTEXT        — cannot proceed without more info from user. Must
                         include REASON + ATTEMPTED + RECOMMENDATION.

why:     Normalizing terminal states unlocks (a) founder readability
         (scan 10 outputs, find the 2 that didn't finish), (b) Analytics
         Dept "blocked rate per week" metric, (c) hook composition
         (subagent-os-contract, cascade-check can key on outcomes).

origin:  gstack-patterns-review 2026-04-24, codex consult top-2 ROI.
         Founder direction 2026-04-24 "Implement these two things."

kill-switch: SUTRA_COMPLETION_PROTOCOL_ENABLED=false in ~/.sutra/config.env
             OR COMPLETION_PROTOCOL_DISABLED=1 env var.

RELATES:
  Consumes sutra-config (PROTO-023) for enable flag. Extends subagent-
  os-contract hook's footer validation. Future HARD promotion once
  skill-layer adoption surpasses ~80% (audit via .enforcement/
  completion-protocol.jsonl).
```

## PROTO-023: Centralized Config (`sutra-config`) [ACTIVE]
_yaml status: active — FOUNDATION (no enforcement). Read-surface for every other hook + protocol. Shipped 2026-04-24 from gstack-patterns-review top-1 ROI._

```
foundation | [single source of truth for opt-ins, thresholds, kill-switches] | FOUNDATION

trigger: Any hook, skill, or protocol that needs a user-controllable knob.

check:   Does the knob live in a single known place readable by
         `source $HOME/.sutra/config.env`?

enforce: None (read-surface protocol). Hooks SHOULD source the file at
         startup and honor values alongside existing env-var checks
         (config is additive, not exclusive — backward compat preserved).

file:    $HOME/.sutra/config.env
         Format: shell-sourceable KEY=VALUE, comments with #.

keys:    (initial defaults — extend as new knobs arrive)
           Kill switches:
             SUTRA_RTK_ENABLED=true
             SUTRA_CODEX_DIRECTIVE_ENABLED=true
             SUTRA_ESTIMATION_COLLECTOR_ENABLED=true
             SUTRA_COMPLETION_PROTOCOL_ENABLED=true
           Thresholds:
             SUTRA_CODEX_TIMEOUT_MS=600000
             SUTRA_DEPTH_DEFAULT=5
             SUTRA_BUILD_LAYER_DEFAULT=L0
           Observability:
             SUTRA_TELEMETRY=off
           Tier:
             SUTRA_TIER=governance

cli:     sutra/marketplace/plugin/bin/sutra-config
           sutra-config get KEY      → value (empty if unset)
           sutra-config set KEY VAL  → creates file + defaults if missing
           sutra-config list         → full file
           sutra-config init         → idempotent create
           sutra-config path         → full path of config file

conventions:
  - Keys MUST be UPPERCASE_ALNUM_UNDERSCORE starting with a letter.
  - Keys SHOULD be prefixed SUTRA_ to avoid collision with system env.
  - Existing env-var overrides still work — config is additive.
  - Per-instance: each Sutra-enabled user has own config under
    $HOME/.sutra/ (respects D33 client firewall).

why:     gstack-patterns-review surfaced 6 scattered config locations
         today. Single source unlocks opt-ins, machine-parseable state,
         and future telemetry/learnings/timeline integrations.

origin:  gstack-patterns-review 2026-04-24, codex top-1 ROI.
         Founder direction 2026-04-24 "Implement these two things."

RELATES:
  Foundation for PROTO-022 (SUTRA_COMPLETION_PROTOCOL_ENABLED read from
  here). Foundation for PROTO-024 (feedback fan-in kill-switch). Foundation
  for future PROTO-025+ (learnings, timeline, review log). Pairs with D32
  (default-off per instance — config is where defaults become per-instance
  choices).
```

## PROTO-024: Client→Team Feedback Fan-in (V1) [ACTIVE]
_yaml status: active — ships plugin v2.2.0 (2026-04-25). Closes the "clients can't upload feedback to Sutra team" gap opened by the vinitharmalkar incident (2026-04-24). V1 is **collaborator-visible inbox**, not a private team-only channel — V2 adds client-side encryption to close that gap. Reuses existing `sankalpasawa/sutra-data` git rail; no new infra._

```
fan-in | [client writes feedback locally AND pushes the same scrubbed file to Sutra team's private git, same /core:feedback call, same turn] | MANUAL

trigger: User invokes `/core:feedback "<text>"` in any session where the
         Sutra plugin is installed.

check:   (C1) Did local write to `~/.sutra/feedback/manual/<ts>.md`
               succeed? (always attempted first; fanout is best-effort)
         (C2) Did `scrub_text()` (lib/privacy-sanitize.sh) run on the
               content before push?
         (C3) Is fanout enabled — i.e., NOT disabled by `--no-fanout`,
               `SUTRA_FEEDBACK_FANOUT=0`, or `~/.sutra-feedback-fanout-
               disabled` file?
         (C4) Is `~/.sutra/sutra-data-cache/` reachable (clone+auth)?
         (C5) Was ONLY the new + prior-unmarked feedback file(s) pushed
               — NOT telemetry-*.jsonl, NOT auto-capture content?

enforce: Functional, not governance gate. Correctness via:
         - Tests: scrub patterns + push-single-file diff assertion.
         - Scope guard: `git add clients/<install_id>/feedback/<fname>`
           with explicit per-file path, no wildcards.
         - Kill-switches: env / file / flag (any one disables fanout).

flow:    CLIENT SIDE (sync, inline, ~2s end-to-end):
           1. user: /core:feedback "this broke at step 3"
           2. plugin scrubs content (lib/privacy-sanitize.sh — V1
              hardened: GH/OpenAI/AWS/Slack/Stripe tokens, JWT, signed
              URLs, DSNs, webhooks, emails, phone, 40+char entropy
              fallback)
           3. plugin writes scrubbed payload to
              ~/.sutra/feedback/manual/<utc-ts>.md (local 0600)
           4. fanout_to_sutra_team():
              - kill-switch checks
              - resolve install_id (lib/project-id.sh)
              - ensure ~/.sutra/sutra-data-cache/ clone (best-effort)
              - sweep prior-unmarked files (≤7d)
              - per file: cp into clients/<install_id>/feedback/,
                          git add explicit path, git commit, git push,
                          touch <src>.uploaded on success
           5. print "captured at <local-path>; sent to Sutra team
              (N items, scrubbed)"

         FAILURE PATH (network/auth/missing cache):
           - Local file is ALREADY on disk. Never lost.
           - No .uploaded marker = file eligible for retry.
           - Next /core:feedback call sweeps unmarked first.
           - NO Stop hook. NO cron. User-initiated retry only.

         SERVER SIDE (founder-operated; no plugin code):
           - Founder pulls sutra-data on holding machine.
           - Reads clients/*/feedback/*.md.
           - Aggregates into sutra/feedback-from-companies/ at
             founder's cadence. (V1 has no automated holding-side
             pipeline — kept manual per founder direction
             "I will do this".)

scope:   MANUAL feedback content only (what the user typed into
         /core:feedback). Auto-capture signals (override_count /
         correction_rate / abandonment) stay LOCAL — fanout NOT in
         this ship. Per founder scope-lock 2026-04-25:
         "only this part they push simultaneously; the rest of
         the rest they should not touch."

privacy: HONEST V1 disclosure (codex 2026-04-25 verdict absorbed —
         see .enforcement/codex-reviews/2026-04-25-proto-024-feedback-
         fanin-and-reset-hook-fix.md):

         WHAT V1 PROVIDES:
         - Strong content scrub (token detectors + entropy fallback)
         - Decoupled from SUTRA_TELEMETRY=0 (manual feedback works
           even when telemetry is off)
         - manifest.identity write REMOVED from push.sh (closes H2
           PII leak — github_login/github_id/git_user_name no longer
           stamped on new versions)
         - Local capture user-visible + user-deletable immediately

         WHAT V1 DOES NOT PROVIDE (DOCUMENTED, NOT CLOSED):
         - Cross-tenant content readability (H1/H10): scrubbed
           feedback content is visible to any push-credentialed
           collaborator on sutra-data. Other installs that successfully
           push telemetry can also read all feedback. PRIVACY.md
           discloses this.
         - install_id opacity (H3): install_id is deterministic
           (sha256(HOME:version)[:16]) — linkable across repos for
           same machine/version.
         - Hard-delete on remote (H5): git history retains scrubbed
           payload after reap. "User-deletable" applies to local file
           and remote tip; history persists.
         - Identity join source-side (H8): not built in V1;
           server-side is founder-manual.

         V2 PLAN (deferred):
         - Client-side encryption (openssl RSA-4096 + AES-256-CBC
           hybrid, public key shipped in plugin) — closes H1/H10
         - Random 128-bit install_id stored in identity.json — closes H3
         - Random UUID filenames on remote — breaks install↔file link
         - Documented key-rotation policy

mechanism (V1 files):
         - sutra/marketplace/plugin/scripts/feedback.sh
           (fanout_to_sutra_team() function added)
         - sutra/marketplace/plugin/lib/privacy-sanitize.sh
           (scrub_text() strengthened with 12+ token patterns +
            high-entropy fallback)
         - sutra/marketplace/plugin/scripts/push.sh
           (manifest.identity stamping REMOVED on new versions)
         - sutra/marketplace/plugin/PRIVACY.md
           (V1 disclosure: collaborator-visible inbox, V2-encrypts)

origin:  Founder direction 2026-04-25 "fix it in this session,
         converge with codex on best way, stringent privacy, no
         third-party tools". Codex round-1 FAIL on transport (shared
         git readability). Codex round-2 FAIL on V1 wording. Round-3
         (post-honest-wording, post-V1-edits) pending.

         vinitharmalkar incident 2026-04-24 — T4 client tried to
         send feedback, was offered public GitHub issue creation.
         Stop-the-bleed hook v1.14.1 closed bad-pattern; PROTO-024
         V1 closes channel-absent.

RELATES:
  Consumes lib/privacy-sanitize.sh (PROTO-024 H7 strengthened scrub).
  Consumes lib/project-id.sh for install_id resolution. Consumes
  PROTO-023 SUTRA_FEEDBACK_FANOUT kill-switch knob. Replaces the
  --public flag as the RECOMMENDED feedback path (--public remains
  as opt-in extension for users who want world-visible feedback).
  V2 will close H1/H3/H5/H8/H10 deferred from V1.
```

## PROTO-025: Structural-Move Authorization (extends PROTO-021) [ACTIVE]

**Trigger**: 2026-04-06 unauthorized `git mv` of `holding/evolution/` (commit `d8407d9`) bundled into a multi-purpose contraction commit. PROTO-021 BUILD-LAYER fires only on `Edit|Write` (content changes). Bash structural operations (`mv`, `rm`, `git mv`, `git rm`, `find -delete`, `bash -c`, `xargs`) slipped past every governance hook. Surfaced + restored 2026-04-27 in commit `87fb3ca`.

**Scope**: structural Bash operations on PROTO-021 HARD paths.

**HARD paths (single source of truth, shared with PROTO-021):**
- `holding/hooks/**`
- `holding/departments/**`
- `holding/evolution/**` (added 2026-04-27)
- `holding/FOUNDER-DIRECTIONS.md` (added 2026-04-27)
- `sutra/marketplace/plugin/**`
- `sutra/os/charters/**`

**Authorization (any one):**
1. `.claude/build-layer-registered` marker present (same marker as PROTO-021 — emit BUILD-LAYER block once per turn).
2. `BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>' <cmd>` (logged).

**Hook**: `holding/hooks/structural-move-check.sh` (PreToolUse Bash). Promotion to `sutra/marketplace/plugin/hooks/structural-move-check.sh` by 2026-05-27 after 30-day clean operation.

**Ledger**: `.enforcement/build-layer-ledger.jsonl` — events `structural-block` / `structural-override` / `structural-allow-marker`.

**Detection patterns**: `mv`, `rm`, `rmdir`, `git mv`, `git rm`, `find ... -delete`, `find ... -exec rm/mv`, `xargs ... rm/mv`, `bash -c '...'`, `sh -c '...'`, `eval '...'`. Conservative — substring match on HARD path anywhere in the command. False-positive cost = one ack-bypass; false-negative cost = unauthorized governance change.

**Why a separate hook (not extend `build-layer-check.sh`)**: PROTO-021 fires on `Edit|Write` event class; PROTO-025 fires on `Bash` event class. Single-responsibility per hook keeps each focused. They share path list, marker, override env, and ledger — same authorization model, two trigger surfaces.

**Spec / design**:
- Hook: `holding/hooks/structural-move-check.sh`
- Test: `holding/hooks/structural-move-check.test.sh` (7 cases — block / override / marker / soft / non-structural / bash-c-evasion / cp-non-destructive — all pass)
- Design doc: `holding/research/2026-04-27-structural-move-protocol-design.md`

**Decommission criteria**: retire when (a) plugin equivalent ships at `sutra/marketplace/plugin/hooks/structural-move-check.sh` and Asawa-holding loads from plugin path, OR (b) Claude Code gains a native structural-move tool routed through Edit/Write hook chain (rendering Bash mv/rm obsolete for governance purposes).

**RELATES**:
- Extends PROTO-021 (same path list, same authorization model, different trigger surface).
- Reuses `BUILD_LAYER_ACK=1` env (single audit lane).
- Reuses `.enforcement/build-layer-ledger.jsonl` (single ledger).
- Closes the gap that allowed the 2026-04-06 incident.

