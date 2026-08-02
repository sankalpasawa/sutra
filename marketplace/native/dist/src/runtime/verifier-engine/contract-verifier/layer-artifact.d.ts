/**
 * Tier-2 artifact assertions (v1 strict grammar; codex fold 2026-05-08).
 *
 * Supported hard_constraint patterns:
 *   forbid:   "no <term>" / "without <term>" / "do not <term>"
 *   require:  "must include <term>"
 *   count:    "<n> <unit>" (must appear literally in artifacts)
 * Anything else -> SKIPPED with id "tier-2/constraint-deferred-to-rubric/<slug>".
 * Tier-4 picks up deferred constraints.
 *
 * Cross-stage propagation invariant: Jaccard token similarity over the
 * FIRST PARAGRAPH only of consecutive stage artifacts. Threshold 0.2.
 *
 * Industry borrow: Hypothesis / fast-check property-based testing —
 * cross-stage propagation is a structural invariant.
 *
 * Industry borrow: BDD Given/When/Then — Cucumber. Acceptance examples'
 * `then` clauses become token-presence predicates over artifacts.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */
import type { GoalContract } from '../../../types/goal-contract.js';
import type { AssertionResult, NativeRun } from '../../../types/assertion-report.js';
export declare function runTier2Artifact(contract: GoalContract, run: NativeRun): AssertionResult[];
//# sourceMappingURL=layer-artifact.d.ts.map