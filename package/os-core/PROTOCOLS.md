# Sutra — Protocols

Executable rules compiled from Asawa + Sutra principles. Every protocol has: trigger, check, enforcement, origin.

## Protocol Index

| ID | Name | Type | Enf. | Status | Mechanism |
|----|------|------|------|--------|-----------|
| PROTO-000 | Every Change Ships With Implementation | Constitutional | HARD | SHIPPED | memory |
| PROTO-001 | Structure Before Creation | Convergent | SOFT | SHIPPED | dispatcher check 4 |
| PROTO-002 | Wait for Parallel Completion | Constitutional | HARD | SHIPPED | agent-completion-check.sh |
| PROTO-003 | Free Tier First | Constitutional | HARD | SHIPPED | onboarding review (advisory) |
| PROTO-004 | Keys in Env Vars Only | Constitutional | HARD | SHIPPED | dispatcher check 5 + DayFlow hook |
| PROTO-005 | Self-Assess Before Foundational Work | Constitutional | SOFT | SHIPPED | dispatcher check 6 + DayFlow hook |
| PROTO-006 | Process Discipline | Constitutional | HARD | SHIPPED | dispatcher check 7 + depth system |
| PROTO-007 | One Metric Per Feature | Federal | SOFT | SHIPPED | CLAUDE.md MEASURE phase |
| PROTO-008 | Follow the Sprint Sequence | Federal | SOFT | SHIPPED | CLAUDE.md depth assessment |
| PROTO-009 | Narration Is Not Artifact | Constitutional | HARD | SHIPPED | dispatcher check 8 + DayFlow hook |
| PROTO-010 | Version Focus | Constitutional | HARD | SHIPPED | session-start file loading |
| PROTO-011 | Company Independence | Constitutional | HARD | SHIPPED | boundary hooks (exit 2) |
| PROTO-012 | Ownership Model | Convergent | SOFT | SHIPPED | advisory (session start) |
| PROTO-013 | Sutra Version Deploy | Federal | SOFT | SHIPPED | verify-os-deploy.sh + manual |
| PROTO-014 | Sutra Version Check | Federal | SOFT | SHIPPED | all companies CLAUDE.md |
| PROTO-015 | Verify Before Commit | Constitutional | HARD | SHIPPED | memory + proportional checks |
| PROTO-016 | Root Cause on Founder Correction | Constitutional | HARD | SHIPPED | memory |
| PROTO-017 | Policy-to-Implementation Coverage | Constitutional | HARD | SHIPPED | policy-coverage-gate.sh + verify-policy-coverage.sh |
| PROTO-018 | Auto-Propagation on Version Bump | Federal | HARD | SHIPPED | upgrade-clients.sh (triggered by CURRENT-VERSION.md change) |
| PROTO-019 | External Peer Review (Codex) on Portfolio Changes | Constitutional | HARD | SHIPPED | codex-review-gate.sh + /codex skill invocation |

Types: **Constitutional** (Asawa-locked, no override) | **Federal** (Sutra, override within bounds) | **Convergent** (both, rule locked, method flexible)

---

## ───── DETAIL: Full definitions ─────

### PROTO-000: Every Change Must Ship With Implementation
```
constitutional | [Asawa P0, P9, D11] | HARD
trigger: Any change that affects how companies operate
check:   4-part rule satisfied? → ship. Any part missing? → mark EXPERIMENTAL.

This is the meta-protocol. It governs everything below.
A change without implementation is prose, not process.

APPLIES TO ALL CHANGE TYPES:

  1. New/changed PROTOCOL       → 4-part rule below
  2. New/changed PRINCIPLE      → must flow downstream (verify-recursive-flow.sh)
  3. New/changed DIRECTION      → must encode TRIGGER/CHECK/ENFORCEMENT
  4. ENGINE UPDATE              → must deploy to companies, content verified
  5. LIFECYCLE CHANGE           → must update SUTRA-CONFIG in companies
  6. NEW FOUNDING DOCTRINE      → must cascade Doctrine > Asawa > Sutra > Companies
  7. MANIFEST CHANGE            → must re-verify all companies against new manifest
  8. HOOK CHANGE                → must re-test, re-register, re-deploy

THE 5-PART RULE (for every change type):

  1. DEFINED:      written in the right file
  2. CONNECTED:    linked to every existing file that references or
                   is referenced by this change. Scan the architecture.
                   New feature? What existing processes use it?
                   New principle? What existing protocols embody it?
                   New engine? What existing files should read from it?
  3. IMPLEMENTED:  mechanism exists (hook / instruction / manifest / memory)
  4. TESTED:       evidence the mechanism works
  5. DEPLOYED:     mechanism active in affected companies

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
implements: P8 (holding/PRINCIPLES.md)
trigger: Orchestrator writing synthesis while agents running
check:   ALL agents complete? → proceed. No? → wait. Never substitute own work.
enforcement: agent-completion-check.sh (PostToolUse) + depth-5 hard gate
origin:  Maze HOD 2026-04-04. Orchestrator wrote report over 3 running agents — missed 6 bugs.
         Dharmik SEO audit 2026-04-07. Orchestrator compiled before 4 agents returned — incomplete JS analysis.
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
override: "skip the process" / "just do it" / "skip depth assessment"
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
trigger: Executing process pipeline (Depth 3+, feature lifecycle, HOD)
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
check:   Does the change satisfy PROTO-000's 5-part rule — DEFINED,
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

## PROTO-018: Auto-Propagation on Version Bump
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

## PROTO-019: External Peer Review on Portfolio Changes
```
constitutional | [cross-company, portfolio-wide] | HARD
trigger: Any change to Asawa holding, Sutra OS, or any company submodule
         (edit to CLAUDE.md, PROTOCOLS.md, MANIFEST-*, SUTRA-CONFIG,
         hooks, engines, or shipped product code) before commit OR
         before land-and-deploy.
check:   Has an external AI peer (Codex) reviewed the diff and reported
         no blocker findings?
enforce: codex-review-gate.sh wraps /codex review and produces a
         review artifact at .enforcement/codex-reviews/{timestamp}.md.
         Gate runs on-demand (pre-commit) and is recorded in commit
         message trailer: "Codex-Reviewed: <verdict>".
         Blocker findings = NO commit until resolved or explicitly
         overridden (CODEX_OVERRIDE=1 with logged reason).
origin:  Founder direction 2026-04-15 — "For anything of Asawa, Sutra,
         or any change I am doing right now, ensure that the review is
         done by the Codex as well. This is applied across Asawa
         Holdings and Companies." Flows from Sutra to every client via
         upgrade-clients.sh + MANIFEST-v1.9.

THE CONTRACT:
  No portfolio change lands without a second AI opinion.
  Claude writes; Codex reviews; founder decides.
  Disagreements surface as findings — resolved by founder, not silently.
```
