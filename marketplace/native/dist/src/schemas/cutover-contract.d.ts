/**
 * CutoverContract — D1 §11 (P-A11) + D3 §3.3 (lifecycle).
 *
 * Charter sub-schema. Captures the parallel-canary cutover contract used when
 * migrating a Tenant's Charter from one engine to another (e.g. Core → Native).
 *
 * M4.7 ships SCHEMA ONLY. The cutover engine (P-B1, M10) reads this contract
 * and drives source+target parallel run, behavior_invariants observation,
 * rollback_gate evaluation, and canary_window timing. Migration tooling
 * (P-C12, M10) wraps the engine.
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d1-authority-map.md §11.1
 * - holding/research/2026-04-29-native-d3-ontology-state-machine.md §3.3
 * - holding/plans/native-v1.0/TASK-QUEUE.md §1 Group A (T-001..T-006)
 *
 * Note on field count: D1 §11.1 lists 6 fields (incl. `success_metrics`); the
 * v1.0 queue spec ships 5 (omits success_metrics; renames `canary_window_seconds`
 * → `canary_window`). Charter already has top-level `success_metrics[]` which
 * the cutover engine can consult — keeping it off the cutover sub-schema avoids
 * duplication. canary_window is a string predicate (not raw seconds) so the
 * engine can interpret durations or ISO-8601 windows uniformly.
 */
import { z } from 'zod';
/**
 * CutoverContract schema — 5 fields, all required when contract is set.
 * Wrapped in `.nullable()` so a Charter without cutover sets `null`.
 *
 * Field semantics:
 * - source_engine        — Engine.id currently active for the Tenant
 * - target_engine        — Engine.id being cut over to (parallel-canary)
 * - behavior_invariants  — predicates that MUST hold across cutover (≥1)
 * - rollback_gate        — predicate; when true → abort cutover + rollback
 * - canary_window        — observation window (e.g. "7d", "PT72H", "60s")
 */
export declare const CutoverContractSchema: z.ZodNullable<z.ZodObject<{
    source_engine: z.ZodString;
    target_engine: z.ZodString;
    behavior_invariants: z.ZodArray<z.ZodString>;
    rollback_gate: z.ZodString;
    canary_window: z.ZodString;
}, z.core.$strip>>;
export type CutoverContract = z.infer<typeof CutoverContractSchema>;
/**
 * Construct a CutoverContract after schema validation. Throws on invalid input.
 *
 * Pass `null` to represent a Charter that does not require cutover (the default
 * for greenfield Charters).
 */
export declare function createCutoverContract(input: CutoverContract): CutoverContract;
/**
 * Predicate: is this CutoverContract shape valid against D1 §11.1?
 *
 * Returns true for `null` (no cutover) AND for fully-populated valid records.
 */
export declare function isValidCutoverContract(v: unknown): v is CutoverContract;
//# sourceMappingURL=cutover-contract.d.ts.map