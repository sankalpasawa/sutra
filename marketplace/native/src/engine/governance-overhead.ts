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

import type { OTelEmitter, OTelEventRecord } from './otel-emitter.js'

/**
 * Six governance disciplines tracked per turn. The set is closed — adding
 * a category requires a coordinated change to the runtime emit-sites that
 * call `track()`. Don't widen casually: each category corresponds to a
 * mandatory block in the founder-facing protocol.
 */
export type GovernanceCategory =
  | 'input_routing'
  | 'depth_estimation'
  | 'blueprint'
  | 'build_layer'
  | 'codex_review'
  | 'hook_fire'

const CATEGORIES: ReadonlyArray<GovernanceCategory> = [
  'input_routing',
  'depth_estimation',
  'blueprint',
  'build_layer',
  'codex_review',
  'hook_fire',
] as const

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
  readonly turn_id: string
  readonly tokens_total: number
  readonly tokens_governance: number
  readonly overhead_pct: number
  readonly per_category: Readonly<Record<GovernanceCategory, number>>
  readonly threshold_tripped: boolean
  readonly threshold: number
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
export class TurnNotStartedError extends Error {
  readonly turn_id: string
  constructor(turn_id: string) {
    super(`GovernanceOverhead: turn '${turn_id}' has not been started`)
    this.name = 'TurnNotStartedError'
    this.turn_id = turn_id
  }
}

/** Default 15% — locked by PS-14. Override via env or ctor option. */
const DEFAULT_THRESHOLD = 0.15

/**
 * Resolve the threshold per the priority chain:
 *   1. Explicit ctor option (highest)
 *   2. SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD env var
 *   3. DEFAULT_THRESHOLD (0.15)
 *
 * Both override paths are clamped to [0, 1] — a threshold below 0 would
 * trip on every turn, above 1 would never trip. Either is operator error;
 * we silently clamp rather than throw because the surrounding contract is
 * non-blocking observability (see module docstring).
 *
 * Invalid env values (NaN, non-numeric strings) fall back to the default —
 * an environment misconfiguration should not silently change the trip
 * boundary.
 */
function resolveThreshold(explicit?: number): number {
  if (explicit !== undefined) {
    if (!Number.isFinite(explicit)) return DEFAULT_THRESHOLD
    return clamp01(explicit)
  }
  const raw = process.env.SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD
  if (raw === undefined || raw === '') return DEFAULT_THRESHOLD
  const parsed = Number.parseFloat(raw)
  if (!Number.isFinite(parsed)) return DEFAULT_THRESHOLD
  return clamp01(parsed)
}

function clamp01(n: number): number {
  if (n < 0) return 0
  if (n > 1) return 1
  return n
}

/** Build a fresh per-category accumulator initialized to zero for every category. */
function emptyPerCategory(): Map<GovernanceCategory, number> {
  const m = new Map<GovernanceCategory, number>()
  for (const c of CATEGORIES) m.set(c, 0)
  return m
}

/** Snapshot the per-category Map into a plain frozen Record for the report. */
function freezePerCategory(
  m: ReadonlyMap<GovernanceCategory, number>,
): Readonly<Record<GovernanceCategory, number>> {
  const out: Record<GovernanceCategory, number> = {
    input_routing: m.get('input_routing') ?? 0,
    depth_estimation: m.get('depth_estimation') ?? 0,
    blueprint: m.get('blueprint') ?? 0,
    build_layer: m.get('build_layer') ?? 0,
    codex_review: m.get('codex_review') ?? 0,
    hook_fire: m.get('hook_fire') ?? 0,
  }
  return Object.freeze(out)
}

interface PerTurnState {
  readonly tokens_total: number
  readonly per_category: Map<GovernanceCategory, number>
}

export interface GovernanceOverheadOptions {
  readonly threshold?: number
  readonly otelEmitter?: OTelEmitter
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
export class GovernanceOverhead {
  /**
   * Active threshold for this instance. Public-readonly so callers + tests
   * can introspect what was resolved. Set once at construction; the env var
   * is sampled at construct-time, not on every `endTurn()` call (mutating
   * env mid-run is not a supported reconfiguration path).
   */
  public readonly threshold: number

  private readonly otelEmitter: OTelEmitter | undefined
  private readonly turns: Map<string, PerTurnState> = new Map()

  constructor(opts: GovernanceOverheadOptions = {}) {
    this.threshold = resolveThreshold(opts.threshold)
    this.otelEmitter = opts.otelEmitter
  }

  /**
   * Begin tracking for `turn_id`. `tokens_total_estimate` is the denominator
   * used in `overhead_pct`. Calling `startTurn()` twice for the same
   * `turn_id` resets the accumulator — useful when a turn restarts mid-flight
   * (e.g. retry path) and the original measurements are no longer relevant.
   *
   * Negative `tokens_total_estimate` is rejected — overhead percentages are
   * meaningless against a negative budget.
   */
  startTurn(turn_id: string, tokens_total_estimate: number): void {
    if (!Number.isFinite(tokens_total_estimate) || tokens_total_estimate < 0) {
      throw new RangeError(
        `GovernanceOverhead.startTurn: tokens_total_estimate must be a non-negative finite number (got ${tokens_total_estimate})`,
      )
    }
    this.turns.set(turn_id, {
      tokens_total: tokens_total_estimate,
      per_category: emptyPerCategory(),
    })
  }

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
  track(turn_id: string, category: GovernanceCategory, tokens: number): void {
    const state = this.turns.get(turn_id)
    if (state === undefined) {
      throw new TurnNotStartedError(turn_id)
    }
    if (!Number.isFinite(tokens) || tokens < 0) {
      throw new RangeError(
        `GovernanceOverhead.track: tokens must be a non-negative finite number (got ${tokens})`,
      )
    }
    state.per_category.set(category, (state.per_category.get(category) ?? 0) + tokens)
  }

  /**
   * Snapshot the live turn WITHOUT ending it. Useful for monotonicity
   * assertions in property tests, or for periodic dashboards. Throws
   * `TurnNotStartedError` if the turn has not been started.
   */
  report(turn_id: string): OverheadReport {
    const state = this.turns.get(turn_id)
    if (state === undefined) {
      throw new TurnNotStartedError(turn_id)
    }
    return this.buildReport(turn_id, state)
  }

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
  getThresholdState(turn_id: string): 'green' | 'yellow' | 'red' {
    const state = this.turns.get(turn_id)
    if (state === undefined) {
      throw new TurnNotStartedError(turn_id)
    }
    const report = this.buildReport(turn_id, state)
    if (report.overhead_pct >= 0.25) return 'red'
    if (report.overhead_pct >= 0.15) return 'yellow'
    return 'green'
  }

  /**
   * End the turn: build the report, emit the alert if tripped, and clear
   * state from the Map (so subsequent `track()` on this `turn_id` will
   * throw). Throws `TurnNotStartedError` if the turn has not been started.
   *
   * Alert emission is fire-and-forget — the call to `otelEmitter.emit()`
   * has its rejection swallowed so observability failures cannot bubble
   * into the caller. (D-NS-27.)
   */
  endTurn(turn_id: string): OverheadReport {
    const state = this.turns.get(turn_id)
    if (state === undefined) {
      throw new TurnNotStartedError(turn_id)
    }
    const report = this.buildReport(turn_id, state)
    this.turns.delete(turn_id)

    if (report.threshold_tripped && this.otelEmitter !== undefined) {
      const event: OTelEventRecord = {
        decision_kind: 'GOVERNANCE_OVERHEAD_ALERT',
        trace_id: turn_id,
        actor: 'sutra-native:governance-overhead',
        attributes: {
          threshold: report.threshold,
          overhead_pct: report.overhead_pct,
          tokens_total: report.tokens_total,
          tokens_governance: report.tokens_governance,
          per_category: report.per_category,
        },
      }
      // Fire-and-forget. The `as unknown` cast is unnecessary because the
      // OTelEventKind union already covers GOVERNANCE_OVERHEAD_ALERT (added
      // alongside this module). If the emitter rejects, swallow it —
      // observability failures NEVER fail a workflow.
      this.otelEmitter.emit(event).catch(() => {
        /* non-blocking by design (D-NS-27) */
      })
    }

    return report
  }

  private buildReport(turn_id: string, state: PerTurnState): OverheadReport {
    let governance = 0
    for (const v of state.per_category.values()) governance += v
    const tokens_total = state.tokens_total
    const overhead_pct = tokens_total === 0 ? 0 : governance / tokens_total
    return Object.freeze({
      turn_id,
      tokens_total,
      tokens_governance: governance,
      overhead_pct,
      per_category: freezePerCategory(state.per_category),
      threshold_tripped: overhead_pct > this.threshold,
      threshold: this.threshold,
    })
  }
}
