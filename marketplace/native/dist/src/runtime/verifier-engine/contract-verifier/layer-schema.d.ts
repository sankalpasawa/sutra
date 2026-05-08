/**
 * Tier-1 schema checks. If contract is shallow, low-confidence, or flagged
 * for clarification, the pipeline should halt before tier-2/3/4.
 *
 * Pure function over the captured GoalContract; no I/O. Cheap deterministic
 * gate so downstream LLM-driven tiers never run on garbage input.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */
import type { GoalContract } from '../../../types/goal-contract.js';
import type { AssertionResult } from '../../../types/assertion-report.js';
export declare function runTier1Schema(contract: GoalContract): AssertionResult[];
//# sourceMappingURL=layer-schema.d.ts.map