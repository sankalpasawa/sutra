# Sutra — System Health Protocol

## What This Is

A taxonomy of everything that happens when systems grow, and the protocols needed to keep them healthy. Growth is not just "more" — it introduces entropy, decay, bloat, drift, and debt across every dimension. This protocol defines what maintenance a growing system needs, when to run it, and how to detect the trigger.

## The Core Insight

Lehman's Laws of Software Evolution (1974): a system will increase in entropy unless specific work is done to reduce it. This mirrors the second law of thermodynamics — disorder increases unless energy is spent maintaining order. Every system — code, docs, protocols, products, orgs — follows this law.

**Healthy growth** = complexity increases AND maintenance keeps pace.
**Bloat** = complexity increases WITHOUT corresponding maintenance.

The difference is not size. It is the ratio of value-bearing complexity to dead-weight complexity.

---

## 1. Taxonomy of Growth Protocols

Every growing system needs ALL of these. They are not interchangeable.

| # | Protocol | Definition | What Decays Without It | Trigger |
|---|----------|-----------|----------------------|---------|
| G1 | **Refactoring** | Restructure internals without changing behavior | Code readability, change velocity | Touching a module takes 2x longer than it should |
| G2 | **Pruning** | Remove features, code, docs that no longer serve a purpose | Surface area, cognitive load | Feature has <5% usage OR 0 engagement for 30 days |
| G3 | **Consolidation** | Merge duplicates into single source of truth | Confusion, contradictions, drift | 2+ artifacts cover the same concept |
| G4 | **Deprecation** | Mark something as end-of-life with a sunset timeline | Zombie features, maintenance burden | Replacement exists AND migration path is clear |
| G5 | **Archival** | Move completed/historical items out of active view | Signal-to-noise ratio in active workspace | Item is done, resolved, or >90 days inactive |
| G6 | **Migration** | Move from old pattern/tool/structure to new one | Tech debt accumulation, split-brain | New standard adopted but old instances remain |
| G7 | **Documentation Gardening** | Update docs to match current reality | Docs rot, new users get lost | Any structural change to code/process |
| G8 | **Dependency Audit** | Review and update external dependencies | Security vulns, compatibility drift | Monthly OR after any security advisory |
| G9 | **Toil Reduction** | Automate repetitive manual work | Operator burnout, error rate increase | Same manual task performed 3+ times |
| G10 | **Complexity Budgeting** | Cap the number of active protocols/features/docs | Unbounded growth, decision paralysis | Addition requires removal (already in PROTO creation) |
| G11 | **Drift Detection** | Verify actual behavior matches documented behavior | Reality diverges from docs/config | After any deploy OR weekly audit |
| G12 | **Capacity Review** | Assess if current architecture handles current load | Performance degradation, outages | Usage doubles OR response time degrades 50% |
| G13 | **Knowledge Refresh** | Re-evaluate assumptions against current environment | Stale strategy, missed opportunities | AI/tech/market: weekly; framework/methodology: bi-weekly; OR after major market shift |
| G14 | **Kill/Pivot Check** | Evaluate whether a live company deserves continued investment | Zombie companies consuming attention with zero traction | 4 weeks post-launch, then monthly |

---

## 2. Cadence Recommendations

Based on patterns from Google SRE, Spotify, Amazon, Basecamp, and mature open-source projects.

| Cadence | Protocols | How |
|---------|-----------|-----|
| **Every session** | G7 (doc gardening), G11 (drift detection) | Built into session-end checklist |
| **Every feature ship** | G1 (refactor touched code), G9 (automate new toil) | Part of feature lifecycle |
| **Weekly** | G5 (archive done items), G3 (consolidate if duplicates found) | Weekly planning process |
| **Monthly** | G8 (dependency audit), G2 (prune unused features), G14 (kill/pivot check for live companies) | Dedicated maintenance session |
| **Weekly** | G13 — AI/tech/market domain research | Weekly review |
| **Bi-weekly** | G13 — framework/methodology research (Cynefin, Wardley, Shape Up, etc.) | Bi-weekly review |
| **Quarterly** | G6 (migration backlog), G12 (capacity review) | Quarterly review |
| **On trigger only** | G4 (deprecation), G10 (complexity budget) | When threshold is crossed |

**Key principle from SRE**: Google keeps toil below 50% of engineer time. The other 50% goes to work that reduces future toil. For Sutra: at least 20% of sessions should be maintenance, not feature work.

---

## 3. Trigger-Based vs Schedule-Based

Schedules catch slow decay. Triggers catch acute problems. You need both.

| Signal | What It Means | Protocol to Run |
|--------|--------------|----------------|
| Ship time for a feature is 2x average | Codebase friction increasing | G1 (refactoring) |
| Same question asked 3x by agent/human | Doc is missing or wrong | G7 (doc gardening) |
| Protocol fires 0 times in 30 days | Protocol may be dead weight | G2 (pruning) or G4 (deprecation) |
| 2+ docs describe the same thing | Duplication crept in | G3 (consolidation) |
| Manual step performed 3+ times | Toil accumulating | G9 (toil reduction) |
| New tool/pattern adopted | Old instances still exist | G6 (migration) |
| Feature usage drops to near-zero | Kano decay — delight became indifferent | G2 (pruning) |
| Error rate spikes after deploy | Drift between expected and actual | G11 (drift detection) |
| Total protocol count exceeds cap | System is getting heavier | G10 (complexity budgeting) |
| Done items cluttering active views | Noise drowning signal | G5 (archival) |
| Live company at 4+ weeks with zero users, zero revenue, zero learnings | Zombie company consuming resources | G14 (kill/pivot check) |

---

## 4. The Healthy Growth Test

Run this quarterly. Five questions.

| # | Question | Healthy | Unhealthy |
|---|----------|---------|-----------|
| 1 | Can a new session orient in <2 minutes? | Yes — clear entry points, current docs | No — stale docs, confusing structure |
| 2 | Is every active file serving a current purpose? | Yes — no zombie files | No — files from 3 months ago untouched |
| 3 | Does adding something require removing something? | Yes — complexity is budgeted | No — everything just accumulates |
| 4 | Are protocols actually firing? | Yes — each fires 1+/month | No — half are dormant |
| 5 | Is maintenance happening without being asked? | Yes — built into cadence | No — only happens in crisis |

---

## 5. Where This Lives in Sutra

```
sutra/layer2-operating-system/
├── a-company-architecture/
│   ├── CONTINUOUS-IMPROVEMENT.md    ← How findings flow (exists)
│   ├── SYSTEM-HEALTH.md            ← THIS FILE: what maintenance to run, when
│   └── processes/
│       ├── ... (existing processes)
│       └── MAINTENANCE-CYCLE.md     ← (future) Executable maintenance checklist
```

**Relationship to existing Sutra:**
- `CONTINUOUS-IMPROVEMENT.md` = how findings flow through the system (reactive)
- `SYSTEM-HEALTH.md` = what proactive maintenance the system needs (proactive)
- `PROTOCOLS.md` (creation lifecycle section) already has complexity budgeting (protocol count cap of 10)
- `VERSION-UPDATES.md` already has the evolution protocol for Sutra itself

This file adds the PROACTIVE dimension. Continuous improvement catches problems after they appear. System health prevents problems before they appear.

---

## 6. Examples From Real Organizations

| Organization | Practice | Maps To |
|-------------|----------|---------|
| **Google SRE** | Error budgets — spend budget on experiments, freeze deploys when exhausted | G12 (capacity review) |
| **Google SRE** | Toil cap at 50% — remaining time is engineering to reduce toil | G9 (toil reduction) |
| **Netflix** | Chaos Monkey — randomly kill services to test resilience | G11 (drift detection) |
| **Amazon** | Two-pizza teams — cap team size to cap coordination overhead | G10 (complexity budgeting) |
| **Basecamp** | Shape Up 6-week cycles with 2-week cooldown for cleanup | G1 (refactoring), G5 (archival) |
| **Martin Fowler** | 15-20% of sprint capacity allocated to refactoring | G1 (refactoring) |
| **Spotify** | Guilds for cross-cutting concerns; chapters for functional alignment | G3 (consolidation) |
| **Stripe** | API versioning with explicit deprecation timelines | G4 (deprecation) |
| **Canonical/Ubuntu** | Diataxis framework — 4 doc types, each maintained separately | G7 (doc gardening) |
| **Kent Beck** | "Make the change easy, then make the easy change" | G1 (refactoring) |
| **Wardley Mapping** | Components evolve genesis → custom → product → commodity | G13 (knowledge refresh) |
| **Cynefin** | "Clockwise drift" — neglected systems fall from clear to chaotic | The whole protocol |

---

## 7. Kill/Pivot Protocol

| # | Protocol | Definition | What Decays Without It | Trigger |
|---|----------|-----------|----------------------|---------|
| G14 | **Kill/Pivot Check** | Evaluate whether a live company deserves continued investment | Zombie companies consuming attention with zero traction | 4 weeks post-launch, then monthly |

### How It Works

The kill/pivot check fires automatically at 4 weeks after a company goes live, then monthly thereafter. It is not optional — every live company gets evaluated.

```
KILL/PIVOT CHECK (fires at 4 weeks post-launch, then monthly):
- Users: any real users? (not founder, not test accounts)
- Revenue: any revenue or clear path within 30 days?
- Learning: did we learn something that justifies continuing?

All three NO → escalate to founder: kill, pivot, or extend with specific hypothesis.
```

**Evaluation rules:**
- **Any signal = continue.** Even one real user or one validated learning justifies the next month.
- **All three NO = escalation.** The founder must make an explicit decision: kill, pivot, or extend. "Extend" requires a specific hypothesis to test in the next 30 days — not "let's keep going and see."
- **Kill is not failure.** A company killed at 4 weeks with clear learnings is a success. A company limping at 6 months with no signal is the failure.
- **Log the decision.** Whether kill, pivot, or extend — record the reasoning in the company's checkpoint file.

**Cadence integration:** Add to the monthly maintenance cycle (Section 2). The check runs alongside G8 (dependency audit) and G2 (pruning).

*Inspired by Pieter Levels' approach: launch fast, measure signal, kill without sentiment.*

---

## 8. The One-Line Summary

**Growth without maintenance is decay with extra steps.**

Every session that adds something should ask: what can I remove, consolidate, or archive? Not as guilt — as hygiene. Like brushing teeth. The system that maintains itself stays small even as it grows large.

---

*Protocol candidate for Sutra PROTO-011 or integration into existing processes.*
*Research date: 2026-04-05*
*Sources: Lehman's Laws, Google SRE Handbook, Martin Fowler (Technical Debt Quadrant), Kano Model, Diataxis Framework, Wardley Mapping, Cynefin Framework, Netflix Chaos Engineering, Amazon Two-Pizza Teams, Basecamp Shape Up.*
