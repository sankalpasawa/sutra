/**
 * GovernanceOverhead — M8 Group AA (T-111/T-112/T-113).
 *
 * Per-turn governance-overhead tracker. PS-14 closure: "total per-turn
 * governance overhead consumes ≤15% of token budget" (memory [Speed is
 * core]). The runtime accumulates tokens spent on the six governance
 * surfaces — input_routing, depth_estimation, blueprint, build_layer,
 * codex_review, hook_fire — and emits a non-blocking OTel alert when the
 * configured threshold is exceeded.
 *
 * Why six categories (and not one bucket): the founder's overhead budget
 * is composed of distinct disciplines. When the alert trips, the per_category
 * snapshot tells the operator WHICH discipline overspent — surfacing that
 * inside the alert avoids a follow-up dashboard query at the moment the
 * signal fires.
 *
 * Why per-turn isolation via `Map<turn_id, state>`: two turns can be
 * legitimately in flight at the same time (e.g. a foreground turn dispatches
 * a subagent that runs its own turn). Each turn's accumulator is keyed by
 * `turn_id` so neither contaminates the other. `endTurn()` removes the
 * key from the Map — repeat tracks on a closed turn throw `TurnNotStartedError`.
 *
 * Why strict-greater-than threshold: the docstring says "≤15%". A turn at
 * exactly 15% is at the budget, not over it. An equality trip would alert
 * the founder for compliant behaviour, eroding the signal. Tests pin this:
 * `tests/contract/engine/governance-overhead.test.ts` covers the boundary;
 * `tests/property/governance-overhead.test.ts` enforces it ≥1000 cases.
 *
 * Why non-blocking alert (D-NS-27): observability NEVER fails the workflow.
 * If the OTel emitter is missing, threshold trip just logs the report and
 * carries on. If it is present and `emit()` rejects, the rejection is
 * swallowed at the call site (we use `.catch(() => {})`) — the executor
 * does not see it.
 *
 * The HARD-STOP at 25% (D5 §3 HS-2) is wired separately at M9 invariants;
 * THIS module only emits the alert.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group AA
 *  - memory [Speed is core] PS-14
 */
import type { OTelEmitter } from './otel-emitter.js';
/**
 * Six governance disciplines tracked per turn. The set is closed — adding
 * a category requires a coordinated change to the runtime emit-sites that
 * call `track()`. Don't widen casually: each category corresponds to a
 * mandatory block in the founder-facing protocol.
 */
export type GovernanceCategory = 'input_routing' | 'depth_estimation' | 'blueprint' | 'build_layer' | 'codex_review' | 'hook_fire';
/**
 * The full report returned by `endTurn()` (and `report()` for an in-flight peek).
 *
 * `overhead_pct` is `tokens_governance / tokens_total` clamped to [0, 1] when
 * `tokens_total === 0` (avoids div-by-zero — a turn that recorded zero
 * tokens has zero overhead by definition).
 *
 * `threshold_tripped` is computed strictly: `overhead_pct > threshold`.
 * Equality does NOT trip — see module docstring.
 */
export interface OverheadReport {
    readonly turn_id: string;
    readonly tokens_total: number;
    readonly tokens_governance: number;
    readonly overhead_pct: number;
    readonly per_category: Readonly<Record<GovernanceCategory, number>>;
    readonly threshold_tripped: boolean;
    readonly threshold: number;
}
/**
 * Thrown when `track()` / `endTurn()` / `report()` is called for a turn that
 * has not had `startTurn()` called (or has already been ended). The runtime
 * MUST initialize state explicitly — silently fabricating a turn would
 * mask integration bugs in the caller.
 *
 * Defined as a plain `Error` subclass with `name` set so `instanceof` works
 * across the test suite. Following the same pattern used by
 * `BuiltinNotAllowedError` in charter-rego-compiler.ts (no central errors
 * module in this codebase).
 */
export declare class TurnNotStartedError extends Error {
    readonly turn_id: string;
    constructor(turn_id: string);
}
export interface GovernanceOverheadOptions {
    readonly threshold?: number;
    readonly otelEmitter?: OTelEmitter;
}
/**
 * Per-turn governance-overhead tracker.
 *
 * Lifecycle:
 *   startTurn(turn_id, tokens_total_estimate)  →  initialize state
 *   track(turn_id, category, tokens)           →  accumulate (≥1 call)
 *   endTurn(turn_id)                           →  emit report + alert + clear state
 *
 * Multiple turns can be in flight concurrently — keyed by `turn_id`. The
 * tracker holds NO global state; one `GovernanceOverhead` instance per
 * runtime is sufficient (and recommended — sharing the threshold + emitter
 * across all turns is the point).
 */
export declare class GovernanceOverhead {
    /**
     * Active threshold for this instance. Public-readonly so callers + tests
     * can introspect what was resolved. Set once at construction; the env var
     * is sampled at construct-time, not on every `endTurn()` call (mutating
     * env mid-run is not a supported reconfiguration path).
     */
    readonly threshold: number;
    private readonly otelEmitter;
    private readonly turns;
    constructor(opts?: GovernanceOverheadOptions);
    /**
     * Begin tracking for `turn_id`. `tokens_total_estimate` is the denominator
     * used in `overhead_pct`. Calling `startTurn()` twice for the same
     * `turn_id` resets the accumulator — useful when a turn restarts mid-flight
     * (e.g. retry path) and the original measurements are no longer relevant.
     *
     * Negative `tokens_total_estimate` is rejected — overhead percentages are
     * meaningless against a negative budget.
     */
    startTurn(turn_id: string, tokens_total_estimate: number): void;
    /**
     * Accumulate `tokens` against `category` for the live turn `turn_id`.
     * Throws `TurnNotStartedError` if `startTurn()` has not been called (or
     * the turn was already ended).
     *
     * Negative or non-finite `tokens` are rejected: monotonicity (tokens
     * never decrease) is a documented property; allowing negatives here
     * would break it. Tests in `tests/property/governance-overhead.test.ts`
     * pin this.
     */
    track(turn_id: string, category: GovernanceCategory, tokens: number): void;
    /**
     * Snapshot the live turn WITHOUT ending it. Useful for monotonicity
     * assertions in property tests, or for periodic dashboards. Throws
     * `TurnNotStartedError` if the turn has not been started.
     */
    report(turn_id: string): OverheadReport;
    /**
     * M9 Group HH (T-161). Threshold-state band classifier:
     *   - 'green'  → overhead_pct ∈ [0, 0.15)  (within budget)
     *   - 'yellow' → overhead_pct ∈ [0.15, 0.25) (alert zone — OTel WARN)
     *   - 'red'    → overhead_pct ∈ [0.25, ∞)  (HS-2: HARD-STOP zone)
     *
     * The HS-2 step-graph-executor wiring (Group HH T-162) reads this
     * value at the top of every step iteration; `'red'` halts the run
     * with state='failed' + failure_reason='hs2_overhead_exceeded' +
     * TERMINATE provenance (codex M9 P1.1 fold — reuses existing failure
     * pathway; no new enums).
     *
     * Bands are CLOSED at the lower bound and OPEN at the upper bound:
     *   green:  [0, 0.15)   — strict-less-than 15% (matches the existing
     *           threshold_tripped semantics: > 15% trips at endTurn).
     *   yellow: [0.15, 0.25) — at-or-above 15%, strict-less-than 25%.
     *   red:    [0.25, ∞)    — at-or-above 25%.
     *
     * Throws `TurnNotStartedError` if the turn has not been started.
     */
    getThresholdState(turn_id: string): 'green' | 'yellow' | 'red';
    /**
     * End the turn: build the report, emit the alert if tripped, and clear
     * state from the Map (so subsequent `track()` on this `turn_id` will
     * throw). Throws `TurnNotStartedError` if the turn has not been started.
     *
     * Alert emission is fire-and-forget — the call to `otelEmitter.emit()`
     * has its rejection swallowed so observability failures cannot bubble
     * into the caller. (D-NS-27.)
     */
    endTurn(turn_id: string): OverheadReport;
    private buildReport;
}
//# sourceMappingURL=governance-overhead.d.ts.map