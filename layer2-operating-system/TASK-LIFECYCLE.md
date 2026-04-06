# Sutra — Task Lifecycle

> One lifecycle. Every task. Every company. Every time.
> Thoroughness scales with the change, not the company.

**Replaces**: The 6-stage Idea Flow (OPERATING-MODEL.md Section 2.1), the 10-stage SDLC (PROCESSES.md), and "The Only Process" (STAGE-1-PRE-LAUNCH.md). They were never different pipelines. They were different thoroughness levels of the same lifecycle.

---

## The Lifecycle

```
THINK ────> PRE ────> EXECUTE ────> POST ────> COMPRESS
  │                                               │
  └──────────────── FEEDBACK LOOP ────────────────┘
```

Every task enters this flow. Every phase runs. What changes is **depth**.

---

## Phase 1: THINK

*What are we doing and why?*

| Activity | Purpose |
|----------|---------|
| **Research** | What do the best practitioners do here? (D20) |
| **Analysis** | What's the complexity, cost, impact of this change? |
| **Framing** | What's the right approach? What are the constraints? |
| **Depth scoring** | Based on complexity x cost x impact, assign a thoroughness level (see Scoring below) |

THINK produces one thing: a **thoroughness level** (1-4) that governs the depth of every subsequent phase.

At Level 1, THINK is a 10-second gut check. At Level 4, it's deep research with expert-pattern review.

**Research Gate** (L3+ mandatory):

At L3+, THINK must produce a documented research step before moving to PRE. The LLM knows industry practices but won't surface them unless required. This gate prevents reinventing known patterns.

| Level | Research Requirement |
|-------|---------------------|
| L1 | None |
| L2 | None |
| L3 | **3-5 bullet "prior art" section**: how do industry/experts approach this type of problem? |
| L4 | **Full prior art scan with references**: named sources, patterns reviewed, approach selected with rationale |

The research artifact lives inline in the task planning output or as a `THINK.research` section in the task log. It does not need to be a separate document.

---

## Phase 2: PRE

*What's the plan?*

| Activity | Purpose |
|----------|---------|
| **Estimation** | Tokens, cost, time, impact table — fed by ESTIMATION-ENGINE.md (D23) |
| **Protocol selection** | Which existing process applies? If none, generate one on the fly (D9/D25) |
| **Plan** | What are the steps? What's the sequence? |

Thoroughness determines depth:
- **Level 1**: One-line estimate ("~10 min, 1 file, trivial")
- **Level 2**: Estimation table with key dimensions
- **Level 3**: Full estimation table + step-by-step plan + **HLD** (see below)
- **Level 4**: Full table + risk assessment + contingency plan + **HLD** + **ADR** (see below)

**HLD Requirement** (L3+ engineering tasks, mandatory):

At L3+, PRE must produce a High-Level Design BEFORE the file-level plan. The LLM naturally plans at file level (which is LLD) but misses system-level implications. The HLD catches cross-cutting concerns before code is written.

| Level | HLD Requirement |
|-------|----------------|
| L1 | None |
| L2 | None |
| L3 | **Text-based HLD (5-10 lines)**: component interaction map, data flow, system boundaries |
| L4 | **Full architecture diagram**: interaction patterns, data flow, boundaries, risks — reviewed before LLD begins |

HLD vs LLD distinction:
- **HLD** = "these components interact this way, data flows here to here"
- **LLD** = "file X gets function Y with signature Z"

**ADR Protocol for Irreversible Decisions** (L3+ mandatory when alternatives exist):

Any L3+ task that involves choosing between alternatives (technology, pattern, architecture) must produce an Architecture Decision Record. In the solo founder + AI model, each session starts fresh — ADRs are how decisions survive between sessions.

| Level | ADR Requirement |
|-------|----------------|
| L1 | None |
| L2 | None |
| L3 | **ADR required for irreversible decisions** — when choosing between alternatives with hard-to-reverse consequences |
| L4 | **ADR required for all significant decisions** — every technology choice, pattern selection, or architecture decision |

ADR template (one page max):
1. **Context** (2 sentences): what situation requires a decision?
2. **Options** (2-3): what alternatives were considered?
3. **Decision** (1 sentence): what was chosen?
4. **Consequences** (2-3 bullets): what are the tradeoffs accepted?

Storage: `org/decisions/{date}-{slug}.md`

---

## Phase 3: EXECUTE

*Do the work.*

| Activity | Purpose |
|----------|---------|
| **Build** | Write code, create docs, ship features — the actual work |
| **Monitor** | Sensors running during execution (design QA, type checks, principle checks) |
| **Adapt** | If something changes mid-task, re-evaluate — don't blindly follow a stale plan |

**Parallelization Gate** (mandatory check at EXECUTE entry):

Before executing sequentially, apply the **independence test**:
1. Enumerate all pending work items
2. For each pair: do they share state (same files, same config, same output)?
3. If NO shared state → dispatch as parallel agents
4. If shared state → execute sequentially

This is not optional. Sequential execution of independent tasks is a **throughput violation** — it wastes time proportional to the number of tasks that could have been parallel. The agent must justify sequential execution of 2+ independent items.

**Root cause for this rule**: Session 2026-04-05 dispatched 5 agents in parallel (wave 1), then fell into sequential mode for waves 2-3. Post-mortem: no structural check forced parallelization at each decision point. Results arrived → agent processed one-by-one → built next thing → repeated. The fix is this gate: EXECUTE always checks for parallelism first.

**Regression Test Rule** (L2+ bug fixes, mandatory):

Every bug fix at L2+ must include a test that would have caught the bug. Without this, the same class of bug recurs. The LLM fixes bugs well but doesn't think about prevention unless required.

| Level | Regression Test Requirement |
|-------|---------------------------|
| L1 | None |
| L2 | **Regression test required**: a test that reproduces the original bug and verifies the fix |
| L3 | **Regression test required**: same as L2, plus edge case coverage for the bug class |
| L4 | **Regression test required**: same as L3, plus root cause analysis documented in test comments |

This rule applies only to bug fix tasks (not new features). For new features, the standard test requirements by level apply.

The old pipeline stages (SHAPE, BUILD, TEST, SHIP, REVIEW, QA) all live inside EXECUTE. Which ones activate depends on thoroughness:

| Level | Active stages |
|-------|--------------|
| **1: Minimal** | Build + ship |
| **2: Standard** | Build + test + ship |
| **3: Thorough** | Shape + build + test + review + ship |
| **4: Critical** | Shape + build + test + review + QA + approval + ship |

---

## Phase 4: POST

*Did it work?*

| Activity | Purpose |
|----------|---------|
| **Measure** | Capture actuals: tokens, cost, time, files touched (from git diff, session metadata) |
| **Compare** | Accuracy delta: estimate vs actual, per dimension (D23 recursive feedback) |
| **Learn** | What worked, what didn't — feed insights back into estimation data |
| **Principle check** | Did any direction or principle get violated? (D27 regression tests) |

POST feeds two systems:
- **ESTIMATION-ENGINE.md** receives the accuracy data (ESTIMATION-LOG.jsonl)
- **DIRECTION-ENFORCEMENT.md** receives violation reports

At Level 1, POST is "log the result." At Level 4, it's a full retrospective with process updates.

**ADR Archival**: If an ADR was produced in PRE, POST confirms the decision held (or documents why it changed during EXECUTE) and ensures the ADR is committed to `org/decisions/`.

---

## Phase 5: COMPRESS

*Reduce overhead for next time.*

COMPRESS is the learning loop that makes the system lighter over time (D23, D30).

| Trigger | Compression |
|---------|-------------|
| 10+ accurate estimates in a category (>80% accuracy) | Estimation compresses to one-line confidence score |
| Consistent principle compliance (10+ clean tasks) | Principle checks become passive (log-only, no active scan) |
| Repeated pattern recognition | Pre-fill estimates: "tasks like X always cost Y, take Z minutes" |
| 5+ expansions since last contraction | Trigger simplification pass (D30) |

COMPRESS is what makes this lifecycle anti-bureaucratic. Process grows when needed and shrinks when proven unnecessary.

---

## Thoroughness Levels

| Level | Name | Triggered when | Example |
|-------|------|---------------|---------|
| **1** | Minimal | Low on all axes | Fix a typo. Update a button label. Change an env var. |
| **2** | Standard | Medium on any axis | Add a new screen. Refactor a component. Write a new process doc. |
| **3** | Thorough | High on any axis | Cross-system feature. New data model field. Third-party integration. |
| **4** | Critical | High on ALL axes, or security/auth/data | Auth rewrite. Payment integration. Data migration. Schema redesign. |

### Phase Depth by Level

| Phase | Level 1 | Level 2 | Level 3 | Level 4 |
|-------|---------|---------|---------|---------|
| **THINK** | 10-sec gut check | 2-min analysis | Research + analysis + framing | Deep research + expert review |
| **PRE** | 1-line estimate | Estimation table | Full table + plan | Full table + risk assessment |
| **EXECUTE** | Build + ship | Build + test + ship | Full SDLC stages | Full SDLC + review + approval |
| **POST** | Log result | Measure + compare | Full retro + learn | Full retro + process update |
| **COMPRESS** | Auto (passive) | Auto (passive) | Review patterns | Review + simplify |

### Artifact Requirements by Phase and Level

This matrix specifies which artifacts each phase MUST produce. Items in **bold** are discipline-specific additions (from artifact chain analysis, 2026-04-06).

| Phase | L1 (Minimal) | L2 (Standard) | L3 (Thorough) | L4 (Critical) |
|-------|-------------|---------------|----------------|----------------|
| **THINK** | 10-sec gut check | 2-min analysis | **Research gate** (3-5 bullets prior art) + analysis + framing | **Research gate** (full prior art scan) + deep analysis + expert review |
| **PRE** | 1-line estimate | Estimation table | Estimation + **HLD** + plan; **ADR if irreversible** | Estimation + **HLD** + risk assessment + **ADR for all decisions** |
| **EXECUTE** | Build + ship | Build + tests; **regression test on bug fixes** | Build + tests + review; **regression test on bug fixes** | Build + tests + review + QA + approval; **regression test on bug fixes** |
| **POST** | Log result | Measure + compare | Log + review; **ADR archive** | Log + review + process update; **ADR archive** |
| **COMPRESS** | Auto (passive) | Auto (passive) | Learnings + pattern review | Learnings + calibration + simplification |

### L1 Fast-Path Gate

L1 tasks that meet ALL of the following criteria skip directly to EXECUTE then COMPRESS, bypassing PRE and POST:

| Criterion | Threshold |
|-----------|-----------|
| Files touched | <= 2 |
| Task type | Simple task or question (not a feature, not a refactor) |
| Complexity score | 1 on all axes |
| Reversibility | Fully reversible |

When the gate passes: `THINK (10-sec score) → EXECUTE → COMPRESS`. No estimation, no plan, no post-measurement.

When the gate fails (any criterion not met): the task is not L1. Re-score at L2+.

This prevents process overhead on trivially small changes while ensuring nothing that deserves scrutiny slips through.

---

## Scoring

Thoroughness level = **max(complexity, cost, impact)**.

The highest score on any single dimension sets the level.

### Complexity

| Score | Definition |
|-------|-----------|
| 1 | Single file, known pattern |
| 2 | Multiple files, known pattern |
| 3 | Cross-system, new pattern |
| 4 | Foundational — shapes everything downstream |

### Cost

| Score | Definition |
|-------|-----------|
| 1 | < $1 token cost, < 30 min |
| 2 | $1-5, 30 min - 2 hrs |
| 3 | $5-20, 2-8 hrs |
| 4 | > $20, > 8 hrs |

### Impact

| Score | Definition |
|-------|-----------|
| 1 | Fully reversible, no users affected |
| 2 | Reversible with effort, few users |
| 3 | Hard to reverse, many users |
| 4 | Irreversible, or security/data/compliance risk |

### Override: Security/Auth/Data

Any task touching authentication, authorization, encryption, PII, or data schema changes gets **automatic Level 3 floor**, regardless of scores. If all three axes are also high, Level 4.

---

## Examples

### Level 1: Fix broken link in README

```
THINK: Known issue, one file, no risk. Level 1.
PRE:   ~2 min, 1 file, $0.05.
EXECUTE: Edit file. Commit. Push.
POST:  Logged.
COMPRESS: n/a
```

### Level 2: Add a new settings screen

```
THINK: Multiple files (screen + navigator + linking), known pattern (done before).
       Complexity 2, Cost 1, Impact 1. Level 2.
PRE:   Estimation table — ~20 min, 3 files, ~$0.50. Plan: create screen, add route, link nav.
EXECUTE: Build screen. Write basic test. Ship to device.
POST:  Actual: 25 min, 3 files, $0.45. Accuracy: 80%. Logged to ESTIMATION-LOG.jsonl.
COMPRESS: Passive — pattern "new screen" gets this data point.
```

### Level 3: Add natural language quick-add parsing

```
THINK: Cross-system (input layer + parse layer + command layer). New pattern (NLP).
       Complexity 3, Cost 2, Impact 2. Level 3.
PRE:   Full estimation table. Plan: research parsing libs, design parse→activity flow,
       build parser, integrate with quick-add, test edge cases.
EXECUTE: Research → Shape brief → Build parser → Test (90%+ accuracy target) → 
         Design QA → Review → Ship.
POST:  Full retro. Parse accuracy measured. Estimation accuracy compared.
       Principle check: D20 (did we research best practices?). Clean.
COMPRESS: "NLP features" category gets calibration data.
```

### Level 4: Migrate auth from Supabase JWT to custom token system

```
THINK: Foundational (every API call uses auth). Security-critical. Irreversible in production.
       Complexity 4, Cost 4, Impact 4. Level 4 + security override.
PRE:   Full estimation table with risk assessment. Rollback plan documented.
       Protocol: full SDLC with CISO review. 
       Estimate: 6-8 hrs, 15+ files, ~$15.
EXECUTE: Shape brief → Tech spec → CISO security review → Build with feature flag → 
         Full test suite → Code review → QA verification → Staged rollout → Ship.
POST:  Full retrospective. Every dimension measured. Process update if anything failed.
       Principle check: all directions scanned. D27 regression tests run.
COMPRESS: "Auth migration" pattern documented for future reference.
```

---

## How This Maps to the Old Pipelines

| Old Pipeline | What It Was | Lifecycle Equivalent |
|-------------|------------|---------------------|
| "The Only Process" (IDEA → build → ship) | Stage-1 minimal process | Level 1 lifecycle |
| Idea Flow (SENSE → SHAPE → DECIDE → SPECIFY → EXECUTE → LEARN) | Medium-depth feature flow | Level 2-3 lifecycle |
| Full SDLC (IDEA → INTAKE → ... → MONITOR → ITERATE) | Heavy enterprise-style process | Level 3-4 lifecycle |

The insight: these were never different systems. A 0-user company doing an auth rewrite needs Level 4. A 1000-user company fixing a typo needs Level 1. Thoroughness follows the **change**, not the company stage.

---

## Integration Points

| System | Role in Lifecycle |
|--------|------------------|
| **ESTIMATION-ENGINE.md** | Feeds the PRE phase. Generates the estimation table. Receives actuals in POST. |
| **Adaptive Protocol Engine** | IS the scoring/routing logic. Reads complexity/cost/impact, outputs thoroughness level. |
| **DIRECTION-ENFORCEMENT.md** | Fires in POST phase. Scans for principle violations (D27 regression). |
| **Evolution Pulse** | Fires in POST phase. Reports outputs, not activities (D17). |
| **PROTOCOLS.md** (creation lifecycle) | Invoked in PRE when no existing protocol covers the task (D9/D25). |
| **ESTIMATION-LOG.jsonl** | Accumulates POST data. Feeds COMPRESS phase pattern recognition. |

---

## Enforcement

| Rule | Behavior |
|------|----------|
| Every task enters the lifecycle | HARD — no task bypasses THINK. Even "just do it" gets a 10-second score. |
| Thoroughness set by scoring, not preference | HARD — cannot choose Level 1 for a Level 3 task. Founder can override UP (more thorough) but not DOWN without explicit approval gate (D29). |
| POST captures actuals for Level 2+ | HARD — task is not complete until actuals are logged. |
| POST captures actuals for Level 1 | SOFT — prompted, not enforced. |
| COMPRESS runs automatically | PASSIVE — no human action required. System tracks patterns. |

---

## Founder Interaction Shortcuts

| You say | What happens |
|---------|-------------|
| "I have an idea: {X}" | CPO creates INTAKE.md, CEO evaluates, specs are created |
| "standup" | All daily agents run, produce cross-department report |
| "strategy" | CEO runs weekly review, produces strategic priorities |
| "ship {feature}" | CTO ships, CQO runs QA, CDaO sets up monitoring |
| "how's {feature}?" | CPO gives status update across all stages |
| "kill {feature}" | Feature logged as KILLED with reason |
| "what should I work on?" | CEO synthesizes all departments, gives #1 priority |

You never have to manage the process. The process manages itself. You set direction. The org executes.

---

## Quick Reference (30-second cheat sheet)

Read this instead of the full engine specs. Takes 30 seconds.

### Before Every Task

**Step 1: Estimate (2 min)**

| Dimension | Quick Answer |
|-----------|-------------|
| Confidence | High (>80%) / Medium (50-80%) / Low (<50%) |
| Files | Count them |
| Time | Use multiplier: config=0.3x, UI=0.45x, security=0.8x of your gut estimate |

If confidence < 40% or cost > $5 tokens: flag to founder.

**Step 2: Pick Depth**
Score the task 1-5 on: impact, sensitivity, complexity. Take the MAX score:

| Max Score | Depth | Pipeline |
|-----------|-------|----------|
| 1-2 | Minimal | build -> ship -> log |
| 3 | Standard | estimate -> build -> test -> ship -> learn |
| 4 | Full | estimate -> SPEC -> build -> test -> review -> ship -> learn |
| 5 | Critical | estimate -> SPEC -> review -> build -> verify -> ship -> learn -> retro |

**Step 3:** Build at that depth. Follow the pipeline. No more, no less.

**Step 4:** Log actuals to engines/estimation-log.jsonl.

Full specs in engines/ if you need them. You probably don't.

---

## Migration Note

This file defines the unified lifecycle. The old files (OPERATING-MODEL.md Section 2.1, PROCESSES.md, STAGE-1-PRE-LAUNCH.md "The Only Process") are not deleted — that is a separate migration task. When those files are encountered, this lifecycle takes precedence.
