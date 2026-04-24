# PEDAGOGY — Sutra Governance Charter

*Version: v1.0.0 · Adopted: 2026-04-24 · Status: active (v1 framework, case-by-case rollout) · Owner: CEO of Sutra*

Sutra's core way of working with humans: **help them first learn, then help them build, and in that journey they grow.**

This charter captures the LEARN → BUILD → GROW framework as Sutra's pedagogy posture. v1 is the framework + principles; implementation ships case-by-case as feedback demands (per `feedback_case_by_case_implementation` memory).

## Purpose

Sutra is not *just* a governance OS. It is a **growth journey** for the human using it. A novice user encountering Sutra for the first time should not face the full governance surface (hooks, depth blocks, BUILD-LAYER, codex directives) — they should first LEARN what these concepts mean, then BUILD real projects with guided assist, then eventually GROW into self-directed power-user mode where Sutra fades into background infrastructure.

Current framing ("governance from day 1") is correct for T1 Asawa-internal but **wrong** for T4 external novices. This charter formalizes the progression.

## 3 Modes (the journey)

| Mode | User state | Sutra posture | Governance intensity | Analog |
|---|---|---|---|---|
| **LEARN** | Doesn't yet know what the OS offers | Teaches concepts, shows, scaffolds; explains before enforcing | Soft enforcement, high explanation | Tutorial / onboarding |
| **BUILD** | Mid-skill; understands concepts, applying them | Assists execution, governance progresses, user produces real work with guidance | Medium enforcement with context | Pair programming |
| **GROW** | Capable; self-directed use of the OS as a tool | Fades into background, enforces only what user has internalized as valuable | Full enforcement, minimal explanation (power-user defaults) | IDE that knows you |

## 8 Principles (ordered by design priority)

1. **Progressive disclosure** — surface the minimum needed for current mode. Unlock more as user demonstrates readiness.
2. **Explain before enforce** — at LEARN level, every blocked action comes with "why" + "how to think about it" alongside the block.
3. **Customer focus first** — pedagogy IS customer focus for novices. Supersedes speed when they conflict.
4. **Respect expertise** — don't force-feed teaching to power users. Detect level; don't assume.
5. **Measurable growth** — level transitions are observable (time-to-first-build, override-explanation-ratio, self-reported skill growth).
6. **Opt-out honored** — users who want to skip LEARN and jump to BUILD can; set `SUTRA_LEVEL=journeyman` (future).
7. **Tier-aware defaults** — T1 Asawa-internal skips LEARN (founder already knows). T4 external defaults to LEARN mode on first install.
8. **Pedagogy ≠ hand-holding** — teach concepts *once* per mode transition; don't re-explain on every use.

## 4 User Levels (finer than the 3 modes)

| Level | Mode | Characteristics | Detection heuristic (inferred) |
|---|---|---|---|
| **L0 Novice** | LEARN | First install; no session history | First plugin install + zero completed tasks |
| **L1 Apprentice** | LEARN → BUILD transition | Understands concepts, first builds | ≥3 completed tasks with depth-blocks, <10 overrides |
| **L2 Journeyman** | BUILD | Produces consistently | ≥10 completed tasks; override-ack-rate ≤20% |
| **L3 Master** | GROW | Self-directed, extends Sutra itself | Has authored a protocol / custom hook / contributed back |

Explicit override: `SUTRA_LEVEL=<novice\|apprentice\|journeyman\|master>` in shell. Auto-detection is advisory; user can always set explicitly.

## Tiered Contract (matches D34 client taxonomy)

| Tier | Default starting level | Upgrade path | Can downgrade? |
|---|---|---|---|
| **T0/T1** Asawa-internal | L2 Journeyman (founder is at L3 but system starts assuming L2 for any internal session) | Automatic via heuristic | Yes, to L0 for teaching purposes |
| **T2** Owned portfolio | L1 Apprentice — operator has Asawa context but may be new to Sutra | Automatic | Yes |
| **T3** Projects (client-owned) | L0 Novice for the client operator | Requires deliberate confirmation at each level boundary | Always |
| **T4** External fleet | L0 Novice on first install | Same — deliberate level confirmation | Always |

## Implementation Primitives (v1 framework → v2 as-needed)

| # | Primitive | v1 state | v2 shippable if feedback demands |
|---|---|---|---|
| 1 | **USER-LEVEL storage** | `~/.sutra/level` file + `SUTRA_LEVEL` env | Auto-detect heuristic daemon |
| 2 | **`/sutra learn <topic>` interactive tutor** | Not built; stub only | Short lessons (charters / protocols / depth / routing / BUILD-LAYER) with live examples from user's files |
| 3 | **Level-aware governance intensity** | Hook rules all fire uniformly | Hooks honor `SUTRA_LEVEL`: at L0, blocks print "why" + "how"; at L3, blocks are silent |
| 4 | **Progressive-disclosure principle** (in CATALOG) | Written into this charter | Promote to top-level principle in `sutra/CATALOG.md` |
| 5 | **Growth telemetry** | Not built | Analytics Dept dimensions: `user_level_transitions`, `first_build_days`, `explanation_to_enforcement_ratio` |
| 6 | **Level-up ceremony** | Not built | Detected transition → one-time congrats + unlocks-gained summary |
| 7 | **Level-down grace** | Not built | Detected struggle → offer temporary downgrade with "why" |
| 8 | **Sutra Tutor agent** | Not built | Separate agent archetype (Socratic, slow-paced) vs Sutra Operator (terse, fast-paced) |

## Key Results (measurable at v2 ship time — v1 is framework-only)

| KR | Target | Measurement method |
|---|---|---|
| KR1 | % T4 new installs reach first successful BUILD within 7 days | Telemetry: install_ts → first completed depth-5 task |
| KR2 | User self-reported skill growth over 30 days | Optional `/sutra feedback --growth-check` prompt (survey-style) |
| KR3 | % governance blocks explained-before-enforced at L0 novice level | `enforce-boundaries.sh` + PROTO-004 + PROTO-021 emit explanation text at L0 |
| KR4 | Retention: % T4 users still active at 30d / 90d | Session telemetry |
| KR5 | Level-transition velocity (L0→L1→L2) | Median days per transition |

## Relationship to Other Charters

- **PRIVACY** (v2.0, shipped) — LEARN mode must explain privacy primitives before the first auto-capture. Novice encountering "we capture signals" needs context.
- **SECURITY** (v1.0, drafted alongside) — LEARN mode teaches D33 / god-mode / permission-gate conceptually before user hits them operationally.
- **TOKENS** — explanation text at L0 costs tokens. Budget: explanation ≤3x the block's original byte count.
- **SPEED** — pedagogy takes time. Speed is core (memory) but Customer Focus First (Principle 0) wins for novices. Reconciliation: speed-to-first-build for novices, speed-to-next-ship for experts.

## Relationship to Three-Product-Tiers

Current memory: Project | CoS | System of CoS (static tiers).

Proposed re-expression as **growth path**: a user journeys through these as they grow —
- **LEARN** mode maps to using Sutra for **Project** tier (single project, operator-as-founder)
- **BUILD** mode maps to **CoS** tier (operator commanding multiple agents/projects)
- **GROW** mode maps to **System of CoS** tier (operator designing new CoS instances)

This ties user-journey to product surface explicitly. Product growth = user growth.

## Conflicts (explicit, to be resolved as shipped)

1. **Governance-from-day-1 vs LEARN-first** — today all users get full PROTO-021 + PROTO-019 + depth blocks. Novice faces enforcement they don't understand. **Resolution**: Level-aware governance in v2.
2. **Markdown-first vs interactive-first teaching** — teaching needs progressive disclosure + curiosity-driven exploration; static docs may be wrong surface. **Resolution**: `/sutra learn` skill when feedback demands.
3. **Default-on vs opt-in pedagogy** — some users want fast start; can't force-feed. **Resolution**: DEFAULT-ON for T4 new installs; DEFAULT-OFF for T1/T2 where operator knows the OS; user can always override via `SUTRA_LEVEL`.
4. **Speed-is-core vs teaching-is-slow** — resolved via tiered default levels (experts skip LEARN) + time-bounded explanations (L0 explanation tax is high but time-limited).

## Review Cadence

- **Monthly**: KR1-KR5 pulse (when v2 primitives ship).
- **Per major Sutra version**: re-read this charter; reconcile if framing drifted.
- **On any LEARN-mode user feedback**: treat as priority input for `/sutra learn` lesson authoring.

## Kill-Switches

| Scope | Kill-switch | Effect |
|---|---|---|
| Per-install | `SUTRA_PEDAGOGY=0` | Skip all LEARN mode explanations; full-power-user defaults |
| Per-session | `SUTRA_LEVEL=master` | Treat this session as L3 regardless of history |
| Fleet | Unship this charter | Fallback to uniform governance (v1 behavior) |

## v1 Scope (what ships with this charter adoption)

- **This document** — framework codified, charter registered.
- **Nothing else** in v1.0.0. Per `feedback_case_by_case_implementation` memory: v2 mechanisms ship only when feedback demands.

Triggers that unpark v2 implementation:
- Any T4 user feedback mentioning "too much governance" / "I don't understand" / "why is this blocked"
- Any T3 onboarding where the operator asks for a simpler start (like Testlify's first-install Stop-hook bug was the trigger for v2.0.1)
- First L0 → L1 transition in telemetry (when we can measure it)

## Prior Art + References

- Memory `project_three_product_tiers` (to be re-expressed as growth path)
- Memory `feedback_speed_is_core` (reconciled via tiered defaults)
- Memory `feedback_case_by_case_implementation` (drives v1 = framework only)
- Memory `project_sutra_vision_apr2026` (CoS agents, System of CoS)
- Asawa parked TODO: `holding/TODO.md` §"Sutra core human pedagogy: learn-then-build-then-grow" (now active via this charter)

---

*Pedagogy is the charter that owns the shape of how humans GROW while using Sutra. Sutra's product is not the OS — it's the journey.*
