# Sutra — Adaptive Protocol Engine v2

ENFORCEMENT: HARD for Tier 2+. The engine MUST run before every task. Founder can override the selected depth (up or down) but must acknowledge.

---

## Purpose

> **Governing Principle**: P10 — Scalability of Intelligence. Match cognitive resource to the problem.

The Adaptive Protocol Engine reads a problem and decides how much process to apply. Every problem has two outputs — code and knowledge. The code is for the user. The knowledge is for the system. The depth of process must match the problem, not be one-size-fits-all.

v2 adds three capabilities over v1:
1. **Pre-scoring gates** — certain triggers bypass scoring and set a floor immediately (from medical ESI and military ROE patterns).
2. **Problem-type routing** — a second axis alongside severity. The path to solution (known vs. discoverable vs. emergent) determines process shape independently.
3. **Undertriage/overtriage tracking** — asymmetric learning targets that treat under-processing as more dangerous than over-processing.

---

## Phase 1: Pre-Scoring Gates

Before any parameter scoring, run this decision tree. Gates set a **floor** — scoring can raise the level higher, but cannot lower it below the gate floor.

```
TASK ARRIVES
    │
    ├─ Does it touch auth, payments, PII, or regulatory/legal compliance?
    │   YES → Floor = L4. Proceed to scoring (score may confirm L4, cannot lower).
    │   NO  ↓
    │
    ├─ Is there an active production incident affecting users RIGHT NOW?
    │   YES → Floor = L4 (Chaotic protocol). Act to stabilize first, full process second.
    │   NO  ↓
    │
    ├─ Does it touch a published API contract, data model schema, or architectural boundary?
    │   YES → Floor = L3. Precedent-setting changes need research phase minimum.
    │   NO  ↓
    │
    ├─ Can the engine confidently score this task? (Do we understand the scope?)
    │   NO  → Floor = L3. Low confidence means research phase is mandatory.
    │   YES ↓
    │
    └─ No gate triggered. Floor = L1. Proceed to scoring.
```

### Gate Rules

- Gates are **cumulative** — if multiple trigger, use the highest floor.
- Gates are **not overridable by scoring** — scoring adds on top of the floor.
- Gates ARE overridable by the founder (logged per SOVEREIGNTY.md).
- Gate results are logged: `gate_triggered: "auth-pii", floor_set: "L4"` or `gate_triggered: "none"`.

---

## Phase 2: Problem-Type Classification

Before parameter scoring, classify the problem along the Cynefin axis. This determines the **shape** of the process (not just depth).

| Problem Type | Cause-Effect | Signal | Process Shape |
|-------------|-------------|--------|---------------|
| **Clear** | Obvious, repeatable. Done this exact thing before. | Pattern exists in codebase. Known inputs, known outputs. | Sense → Categorize → Respond. Apply existing pattern. Skip research. |
| **Complicated** | Discoverable through analysis. Requires expertise but the answer exists. | Familiar domain, new variation. Can find examples externally. | Sense → Analyze → Respond. Research phase maps the territory, then build. |
| **Complex** | Emergent. Only visible in retrospect. Can't predict outcome. | First time for anyone. "Will users like this?" Unknown unknowns present. | Probe → Sense → Respond. Small experiments first. Full pipeline with checkpoints. |
| **Chaotic** | No discernible relationship. Active crisis. | Production down. Data corruption. Security breach. | Act → Sense → Respond. Stabilize first. Process comes after stability. |

### How Problem Type Modifies Depth

Problem type is a **second axis**, not a replacement for severity scoring. The combination determines the final level:

| | Low Stakes (score 1-2) | Medium Stakes (score 3) | High Stakes (score 4-5) |
|---|---|---|---|
| **Clear** | L1 — apply pattern, ship | L2 — estimate + apply pattern | L2-L3 — apply pattern with safeguards |
| **Complicated** | L2 — light analysis needed | L2-L3 — analysis + testing | L3 — full pipeline |
| **Complex** | L2-L3 — probe needed regardless of stakes | L3 — full pipeline with experiments | L4 — maximum process, probe before committing |
| **Chaotic** | L3 — stabilize, then assess | L4 — emergency protocol | L4 — emergency protocol, all hands |

Key insight: a Complex problem at low stakes still needs L2-L3 because the path to solution is unknown. A Clear problem at high stakes may only need L2 with careful testing because the solution is known.

---

## Phase 3: Parameter Scoring

Score each parameter 1-5. The engine reads the task description and codebase context to assign scores.

### The 10 Core Parameters

| # | Parameter | What It Measures | 1 (Low) | 3 (Medium) | 5 (Critical) |
|---|-----------|-----------------|---------|------------|---------------|
| 1 | **Causal Clarity** | Is the path to solution known? | Clear — done this exact thing, known outcome | Complicated — discoverable with analysis | Complex/Chaotic — emergent or unknowable outcome |
| 2 | **Irreversibility** | Can the action be undone? | One `git revert` undoes it cleanly | Requires data migration or multi-step rollback | Irreversible — data loss, sent notifications, published API, legal filing |
| 3 | **Blast Radius** | How many systems/users/components break if this goes wrong? | 1 file, 0 users, no dependents | 3-8 files, one feature area, moderate dependents | 9+ files, cross-service, all users, multiple downstream systems |
| 4 | **Component Maturity** | Is this pattern Genesis, Custom, Product, or Commodity? | Commodity — fully standardized, automated | Product — best practices exist, following them | Genesis — novel, no prior art anywhere. First attempt. |
| 5 | **Resource Consumption** | How many distinct systems/layers/tools does this require? | 1 layer, 1 tool, no external deps | 2 layers, 2-3 tools, 1 external dependency | 3+ layers, multiple services, external APIs, review cycles needed |
| 6 | **Precedent Impact** | Does this create a pattern future tasks will follow? | Nth instance of an existing pattern | Extends an existing pattern in a new direction | First-of-kind — new API contract, data model, or architectural pattern |
| 7 | **Assessment Confidence** | How sure is the engine about its own scoring? | High — scope is clear, parameters are obvious | Moderate — some ambiguity, but bounded | Low — can't tell scope, don't understand the domain, need research |
| 8 | **Appetite** | How much time/resource is the founder willing to invest? | Founder says "30 minutes max" — minimal investment | No explicit limit — default investment | Founder says "take whatever time it needs" — full investment |
| 9 | **Company Stage** | Organizational maturity and user base? | Pre-launch, no users (mistakes are free) | Beta or early users (mistakes cost trust) | Growth/scale with revenue (mistakes cost money and users) |
| 10 | **Sensitivity Floor** | Does this touch a domain that forces minimum depth? | No security/data/legal/financial touch | Adjacent to sensitive domains | Auth, payments, PII, legal, regulatory — triggers pre-scoring gate |

---

## Phase 4: Scoring Model

This is NOT a weighted average. A task that scores 5 on Sensitivity and 1 on everything else is a Level 4 task, not a "2.5" task.

### Step-by-step scoring:

**Step 1: Check pre-scoring gates (Phase 1).** Record the floor.

**Step 2: Classify problem type (Phase 2).** Record Clear/Complicated/Complex/Chaotic.

**Step 3: Score all 10 parameters (1-5 each).**

**Step 4: Compute severity score.**

Group parameters into three scoring categories:

```
stakes_max     = max(Irreversibility, Blast Radius, Sensitivity Floor, Company Stage)
complexity_max = max(Causal Clarity, Component Maturity, Resource Consumption)
judgment_max   = max(Precedent Impact, Assessment Confidence)
```

Composite severity = max(stakes_max, complexity_max, judgment_max).

Note: **Appetite does not enter the composite.** It is an override parameter (see Step 6).

**Step 5: Map severity to depth level using the two-axis table (Phase 2).**

Cross-reference: severity score (composite) x problem type → candidate depth level.

| Composite Score | Clear | Complicated | Complex | Chaotic |
|-----------------|-------|-------------|---------|---------|
| 1-2 | L1 | L2 | L2 | L3 |
| 3 | L2 | L2 | L3 | L4 |
| 4 | L2 | L3 | L3 | L4 |
| 5 | L3 | L3 | L4 | L4 |

**Step 6: Apply modifiers.**

- **Gate floor**: If pre-scoring gate set a floor, use max(candidate level, gate floor).
- **Appetite override**: If Appetite = 1 (founder explicitly limiting), the engine may reduce by one level IF no gate floor is active. This reshapes process to fit the budget — scope is cut, not quality. If Appetite = 5 (founder explicitly investing), the engine may raise by one level.
- **Tier constraints**: Apply tier ceiling/floor (see Tier Behavior section).

**Step 7: Output.**

```
gate_triggered: "none" | "auth-pii" | "incident" | "precedent" | "low-confidence"
gate_floor: L1 | L3 | L4
problem_type: Clear | Complicated | Complex | Chaotic
parameter_scores: { causal_clarity: 2, irreversibility: 1, blast_radius: 1, ... }
composite_severity: 3
candidate_level: L2
appetite_modifier: 0 | -1 | +1
tier_constraint: "none" | "capped at L3 by Tier 2" | "raised to L2 by Tier 3"
final_level: L2
```

---

## Process Depth Levels

### Level 1: Minimal

**Pipeline:** build → ship → log.

No review, no spec, no research phase. The task is well-understood and low-risk.

**When:** CSS fixes, copy changes, dependency bumps with no breaking changes, well-understood CRUD following existing patterns, config tweaks. Problem type is Clear, stakes are low.

**Sutra involvement:** Estimation table entry only. No pipeline activation. Compliance check skipped (counted toward the "every 3rd feature" cadence for Tier 1).

**Time budget:** Minutes. If this takes more than 30 minutes, re-evaluate — it may not be Level 1.

**What gets logged:** Task name, time spent, files changed. One line in LEARN.md if anything surprised you.

### Level 2: Standard

**Pipeline:** estimate → build → test → ship → learn.

Light process. Estimation up front to catch scope creep. Testing before ship. Learning after.

**When:** New features in familiar territory, moderate scope, UI components with clear specs, API endpoints following established patterns. Also: Complex problems at low stakes (the probe is lightweight) or Clear problems at high stakes (known solution, careful execution).

**Sutra involvement:** Estimation Engine runs. Lightweight review (self-check, not peer review). Compliance check runs.

**Time budget:** Hours. If estimation says > 1 day, re-evaluate — it may be Level 3.

**What gets logged:** Estimation vs. actual. LEARN.md entry with depth evaluation. Metrics update.

### Level 3: Full

**Pipeline:** estimate → research → spec → build → test → review → ship → learn.

Full process. Research phase to map the territory. Spec to define the approach. Review before ship.

**When:** Cross-cutting changes, new domains, user-facing features with UX implications, changes that touch multiple services, precedent-setting decisions, anything where problem type is Complex. Also triggered by low assessment confidence (need research to understand scope).

**Sutra involvement:** Full pipeline with compliance checks. All relevant skills activate (/plan, /review, /qa). Founder checkpoint if involvement level is "hands-on" or "strategic."

**Time budget:** Days. Normal pace, no shortcuts on quality.

**What gets logged:** Research findings. Spec document. Review notes. Estimation accuracy. LEARN.md entry with depth evaluation. Full metrics.

### Level 4: Critical

**Pipeline:** estimate → research → spec → peer review → build → platform-appropriate rollout → verify → ship → learn → retro.

Maximum process. Peer review of the spec before building. Platform-appropriate rollout. Verification in production. Retrospective after.

**When:** Auth system changes, payment flows, data model migrations, irreversible decisions, anything touching PII or regulatory compliance, public API changes, active production incidents (Chaotic protocol). Always triggered by the auth/PII/payments pre-scoring gate.

**Sutra involvement:** Full pipeline + founder checkpoint (mandatory, regardless of involvement level). Post-ship canary mandatory. Retro feeds back into Sutra.

**Platform-specific rollout (replaces "staged rollout"):**

| Platform | Rollout Strategy |
|----------|-----------------|
| Web app (Next.js/Vercel) | Preview deploy → verify → promote to production |
| Mobile app (Expo) | EAS build → internal test → TestFlight/Play Store beta → production |
| Edge functions (Supabase) | Deploy is all-or-nothing — verify via test calls before and after, rollback via git revert |
| CLI tool | Publish to npm with `--tag beta` → test → promote to `latest` |
| Database migration | Run on staging DB first → verify → run on production with backup |

If the platform doesn't support staged rollout, the "rollout" step becomes: deploy → immediate verify → rollback plan ready.

**Time budget:** Days to weeks. No rushing. If time pressure conflicts, flag it — do not lower the level.

**What gets logged:** Everything from Level 3, plus: rollout plan (platform-specific), verification results, retro document. All artifacts preserved.

---

## Minimum Verification Evidence Per Level

VERIFY is proof, not a checklist. Each depth level has a minimum evidence requirement.

| Level | Minimum Evidence Required | Example |
|-------|--------------------------|---------|
| **L1 Minimal** | None — no VERIFY artifact. Ship log entry in METRICS.md suffices. | "Shipped vercel.json cron config" |
| **L2 Standard** | One concrete check: build passes, app loads, or feature renders. | `npm run build` → exit 0, or screenshot of feature working |
| **L3 Full** | Test output or grep evidence proving the feature works. | "45/45 tests pass" or `grep -c "requireAuth" functions/*/index.ts → 5` |
| **L4 Critical** | Test output + deployment verification + rollback plan documented. | Tests pass + preview deploy verified + "rollback: git revert abc123" |

### What Counts as Evidence

| Evidence Type | Counts | Doesn't Count |
|--------------|--------|---------------|
| Test output | `PASS: 45/45 tests` | "Tests look good" |
| Grep result | `5 functions import requireAuth` | "All functions updated" |
| Build output | `exit 0, no errors` | "Builds clean" |
| Deployment URL | `https://app.vercel.app (200 OK)` | "Deployed successfully" |
| Screenshot | Actual screenshot file | "Looks right" |

### The Rule

If VERIFY.md says "PASS" without evidence, it violates PROTO-010.
The evidence must be **reproducible** — another agent reading the VERIFY could verify the same thing.

---

## How Routing Works

### Runtime flow:

```
1. TASK ARRIVES
   Source: TODO.md priority, user request, incident, or dependency trigger.

2. PRE-SCORING GATES (Phase 1)
   Check: auth/PII/payments? Production incident? API/schema change? Scope clarity?
   Output: gate floor (L1/L3/L4).

3. PROBLEM-TYPE CLASSIFICATION (Phase 2)
   Assess: Clear / Complicated / Complex / Chaotic.
   Reads: task description, codebase context, prior art in repo.

4. PARAMETER SCORING (Phase 3)
   Score 10 parameters (1-5 each).
   Reads: task description, affected files (git diff preview or file list),
          codebase context (what the files do, what depends on them),
          company SUTRA-CONFIG.md (stage, involvement level, tier).

5. DEPTH SELECTION (Phase 4)
   Cross-reference: severity score x problem type → candidate level.
   Apply: gate floor, appetite modifier, tier constraints.
   Output: final depth level + activated protocols.

6. TASK EXECUTES AT SELECTED DEPTH
   The session follows the configured pipeline.
   Mid-task escalation rules apply (see below).
   Mid-task de-escalation requires founder override.

7. POST-TASK: EFFECTIVENESS CHECK + TRIAGE TRACKING
   Evaluate: was the depth right?
   Record: depth_selected, depth_correct, delta, reason, triage_class.
   Feed into learning loop.
```

### Protocol activation per level:

| Level | Activated Protocols |
|-------|-------------------|
| L1 | None — just build |
| L2 | /estimate |
| L3 | /estimate, /plan, /review, /qa |
| L4 | /estimate, /plan, /review, /qa, /canary, staged rollout |

### Mid-task escalation rules:

- If during build you discover the task touches auth, payments, or PII: **escalate to Level 4 immediately**. No override possible.
- If during build you discover more than 2x the estimated files are affected: **escalate one level**.
- If during build you discover an unknown unknown (something you didn't know you didn't know): **escalate one level**.
- If the problem type shifts (e.g., started as Complicated, turns out to be Complex): **re-route using the two-axis table**.
- Escalation adds the missing pipeline steps. It does not restart from scratch.

### Mid-task de-escalation:

- Only by founder override.
- Founder says "this doesn't need full process" or "skip the review."
- Logged as override per SOVEREIGNTY.md protocol.

---

## The Routing Table

Concrete examples showing the full v2 scoring pipeline:

| Task | Gate | Problem Type | Severity | Final Level | Rationale |
|------|------|-------------|----------|-------------|-----------|
| Fix button color on landing page | none | Clear | 1 | **L1** | Known pattern, zero risk, commodity task. |
| Update privacy policy page content | none | Clear | 2 | **L1** | Known pattern, low risk. Sensitivity=2 doesn't trigger gate. |
| Add new card component to feed | none | Clear | 2 | **L2** | Clear pattern but enough scope to warrant estimation. |
| Implement deep linking for share URLs | none | Complicated | 3 | **L2** | Discoverable solution, moderate scope. Analysis needed. |
| Build content moderation pipeline | none | Complex | 3 | **L3** | Emergent problem — "what should we moderate?" is unknowable upfront. Probe first. |
| Add RLS policies to all tables | auth-pii (L4) | Complicated | 5 | **L4** | Gate triggers on PII. Sensitivity=5 confirms. |
| Redesign onboarding flow (user-facing) | none | Complex | 4 | **L3** | "Will users like this?" is emergent. Full pipeline with experiments. |
| Migrate database schema (add new entity) | precedent (L3) | Complicated | 5 | **L4** | Gate triggers on schema change (precedent). Irreversibility=4, Foundationality=5 push to L4. |
| Integrate third-party payment provider | auth-pii (L4) | Complicated | 5 | **L4** | Gate triggers on payments. Maximum process. |
| Set up CI/CD pipeline | precedent (L3) | Complicated | 4 | **L3** | Creates infrastructure pattern. Gate ensures research phase minimum. |
| "Will users pay for feature X?" | low-confidence (L3) | Complex | 2 | **L3** | Low stakes technically, but causally unclear. Confidence gate forces research. |
| CSS hotfix during production incident | incident (L4) | Chaotic | 2 | **L4** | Incident gate overrides low severity. Stabilize first. |

---

## Learning Loop

The engine improves over time through structured feedback.

### Per-task feedback (in LEARN.md):

Every task records:
```yaml
depth_selected: 3
depth_correct: 2
delta: -1
triage_class: overtriage    # undertriage | correct | overtriage
reason: "Standard feature in familiar pattern. Review step added no new information."
task_category: "feed-feature"
problem_type: Clear
gate_triggered: none
```

### Triage Tracking

Every task is classified into one of three triage outcomes:

| Triage Class | Definition | Risk Level |
|-------------|-----------|------------|
| **Undertriage** | Depth was too low. Missed steps that were needed. Something went wrong or nearly went wrong. | HIGH — most dangerous. Under-processing causes bugs, security holes, rework. |
| **Correct** | Depth was right. Every step added value, no step was wasted. | NONE — this is the target. |
| **Overtriage** | Depth was too high. Steps were run that added no information or value. | LOW — wastes time but doesn't cause harm. |

### Triage Targets (asymmetric)

| Metric | Target | Rationale |
|--------|--------|-----------|
| Undertriage rate | **< 5%** | Under-processing is dangerous. Nearly every task should get enough process. |
| Overtriage rate | **< 30%** | Over-processing wastes time but is the safer failure mode. Tolerate more of it. |
| Correct rate | **> 65%** | The majority of routing decisions should be right. |

When undertriage rate exceeds 5%: **all locked rules unlock**. The engine is being too aggressive with shortcuts.

When overtriage rate exceeds 30%: review locked rules for the most over-triaged categories and consider lowering their default levels.

### Aggregation table:

Track per task category:

| Task Category | Tasks | Correct | Over | Under | Accuracy | Undertriage % | Overtriage % |
|---------------|-------|---------|------|-------|----------|---------------|--------------|
| feed-feature | 12 | 10 | 2 | 0 | 83% | 0% | 17% |
| auth-change | 3 | 3 | 0 | 0 | 100% | 0% | 0% |
| schema-migration | 4 | 3 | 0 | 1 | 75% | 25% | 0% |

### Locking rules:

- When accuracy exceeds **90% over 10+ tasks** for a category, lock the routing rule. The engine uses the locked rule without re-scoring for that category.
- Locked rules include an expiry: re-evaluate when company stage changes or after 50 tasks (whichever comes first).
- Any **undertriage event** immediately unlocks the rule for that category. Under-processing is more dangerous than over-processing.
- When a category has > 30% overtriage over 10+ tasks, flag for review (don't auto-adjust — the founder decides).

### Stage recalibration:

When the company's stage changes (pre-launch → beta, beta → growth, growth → scale):
- All locked rules unlock.
- Company Stage parameter baseline shifts up by 1.
- All triage tracking resets to zero for the new stage.
- The engine re-learns at the new stage.

This prevents rules learned during pre-launch ("schema changes are fine at Level 2") from carrying into growth ("schema changes affect 10,000 users now").

### LEARN.md feedback format:

Every LEARN.md entry should include a depth evaluation section:

```yaml
## Depth Evaluation
depth_selected: 3
depth_correct: 3
triage_class: correct
problem_type_selected: Complicated
problem_type_correct: Complicated
gate_triggered: precedent
notes: "Research phase correctly identified the edge case in the existing API contract."
```

When `depth_correct != depth_selected`, explain what was missed (undertriage) or what added no value (overtriage). This is what trains the next routing decision.

---

## Integration Points

| Direction | System | What Flows |
|-----------|--------|------------|
| **Receives from** | Estimation Engine (`d-engines/`) | Cost estimate, confidence level, scope assessment. Low confidence raises Assessment Confidence score AND may trigger the low-confidence pre-scoring gate. |
| **Receives from** | TODO.md / user request | Task description, priority, deadline. |
| **Receives from** | SUTRA-CONFIG.md | Company tier, stage, founder involvement level. |
| **Feeds into** | `b-agent-architecture/` | Which skills and protocols to activate for this task. |
| **Feeds into** | `b-agent-architecture/SKILL-CATALOG.md` | Skill activation list per depth level. |
| **Feeds into** | LEARN.md | Depth evaluation, triage classification, routing accuracy data. |
| **Validated by** | Effectiveness Agent | Post-task audit: was the depth right? Assigns triage class. |
| **Respects** | `c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` (Part 1: Sovereignty) | Founder override always available. Override logged per protocol. |
| **Respects** | `c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` (Part 2: Involvement Levels) | Hands-on = more checkpoints. Delegated = fewer. Does not change depth level, only checkpoint frequency. |

---

## Tier Behavior

The Adaptive Protocol Engine operates WITHIN a complexity tier (defined in `CLIENT-ONBOARDING.md` Appendix A). It does not change the tier. It varies process depth within the tier's allowed range.

| Tier | Depth Range | Constraints |
|------|-------------|-------------|
| **1 (Personal)** | Levels 1-2 | Level 3 available on founder request only. Level 4 never (no team to peer review, no staged rollout infra). |
| **2 (Product)** | Levels 1-3 | Level 4 available on founder request only. Default ceiling is Level 3. |
| **3 (Company)** | Levels 2-4 | Level 1 never — at scale, even "simple" changes carry risk from blast radius. Minimum is Level 2. |

### When tier constrains the engine:

If the scoring model selects Level 4 but the tier only allows up to Level 3:
1. Engine applies Level 3 (the tier maximum).
2. Engine logs: "Depth 4 recommended but constrained to 3 by Tier 2. Founder can override up."
3. If the constraining parameter was Sensitivity Floor >= 4 or a pre-scoring gate triggered, the engine flags this as a **risk acceptance** — the founder must acknowledge.

If the scoring model selects Level 1 but the tier minimum is Level 2:
1. Engine applies Level 2 (the tier minimum).
2. No flag needed. The overhead is minimal and the safety is real.

---

## Enforcement

ENFORCEMENT: HARD for Tier 2+.

### What "HARD" means:

- The engine MUST run before every task begins execution.
- The engine MUST output: gate result, problem type, parameter scores, composite score, selected level, activated protocols.
- The output MUST be visible (logged to session, not silent).
- Skipping the engine is a BLOCK violation (task cannot proceed).

### Founder override:

- Founder can override the selected depth — both up and down.
- Override up: always allowed, no justification needed ("I want full process on this").
- Override down: allowed, but must acknowledge. "I understand this was scored Level 4 but I want Level 2" is valid. It is logged per SOVEREIGNTY.md.
- Override does not change the score. It changes the executed depth. The learning loop records both: `depth_selected: 4, depth_executed: 2, override: true, triage_class: override`.

### Tier 1 behavior:

- SOFT enforcement. The engine runs and recommends a depth, but does not block if the founder ignores it.
- Rationale: Tier 1 companies are personal tools. Process friction has higher cost than process gaps at this scale.

---

## Quick Reference: The Full Pipeline

```
┌─────────────────────────────────────────────────────┐
│                   TASK ARRIVES                       │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  PRE-SCORING    │
              │  GATES          │  Auth/PII? Incident? Schema? Confidence?
              │  → Set floor    │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  PROBLEM TYPE   │
              │  CLASSIFICATION │  Clear / Complicated / Complex / Chaotic
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  SCORE 10       │
              │  PARAMETERS     │  1-5 each, grouped into 3 categories
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  TWO-AXIS       │
              │  LOOKUP         │  Severity x Problem Type → Candidate Level
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  APPLY          │
              │  MODIFIERS      │  Gate floor, appetite, tier constraints
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  EXECUTE AT     │
              │  SELECTED DEPTH │  L1 / L2 / L3 / L4 pipeline
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  LEARN          │  Depth evaluation + triage classification
              │  → Feed back    │  Undertriage < 5%, Overtriage < 30%
              └─────────────────┘
```

---

## Origin

Maze onboarding, 2026-04-04. Ran SUTRA mode on two features during the first build session: a static privacy policy page and a full RLS rewrite with row-level security across all tables. Both went through the identical pipeline. The code output was identical for both approaches. The process added no value to the privacy policy page and was essential for the RLS rewrite.

v2 informed by research across 8 external frameworks (2026-04-06): Cynefin (problem-type classification), Wardley Mapping (component maturity), Military ROE (pre-scoring gates, asymmetric escalation), Medical ESI (resource prediction, triage tracking), Toyota Kata (learning loops), Legal Proportional Process (precedent impact), Spotify Model (cross-boundary coordination), Shape Up (appetite-based scoping). Full research at `holding/research/ADAPTIVE-PROTOCOL-RESEARCH.md`.
