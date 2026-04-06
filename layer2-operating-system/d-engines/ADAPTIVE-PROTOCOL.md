# Sutra — Adaptive Protocol Engine v3

ENFORCEMENT: HARD for Tier 2+. The engine MUST run before every task. Founder can override the selected depth (up or down) but must acknowledge.

---

## Purpose

> **Governing Principle**: The depth of process must match the task, not the company size. A button change in a 10,000-user app is still Depth 1 if it affects one component.

The Adaptive Protocol Engine selects the depth for every task. The depth controls **task decomposition granularity** — how finely a task is broken down before the LLM executes each piece.

### The Core Trade-off: Speed vs Precision

Speed and precision cannot be simultaneously maximized. The more precisely you decompose a task (higher depth), the slower you move. The faster you move (lower depth), the less precise your output. The total cognitive budget per unit of time is roughly constant.

The engine's job: **given this task, where on the speed-precision curve should you sit?**

```
Speed <===============================> Precision
  1        2        3        4        5
 direct   think    research  architect  full
          then do  then do   then do    cascade
```

That number IS the depth. Everything else — gates, parameters, scoring — is internal machinery to arrive at that single number.

---

## The Five Depths

Each depth level adds one layer of thinking before code. The process is always the same — LLM does a task. What changes is how fine-grained you decompose before handing it to the LLM.

### Depth 1: Direct

**LLM --> code --> done.**

Zero intermediate artifacts. The answer is obvious. No decomposition needed.

**Example:** "Change this button color." "Fix this typo." "Update this copy."

**PRD at Depth 1:** "Write a PRD for this feature" — LLM writes the whole PRD in one shot.

**Code at Depth 1:** "Add a loading spinner to this component" — LLM writes the code directly.

**What gets logged:** Task name, time spent, files changed. One line in LEARN.md if anything surprised you.

**Time budget:** Minutes.

### Depth 2: Think Then Do

**Estimate --> code --> verify.**

One layer of analysis. Scope the work, sanity-check the approach, then execute. Light estimation catches scope creep before you start.

**Example:** "Add a new card component following the existing pattern." "Integrate this SDK — docs exist, follow them."

**PRD at Depth 2:** Outline the sections first, then write the PRD. Quick review of the outline before committing.

**Code at Depth 2:** Estimate files affected, check for existing patterns, then build. Verify with a build/test.

**What gets logged:** Estimation vs actual. LEARN.md entry with depth evaluation.

**Time budget:** Hours.

### Depth 3: Research Then Plan Then Do

**Research --> plan --> code --> test --> review.**

Two layers before code. Map the territory first. Understand what exists, what's been tried, what the options are. Then plan, then execute.

**Example:** "Build content moderation. What should we moderate?" "Redesign onboarding — will users complete it?"

**PRD at Depth 3:** Research the problem space, identify comparable products, outline sections, write each section with evidence, review the whole document.

**Code at Depth 3:** Research approaches, write a spec/plan, implement against the spec, test, review before shipping.

**What gets logged:** Research findings. Plan document. Review notes. Estimation accuracy. Full metrics.

**Time budget:** Days.

### Depth 4: Architect Then Research Then Plan Then Do

**HLD --> research --> LLD --> code --> test --> staged verify.**

Three layers. System-level thinking before touching code. High-level design first, then deep research into the details, then low-level design, then implementation with staged verification.

**Example:** "Migrate the database schema across all services." "Build the auth system from scratch."

**PRD at Depth 4:** Stakeholder analysis, market research, competitive analysis, problem decomposition, section-by-section writing with sub-sections individually crafted, cross-reference review, consistency check.

**Code at Depth 4:** HLD defining architecture, research into each component, LLD per component, implementation per LLD, tests per component, staged rollout with verification at each stage.

**What gets logged:** Everything from Depth 3, plus: architecture documents, rollout plan, verification results.

**Time budget:** Days to weeks.

### Depth 5: Full Cascade

**Domain experts --> market research --> architecture (HLD) --> detailed design (LLD) --> implementation --> multi-stage verification --> retrospective.**

Maximum depth. Every layer of thinking activated. Each sub-area gets its own decomposition. The task is broken into pieces so small that each one gets directed, focused intelligence from the LLM.

**Example:** "Build the payment infrastructure." "Design the company's data architecture." "Create a new product vertical."

**PRD at Depth 5:** Domain expert research, market landscape analysis, user research synthesis, competitive feature matrix, problem decomposition into sub-problems, each sub-problem gets its own mini-PRD, cross-references validated, success metrics defined per section, acceptance criteria per sub-section.

**Code at Depth 5:** Full SDLC. Expert consultation on approach, HLD with architecture decisions documented, LLD per module, implementation broken into atomic subtasks each with clear inputs/outputs, tests at unit/integration/e2e levels, staged rollout per platform, post-deploy verification, retrospective feeding back into the engine.

**What gets logged:** All artifacts preserved. Full retrospective document. Triage evaluation.

**Time budget:** Weeks.

---

## The Decomposition Principle

The depth doesn't change what gets built. It changes how finely you think before building.

```
Depth 1: "Write a PRD for this feature"
         --> LLM writes the whole PRD

Depth 5: "Write the user problem statement"
         "Write the success metrics"
         "Write the technical constraints"  
         "Write the edge cases for constraint #2"
         "Write the acceptance criteria for edge case #3"
         --> LLM writes each piece with full focus
```

Same output. Different precision. At Depth 5, you're not trusting the LLM to hold the whole problem in its head — you're decomposing it into pieces small enough that each one gets directed, focused intelligence.

**Selective depth (future evolution):** A task can run at Depth 3 overall but Depth 5 on the sensitive sub-area. The auth logic gets Depth 5 decomposition while the UI wrapper stays Depth 1. For now, the depth applies uniformly per task. Variable depth per sub-area is the next evolution.

---

## How The Engine Selects The Depth

### Step 1: Pre-Scoring Gates

Before any scoring, check for hard floors. Gates set a minimum depth — scoring can raise it higher but cannot lower it below the floor.

```
TASK ARRIVES
    |
    |-- Does it touch auth, payments, PII, or regulatory/legal?
    |   YES --> Floor = Depth 4. Proceed to scoring.
    |   NO  |
    |
    |-- Is there an active production incident affecting users NOW?
    |   YES --> Floor = Depth 4 (Chaotic). Stabilize first.
    |   NO  |
    |
    |-- Does it touch a published API, data model, or architectural boundary?
    |   YES --> Floor = Depth 3. Precedent-setting needs research minimum.
    |   NO  |
    |
    |-- Can the engine confidently score this task?
    |   NO  --> Floor = Depth 3. Low confidence = research mandatory.
    |   YES |
    |
    +-- No gate triggered. Floor = Depth 1.
```

**Gate rules:**
- Cumulative — multiple triggers use the highest floor.
- Not overridable by scoring — scoring adds on top.
- Overridable by founder (logged per SOVEREIGNTY.md).
- Logged: `gate_triggered: "auth-pii", floor_set: 4` or `gate_triggered: "none"`.

### Step 2: Problem-Type Classification (Cynefin)

Classify the problem. This determines the **shape** of decomposition, not just depth.

| Problem Type | Signal | Decomposition Shape |
|-------------|--------|-------------------|
| **Clear** | Done this exact thing before. Pattern exists. | Apply existing pattern. Skip research layers. |
| **Complicated** | Discoverable with analysis. Docs/examples exist. | Research maps territory, then build on findings. |
| **Complex** | Emergent. Can't predict outcome. Unknown unknowns. | Probe with small experiments first. Iterate. |
| **Chaotic** | Active crisis. No discernible cause-effect. | Stabilize first. Process comes after stability. |

### Step 3: Score the Parameters

Score each 1-5. These measure what actually determines the depth:

| # | Parameter | What It Measures | 1 | 5 |
|---|-----------|-----------------|---|---|
| 1 | **Causal Clarity** | Is the path to solution known? | Done this exact thing before | Emergent, unknowable upfront |
| 2 | **Irreversibility** | Can you undo it? | One git revert | Can't undo — data loss, published API |
| 3 | **Blast Radius** | What breaks if this goes wrong? | 1 file, 0 users | Cross-service, all users |
| 4 | **Component Maturity** | Novel or commodity? | Commodity, standardized | Genesis, first attempt ever |
| 5 | **Resource Consumption** | How many systems/layers involved? | 1 layer, 1 tool | 3+ layers, external APIs |
| 6 | **Precedent Impact** | Sets a pattern others follow? | Nth instance of existing pattern | First-of-kind, defines THE pattern |
| 7 | **Assessment Confidence** | How sure is the engine? | Scope is crystal clear | Can't tell scope, need research |
| 8 | **Appetite** | Founder's time/resource budget? | "30 minutes max" | "Take whatever it needs" |
| 9 | **Company Stage** | What's the blast radius amplifier? | Pre-launch, mistakes are free | Growth/scale, mistakes cost money |
| 10 | **Sensitivity Floor** | Sensitive domain? | No security/data/legal touch | Auth, payments, PII, regulatory |

**What does NOT determine the depth:**
- Company size alone
- User count alone
- Team size alone
- How long the company has existed

Company stage only matters when it **actually amplifies** blast radius. A pre-launch company's button change and a growth company's button change are both Depth 1 if blast radius is 1 component.

### Step 4: Compute the Depth

**This is NOT a weighted average.** A single 5 drives the depth up.

```
stakes_max     = max(Irreversibility, Blast Radius, Sensitivity Floor, Company Stage)
complexity_max = max(Causal Clarity, Component Maturity, Resource Consumption)
judgment_max   = max(Precedent Impact, Assessment Confidence)

composite = max(stakes_max, complexity_max, judgment_max)
```

Appetite does not enter the composite. It's a modifier (Step 5).

Cross-reference composite x problem type:

| Composite | Clear | Complicated | Complex | Chaotic |
|-----------|-------|-------------|---------|---------|
| 1-2 | Depth 1 | Depth 2 | Depth 2 | Depth 3 |
| 3 | Depth 2 | Depth 2 | Depth 3 | Depth 4 |
| 4 | Depth 2 | Depth 3 | Depth 3 | Depth 4 |
| 5 | Depth 3 | Depth 3 | Depth 4 | Depth 5 |

### Step 5: Apply Modifiers

- **Gate floor:** Use max(candidate depth, gate floor).
- **Appetite:** If founder limits ("30 min max"), reduce by one level IF no gate floor active. If founder invests ("take whatever time"), raise by one level.
- **Chaotic at Depth 5:** Complex + composite 5 + Chaotic crisis = Depth 5. Full cascade with stabilization first.

### Step 6: Output

```yaml
gate_triggered: "none"
gate_floor: 1
problem_type: Complicated
parameter_scores: { causal_clarity: 2, irreversibility: 1, ... }
composite: 3
candidate_depth: 2
appetite_modifier: 0
final_depth: 2
decomposition: "estimate scope, then build, then verify"
```

---

## Minimum Verification Evidence Per Depth

| Depth | Minimum Evidence | Example |
|------|-----------------|---------|
| 1 | None. Ship log entry suffices. | "Shipped button color change" |
| 2 | One concrete check: build passes or feature renders. | `npm run build` exit 0 |
| 3 | Test output or grep evidence proving it works. | "45/45 tests pass" |
| 4 | Test output + deployment verification + rollback plan. | Tests pass + preview deploy verified |
| 5 | All of Depth 4 + retrospective + documentation. | Full artifact chain preserved |

**The rule:** If verification says "PASS" without evidence, it violates PROTO-010. Evidence must be reproducible.

---

## Protocol Activation Per Depth

| Depth | What Activates |
|------|---------------|
| 1 | Nothing — just build |
| 2 | /estimate |
| 3 | /estimate, /plan, /review, /qa |
| 4 | /estimate, /plan, /review, /qa, /canary, staged rollout |
| 5 | Everything from Depth 4 + expert research, HLD, LLD, retrospective |

---

## Mid-Task Depth Shifts

### Escalation (automatic):

- Discover the task touches auth/payments/PII: **escalate to Depth 4 immediately**. Not overridable.
- Discover 2x more files affected than estimated: **escalate one level**.
- Discover an unknown unknown: **escalate one level**.
- Problem type shifts (Complicated --> Complex): **re-route using the two-axis table**.
- Escalation adds missing decomposition layers. Does not restart from scratch.

### De-escalation (founder only):

- Founder says "this doesn't need full process" or "skip the review."
- Logged as override per SOVEREIGNTY.md.

---

## The Three Layers

The engine is Layer 3. Two layers sit above it:

```
STRATEGY    "What matters"       OKRs, big rocks, vision, charters
SELECTION   "What to do now"     Prioritization, sequencing
EXECUTION   "How deep"           Adaptive Protocol Engine (depth 1-5)

Strategy picks the task.
Selection sequences it.
Engine picks the depth.
```

Strategy and selection also have depths — deciding "what to work on" can itself be Depth 1 ("founder says do this") through Depth 5 ("full strategic planning with market research"). The depth system is fractal.

---

## The Routing Table

Concrete examples showing the full scoring pipeline:

| Task | Gate | Type | Composite | Depth | Rationale |
|------|------|------|-----------|------|-----------|
| Fix button color | none | Clear | 1 | **1** | Known, zero risk, one file |
| Update privacy policy content | none | Clear | 2 | **1** | Known pattern, low risk |
| Add new card component | none | Clear | 2 | **2** | Clear but enough scope for estimation |
| Deep linking for share URLs | none | Complicated | 3 | **2** | Discoverable, moderate scope |
| Content moderation pipeline | none | Complex | 3 | **3** | "What to moderate?" is unknowable upfront |
| RLS policies on all tables | auth-pii (4) | Complicated | 5 | **4** | Gate fires on PII, sensitivity confirms |
| Redesign onboarding flow | none | Complex | 4 | **3** | Emergent — "will users like this?" |
| Database schema migration | precedent (3) | Complicated | 5 | **4** | Gate + irreversibility + precedent |
| Payment provider integration | auth-pii (4) | Complicated | 5 | **4** | Gate fires on payments |
| CI/CD pipeline setup | precedent (3) | Complicated | 4 | **3** | Creates infra pattern, gate ensures research |
| Build entire auth system | auth-pii (4) | Complex | 5 | **5** | PII gate + complex + max composite |
| Company data architecture | none | Complex | 5 | **4** | Genesis maturity, max precedent |
| Button change in 10K-user app | none | Clear | 1 | **1** | Company size irrelevant — blast radius is 1 |

---

## Learning Loop

### Per-task feedback:

Every task records in LEARN.md:

```yaml
depth_selected: 3
depth_correct: 2
delta: -1
triage_class: overtriage
reason: "Familiar pattern. Research step added no information."
task_category: "feed-feature"
problem_type: Clear
gate_triggered: none
```

### Triage tracking:

| Class | Definition | Risk |
|-------|-----------|------|
| **Undertriage** | Depth too low. Missed needed steps. | HIGH — causes bugs, rework |
| **Correct** | Depth was right. Every step added value. | Target |
| **Overtriage** | Depth too high. Steps wasted. | LOW — wastes time only |

### Triage targets (asymmetric):

| Metric | Target | Rationale |
|--------|--------|-----------|
| Undertriage rate | < 5% | Under-processing is dangerous |
| Overtriage rate | < 30% | Over-processing is the safer failure mode |
| Correct rate | > 65% | Majority of routing should be right |

When undertriage > 5%: all locked rules unlock.
When overtriage > 30%: review locked rules for over-triaged categories.

### Locking rules:

- Accuracy > 90% over 10+ tasks for a category: lock the routing rule.
- Any undertriage event: immediately unlock that category.
- Locked rules expire when company stage changes or after 50 tasks.

### Stage recalibration:

When stage changes (pre-launch --> beta --> growth --> scale):
- All locked rules unlock.
- Triage tracking resets for the new stage.
- Engine re-learns at the new stage.

---

## Company State

Company state is passive input to this engine, not a separate system. Growing a company is a task — it goes through the same engine.

### Config

```yaml
# Lives in each company's SUTRA-CONFIG.md
company_state:
  stage: "pre-launch"
  user_count: 0
  active_depts: ["product", "engineering"]
  dormant_depts: ["quality", "data", "growth", "security", "design",
                  "content", "legal", "finance", "ops"]
  active_protocols: ["P4", "P10"]
```

### State Transitions

When a task needs a dormant capability, the engine flags it:

```
1. Task arrives: "Add QA test suite"
2. Engine routes: needs /qa skill.
3. Checks: quality dept is dormant.
4. Flags: "This task needs QA. Activate quality department?"
5. Founder confirms.
6. company_state updates.
7. Task proceeds.
```

### Activation Signals

Not automatic triggers — signals the engine watches. Engine recommends, founder decides.

| Signal | Recommended Activation |
|--------|----------------------|
| First task needing test verification | Quality dept |
| First task needing usage data | Data dept |
| First task targeting user acquisition | Growth dept |
| First external security concern | Security dept |
| First task where design judgment needed | Design dept |
| Revenue > $0/mo | Finance dept |
| Manual ops becoming repeated pain | Ops dept |
| Pre-launch checklist begins | Legal dept |

### Stage Transitions

| Transition | Trigger | Engine Effect |
|-----------|---------|---------------|
| pre-launch --> beta | First real users | Locked rules reset |
| beta --> growth | Product-market fit proven | All tasks minimum Depth 2 |
| growth --> scale | Team > 1 or users > 1000 | Full depth range, minimum Depth 2 |

---

## Integration Points

| Direction | System | What Flows |
|-----------|--------|------------|
| **Receives from** | Estimation Engine | Cost, confidence, scope. Low confidence may trigger gate. |
| **Receives from** | TODO.md / user request | Task description, priority. |
| **Receives from** | SUTRA-CONFIG.md | Company state, founder involvement level. |
| **Feeds into** | Agent architecture | Which skills/protocols activate per depth. |
| **Feeds into** | LEARN.md | Depth evaluation, triage, accuracy data. |
| **Validated by** | Effectiveness check | Post-task: was the depth right? |
| **Respects** | Sovereignty | Founder override always available, always logged. |

---

## Enforcement

### HARD (Tier 2+):
- Engine MUST run before every task.
- Engine MUST output: gate result, problem type, scores, depth, activated protocols.
- Output MUST be visible (not silent).
- Skipping the engine is a BLOCK violation.

### SOFT (Tier 1):
- Engine runs and recommends. Does not block if founder ignores it.
- Rationale: personal tools have higher friction cost than process gaps.

### Founder override:
- Override up: always allowed.
- Override down: allowed, must acknowledge. Logged per SOVEREIGNTY.md.
- Override doesn't change the score. Changes the executed depth. Learning loop records both.

---

## Origin

v1: Maze onboarding, 2026-04-04. Two features got identical pipeline — privacy policy page and RLS rewrite. Process added no value to the first and was essential for the second.

v2 (2026-04-06): Added pre-scoring gates, Cynefin classification, undertriage/overtriage tracking. Informed by 8 external frameworks: Cynefin, Wardley Mapping, Military ROE, Medical ESI, Toyota Kata, Legal Proportional Process, Spotify Model, Shape Up. Full research at `holding/research/ADAPTIVE-PROTOCOL-RESEARCH.md`.

v3 (2026-04-06): Reframed around speed-precision trade-off. 4 levels --> 5 depths. Depths defined by decomposition granularity, not pipeline steps. Removed company-size floor — company stage only matters when it amplifies blast radius. Merged Progressive OS into Company State section. Three-layer model: Strategy > Selection > Execution. The depth system is fractal — applies to strategy and meta-decisions, not just code tasks.

**Governing insight:** Speed and precision cannot be simultaneously maximized. The engine's job is to place each task at the right point on that curve.
