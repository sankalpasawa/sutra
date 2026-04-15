# Sutra — Deployment Model

> Deployment is not "files exist." Deployment is "behavior changed."

This document defines what it means for any principle, protocol, or feature to be "deployed." PROTO-013 (version deploy) references this model. The verification scripts (`verify-os-deploy.sh`, `verify-recursive-flow.sh`) check against it.

---

## The Deployment Ladder

Every principle, protocol, and feature climbs 5 layers. Each layer has a verification method and a cost. A thing is "fully deployed" when it reaches the appropriate layer — not everything needs L5.

```
L5 EVOLVE     The thing improved based on feedback with provenance
L4 ENFORCE    A hook prevents violation (mechanical)
L3 BEHAVE     Real sessions produce artifacts showing the behavior
L2 STRUCTURE  Protocols, engines, or processes embody the principle
L1 TEXT       The thing is written in the right files
```

### L1: Text Exists

The principle/protocol/feature is written in the right files at the right layers (Doctrine, Asawa, Sutra, Company).

**Verify**: `grep` for it. `verify-recursive-flow.sh` checks this.
**Get here**: Write it. Propagate downstream per PROTO-013.
**Cost**: Minutes.
**Sufficient for**: Internal-only documentation, reference principles that don't drive behavior directly.

### L2: Structure Exists

The principle shapes at least one protocol, engine, or process. There's a traceable link: "This protocol exists BECAUSE of this principle."

**Verify**: For each principle, list which protocols implement it. If zero, L2 is incomplete.
**Get here**: When writing any protocol, check each principle and ask: "does this protocol embody this principle?" If a principle has zero implementing protocols, create one or document why it doesn't need one.
**Cost**: Hours.
**Sufficient for**: Principles that guide design decisions but don't need per-task enforcement.

**Traceability format** (add to protocol headers):
```
implements: [P0, P3, D26]
```

### L3: Behavior Exists

Real sessions produce artifacts showing the behavior. Not "the instructions say to do it" but "the logs prove it was done."

**Verify**: Read session artifacts — estimation logs, git commits, triage entries, feedback files. Does the behavior appear?
**Get here**: Run real tasks with the OS active. If the behavior doesn't appear, the instructions are unclear — rewrite until they produce the behavior naturally.
**Cost**: Days (needs real usage — at least 5 sessions).
**Sufficient for**: Most features. If L3 shows > 80% compliance, L4 (hooks) is unnecessary friction.

**Evidence types**:
- Estimation log entries with `depth_selected` and `triage_class`
- Git commits referencing depth assessments
- Feedback files in `feedback-to-sutra/`
- Session artifacts (plans, research docs) at appropriate depth

### L4: Enforcement Exists

A hook mechanically prevents violation. Not advisory — blocking. The system cannot proceed without compliance.

**Verify**: Try to violate it. Does the hook block?
**Get here**: Only after L3 shows persistent non-compliance (< 80% over 5+ sessions). Hooks add friction — only add when the cost of non-compliance exceeds the cost of friction.
**Cost**: Hours to build, permanent friction cost per session.
**Sufficient for**: Critical features where non-compliance causes real harm (boundary isolation, auth, data safety).

**Escalation path**:
```
L3 compliance < 80%
  --> Rewrite instructions (try to fix at L1/L2 first)
  --> If still < 80% after rewrite
  --> Add advisory hook (soft reminder)
  --> If still < 80% after advisory
  --> Add blocking hook (L4)
```

### L5: Evolution Happened

The thing has improved based on feedback, and the change has provenance. The feedback loop is closed — usage data feeds back, the principle/protocol gets refined, the system gets better.

**Verify**: Git history shows the thing changed, and the commit has a TRIGGER/SOURCE/EVIDENCE block.
**Get here**: Close the feedback loop. This can't be rushed — needs enough usage data to learn from.
**Cost**: Weeks to months.
**Sufficient for**: Mature features that have been through multiple real-world cycles.

---

## Change Provenance (mandatory for any mutation)

Every change to a principle, protocol, or process at any layer must have provenance. No "good idea" changes.

**Three valid sources:**

| Source | What It Is | Example |
|--------|-----------|---------|
| **Customer feedback** | A specific incident or pattern from usage | Founder said "what does gear mean?" — renamed to "depth" |
| **Usage data** | Triage, estimation, or adoption scorecard numbers | Overtriage rate 40% on feed-features — lowered default depth |
| **OKR objective** | A measurable goal driving the change | "Reduce governance overhead to < 15%" — deferred session-start files |

**Never valid:**
- "Seems like a good idea" without evidence
- "Best practice" without our own validation
- "Cleaner architecture" without a problem it solves
- "Other companies do this" without proving it applies to us

**Commit format for changes with provenance:**
```
TRIGGER: [what happened — the specific event or data point]
SOURCE: feedback | data | OKR
EVIDENCE: [incident reference, number, or goal ID]
```

---

## Deployment Depth by Type

Not everything needs L5. The appropriate deployment depth depends on what's being deployed:

| Type | Target Depth | Rationale |
|------|-------------|-----------|
| Founding Principle | L2 minimum | Must shape structure, not just exist as text |
| Sutra Protocol | L3 minimum | Must produce behavior in real sessions |
| Engine Feature (depth, estimation) | L3, escalate to L4 if < 80% | Must produce artifacts |
| Company-specific Process | L3 minimum | Must be followed in that company's sessions |
| Enforcement Hook | L4 by definition | Hooks ARE L4 |
| Session Instruction (CLAUDE.md) | L3 minimum | Must produce visible behavior |

---

## The Deployment Audit

Run periodically (weekly review, every OS deploy) to check deployment depth across the system.

**Script**: `bash holding/hooks/verify-recursive-flow.sh` (checks L1 text flow)
**Script**: `bash holding/hooks/verify-os-deploy.sh <company>` (checks L1-L4 per company)
**Manual**: L3 behavior check requires reading session artifacts
**Manual**: L5 evolution check requires reading git history for provenance

**Audit output format**:

```
DEPLOYMENT DEPTH AUDIT
======================

                    L1     L2        L3        L4       L5
                    TEXT   STRUCTURE BEHAVIOR  ENFORCE  EVOLVE

P0 Customer Focus   YES    ?         ?         NO       NO
D26 Depth System    YES    YES       X entries NO       NO
PROTO-014 Version   YES    YES       ?         NO       NO
...

Target vs Actual:
  Principles at L2+:    X/Y
  Protocols at L3+:     X/Y
  Engine features at L3+: X/Y
  Gap count: Z
```

---

## Integration with PROTO-013

PROTO-013 Phase 3 (Verify) maps to this model:
- Level 1 verification = L1 (text exists)
- Level 2 verification = L3 (behavior appears in session)
- Level 3 verification = L3 (adoption scorecard over 5 sessions)
- Level 4 verification = L4 (hook prevents violation)

PROTO-013 Phase 4 (Graduation) maps to L2 → L3 transition.
PROTO-013 Phase 5 (Deprecation) is reverse deployment — L5 → L4 → L3 → L2 → L1 removal.

---

## Frequency

| Check | When | Script |
|-------|------|--------|
| L1 recursive flow | Every OS deploy, weekly review | `verify-recursive-flow.sh` |
| L1-L4 per company | Every OS deploy | `verify-os-deploy.sh <company>` |
| L3 behavior audit | After 5 sessions with new feature | Manual: read estimation log |
| L5 evolution check | Monthly review | Manual: git log with provenance |
| Full deployment audit | Monthly, or after major OS version | All scripts + manual checks |

---

## Proof Artifacts (every principle names its evidence)

Borrowed from ISO/SOC2: documentation without named evidence is theater. Each principle, protocol, and feature must declare what PROVES it's implemented. Not "exists in file" — "produced this artifact in a real session."

| Principle/Feature | Proof Artifact | Where to Find It |
|-------------------|---------------|-----------------|
| P0 Customer Focus | Zero unexplained jargon in session output | Session transcript review |
| P9 Don't Hardcode | Company-specific params in SUTRA-CONFIG, not in engine | Grep engine for hardcoded company names |
| D26 Depth System | `depth_selected` entries in estimation-log.jsonl | `grep depth_selected os/engines/estimation-log.jsonl` |
| PROTO-014 Version Check | Version comparison output at session start | Session transcript first 20 lines |
| Estimation Engine | `estimated_tokens` + `actual_tokens` entries in log | `wc -l os/engines/estimation-log.jsonl` |
| Triage Logging | `triage_class` entries in estimation log | `grep triage_class os/engines/estimation-log.jsonl` |
| Feedback Loop | Files in `os/feedback-to-sutra/` | `ls os/feedback-to-sutra/*.md` |
| Input Routing | Classification block before actions | Session transcript |
| Boundary Isolation | Hook blocks edit outside company dir | `bash .claude/hooks/enforce-boundaries.sh` with outside path |

If a principle has no named proof artifact, it is not deployable — it's just prose.

---

## Briefback Pattern (from military doctrine)

Before executing any task that implements a principle, the agent RESTATES which principle it's applying and why. This is the military "briefback" — subordinates explain the plan back before executing.

In practice: the depth assessment block IS a briefback. "TASK: X | DEPTH: 3 | IMPACT: Y" is the agent saying "here's what I'm about to do and how deep I'm going." The principle (D26) is embodied in the output, not just referenced.

Extend this: when a protocol fires, the agent should state which principle triggered it. "Input routing per D3 — every task has a Sutra path." This makes the principle-to-behavior link visible in every session.

---

## Desired State Convergence (from Ansible/Puppet)

The verification scripts should not just CHECK state — they should CONVERGE toward it. If `verify-recursive-flow.sh` finds P0 missing from Sutra's operating model, it shouldn't just report FAIL — it should offer to fix it.

Current: scripts report gaps.
Target: scripts report gaps AND generate the fix command.

```
[FAIL] Principle 0 NOT in Sutra operating model
       FIX: Add P0 to sutra/layer2-operating-system/OPERATING-MODEL.md
       RUN: bash holding/hooks/fix-deployment-gap.sh P0 sutra
```

This is future work — build when the gap detection is mature enough.

---

## Change Provenance Format (from ITIL + Legal + Medical)

Every mutation at any layer uses this format in commit messages:

```
TRIGGER: [specific event — incident, data point, feedback, OKR]
SOURCE:  [customer | data | OKR | incident]
EVIDENCE: [reference — session date, log entry, founder quote, metric]
GRADE:   [I: direct evidence | II: pattern | III: judgment]
```

Evidence grading (from medical protocols):
- **Grade I**: Direct observation or data (founder said X, log shows Y)
- **Grade II**: Pattern across multiple instances (3 sessions showed Z)
- **Grade III**: Judgment call with rationale (no direct evidence, but reasoning is...)

Grade III changes are provisional — they should be re-evaluated after 5 uses. Grade I changes are permanent unless contradicted by new Grade I evidence.

---

## Origin

Designed 2026-04-06.

TRIGGER: OS deployed to 5 companies but only L1 (text) verified. P0 had zero downstream flow.
SOURCE: data (deployment depth audit)
EVIDENCE: verify-recursive-flow.sh caught 2/27 gaps. L3 had 3 triage entries total across all companies.
GRADE: I (direct observation)

Research sources (2026-04-06):
- ISO/SOC2 audit chains (policy > control > procedure > evidence)
- Military doctrine cascade (doctrine > OPORD > briefback > AAR)
- Toyota gemba walks (standard at execution point, not in binder)
- McDonald's franchise inspection (binary checklist, score, coach)
- Ansible/Puppet desired-state convergence (declare, enforce, detect drift)
- ITIL change management (trigger > justification > approval > linkage)
- Medical protocol updates (evidence-graded triggers, citation chains)
- Legal regulatory process (legislative intent, RIA, notice-and-comment)
- Git/RFC/ADR provenance (conventional commits, linked issues, decision records)
