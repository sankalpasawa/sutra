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

## Origin

Designed 2026-04-06. Triggered by: OS deployed to 5 companies but only L1 (text) was verified. Principle 0 (Customer Focus) existed in Founding Doctrine but flowed to zero downstream files. The `verify-recursive-flow.sh` script caught 2 gaps, proving L1 verification works. L2-L5 verification did not exist.

Informed by: ISO/SOC2 audit chains (policy → procedure → evidence), Toyota gemba walks (go see the actual work), Ansible desired-state drift detection, franchise inspection cycles, ITIL change management provenance.
