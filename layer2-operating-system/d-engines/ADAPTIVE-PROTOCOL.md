# Sutra — Adaptive Protocol Engine

ENFORCEMENT: HARD for Tier 2+. The engine MUST run before every task. Founder can override the selected depth (up or down) but must acknowledge.

---

## Purpose

The Adaptive Protocol Engine is the meta-skill of Sutra: it reads a problem and decides how much process to apply. Every problem has two outputs — code and knowledge. The code is for the user. The knowledge is for the system. But the depth of process should match the problem, not be one-size-fits-all. A privacy policy page and an auth system rewrite should not pass through the same pipeline. This engine evaluates problem parameters and context parameters at runtime, then selects the appropriate protocol depth — replacing static classification with dynamic routing.

---

## Problem Parameters

Score each parameter 1-5. The engine reads the task description and codebase context to assign scores.

### Importance Parameters

| Parameter | 1 (Low) | 3 (Medium) | 5 (Critical) |
|-----------|---------|------------|---------------|
| **Impact** | Cosmetic, no user-facing change | Affects UX or a single feature | Affects the core bet, system-wide, or all users |
| **Sensitivity** | No security/data/legal/financial touch | Touches user data or has compliance adjacent implications | Auth, payments, PII, legal, regulatory |
| **Criticality** | Nice-to-have, nothing blocks on it | Blocks one other task or is on the current sprint path | Blocks launch, blocks revenue, or is on the critical path |
| **Foundationality** | Leaf change, nothing depends on it | Shapes a feature area, moderate downstream effect | Shapes the data model, architecture, or API contract — hard to change later |

### Complexity Parameters

| Parameter | 1 (Low) | 3 (Medium) | 5 (High) |
|-----------|---------|------------|-----------|
| **Technical complexity** | 1-2 files, single layer, no coupling | 3-8 files, 2 layers, moderate coupling | 9+ files, 3+ layers, tight coupling or cross-service |
| **Domain novelty** | Done this exact thing before (pattern exists) | Familiar domain, new variation | First time in this domain, no prior art in the codebase |
| **Unknown unknowns** | Fully mapped, clear inputs and outputs | Some ambiguity, but can discover during build | Uncharted — don't know what we don't know |

### Context Parameters

| Parameter | 1 (Low) | 3 (Medium) | 5 (High) |
|-----------|---------|------------|-----------|
| **Company stage** | Pre-launch, no users (mistakes are free) | Beta or early users (mistakes cost trust) | Growth/scale with revenue (mistakes cost money and users) |
| **Time pressure** | No deadline, can take the time needed | Deadline within 2 weeks, some urgency | Deadline within 48 hours, competitive or contractual urgency |
| **Reversibility** | One `git revert` undoes it cleanly | Requires data migration or multi-step rollback | Irreversible — data loss, sent notifications, published API, legal filing |

### Human Parameters

| Parameter | 1 (Low) | 3 (Medium) | 5 (High) |
|-----------|---------|------------|-----------|
| **Founder energy** | Founder is low-bandwidth, delegate everything possible | Founder is available but focused elsewhere | Founder is engaged and has attention for this |
| **Stakeholder visibility** | Internal only, no one sees this | Internal + a few users see it | External-facing, investors, press, or public launch |

---

## The Scoring Model

This is NOT a weighted average. Averages dilute signal — a task that scores 5 on Sensitivity and 1 on everything else is not a "2.5" task. It is a 5-level task.

### How it works:

1. **Score all parameters** (1-5 each).
2. **Take the max within each category:**
   - `importance_max` = max(Impact, Sensitivity, Criticality, Foundationality)
   - `complexity_max` = max(Technical complexity, Domain novelty, Unknown unknowns)
   - `context_max` = max(Company stage, Time pressure, Reversibility)
   - `human_max` = max(Founder energy, Stakeholder visibility)
3. **Composite score = max(importance_max, complexity_max, context_max)**
   - Human parameters do NOT raise the composite score. They modify execution style within the selected level (e.g., high founder energy at Level 3 means more checkpoints, not Level 4).
4. **Apply ceiling from Time pressure:** If Time pressure = 5 and composite score >= 4, flag the conflict. The engine cannot lower depth for safety, but it CAN streamline the selected level's steps (parallelize research + spec, shorten review).

### Score-to-Level mapping:

| Composite Score | Process Depth Level |
|-----------------|---------------------|
| 1-2 | Level 1: Minimal |
| 3 | Level 2: Standard |
| 4 | Level 3: Full |
| 5 | Level 4: Critical |

---

## Process Depth Levels

### Level 1: Minimal (composite 1-2)

**Pipeline:** build -> ship -> log.

No review, no spec, no research phase. The task is well-understood and low-risk.

**When:** CSS fixes, copy changes, dependency bumps with no breaking changes, well-understood CRUD patterns, config tweaks.

**Sutra involvement:** Estimation table entry only. No pipeline activation. Compliance check skipped (counted toward the "every 3rd feature" cadence for Tier 1).

**Time budget:** Minutes. If this takes more than 30 minutes, re-evaluate — it may not be Level 1.

**What gets logged:** Task name, time spent, files changed. One line in LEARN.md if anything surprised you.

### Level 2: Standard (composite 3)

**Pipeline:** estimate -> build -> test -> ship -> learn.

Light process. Estimation up front to catch scope creep. Testing before ship. Learning after.

**When:** New features in familiar territory, moderate scope changes, UI components with clear specs, API endpoints following established patterns.

**Sutra involvement:** Estimation Engine runs. Lightweight review (self-check, not peer review). Compliance check runs.

**Time budget:** Hours. If estimation says > 1 day, re-evaluate — it may be Level 3.

**What gets logged:** Estimation vs actual. LEARN.md entry. Metrics update.

### Level 3: Full (composite 4)

**Pipeline:** estimate -> research -> spec -> build -> test -> review -> ship -> learn.

Full process. Research phase to map the territory. Spec to define the approach. Review before ship.

**When:** Cross-cutting changes, new domains, user-facing features with UX implications, changes that touch multiple services, anything that reshapes a feature area.

**Sutra involvement:** Full pipeline with compliance checks. All relevant skills activate (/plan, /review, /qa). Founder checkpoint if involvement level is "hands-on" or "strategic."

**Time budget:** Days. Normal pace, no shortcuts on quality.

**What gets logged:** Research findings. Spec document. Review notes. Estimation accuracy. LEARN.md entry. Full metrics.

### Level 4: Critical (composite 5)

**Pipeline:** estimate -> research -> spec -> peer review -> build -> staged rollout -> verify -> ship -> learn -> retro.

Maximum process. Peer review of the spec before building. Staged rollout (deploy to subset/staging first). Verification in production. Retrospective after.

**When:** Auth system changes, payment flows, data model migrations, irreversible decisions, anything touching PII or regulatory compliance, public API changes.

**Sutra involvement:** Full pipeline + founder checkpoint (mandatory, regardless of involvement level). Staged rollout required. Post-ship canary mandatory. Retro feeds back into Sutra.

**Time budget:** Days to weeks. No rushing. If time pressure conflicts, flag it — do not lower the level.

**What gets logged:** Everything from Level 3, plus: rollout plan, verification results, retro document. All artifacts preserved.

---

## How Routing Works

### Runtime flow:

```
1. TASK ARRIVES
   Source: TODO.md priority, user request, incident, or dependency trigger.

2. ENGINE SCORES PARAMETERS
   Reads: task description, affected files (git diff preview or file list),
          codebase context (what the files do, what depends on them),
          company SUTRA-CONFIG.md (stage, involvement level, tier).
   Outputs: 13 parameter scores + composite score + selected level.

3. ENGINE SELECTS PROCESS DEPTH
   Applies scoring model. Maps composite to level.
   Checks tier constraints (see Tier Behavior below).
   If level requires founder checkpoint, marks it.

4. ENGINE CONFIGURES PROTOCOLS
   Activates the skills and protocols for the selected level:
   - Level 1: no skills activated, just build
   - Level 2: /estimate
   - Level 3: /estimate, /plan, /review, /qa
   - Level 4: /estimate, /plan, /review, /qa, /canary, staged rollout

5. TASK EXECUTES AT SELECTED DEPTH
   The session follows the configured pipeline.
   If the task reveals higher complexity mid-execution (scope creep,
   unexpected coupling), the engine can ESCALATE the level mid-task.
   It cannot DE-ESCALATE without founder override.

6. POST-TASK: EFFECTIVENESS CHECK
   After task completes, evaluate:
   - Was the depth right?
   - Did we skip steps we needed? (under-process)
   - Did we run steps that added no value? (over-process)
   Record: depth-selected, depth-that-was-right, delta, reason.

7. FEEDBACK LOOP
   LEARN.md entry includes depth evaluation.
   Engine adjusts routing weights for similar tasks.
   See Learning Loop below.
```

### Mid-task escalation rules:

- If during build you discover the task touches auth, payments, or PII: escalate to Level 4 immediately. No override possible.
- If during build you discover more than 2x the estimated files are affected: escalate one level.
- If during build you discover an unknown unknown (something you didn't know you didn't know): escalate one level.
- Escalation adds the missing pipeline steps. It does not restart from scratch.

### Mid-task de-escalation:

- Only by founder override.
- Founder says "this doesn't need full process" or "skip the review."
- Logged as override per SOVEREIGNTY.md protocol.

---

## The Routing Table

Concrete examples showing parameter scores and selected depth:

| Task | Impact | Sens. | Crit. | Found. | Tech. | Novel. | Unkn. | Stage | Time | Revers. | Composite | Depth |
|------|--------|-------|-------|--------|-------|--------|-------|-------|------|---------|-----------|-------|
| Fix button color on landing page | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 1 | 1 | 2 | L1: Minimal |
| Update privacy policy page content | 1 | 2 | 1 | 1 | 1 | 1 | 1 | 2 | 1 | 1 | 2 | L1: Minimal |
| Add new card component to feed | 2 | 1 | 2 | 1 | 2 | 2 | 1 | 2 | 3 | 1 | 3 | L2: Standard |
| Implement deep linking for share URLs | 3 | 1 | 3 | 2 | 3 | 3 | 2 | 2 | 3 | 1 | 3 | L2: Standard |
| Build content moderation pipeline | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 2 | 2 | 2 | 3 | L2: Standard |
| Add RLS policies to all tables | 4 | 5 | 3 | 4 | 3 | 2 | 2 | 2 | 2 | 3 | 5 | L4: Critical |
| Redesign onboarding flow (user-facing) | 4 | 1 | 3 | 3 | 4 | 3 | 3 | 3 | 2 | 2 | 4 | L3: Full |
| Migrate database schema (add new entity) | 3 | 2 | 3 | 5 | 3 | 2 | 2 | 3 | 2 | 4 | 5 | L4: Critical |
| Integrate third-party payment provider | 4 | 5 | 4 | 4 | 4 | 4 | 3 | 3 | 3 | 5 | 5 | L4: Critical |
| Set up CI/CD pipeline | 2 | 1 | 2 | 4 | 3 | 2 | 2 | 2 | 1 | 2 | 4 | L3: Full |

**Reading the table:** The composite score is the max across all non-human parameter categories. RLS policies score 5 on Sensitivity alone — that single parameter forces Level 4, regardless of everything else being low.

---

## Learning Loop

The engine improves over time through structured feedback.

### Per-task feedback (in LEARN.md):

Every task records:
```
depth_selected: 3
depth_correct: 2
delta: -1 (over-processed)
reason: "Standard feature in familiar pattern. Review step added no new information."
task_category: "feed-feature"
```

### Aggregation:

Track `depth_selected` vs `depth_correct` for each task category:

| Task Category | Tasks | Correct | Over | Under | Accuracy |
|---------------|-------|---------|------|-------|----------|
| feed-feature | 12 | 10 | 2 | 0 | 83% |
| auth-change | 3 | 3 | 0 | 0 | 100% |
| schema-migration | 4 | 3 | 0 | 1 | 75% |

### Locking rules:

- When accuracy exceeds **90% over 10+ tasks** for a category, lock the routing rule. The engine uses the locked rule without re-scoring for that category.
- Locked rules include an expiry: re-evaluate when company stage changes or after 50 tasks (whichever comes first).
- Any **under-process** event (depth was too low) immediately unlocks the rule for that category. Under-process is more dangerous than over-process.

### Stage recalibration:

When the company's stage changes (pre-launch -> beta, beta -> growth, growth -> scale):
- All locked rules unlock.
- Context parameter baselines shift up by 1.
- The engine re-learns at the new stage.

This prevents rules learned during pre-launch ("schema changes are fine at Level 2") from carrying into growth ("schema changes affect 10,000 users now").

---

## Integration Points

| Direction | System | What flows |
|-----------|--------|------------|
| **Receives from** | Estimation Engine (`d-engines/`) | Cost estimate, confidence level, scope assessment. Low confidence raises Unknown unknowns score. |
| **Receives from** | TODO.md / user request | Task description, priority, deadline. |
| **Receives from** | SUTRA-CONFIG.md | Company tier, stage, founder involvement level. |
| **Feeds into** | `b-agent-architecture/` | Which skills and protocols to activate for this task. |
| **Feeds into** | `b-agent-architecture/SKILL-CATALOG.md` | Skill activation list per depth level. |
| **Feeds into** | LEARN.md | Depth evaluation, routing accuracy data. |
| **Validated by** | Effectiveness Agent | Post-task audit: was the depth right? |
| **Respects** | `c-human-agent-interface/SOVEREIGNTY.md` | Founder override always available. Override logged per protocol. |
| **Respects** | `c-human-agent-interface/INVOLVEMENT-LEVELS.md` | Hands-on = more checkpoints. Delegated = fewer. Does not change depth level, only checkpoint frequency. |

---

## Tier Behavior

The Adaptive Protocol Engine operates WITHIN a complexity tier (defined in `a-company-architecture/COMPLEXITY-TIERS.md`). It does not change the tier. It varies process depth within the tier's allowed range.

| Tier | Depth Range | Constraints |
|------|-------------|-------------|
| **1 (Personal)** | Levels 1-2 | Level 3 available on founder request only. Level 4 never (no team to peer review, no staged rollout infra). |
| **2 (Product)** | Levels 1-3 | Level 4 available on founder request only. Default ceiling is Level 3. |
| **3 (Company)** | Levels 2-4 | Level 1 never — at scale, even "simple" changes carry risk from blast radius. Minimum is Level 2. |

### When tier constrains the engine:

If the scoring model selects Level 4 but the tier only allows up to Level 3:
1. Engine applies Level 3 (the tier maximum).
2. Engine logs: "Depth 4 recommended but constrained to 3 by Tier 2. Founder can override up."
3. If the constraining parameter was Sensitivity >= 4, the engine flags this as a **risk acceptance** — the founder must acknowledge.

If the scoring model selects Level 1 but the tier minimum is Level 2:
1. Engine applies Level 2 (the tier minimum).
2. No flag needed. The overhead is minimal and the safety is real.

---

## Enforcement

ENFORCEMENT: HARD for Tier 2+.

### What "HARD" means:

- The engine MUST run before every task begins execution.
- The engine MUST output: parameter scores, composite score, selected level, activated protocols.
- The output MUST be visible (logged to session, not silent).
- Skipping the engine is a BLOCK violation (task cannot proceed).

### Founder override:

- Founder can override the selected depth — both up and down.
- Override up: always allowed, no justification needed ("I want full process on this").
- Override down: allowed, but must acknowledge. "I understand this was scored Level 4 but I want Level 2" is valid. It is logged per SOVEREIGNTY.md.
- Override does not change the score. It changes the executed depth. The learning loop records both: `depth_selected: 4, depth_executed: 2, override: true`.

### Tier 1 behavior:

- SOFT enforcement. The engine runs and recommends a depth, but does not block if the founder ignores it.
- Rationale: Tier 1 companies are personal tools. Process friction has higher cost than process gaps at this scale.

---

## Origin

Maze onboarding, 2026-04-04. Ran SUTRA mode on two features during the first build session: a static privacy policy page and a full RLS rewrite with row-level security across all tables. Both went through the identical pipeline — estimation, research, spec, build, test, review, ship, learn. Compliance audit at the end showed 28 failures. Rebuilt with full process — the code output was identical. The process added no value to the privacy policy page and was essential for the RLS rewrite.

Founder insight: "The process has two outputs — code and knowledge. The code is for the user. The knowledge is for the system. But the DEPTH of process should match the problem, not be one-size-fits-all."

This engine exists because Sutra's first instinct — apply maximum process to everything — is wrong. The right instinct is: apply the right process to everything. The Adaptive Protocol Engine is how Sutra learns the difference.
