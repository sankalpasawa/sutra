# Sutra — Mid-Stage Company Onboarding

## What This Is

The process for installing Sutra on a company that already exists. Unlike CLIENT-ONBOARDING.md (which takes a founder from idea to company), this handles the harder case: a running company with existing code, conventions, habits, and debt.

This is Sutra's expansion product. As Sutra grows, most new clients will NOT be greenfield. They'll be companies that have been building for weeks or months and need process installed onto a running system.

---

## The Difference from Greenfield

| | Greenfield (CLIENT-ONBOARDING.md) | Mid-Stage (this document) |
|---|---|---|
| **Starting point** | An idea in the founder's head | Running code, existing conventions, accumulated habits |
| **Risk** | Building the wrong thing | Breaking what already works |
| **Approach** | Generate from scratch | Assess, map, adapt, deploy incrementally |
| **Biggest challenge** | Extracting clarity | Changing behavior without disrupting flow |
| **Duration** | ~60 minutes | ~2-3 sessions (assess → plan → deploy → verify) |

---

## The Five Phases

```
ASSESS → MAP → PLAN → DEPLOY → VERIFY
(session 1)  (session 1)  (session 1)  (session 2)  (session 2-3)
```

### Phase 0: ASSESS — Understand What Exists

**Input**: Access to the company's repo
**Process**: Audit the current state without changing anything
**Output**: ASSESSMENT.md in the company's os/ directory
**Gate**: Founder reviews and confirms the assessment is accurate

#### What to Audit

1. **Codebase health**
   - How many files? What framework? What's the architecture?
   - Any existing tests? Coverage?
   - Tech debt: what's documented vs what's hidden?

2. **Process health**
   - Does a CLAUDE.md exist? How long? How many conventions?
   - Is there a TODO.md? How organized?
   - Are there any existing process docs (PLAN.md, DESIGN.md, ARCHITECTURE.md)?
   - Are they consulted or ignored?

3. **Habits**
   - Look at recent git history: are commits structured or chaotic?
   - Are there design mockups before code? Or code-first?
   - Is there any QA process? Sensors? Design compliance?
   - How are decisions logged?

4. **Existing OS (if any)**
   - Was Sutra previously installed? What version?
   - Are there operating system files? Are they being followed?
   - What hooks exist? Are they wired? Do they fire?

5. **Conventions vs Sutra processes**
   - Which existing conventions ALIGN with Sutra? (keep these)
   - Which conventions CONFLICT with Sutra? (flag for founder)
   - What's MISSING that Sutra provides? (add these)

#### Output Format

```markdown
# {Company} — Sutra Deployment Assessment

## Current State
- Codebase: {summary}
- Process maturity: {none / informal / documented / enforced}
- Existing OS: {none / partial / full but unenforced}

## What Works (keep)
- {convention 1}
- {convention 2}

## What Conflicts (flag)
- {conflict 1}: company does X, Sutra expects Y
- {conflict 2}

## What's Missing (add)
- {gap 1}
- {gap 2}

## Top 3 Risks
1. {risk}
2. {risk}
3. {risk}

## Recommended Deployment Order
1. {first thing to install}
2. {second}
...
```

---

### Phase 1: MAP — Map Existing Conventions to Sutra

**Input**: ASSESSMENT.md
**Process**: For each Sutra process, determine: adopt as-is, adapt, or skip for now
**Output**: MAPPING.md in the company's os/ directory
**Gate**: Founder approves the mapping

#### What to Map

| Sutra Process | Status | Company Equivalent | Action |
|---|---|---|---|
| Node structure (Mission → Commitment → Task) | ? | Flat TODO.md | Restructure |
| 7-step feature lifecycle | ? | "Just code it" | Install with enforcement |
| Daily standup | ? | None | Activate |
| Weekly review | ? | None | Activate |
| 5 sensors | ? | None | Build and wire |
| Metrics logging | ? | METRICS.md exists, 6 entries | Make consistent |
| Knowledge system | ? | PKS.md exists, not consulted | Integrate into Shape step |
| Design mockup before code | ? | Sometimes | Enforce via process-gate |

For each row, decide:
- **Adopt**: install Sutra's version as-is
- **Adapt**: modify Sutra's version to fit company's existing patterns
- **Defer**: not needed at this stage/tier, install later

---

### Phase 2: PLAN — Create Deployment Plan

**Input**: MAPPING.md
**Process**: Order the deployments to minimize disruption
**Output**: DEPLOYMENT-PLAN.md in the company's os/ directory
**Gate**: Founder reviews and approves the plan

#### Planning Principles

1. **Start with what's invisible.** Install audit logging, enforcement hooks, directory structures. The founder sees no change in their workflow, but the infrastructure is ready.

2. **Then add structure.** Restructure TODO into nodes. Activate standup. These change how the session starts but don't change how code gets written.

3. **Then add gates.** Process-gate hook, design-before-code requirement. These change how features get built. This is where resistance happens.

4. **Then add sensors.** Automated quality checks that run post-commit. These catch drift without blocking flow.

5. **Then run one feature end-to-end.** The real test. Shape → Design → Specify → Build → Verify → Ship → Learn on a real feature.

#### Deployment Order Template

```
Phase 1: Infrastructure (invisible)
  - Install enforcement hooks
  - Create .enforcement/ directory
  - Create .planning/features/ directory
  - Wire settings.json

Phase 2: Structure (visible, non-blocking)
  - Restructure TODO.md into Mission → Commitment → Task
  - Activate daily standup in CLAUDE.md
  - Activate weekly review cadence
  - Create WEEKLY-REVIEW.md template

Phase 3: Gates (behavior change)
  - Activate process-gate.sh (Shape before Build)
  - Integrate knowledge system into Shape template
  - Make metrics logging mandatory

Phase 4: Sensors (automated quality)
  - Build and wire 5 sensors (or company-appropriate subset)
  - Run initial sensor pass — baseline the current state
  - Don't fix sensor violations immediately — log them

Phase 5: Validation (proof it works)
  - Run one feature through full 7-step process
  - Log metrics: ship time, break rate, quality
  - Compare to previous features (before Sutra)
  - Founder feedback: what helped, what was friction, what to adjust
```

---

### Phase 3: DEPLOY — Execute the Plan

**Input**: Approved DEPLOYMENT-PLAN.md
**Process**: Execute each phase in order, one commit per change
**Output**: Working Sutra installation
**Gate**: Each phase verified before proceeding to next

#### Execution Rules

1. **One phase at a time.** Don't bundle infrastructure + structure + gates in one session.
2. **Verify after each phase.** Does the system still work? Did anything break?
3. **Commit per change.** Clean git history showing exactly what was installed.
4. **Don't fix old bugs.** If sensors find existing issues, log them. Don't fix during deployment. Fixing during deployment confuses "did Sutra break it?" vs "was it already broken?"

---

### Phase 4: VERIFY — Confirm the Installation Works

**Input**: Completed deployment
**Process**: Run the full system through one real feature
**Output**: Verification report + first LEARN.md entry
**Gate**: Founder confirms Sutra is working and helpful (not just installed)

#### Verification Checklist

- [ ] Session starts with standup (Mission, Commitments, blockers)
- [ ] Feature starts with SHAPE.md (process-gate enforces this)
- [ ] Design mockup created before code (if visual change)
- [ ] Knowledge system consulted (which layers, which files)
- [ ] Code written, committed, pushed
- [ ] Sensors run post-commit (no new violations)
- [ ] Metrics logged (ship time, break rate, decision speed)
- [ ] LEARN.md written (surprises, feedback for Sutra)
- [ ] Weekly review includes this feature

---

## Tier-Specific Adjustments

Not every company needs every phase. Tier determines depth:

| Phase | Tier 1 (Personal) | Tier 2 (Product) | Tier 3 (Company) |
|---|---|---|---|
| Infrastructure | Soft hooks only | Mixed hooks | Hard hooks |
| Structure | Simple TODO restructure | Full node structure | Full + department tracking |
| Gates | Soft warnings | Shape is hard, rest soft | All hard |
| Sensors | 2-3 basic sensors | 5 standard sensors | 5+ custom sensors |
| Validation | 1 feature | 1 feature + metrics comparison | 3 features + team review |

---

## After Deployment

Once Sutra is installed:

1. **Remove the deployment priority from CLAUDE.md** (it was a one-time instruction)
2. **Set SUTRA-CONFIG.md to the correct mode** (SUTRA / DIRECT / AUTO)
3. **Start the A/B test if configured** (first 5 features alternate SUTRA/DIRECT)
4. **Schedule the first weekly review** (end of week after deployment)
5. **Send feedback to Sutra** (what worked, what was friction, what's missing)

---

## Evolution

This process will improve with every deployment:
- DayFlow is the first mid-stage onboarding. Learnings feed back here.
- Every conflict, every risk, every "this didn't work" becomes a known pattern.
- The ASSESSMENT template grows as more company types are encountered.
- The MAPPING table expands as Sutra adds more processes.
