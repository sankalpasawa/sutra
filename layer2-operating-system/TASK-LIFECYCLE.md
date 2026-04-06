# Sutra — Task Lifecycle

> One lifecycle. Every task. Every company. Every time.
> Thoroughness scales with the change, not the company.

**Replaces**: The 6-stage Idea Flow (OPERATING-MODEL.md Section 2.1), the 10-stage SDLC (PROCESSES.md), and "The Only Process" (STAGE-1-PRE-LAUNCH.md). They were never different pipelines. They were different thoroughness levels of the same lifecycle.

---

## The Lifecycle

```
OBJECTIVE ──> OBSERVE ──> SHAPE ──> PLAN ──> EXECUTE ──> MEASURE ──> LEARN
    │                                                                  │
    └────────────────────── FEEDBACK LOOP ─────────────────────────────┘
```

Every task enters this flow. Every phase runs. What changes is **depth**.

---

## Phase 1: OBJECTIVE

*What are we trying to achieve?*

| Activity | Purpose |
|----------|---------|
| **Goal definition** | What is the desired outcome? What does success look like? |
| **Scope boundary** | What is in scope and out of scope? |

OBJECTIVE produces one thing: a **clear statement of intent** that anchors every subsequent phase.

At Level 1, OBJECTIVE is implicit in the task itself. At Level 4, it's a written goal with success criteria.

---

## Phase 2: OBSERVE

*What's the situation?*

| Activity | Purpose |
|----------|---------|
| **Research** | What do the best practitioners do here? (D20) |
| **Analysis** | What's the complexity, cost, impact of this change? |
| **Depth scoring** | Based on complexity x cost x impact, assign a thoroughness level (see Scoring below) |

OBSERVE produces one thing: a **thoroughness level** (1-4) that governs the depth of every subsequent phase.

At Level 1, OBSERVE is a 10-second gut check. At Level 4, it's deep research with expert-pattern review.

**Research Gate** (L3+ mandatory):

At L3+, OBSERVE must produce a documented research step before moving to PLAN. The LLM knows industry practices but won't surface them unless required. This gate prevents reinventing known patterns.

| Level | Research Requirement |
|-------|---------------------|
| L1 | None |
| L2 | None |
| L3 | **3-5 bullet "prior art" section**: how do industry/experts approach this type of problem? |
| L4 | **Full prior art scan with references**: named sources, patterns reviewed, approach selected with rationale |

The research artifact lives inline in the task planning output or as an `OBSERVE.research` section in the task log. It does not need to be a separate document.

---

## Phase 3: SHAPE

*What's the right approach?*

| Activity | Purpose |
|----------|---------|
| **Framing** | What's the right approach? What are the constraints? |
| **Option evaluation** | Which approach best fits the objective given what we observed? |

SHAPE translates observation into a concrete approach direction before detailed planning begins.

---

## Phase 4: PLAN

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

At L3+, PLAN must produce a High-Level Design BEFORE the file-level plan. The LLM naturally plans at file level (which is LLD) but misses system-level implications. The HLD catches cross-cutting concerns before code is written.

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

Any L3+ task that involves choosing between alternatives (technology, pattern, architecture) must produce an Architecture Decision Record. In the solo founder + AI model, each session starts fresh -- ADRs are how decisions survive between sessions.

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

## Phase 5: EXECUTE

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

## Phase 6: MEASURE

*Did it work?*

| Activity | Purpose |
|----------|---------|
| **Measure** | Capture actuals: tokens, cost, time, files touched (from git diff, session metadata) |
| **Compare** | Accuracy delta: estimate vs actual, per dimension (D23 recursive feedback) |
| **Principle check** | Did any direction or principle get violated? (D27 regression tests) |

MEASURE feeds two systems:
- **ESTIMATION-ENGINE.md** receives the accuracy data (ESTIMATION-LOG.jsonl)
- **DIRECTION-ENFORCEMENT.md** receives violation reports

At Level 1, MEASURE is "log the result." At Level 4, it's a full retrospective with process updates.

**ADR Archival**: If an ADR was produced in PLAN, MEASURE confirms the decision held (or documents why it changed during EXECUTE) and ensures the ADR is committed to `org/decisions/`.

---

## Phase 7: LEARN

*Reduce overhead for next time.*

LEARN is the learning loop that makes the system lighter over time (D23, D30).

| Trigger | Compression |
|---------|-------------|
| 10+ accurate estimates in a category (>80% accuracy) | Estimation compresses to one-line confidence score |
| Consistent principle compliance (10+ clean tasks) | Principle checks become passive (log-only, no active scan) |
| Repeated pattern recognition | Pre-fill estimates: "tasks like X always cost Y, take Z minutes" |
| 5+ expansions since last contraction | Trigger simplification pass (D30) |

**Post-task triage checks** (captured on every task, feeds A-01, A-02, A-04):

Triage check: Was the depth level correct?
- **CORRECT**: depth matched the actual complexity
- **UNDERTRIAGE**: should have been deeper (missed something)
- **OVERTRIAGE**: was too heavy (wasted effort)

Problem type check: Was the classification correct? (clear/complicated/complex/chaotic)
- Record `problem_type_selected` (at OBSERVE) and `problem_type_correct` (at LEARN)
- Mismatch signals the Cynefin classification needs calibration

LEARN is what makes this lifecycle anti-bureaucratic. Process grows when needed and shrinks when proven unnecessary.

### Task-to-Protocol Conversion (the missing loop)

Every solved task is a candidate protocol. The first time you solve a problem, it's problem-solving (Gear 3-5). The second time, if a protocol exists, it's execution (Gear 1-2). LEARN is where this conversion happens.

**After every task at Gear 3+, LEARN asks:**

```
1. Will this type of task recur?
   NO  --> log and move on
   YES --> proceed to step 2

2. Is the solution generalizable?
   NO  --> too context-specific, log the pattern but don't formalize
   YES --> proceed to step 3

3. Extract the protocol:
   - TRIGGER: what signals this type of task? (e.g., "new SDK integration")
   - PROCESS: what steps worked? (ordered, with inputs/outputs per step)
   - GEAR: what gear should this be next time? (usually current gear - 1 or - 2)
   - VERIFY: how do you know it worked?

4. Store:
   - If it fits an existing protocol: update that protocol with the new pattern
   - If it's new: create a minimal protocol entry
   - Protocol lives in: company's os/protocols/ or Sutra's PROTOCOLS.md
     depending on whether it's company-specific or universal
```

**What a converted protocol looks like:**

```yaml
protocol: sdk-integration
trigger: "integrate a third-party SDK with existing docs"
gear: 2  # was Gear 3 when first solved, now Gear 2
process:
  - read SDK docs and changelog for breaking changes
  - check existing integration patterns in codebase
  - install + configure following docs
  - verify with build + one smoke test
  - log any gotchas for next time
source_task: "Sentry crash reporting integration (2026-04-05)"
times_used: 0
last_refined: 2026-04-05
```

**Protocol maturity:**
- **0 uses**: candidate — created from one task, untested as protocol
- **3 uses**: proven — survived 3 applications, refine based on what varied
- **10 uses**: locked — stable pattern, Gear 1 candidate, auto-apply

**The gear drop:**
When a protocol exists for a task type, the Adaptive Protocol Engine reads it and drops the gear. First time building auth = Gear 5. After auth protocol exists = Gear 2 (follow the protocol). After 10 uses = Gear 1 (the protocol is the task).

This is how the system gets faster over time without getting sloppier. The thoroughness was already done — it's baked into the protocol. You're not skipping the thinking. You're reusing the thinking.

---

## Gears (Thoroughness)

Gear selection is handled by the Adaptive Protocol Engine (`d-engines/ADAPTIVE-PROTOCOL.md` v3). The gear controls decomposition granularity — how finely a task is broken down before the LLM executes each piece. See the engine doc for the full scoring model.

| Gear | Name | When | Example |
|------|------|------|---------|
| **1** | Direct | LLM knows the answer. Zero decomposition. | Fix a typo. Change a button color. |
| **2** | Think then do | One layer of analysis before code. | Add a screen following existing pattern. SDK integration with docs. |
| **3** | Research then plan | Two layers before code. Map territory first. | Content moderation pipeline. Onboarding redesign. |
| **4** | Architect then build | Three layers. System-level thinking first. | Database schema migration. Auth system from scratch. |
| **5** | Full cascade | Every layer activated. Atomic subtask decomposition. | Payment infrastructure. Company data architecture. |

### Phase Depth by Level

| Phase | Level 1 | Level 2 | Level 3 | Level 4 |
|-------|---------|---------|---------|---------|
| **OBJECTIVE** | Implicit in task | 1-line goal | Written goal statement | Goal + success criteria |
| **OBSERVE** | 10-sec gut check | 2-min analysis | Research + analysis | Deep research + expert review |
| **SHAPE** | Implicit | Quick framing | Approach evaluation | Approach + constraints + options |
| **PLAN** | 1-line estimate | Estimation table | Full table + plan | Full table + risk assessment |
| **EXECUTE** | Build + ship | Build + test + ship | Full SDLC stages | Full SDLC + review + approval |
| **MEASURE** | Log result | Measure + compare | Full retro | Full retro + process update |
| **LEARN** | Auto (passive) | Auto (passive) | Review patterns | Review + simplify |

### Artifact Requirements by Phase and Level

This matrix specifies which artifacts each phase MUST produce. Items in **bold** are discipline-specific additions (from artifact chain analysis, 2026-04-06).

| Phase | L1 (Minimal) | L2 (Standard) | L3 (Thorough) | L4 (Critical) |
|-------|-------------|---------------|----------------|----------------|
| **OBJECTIVE** | Implicit in task | 1-line goal | Written goal statement | Goal + success criteria |
| **OBSERVE** | 10-sec gut check | 2-min analysis | **Research gate** (3-5 bullets prior art) + analysis | **Research gate** (full prior art scan) + deep analysis + expert review |
| **SHAPE** | Implicit | Quick framing | Approach evaluation + framing | Approach + constraints + options evaluated |
| **PLAN** | 1-line estimate | Estimation table | Estimation + **HLD** + plan; **ADR if irreversible** | Estimation + **HLD** + risk assessment + **ADR for all decisions** |
| **EXECUTE** | Build + ship | Build + tests; **regression test on bug fixes** | Build + tests + review; **regression test on bug fixes** | Build + tests + review + QA + approval; **regression test on bug fixes** |
| **MEASURE** | Log result | Measure + compare | Log + review; **ADR archive** | Log + review + process update; **ADR archive** |
| **LEARN** | Auto (passive) | Auto (passive) | Learnings + pattern review | Learnings + calibration + simplification |

### L1 Fast-Path Gate

L1 tasks that meet ALL of the following criteria skip directly to EXECUTE then LEARN, bypassing PLAN and MEASURE:

| Criterion | Threshold |
|-----------|-----------|
| Files touched | <= 2 |
| Task type | Simple task or question (not a feature, not a refactor) |
| Complexity score | 1 on all axes |
| Reversibility | Fully reversible |

When the gate passes: `OBJECTIVE → OBSERVE (10-sec score) → EXECUTE → LEARN`. No estimation, no plan, no measurement.

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
OBJECTIVE: Fix the broken link.
OBSERVE: Known issue, one file, no risk. Level 1.
SHAPE: Straightforward edit.
PLAN:  ~2 min, 1 file, $0.05.
EXECUTE: Edit file. Commit. Push.
MEASURE: Logged.
LEARN: n/a
```

### Level 2: Add a new settings screen

```
OBJECTIVE: Add a settings screen to the app.
OBSERVE: Multiple files (screen + navigator + linking), known pattern (done before).
         Complexity 2, Cost 1, Impact 1. Level 2.
SHAPE: Follow existing screen pattern.
PLAN:  Estimation table — ~20 min, 3 files, ~$0.50. Plan: create screen, add route, link nav.
EXECUTE: Build screen. Write basic test. Ship to device.
MEASURE: Actual: 25 min, 3 files, $0.45. Accuracy: 80%. Logged to ESTIMATION-LOG.jsonl.
LEARN: Passive — pattern "new screen" gets this data point.
```

### Level 3: Add natural language quick-add parsing

```
OBJECTIVE: Enable natural language quick-add so users can type free-form text to create activities.
OBSERVE: Cross-system (input layer + parse layer + command layer). New pattern (NLP).
         Complexity 3, Cost 2, Impact 2. Level 3.
SHAPE: Parse→activity flow with library evaluation.
PLAN:  Full estimation table. Plan: research parsing libs, design parse→activity flow,
       build parser, integrate with quick-add, test edge cases.
EXECUTE: Research → Shape brief → Build parser → Test (90%+ accuracy target) → 
         Design QA → Review → Ship.
MEASURE: Full retro. Parse accuracy measured. Estimation accuracy compared.
         Principle check: D20 (did we research best practices?). Clean.
LEARN: "NLP features" category gets calibration data.
```

### Level 4: Migrate auth from Supabase JWT to custom token system

```
OBJECTIVE: Migrate auth from Supabase JWT to custom token system for full control.
OBSERVE: Foundational (every API call uses auth). Security-critical. Irreversible in production.
         Complexity 4, Cost 4, Impact 4. Level 4 + security override.
SHAPE: Custom token approach with feature flag rollout.
PLAN:  Full estimation table with risk assessment. Rollback plan documented.
       Protocol: full SDLC with CISO review. 
       Estimate: 6-8 hrs, 15+ files, ~$15.
EXECUTE: Shape brief → Tech spec → CISO security review → Build with feature flag → 
         Full test suite → Code review → QA verification → Staged rollout → Ship.
MEASURE: Full retrospective. Every dimension measured. Process update if anything failed.
         Principle check: all directions scanned. D27 regression tests run.
LEARN: "Auth migration" pattern documented for future reference.
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
| **ESTIMATION-ENGINE.md** | Feeds the PLAN phase. Generates the estimation table. Receives actuals in MEASURE. |
| **Adaptive Protocol Engine** | IS the scoring/routing logic. Reads complexity/cost/impact, outputs thoroughness level. |
| **DIRECTION-ENFORCEMENT.md** | Fires in MEASURE phase. Scans for principle violations (D27 regression). |
| **Evolution Pulse** | Fires in MEASURE phase. Reports outputs, not activities (D17). |
| **PROTOCOLS.md** (creation lifecycle) | Invoked in PLAN when no existing protocol covers the task (D9/D25). |
| **ESTIMATION-LOG.jsonl** | Accumulates MEASURE data. Feeds LEARN phase pattern recognition. |

---

## Enforcement

| Rule | Behavior |
|------|----------|
| Every task enters the lifecycle | HARD — no task bypasses OBJECTIVE. Even "just do it" gets a 10-second score. |
| Thoroughness set by scoring, not preference | HARD — cannot choose Level 1 for a Level 3 task. Founder can override UP (more thorough) but not DOWN without explicit approval gate (D29). |
| MEASURE captures actuals for Level 2+ | HARD — task is not complete until actuals are logged. |
| MEASURE captures actuals for Level 1 | SOFT — prompted, not enforced. |
| LEARN runs automatically | PASSIVE — no human action required. System tracks patterns. |

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
