# Sutra — Human-Sutra Interaction Engine

ENFORCEMENT: SOFT (V1 — skill-only, classifier + logger; no hook gate) -> HARD (V2+ — hook-enforced classification, ledger-backed)
STATUS: V1 SHIPPING 2026-05-01 (Phase 2 of `holding/plans/h-sutra-layer-v1.0/PLAN.md`)
DRI: CEO of Asawa (founder direction D42); engine-of-record for the Human-Sutra Interaction Layer charter and all future H-Sutra ADRs.

Charter: `sutra/os/charters/HUMAN-SUTRA-LAYER.md`
ADR (locked decisions): `sutra/os/decisions/ADR-001-h-sutra-9cell-grid.md`

---

## Purpose

The Human-Sutra Interaction Engine is the durable home for the classification layer that labels every founder <-> Sutra <-> Sutra act into one of 9 cells (3 verbs x 3 directions) with 3 orthogonal tags + REVERSIBILITY metadata. The engine **binds** the skill that ships V1 (`core:human-sutra`) to project-level memory, time, and context so that as instrumentation data accrues, behavior-optimization rules can be added without forking doctrine.

Per founder direction D42 (2026-05-01): **Visibility Before Influence**. v1.0 = classifier + logger only. v1.1+ = data-driven rule changes routed through this engine via numbered ADRs.

The current skill (`sutra/marketplace/plugin/skills/human-sutra/`) is V1's raw form — a stateless rule that emits the header tag and persists a log row per turn. This engine is the slot that holds the skill plus the project state the skill alone cannot hold (history of cell distributions, founder-revised guardrails, fleet-state-aware tag inference).

---

## Doctrine — Engine vs Skill

Founder direction (2026-04-27, refined; mirrored from `sutra/os/engines/BLUEPRINT-ENGINE.md`):

| Term | What it is | Analog |
|------|------------|--------|
| **Skill** | Raw form of intelligence — stateless rule, same output every invocation | Knowledge |
| **Engine** | A **bound** (container) for skills + **project-level** memory/time/context | Wisdom |

A **skill** is stateless. Same input -> same output, every time. The H-Sutra V1 skill takes a turn, returns a 9-cell label + 3 tags + REVERSIBILITY, appends a log row, emits a header tag. No state, no memory.

An **engine** is the bound that wraps a set of skills AND binds them to the project's evolving state. The PROJECT is the meta-layer; the founder is one actor; other actors include the codebase, milestones, partners, regulatory state, supply chain, fleet, and time itself.

The three powers an engine has that a skill alone does not — all **project-level**:

| Power | For this engine, project-level meaning |
|-------|----------------------------------------|
| **Memory** | The history of every classified turn (`holding/state/interaction/log.jsonl`) — what cells fired, where over-asking happened, which CLARIFY questions converged, which were demoted to OUT-ASSERT. |
| **Time** | The history of D-direction architecture decisions in `holding/FOUNDER-DIRECTIONS.md` — D42 instituted this layer; D-directions before/after frame what the layer evolves toward. |
| **Context** | Current fleet state — what's running, who's blocked, who's waiting (`bash holding/departments/analytics/fleet.sh`). Tag inference (TIMING, CHANNEL) becomes sharper when the engine knows fleet state. |

**Engine = empty bound by default.** This engine ships V1 with one skill inside and a thin layer of project-state binding (log path declared, D42 cited, fleet hook referenced). As skills accumulate and observed data shapes the doctrine, the engine fills.

**Engines update over time.** Updates are manual at V1; stringent update protocols (when, by whom, with what acceptance criteria) are deferred until the pattern stabilizes — same posture as `BLUEPRINT-ENGINE.md`.

**V1 of any new primitive = a skill inside an empty engine bound.** V2+ fills the bound — skills accumulate, project memory/time/context become legible, the engine begins applying skills with awareness of project state.

---

## What this engine does

V1 surface area, three responsibilities:

| Responsibility | What it does | Where it lives |
|----------------|--------------|----------------|
| **Classification** | For every turn, determine principal_act (DIRECT/QUERY/ASSERT) + direction (INBOUND/INTERNAL/OUTBOUND) + mixed_acts using precedence DIRECT > QUERY > ASSERT. | Skill: `core:human-sutra` (Task 2.4) |
| **Tag inference** | Infer TENSE (past/present/future), TIMING (now/later/recurring), CHANNEL (in-band/out-of-band). Compute REVERSIBILITY + decision_risk via denylist + sensitive-domain keyword scan. | Skill: `core:human-sutra` (Task 2.4) |
| **Persistence** | Append one row per turn to `holding/state/interaction/log.jsonl` (atomic JSONL). Fail-CLOSED on the row write (skip on classifier crash, never half-write); fail-OPEN for downstream skills (missing row never blocks Edit/Write/Bash). | Classifier bash script (Task 2.3) |

V1 does NOT do:

- Hook-enforced gating (deferred to V2 if drift observed)
- Behavior-optimization rules beyond the 4 charter guardrails (deferred to v1.1+ via ADR-002)
- Tag inference using project context (e.g., fleet-state-aware CHANNEL routing) — deferred to v1.1+
- Cross-session continuity / memory of recurring task shapes (deferred to v1.2+)

Surface invariant (charter Stage-3-only emission rule): only Stage 3 SURFACE may emit founder-visible output. The engine binds skills that respect this invariant; it does NOT introduce new surfacing paths.

---

## Skills bound by this engine

| Skill | Path | Status | Role |
|-------|------|--------|------|
| `core:human-sutra` | `sutra/marketplace/plugin/skills/human-sutra/SKILL.md` | V1 (shipped at commit 106a94a) | Per-turn classifier + tag inference + log-row emission + header tag rendering. |

V1 ships with **one** skill inside this bound. V2+ candidates (require ADR per evolution discipline below):

| Future skill (illustrative, NOT committed) | Trigger to add |
|--------------------------------------------|----------------|
| `core:human-sutra-aggregator` | once 100-500 turns logged, periodic distribution summary becomes useful. |
| `core:human-sutra-cohort-routing` | once cell distributions diverge meaningfully across fleet cohorts (T2 owned vs T3 projects vs T4 fleet). |
| `core:human-sutra-irreversibility-tuner` | once denylist false-positives / false-negatives are measurable. |

These are NOT shipped. They are placeholders to make the bound's intent legible. Each requires its own ADR + regression test before it lands.

---

## Future direction routes here

**Future founder direction containing the words "h-sutra", "human-sutra", "interaction layer", "9-cell grid", "interaction classification", "OUT-QUERY", "OUT-ASSERT", "OUT-DIRECT", "REVERSIBILITY tag", "TENSE/TIMING/CHANNEL", or any variation referencing the v1.0 charter primitives -> improvements route to this engine.**

This is the durable home for all H-Sutra-related improvements. Memory entry (forthcoming, post Task 2.7) will carry the routing rule so it surfaces in future conversations. Do NOT spawn parallel doctrine for h-sutra variants — extend this engine via ADR.

ADR routing (canonical evolution path):

| ADR | Topic | Status |
|-----|-------|--------|
| ADR-001 | 9-cell CQRS-extended grid + 3 tags + 4 safety rules (v1.0 baseline) | accepted, 2026-05-01 |
| ADR-002+ | Behavior-optimization rules (over-asking fix, confidence-gate tuning, retry tuning), AUDIENCE/SEVERITY/CONTINUITY tags, new cells (e.g., META-*), log rotation policy, cohort-aware routing | proposed only after 100-500 turns of instrumented data |

Every future ADR MUST:

1. Cite at least one real prior interaction the v_n schema failed to capture.
2. Add at least one new fixture to `sutra/marketplace/plugin/skills/human-sutra/tests/fixtures.json` demonstrating the new shape catches it.
3. Keep ADR-001's 13-fixture regression set passing — failure is a blocker.
4. Land in `sutra/os/decisions/` as a numbered file before the engine binds any new skill or rule.

This mirrors ADR-001's evolution discipline (charter § Evolution discipline) and the architecture-decision-record literature (Nygard, 2011).

---

## Project state binding

The three project-level powers, mapped to concrete files / commands the engine reads:

| Power | Surface | What the engine reads |
|-------|---------|-----------------------|
| **Memory** | `holding/state/interaction/log.jsonl` (the INTERACTION-LOG; one row per classified turn; charter § Logging schema) | Aggregate cell distribution; over-asking rate (OUT-QUERY count vs principal_act=DIRECT count); CLARIFY-then-demote frequency; denylist hit rate; STAGE-1-FAIL retry outcomes. |
| **Time** | `holding/FOUNDER-DIRECTIONS.md` (D-direction registry; D42 = the directing instruction for this engine; future D-directions framing the evolution) | Architecture decisions over time; doctrine generations; priority resets; the precise founder words that trigger ADR-N+1. |
| **Context** | `bash holding/departments/analytics/fleet.sh` (fleet snapshot — who's running Sutra, who's blocked, who's waiting) | Current fleet state; cohort breakdown; TIMING / CHANNEL inference inputs (e.g., founder-presence -> in-band default vs out-of-band when away). |

V1 wires these surfaces declaratively (paths declared, skill knows where they live). V1 does NOT actively read them at classification time — the V1 skill is stateless. V2+ adds engine-side reads that bias tag inference and routing using the bound state.

Binding rules:

- **Memory append is fail-CLOSED at the row level** (charter Phase 3.4): a corrupted classifier MUST skip the row, never half-write. Recovery is by re-classifying on next turn — no retroactive fix-up.
- **Memory read is fail-OPEN** (V2+): if `log.jsonl` is missing or unparseable, the engine falls back to V1 stateless behavior. A broken log MUST NEVER block Edit/Write/Bash.
- **Time binding** is read-only — D-direction registry is the founder's authoring surface; the engine cites it but never writes it.
- **Context binding** is read-only and best-effort — fleet snapshot may be stale; tag inference treats fleet state as a hint, not a contract.

---

## Related

- Charter (policy layer): `sutra/os/charters/HUMAN-SUTRA-LAYER.md`
- ADR-001 (locked decisions): `sutra/os/decisions/ADR-001-h-sutra-9cell-grid.md`
- Skill (raw rule, V1): `sutra/marketplace/plugin/skills/human-sutra/SKILL.md` (shipped at commit 106a94a)
- Classifier script: `sutra/marketplace/plugin/skills/human-sutra/scripts/classify.sh` (shipped at commit 7a32af4)
- Founder direction: D42 in `holding/FOUNDER-DIRECTIONS.md` (shipped at commit 8305df8)
- Plan: `holding/plans/h-sutra-layer-v1.0/PLAN.md`
- Codex verdict (R2 PASS, DIRECTIVE-ID 1777572677): `.enforcement/codex-reviews/2026-05-01-h-sutra-v1.0-plan-consult.md`
- Sibling engine (shape reference): `sutra/os/engines/BLUEPRINT-ENGINE.md`
