<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/engines/DISPATCH-ENGINE.md (D54). Do not edit here. -->
# DISPATCH-ENGINE — Work Dispatch (HLD v1.0, WDP W2-T19)

| Field | Value |
|---|---|
| Status | DRAFT — G2 dual review pending, founder sign-off T26 pending |
| Decision inputs | ADR-030; PROGRAM.md §0 D-A..D-I; TOUCHES-CONTRACT v1 (fixtures are law); dual pre-write consult folded (lifecycle + top-tier gate) |
| Consumers | W3 LLDs; sutra-dispatch CLI; dispatch-gate.sh; T4 fleet at held promotion |

## 1. Position in the spine

DISPATCH is the mandatory 7th stage (founder D-A, HARD): after BLUEPRINT, before any atom runs. It answers, per unit of work: WHERE does each step run, WITH WHAT model+effort, UNDER WHAT mutation authority, and HOW failures recover. Its record is written at atom-open; its enforcement is the dispatch gate (W6).

```
Input -> Depth -> Flow -> Placement -> Blueprint -> DISPATCH -> Atom(s) -> Close
                                          |             |
                                     plan of work   who/where/what-model
```

## 2. The safety property (D-G)

A mutation is authorized iff the open atom's declared `touches` covers the target path under TOUCHES-CONTRACT v1 (M0 canonicalization, M1 exact, M2 dir-prefix with boundary, M4-M5 deny, M6 reads never gated, M7 evidence paths only via controlled writer). `fixtures/touches-fixtures.sh` is the executable law: any gate implementation MUST pass it unmodified. Everything else in this engine is routing and ergonomics; this clause is the guarantee.

## 3. Placement resolution (per unit, first match wins)

INLINE is valid ONLY when the parent session satisfies the step's routed floor (model+effort per §4) — otherwise the step SPAWNS to its routed model even if single (G2 codex P1: a governance atom must never run under-floor just because it is small). Disjoint touches are NECESSARY for write-safety, NOT sufficient for parallelism: every dispatch record carries `depends_on[]` edges; dependent steps serialize regardless of touches (G2 codex P1).

| # | Condition | Placement |
|---|---|---|
| P1 | single step AND parent satisfies routed floor | INLINE |
| P2 | steps sequential AND manifest VERIFIES in parent (CONTEXT-MANIFEST.md) AND parent satisfies floor | INLINE serial; manifest RE-VERIFIED before every subsequent step — mismatch halts (re-manifest or convert to SPAWN, §3 this table) |
| P3 | steps >= 2, PAIRWISE-DISJOINT touches, no depends_on between them, identical routing | SPAWN, multi-atom per session group |
| P4 | disjoint + independent, differing routing | SPAWN, one session per routing group |
| P5 | parallel steps with OVERLAPPING touches | conflict-planned BEFORE grouping: serialize, or SPAWN + worktree isolation + a mandatory INTEGRATION unit (below) |
| P6 | group > 8 sessions | chunk |
| P7 | DEFAULT (anything unmatched — incl. sequential + overlapping + no verifiable manifest) | SPAWN serial: one session, ordered atoms, explicit no-manifest briefing (G2 deepseek P1: the table must be total) |

**Integration unit (G2 fold)**: worktree results merge through their OWN unit — touches = union of the overlap, its own verify contract, its own ledger attribution; merge conflicts halt and surface, never auto-resolve. The merge is a mutation like any other.

Grouping key is declared-touches disjointness + routing — never a semantic "context key" (rejected, ADR-030).

## 4. Model + effort routing (D-F)

All model facts live in `routing-policy.json` (versioned; the spine never names models). Rules the policy must encode:
- conservative default (Opus-tier, effort high);
- cheap tier ONLY for mechanically-verifiable, single-file, low-blast-radius atoms;
- FLOORS: governance paths (charters, founder directions, engine specs, ADRs, plugin runtime) -> minimum Opus-tier regardless of computed class; context > 200K tokens excludes 200K-window models;
- adaptive escalation (ADAPTIVE ESCALATION): verify-fail -> one tier up + effort bump; context overflow -> 1M-window model; max 2 escalations; every escalation writes an auditable decision record;
- TOP-TIER HUMAN GATE (dual consult fold; scope per G2 deepseek P2): founder approval required for the price-max tier on BOTH initial classification AND escalation, unless the dispatch record declared `auto_escalate_max=true` up front. Auto-escalation bumps at most ONE tier silently (`tier_jump_max: 1` in policy).

## 5. Session = agent (D-A mechanism)

SPAWN materializes as a harness subagent: `Agent(model, effort, isolation)`. The briefing carries: context manifest, touches (binding), verify contract, and the Sutra discipline footer. Spawned agents open their OWN atoms — the floor applies to their session ids; parent atoms never authorize child mutations.

## 6. Lifecycle & recovery (dual pre-write consult fold — HLD-level, not deferable)

- **Atom states**: `open -> closed` (verify pass) | `open -> abandoned` (reason, recorded). VERIFY-FAILED is not a state: the atom stays open, `attempt++`, max 3 then STOP-and-surface.
- **Retry identity**: retries reuse the SAME atom (same work identity). A new approach = abandon with reason + new atom referencing its predecessor (`supersedes`).
- **Invariant**: every mutation is attributable to exactly ONE open atom and ONE dispatch record. The floor journal is the authoritative sighting; a reconciliation pass (telemetry) flags journal mutations lacking attribution as violations.
- **Crash recovery**: mutation-then-crash before record write is detected by reconciliation (journal row without close record); the unit resumes by re-verifying its manifest, then either continuing the open atom or abandoning it explicitly. No silent cleanup.
- **Stale atoms**: open > 24h surfaces in the dispatch report as a review candidate.
- **Rollback boundary**: SPAWN + worktree isolates by construction; INLINE relies on git (no engine-level rollback in v1 — pinned limitation, revisit if telemetry shows mid-unit corruption).
- **Evidence ownership**: `.sutra/*ledger*` + `.enforcement/**` are append-only via the controlled writer (W6-T51); no atom's touches can authorize direct writes there (M7).

## 7. Enforcement (W6)

One HARD PreToolUse gate covering EVERY mutation surface: Edit/Write/Agent directly, and Bash mutations via composition with the atom floor's HARD-BASH branch (same touches semantics — shell is not a bypass; G2 codex P1). Blocked unless (a) an ACTIVE dispatch decision row matches the OPEN atom_id + session_id — a stale or unrelated unit record satisfies nothing (G2 codex P1) — with Agent calls matching the recorded model/effort/isolation, and (b) for mutations, the open atom's touches covers the target (Sec 2). Reads are never gated (M6). Kill-switch `~/.dispatch-gate-disabled` + RUNBOOK; 24h observation window before program close; the interim shim (W0-T02) EXPIRES at gate wiring, asserted by test.

## 8. Telemetry

Per TELEMETRY-DESIGN.md: append-only dispatch ledger joined to the atom ledger by atom_id; signals (under-modeled, over-modeled, touches_breadth over-breadth, escalations, touches_miss) are REVIEW CANDIDATES, never verdicts. Adaptive escalation + this ledger — not upfront precision — is how routing gets good (codex: telemetry tunes heuristics after the fact).
