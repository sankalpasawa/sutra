# ADR-001: Human-Sutra Interaction Layer — 9-Cell CQRS-Extended Grid + 3 Tags

- **Status**: accepted
- **Date**: 2026-05-01
- **Author**: CEO of Asawa session (Claude) + founder Sankalp
- **References**:
  - Charter: `sutra/os/charters/HUMAN-SUTRA-LAYER.md` (Task 2.1, written after this ADR)
  - Engine of record: `sutra/os/engines/HUMAN-SUTRA-ENGINE.md` (Task 2.2, future)
  - Skill: `sutra/marketplace/plugin/skills/human-sutra/SKILL.md` (Task 2.4, future)
  - D-direction: D42 in `holding/FOUNDER-DIRECTIONS.md` (Task 2.7, future)
  - Codex verdict (R2 PASS): `.enforcement/codex-reviews/2026-05-01-h-sutra-v1.0-plan-consult.md`
  - Prior DESIGN consult brief: `holding/research/2026-04-30-h-sutra-layer-codex-consult.md`
  - Prior framing (superseded): `sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` (policy layer; this ADR adds the missing classification layer)

---

## Decision table (compact, codex P3.7 fold)

The full taxonomy at a glance. 3 verbs (QUERY / ASSERT / DIRECT) × 3 directions (INBOUND / INTERNAL / OUTBOUND) = 9 cells. Read top-to-bottom in <30s.

| principal_act | mixed_acts (allowed secondary) | stage_owner | allowed_outbound_forms | gate_condition | default_on_ambiguity |
|---|---|---|---|---|---|
| IN-QUERY | ASSERT | Stage 1 (INTAKE) | n/a (inbound) | confidence ≥ 0.7 OR named-referent resolvable | route to OUT-QUERY (CLARIFY) |
| IN-ASSERT | QUERY | Stage 1 (INTAKE) | n/a (inbound) | claim has identifiable target (file / decision / artifact) | route to OUT-QUERY (CLARIFY) |
| IN-DIRECT | ASSERT, QUERY | Stage 1 (INTAKE) | n/a (inbound) | irreversibility flag set OR target resolvable | route to OUT-QUERY (CLARIFY) |
| INT-QUERY | (none) | Stage 2 (PROCESSING) | n/a (internal) | callee in registry; call budget remaining | abort with INT-ASSERT (failure) up the chain |
| INT-ASSERT | (none) | Stage 2 (PROCESSING) | n/a (internal) | sender identifiable; payload schema-valid | drop; log to triage |
| INT-DIRECT | (none) | Stage 2 (PROCESSING) | n/a (internal) | callee exists; auth/scope satisfied | refuse; surface as OUT-ASSERT (DISAGREE) |
| OUT-QUERY | (none — pure ask) | Stage 3 (SURFACE) | CLARIFY | named variable + why-default-unsafe + one-turn-answerable ALL satisfied | demote to OUT-ASSERT (INFORM) with stated assumption |
| OUT-ASSERT | (none — pure tell) | Stage 3 (SURFACE) | INFORM, DISAGREE, ACK | content has source (artifact / log / verdict) | suppress; do not fabricate |
| OUT-DIRECT | (none — pure ask-to-act) | Stage 3 (SURFACE) | ASK·LATER, HANDOFF, CASCADE | recipient identifiable + action atomic + reversibility known | refuse; emit OUT-ASSERT (DISAGREE) explaining gap |

**Classification precedence for mixed acts**: `DIRECT > QUERY > ASSERT`. A turn that contains a directive plus a question plus an assertion is logged as principal=DIRECT with `mixed_acts=[QUERY, ASSERT]`.

**REVERSIBILITY** is execution metadata, not a 4th tag — see Decision §4.

---

## Context

Sutra v1.9.1 already has policy at the human-Sutra seam (Sovereignty Contract, Override Protocol, Involvement Levels in `c-human-agent-interface/HUMAN-AGENT-INTERFACE.md`) and per-turn governance blocks (Input Routing TYPE classifier, Depth + Estimation, BLUEPRINT, Build-Layer, Codex review). What it lacks is a **MECE classification of the interaction itself** — a way to label every founder→Sutra, Sutra↔Sutra, and Sutra→founder act so that flow becomes visible before any optimization is attempted.

Founder direction (D42, 2026-05-01):

> "first I want to institute the above framework, so I get visibility of the flow and then influence it as per the way which is efficient"

This is the **Visibility Before Influence** principle. Translation into ADR terms: ship classification + logging in v1.0; defer all rule changes (over-asking fixes, retry tuning, gate-rule refactors) to v1.1+ once 3-4h of real instrumented data exists. (Memory: `[Wait for data before optimizing]`.)

The existing Input Routing skill classifies founder TYPE (direction / task / feedback / new-concept / question) but does not cover (a) Sutra-internal traffic between main session and subagents, (b) outbound emissions back to the founder, or (c) cross-cutting properties like tense / timing / channel. v1.0 fills this gap with a single MECE grid + 3 tags + 4 safety rules — minimum-viable, evolve via ADR-with-regression-test.

---

## Decision

### 1. The 9-cell CQRS-extended grid

Two axes, three values each, 9 cells.

|  | QUERY | ASSERT | DIRECT |
|---|---|---|---|
| **INBOUND** (founder → Sutra) | IN-QUERY ("what is X?") | IN-ASSERT ("you missed Y" / critique) | IN-DIRECT ("do X" / "build it") |
| **INTERNAL** (Sutra ↔ Sutra) | INT-QUERY (subagent asks main for context) | INT-ASSERT (codex verdict / subagent result) | INT-DIRECT (main dispatches subagent / handoff) |
| **OUTBOUND** (Sutra → founder) | OUT-QUERY (CLARIFY — gating question) | OUT-ASSERT (INFORM / DISAGREE / ACK) | OUT-DIRECT (ASK·LATER / HANDOFF / CASCADE) |

Verbs are CQRS-extended: QUERY (read, no state change), ASSERT (declare a fact / claim), DIRECT (request state change / action). MECE holds because (a) every act is either reading, telling, or asking-to-act and (b) every act has exactly one source-target direction in {founder→sutra, sutra↔sutra, sutra→founder}.

### 2. Three orthogonal tags (v1 minimum)

```
TENSE     past | present | future        (what content references)
TIMING    now  | later   | recurring     (when execution happens)
CHANNEL   in-band | out-of-band          (outbound delivery surface)
```

Why these three: TENSE separates "what shipped" from "what's shipping" from "what will ship" (load-bearing for INFORM vs ASK·LATER routing); TIMING separates immediate execution from deferred reminders from recurring cron-like work (load-bearing for routing into Sutra schedule vs immediate action); CHANNEL separates terminal output from out-of-band notifications (Resend email, push, etc.). AUDIENCE / SEVERITY / CONTINUITY were considered (see Alternatives §c) and deferred.

### 3. REVERSIBILITY as execution metadata (NOT a 4th tag)

REVERSIBILITY ∈ {reversible, irreversible} is captured per turn but lives as **execution metadata on the act**, not as a tag. Reasoning: tags describe the act's content/timing/surface; REVERSIBILITY describes downstream consequence and gates the safety rules (§4). Mixing them inflates the tag space without adding classification power.

REVERSIBILITY is stamped at Stage 1 for IN-DIRECT (and at Stage 2 for INT-DIRECT) by the classifier. It is logged alongside the cell in `holding/state/interaction/log.jsonl`.

### 4. Four safety rules

**Rule 1 — Classification precedence `DIRECT > QUERY > ASSERT`** (mixed acts).
A single turn can carry multiple acts. The principal act is the one with highest precedence; the rest are logged in `mixed_acts`. Rationale: directives have the highest blast radius and must own the routing; questions still gate execution but do not override a clear directive; assertions are the lowest-priority side channel. Example: "I think that is done now. So is it done already?" → principal=ASSERT, mixed_acts=[QUERY] (no directive present, so QUERY does not promote).

**Rule 2 — Stage-3-only emission invariant**.
Only Stage 3 (SURFACE) may emit founder-visible output. Stage 1 (INTAKE) and Stage 2 (PROCESSING) may **draft** but never **surface**. A subagent mid-execution that needs to ask the founder must promote its question into an INT-ASSERT up to Stage 3, which then re-emits as OUT-QUERY. This prevents Stage 2 from leaking inbound/outbound semantics (codex DESIGN finding §2) and keeps a single audit point for everything the founder sees.

**Rule 3 — OUT-QUERY guardrails**.
Every OUT-QUERY must satisfy three properties before it is allowed to surface:
- (i) **named variable**: the question targets a specific named variable (e.g., "which file: A or B?"), not an open-ended fishing prompt.
- (ii) **why default unsafe**: the gate-condition declaration must say why proceeding with a default is unsafe (e.g., "irreversible publication" or "ambiguous referent could overwrite wrong file").
- (iii) **one-turn-answerable**: the founder can answer in a single message (yes/no, A/B/C, a name, a path) — not a multi-step deliberation.

If any of (i)/(ii)/(iii) fails, demote to OUT-ASSERT (INFORM) with the stated assumption. This kills the over-asking pathology before it ships.

**Rule 4 — Bounded retry + irreversible-domain denylist**.
On Stage 1 confidence-gate FAIL, emit OUT-QUERY (CLARIFY) at most **once**. On the second failure of the same turn, proceed-or-refuse based on REVERSIBILITY:
- REVERSIBILITY=reversible → proceed with stated assumption (logged as OUT-ASSERT before action).
- REVERSIBILITY=irreversible → refuse with OUT-ASSERT (DISAGREE) and require an explicit IN-DIRECT re-prompt from the founder.

This terminates the gate-fail loop (codex DESIGN finding §4) and prevents Sutra from blocking on low-confidence reversible asks. The **irreversible-domain denylist** (6 categories — proceeding-with-assumption is forbidden regardless of REVERSIBILITY heuristic):

1. Destructive file ops (`rm -rf`, `git reset --hard`, `git push --force`, mass-delete, mass-rename)
2. External sends (Resend / email / Slack / Discord / SMS / push notifications crossing the founder→external boundary)
3. Founder-reputation outputs (anything signed as Sankalp / Asawa / Sutra to an external party — investor, client, hire)
4. Money movement (Stripe / wire / PSP / crypto / payroll)
5. Legal / compliance (contracts, ToS, privacy policy, regulatory filings)
6. Irreversible publication (git push to public repos, npm publish, Play Store / App Store release, public website publish)

Acts touching denylist domains route to refuse-and-re-prompt regardless of REVERSIBILITY classifier output.

---

## Alternatives considered

| Alt | Description | Rejection rationale |
|---|---|---|
| **a** | Single-axis taxonomy (just KNOW / DO / META) | Fails MECE: loses direction (founder→sutra vs sutra→founder collapse together); loses internal/subagent traffic entirely. |
| **b** | Flat HC1-HC8 (prior framing) | Fails MECE: categories overlap (HC2 "context" and HC4 "delegation" both cover IN-DIRECT); not a grid, so taxonomy can't be reasoned over compositionally. |
| **c** | Larger initial grid (add AUDIENCE / SEVERITY / CONTINUITY tags in v1) | Too complex for v1 — 6 tags × 9 cells = 54 dimensions to classify per turn before a single optimization is attempted. Violates "instrumentation before influence". Defer to v1.1+ via ADR. |
| **d** | Ship rule-changes in v1.0 (fix over-asking, tune confidence-gate, etc.) | Violates D42 "Visibility before Influence". Without 3-4h of instrumented data we'd be optimizing on intuition. v1.0 = classifier + logger only; v1.1 = first data-driven rule change. |

---

## Consequences

**What it enables:**
- **Visibility**: every interaction labeled into one of 9 cells + 3 tags, logged to `holding/state/interaction/log.jsonl`. The founder can grep / aggregate / chart cell distribution within hours.
- **ADR-driven evolution**: any new cell, tag, or axis ships as a new ADR with a regression test asserting the new shape catches a real prior interaction. Taxonomy growth is auditable.
- **Sharper safety**: Rule 4's irreversible-domain denylist + REVERSIBILITY metadata combine to make "proceed with assumption" a default for low-stakes reversible asks while keeping high-stakes irreversible asks gated.
- **Subagent governance**: INT-* cells make sub-agent ↔ main traffic a first-class object — debugging a subagent failure now means inspecting INT-QUERY / INT-ASSERT / INT-DIRECT rows, not parsing free-form logs.

**What it costs:**
- One extra classifier step per turn (Stage 1 must label cell + 3 tags + REVERSIBILITY before routing). Target overhead: <300ms / <500 tokens per turn.
- ~3 tags of header space in every response for the OS Trace surface (`OUT-{QUERY|ASSERT|DIRECT} · TENSE=… · TIMING=… · CHANNEL=…`).
- Log file growth: `holding/state/interaction/log.jsonl` adds 1 row per turn. At 200 turns/day this is ~6k rows/month, ~1MB/month at ~150 bytes/row. Tolerable; rotation policy deferred to v1.1.
- One more concept the founder has to internalize. Mitigated by the quick-card (Task 2.5) and by all 13 prior interactions being pre-classified in §Regression test set below.

---

## Regression test set

13 prior interactions classified into the v1.0 grid. Source of truth: `sutra/marketplace/plugin/skills/human-sutra/tests/fixtures.json`. Every future ADR proposing a grid change MUST keep this set passing AND add ≥1 new fixture demonstrating the new cell catches a real (previously-unrepresented) interaction.

| # | Quote (input) | Direction | Verb | Tense | Reversibility | Risk |
|---|---|---|---|---|---|---|
| 1 | I want to build a human Sutra layer | INBOUND | DIRECT | — | reversible | medium |
| 2 | What is a core restructure phase 0 to 6? | INBOUND | QUERY | past | reversible | low |
| 3 | I think that is done now. So is it done already? | INBOUND | ASSERT (mixed: QUERY) | — | reversible | low |
| 4 | lets build it for core plugin, solve for native later | INBOUND | DIRECT | — | reversible | medium |
| 5 | what do we have right now in place | INBOUND | QUERY | present | reversible | low |
| 6 | Lets redesign the above block diagram | INBOUND | DIRECT | — | reversible | low |
| 7 | stimulate scenarios | INBOUND | DIRECT | — | reversible | low |
| 8 | didnt get it | INBOUND | ASSERT | — | reversible | low |
| 9 | you missed the d42 row in TODO.md, fix it | INBOUND | DIRECT (mixed: ASSERT) | — | reversible | low |
| 10 | push the native v1.0.1 tag to origin/main | INBOUND | DIRECT | — | irreversible | high |
| 11 | what shipped overnight? | INBOUND | QUERY | past | reversible | low |
| 12 | remind me to clean up the flag in 2 weeks | INBOUND | DIRECT | — | reversible | low |
| 13 | do that thing | INBOUND | STAGE-1-FAIL (ambiguous-referent) | — | — | — |

Notes on edge cases:
- Row 3 demonstrates **classification precedence** rule (no DIRECT present, so QUERY does not promote over ASSERT — principal stays ASSERT).
- Row 9 demonstrates **DIRECT promotion**: even though there's an assertion ("you missed the d42 row"), the imperative "fix it" makes principal=DIRECT.
- Row 10 demonstrates **irreversible-domain denylist** trigger (irreversible publication category) — Rule 4 applies; cannot proceed-with-assumption even though REVERSIBILITY classifier returns "irreversible".
- Row 12 demonstrates the **TIMING=later** tag (deferred execution; routes to schedule rather than immediate action).
- Row 13 is the **STAGE-1-FAIL fixture** — the classifier correctly fails to resolve the referent ("that thing") and emits OUT-QUERY (CLARIFY) per Rule 4 (first attempt). On second STAGE-1-FAIL, REVERSIBILITY-unknown defaults to refuse.

All 13 fixtures must pass the classifier test harness shipped in Task 2.4 / Task 2.5. Failure of any row = blocker on Phase 2 verification.

---

## Codex consult

Two rounds.

**R1 (CHANGES-REQUIRED, 2026-05-01)** — 8 findings on the v1.0 PLAN: 2 P1 (activation/wiring missing in Phase 2; "single atomic commit" wording wrong) + 4 P2 (Phase 1 under-covers invariants; backward-compat testing thin; Phase 3 fit-analysis underspecified; tasks not ≤1hr atomic) + 2 P3 (bash+jq sufficient + helper; ADR ordering before fit verification). All 8 folded into v1.0.

**R2 (PASS, 2026-05-01, DIRECTIVE-ID 1777572677)** — verbatim verdict: *"The fold closes all eight prior findings without introducing a new obvious gap from the text provided. Verdict: PASS."*

Verdict file: `.enforcement/codex-reviews/2026-05-01-h-sutra-v1.0-plan-consult.md`.
Prior DESIGN brief (R1 inputs, full 7-question framing): `holding/research/2026-04-30-h-sutra-layer-codex-consult.md`.

This ADR is the codex-P3.8 fold: ADR lands at Task 2.6 (before Charter at Task 2.1 in serial order — this file is the lock; everything downstream cites it).
