# ADR-030 — Work Dispatch: placement, routing, and touches-scoped authorization

**Status**: ACCEPTED — founder sign-off 2026-08-04 (WDP W2-T26), "as-is" including the fable-tier human gate on BOTH initial classification and escalation. G2 dual-reviewed (codex 5P1+5P2, deepseek 1P1+4P2 — all folded pre-sign-off). Founder decisions D-A..D-I (PROGRAM.md §0) are fixed inputs.

## Context

A 12-defect audit (2026-08-03) showed the Work-Atom layer verified transitions but not scope, relevance, or routing: any open atom authorized any mutation (d1); `model`/`touches` were write-only (d7); four classes of gate false positives fired in one live session (d9-d12). Founder ruled: a DISPATCH stage — placement, session grain, per-atom model+effort — becomes MANDATORY per unit and HARD-enforced; dual AI review (codex + DeepSeek) at every gate; T4 fleet promotion HELD.

## Decision

1. **Safety property**: mutation authorized iff the open atom's `touches` covers the target (TOUCHES-CONTRACT v1; fixtures are the law). Stage ceremony is secondary; this check is the guarantee.
2. **Grouping**: spawned sessions group by PAIRWISE-DISJOINT declared touches + identical routing. The semantic `session_key=(context_key, model, effort)` primitive is **REJECTED** (codex P1 2026-08-03: undefined context_key; ignores mutation overlap, worktree, ordering).
3. **Context manifests verify PRESENCE, never group sessions** (explicit — the reader must not infer a revived context key): INLINE-serial requires a hash-verified manifest; unverifiable manifest -> SPAWN with the manifest as briefing.
4. **Routing**: facts in versioned `routing-policy.json`; conservative default; floors (governance paths -> min Opus-tier; >200K excludes 200K-window models); adaptive escalation (max 2, audited); **top-tier jump requires founder approval** unless `auto_escalate_max=true` was declared at dispatch.
5. **Lifecycle**: atoms are `open -> closed|abandoned`; retries keep atom identity (attempt++, max 3); new approach = abandon + `supersedes` reference; invariant: every mutation attributable to exactly one open atom + one dispatch record; reconciliation flags orphans; stale (>24h) atoms surface as candidates.
6. **Enforcement**: one HARD PreToolUse gate (W6) on Edit/Write/Agent — dispatch record present + touches coverage; reads never gated; kill-switch + runbook + 24h observation before program close.

## Defect dispositions

| Defect | Disposition |
|---|---|
| 1 scope | CLOSED by touches gate (W6-T50); interim SOFT logging live since W1-T17 |
| 2,5,6,9,10,11,12 | CLOSED in W1 (suites: atom-v0 12, bash-gate 12, cards 8, w1-regression 21, w1-t13 8 — ALL PASS) |
| 3 relevance | CLOSED as PROCESS guarantee: machine-checked verifier-declaration schema at open (W3-T28) + close-time rejection tests (W4-T41). This is a syntactic/process closure — semantic relevance proof is declared OUT OF REACH and pinned, not silently claimed. |
| 4 evidence store | CLOSED by W6-T51: evidence paths removed from mutation whitelist; hooks retain append capability **through the controlled append-only writer ONLY** — no direct path writes for anyone, hooks included. |
| 7 model write-only | CLOSED by atom v0.3 (W4-T38): model/effort/touches land in ledger rows |
| 8 fleet | **HELD** (founder D-C). Consistent with shipping W1-T13 fixes to already-fleet-shipped hooks: bug-fixes to an EXISTING surface ship; the NEW dispatch discipline does not, until the hold lifts. |

## Consequences

- Ceremony cost is real: 11 gate interventions were recorded while building W0-W2 alone; the W1 false-positive fixes are the mitigation, and the 24h observation window (W6-T58) is the proof obligation before close.
- Routing quality is EARNED via telemetry candidates + policy version bumps, not assumed (the ladder will misroute at margins by design).
- The interim dispatch shim expires at gate wiring (asserted by W6-T53); if it survives, that is a defect, not a feature.
