/**
 * CutoverApplier — v1.3.0 W6 (final wave production hardening).
 *
 * DRY-RUN ONLY. The real apply-with-rollback path is DEFERRED to v1.x.1
 * per plan §6 + codex implicit advisory.
 *
 * What dryRunApplyCutover does:
 *   - Validates the input via validateCutoverContract.
 *   - Returns a CutoverPlan describing the parallel-canary cutover that
 *     WOULD happen: which engines participate, which invariants would be
 *     observed, which rollback gate would be evaluated, and how long the
 *     canary window would last.
 *   - Performs ZERO mutation. No filesystem writes, no router edits, no
 *     ledger appends.
 *
 * The plan output is a structured artifact callers can render, log, or
 * compare against the v1.x.1 actual-apply implementation when it ships.
 */
export interface PlannedMutation {
    /** Stable identifier for the mutation (e.g. 'switch_router_target_engine'). */
    readonly kind: string;
    /** Which engine surface would be touched. */
    readonly target: 'router' | 'ledger' | 'observer' | 'workflow_pool';
    /** Human-readable summary the operator can review. */
    readonly description: string;
    /** Whether the mutation is reversible by the rollback path. */
    readonly reversible: boolean;
}
export interface CutoverPlan {
    readonly source_engine: string;
    readonly target_engine: string;
    readonly canary_window: string;
    /** Parsed canary window in seconds (informational; null when unparseable). */
    readonly canary_window_seconds: number | null;
    readonly behavior_invariants: ReadonlyArray<string>;
    readonly rollback_gate: string;
    readonly planned_mutations: ReadonlyArray<PlannedMutation>;
    /** Always 'dry-run' at v1.3.0; v1.x.1 will introduce 'apply'. */
    readonly mode: 'dry-run';
    /** True when the plan was built from a structurally valid contract. */
    readonly valid: boolean;
    /** Validation errors when valid=false; empty when valid=true. */
    readonly errors: ReadonlyArray<string>;
}
export interface DryRunOptions {
    /** Override the now() clock for deterministic plan output (informational). */
    readonly now_ms?: () => number;
}
/**
 * Plan a cutover application without mutating anything. Returns the
 * CutoverPlan even when invalid — `valid=false` + `errors[]` populated —
 * so callers can render the same shape regardless of outcome.
 *
 * For `null` contracts (no cutover required), returns a degenerate plan
 * with empty mutations and valid=true.
 */
export declare function dryRunApplyCutover(contract: unknown, _opts?: DryRunOptions): CutoverPlan;
//# sourceMappingURL=cutover-applier.d.ts.map